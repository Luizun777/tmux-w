"""Panel: una pseudoconsola ConPTY (pywinpty) + emulador de terminal (pyte)."""

import itertools
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pyte
from winpty import PTY

from .vtfilter import VtSanitizer

DEFAULT_SHELL = "powershell.exe"

# Tras un resize, la app tarda en repintar al ancho nuevo y suele emitir antes
# un frame al ancho VIEJO (más ancho). Durante esta ventana desactivamos el
# autowrap del panel para que ese contenido sobrante no haga wrap+scroll y deje
# filas residuales que el repintado incremental ya no limpia. Ver Pane.resize.
RESIZE_SETTLE = 0.5


class PaneScreen(pyte.HistoryScreen):
    """HistoryScreen + SU/SD (CSI S / CSI T), que pyte no implementa."""

    def scroll_up(self, count: int = 1) -> None:
        count = max(1, count)
        top, bottom = self.margins or (0, self.lines - 1)
        for _ in range(count):
            if top == 0:
                self.history.top.append(self.buffer[top])
            for y in range(top, bottom):
                self.buffer[y] = self.buffer[y + 1]
            self.buffer.pop(bottom, None)
        self.dirty.update(range(top, bottom + 1))

    def scroll_down(self, count: int = 1) -> None:
        count = max(1, count)
        top, bottom = self.margins or (0, self.lines - 1)
        for _ in range(count):
            for y in range(bottom, top, -1):
                self.buffer[y] = self.buffer[y - 1]
            self.buffer.pop(top, None)
        self.dirty.update(range(top, bottom + 1))


class PaneStream(pyte.Stream):
    """Stream de pyte con CSI S/T añadidos a la tabla de despacho."""

    csi = dict(pyte.Stream.csi)
    csi.update({"S": "scroll_up", "T": "scroll_down"})
    events = frozenset(itertools.chain(pyte.Stream.events, ["scroll_up", "scroll_down"]))


def _which(name: str) -> str | None:
    """shutil.which + rutas estándar de Windows (el PATH puede venir en formato unix)."""
    if "\\" in name or "/" in name:
        return name if Path(name).is_file() else None
    if not name.lower().endswith((".exe", ".bat", ".cmd", ".com")):
        name += ".exe"
    found = shutil.which(name)
    if found:
        return found
    sysroot = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    for candidate in (
        sysroot / "System32" / name,
        sysroot / "System32" / "WindowsPowerShell" / "v1.0" / name,
        sysroot / name,
    ):
        if candidate.is_file():
            return str(candidate)
    # PATH con separador ':' (entornos tipo bash)
    raw = os.environ.get("PATH", "")
    if ":" in raw and ";" not in raw:
        for part in raw.split(":"):
            if len(part) == 1:  # letra de unidad partida ('C', ...)
                continue
            p = Path(part) / name
            if p.is_file():
                return str(p)
    return None


def _resolve_command(command: str | None, default_shell: str) -> tuple[str, str | None]:
    """Devuelve (appname, cmdline) para winpty.PTY.spawn."""
    cmd = (command or "").strip() or default_shell
    parts = cmd.split(None, 1)
    exe = _which(parts[0])
    if exe is None:
        raise RuntimeError(f"ejecutable no encontrado: {parts[0]}")
    return exe, cmd if len(parts) > 1 else None


class Pane:
    """Un proceso bajo ConPTY cuya salida alimenta una pantalla pyte con scrollback."""

    def __init__(
        self,
        pane_id: int,
        cols: int,
        rows: int,
        command: str | None = None,
        default_shell: str = DEFAULT_SHELL,
        history: int = 2000,
        cwd: str | None = None,
        on_dirty=None,
        on_exit=None,
    ):
        self.id = pane_id
        self.cols = max(2, cols)
        self.rows = max(1, rows)
        self.dead = False
        self.on_dirty = on_dirty
        self.on_exit = on_exit
        self.lock = threading.RLock()
        self.screen = PaneScreen(self.cols, self.rows, history=max(history, self.rows), ratio=0.5)
        self.stream = PaneStream(self.screen)
        self._sanitizer = VtSanitizer()
        self._wrap_resume_at = 0.0  # > now: autowrap desactivado hasta ese instante
        self.pty = PTY(self.cols, self.rows)
        exe, cmdline = _resolve_command(command, default_shell)
        self.command = command or default_shell
        ok = self.pty.spawn(exe, cmdline=cmdline, cwd=cwd)
        if not ok:
            raise RuntimeError(f"no se pudo lanzar {exe!r}")
        self.pid = self.pty.pid
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True, name=f"pane-{pane_id}-reader"
        )
        self._reader.start()

    # ------------------------------------------------------------------ io
    def _read_loop(self) -> None:
        while True:
            try:
                data = self.pty.read(8192, blocking=True)
            except Exception:
                break
            if not data:
                if self.pty.iseof() or not self.pty.isalive():
                    break
                continue
            data = self._sanitizer.feed(data)
            if not data:
                continue
            with self.lock:
                # pasada la ventana de settle tras un resize, restaura el
                # autowrap (lo desactivó resize() para no descuadrar el frame
                # al ancho viejo que la app emite antes de repintar)
                if self._wrap_resume_at and time.monotonic() >= self._wrap_resume_at:
                    self.screen.mode.add(pyte.modes.DECAWM)
                    self._wrap_resume_at = 0.0
                try:
                    self.stream.feed(data)
                except Exception:
                    pass  # secuencia VT que pyte no soporta: ignorar
            if self.on_dirty:
                self.on_dirty(self)
        self.dead = True
        if self.on_exit:
            self.on_exit(self)

    def write(self, data: str) -> None:
        if self.dead:
            return
        try:
            self.pty.write(data)
        except Exception:
            self.dead = True

    # -------------------------------------------------------------- control
    def resize(self, cols: int, rows: int) -> bool:
        """Redimensiona pantalla pyte + ConPTY. True si cambió el tamaño."""
        cols, rows = max(2, cols), max(1, rows)
        if (cols, rows) == (self.cols, self.rows):
            return False
        self.cols, self.rows = cols, rows
        with self.lock:
            self.screen.resize(rows, cols)
            # pyte no reposiciona el cursor al achicar: fuera de rango, las
            # siguientes escrituras irían a filas/columnas fantasma invisibles
            cur = self.screen.cursor
            cur.x = min(cur.x, cols - 1)
            cur.y = min(cur.y, rows - 1)
            # Tras un resize (p.ej. al dividir la ventana) la app repinta. Las
            # TUI full-screen como Claude Code posicionan con el cursor y
            # escriben los espacios como CUF (ESC[<n>C), asumiendo que la
            # terminal reflowó y las celdas saltadas están en blanco. pyte NO
            # reflowa: las celdas viejas DENTRO del nuevo ancho sobreviven al
            # resize y se filtran entre el texto repintado (guiones y restos de
            # bordes -> "Claude deformado"). Limpiamos la pantalla visible para
            # que el repintado caiga sobre un lienzo limpio; el scrollback
            # (history) se conserva. Es seguro para shells: ConPTY reemite toda
            # la pantalla visible (cada fila con ESC[K) tras el set_size.
            self.screen.buffer.clear()
            self.screen.dirty.update(range(rows))
            # Además, la app suele emitir un primer frame al ancho VIEJO antes
            # de repintar al nuevo; ese contenido (más ancho que el panel) haría
            # wrap+scroll en pyte y dejaría filas residuales que el repintado
            # incremental no borra. Desactivamos el autowrap durante la ventana
            # de settle; _read_loop lo restaura al expirar. El autowrap normal
            # (líneas largas de shell) se conserva fuera de esa ventana.
            self.screen.mode.discard(pyte.modes.DECAWM)
            self._wrap_resume_at = time.monotonic() + RESIZE_SETTLE
        if not self.dead:
            try:
                self.pty.set_size(cols, rows)
            except Exception:
                pass
        if self.on_dirty:
            self.on_dirty(self)
        return True

    def kill(self) -> None:
        """Termina el árbol de procesos del panel."""
        self.dead = True
        try:
            subprocess.run(
                ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    # ---------------------------------------------------------------- state
    @property
    def title(self) -> str:
        t = (self.screen.title or "").strip()
        if not t:
            t = self.command.split()[0]
        # rutas tipo C:\...\powershell.exe -> powershell
        base = t.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        if base.lower().endswith(".exe"):
            base = base[:-4]
        return base or "?"

    def alive(self) -> bool:
        return not self.dead and self.pty.isalive()

    def snapshot_lines(self) -> list[list]:
        """Historial + pantalla como lista de filas de pyte.Char (para copy-mode)."""
        with self.lock:
            rows = []
            for line in self.screen.history.top:
                rows.append([line[x] for x in range(self.cols)])
            for y in range(self.rows):
                line = self.screen.buffer[y]
                rows.append([line[x] for x in range(self.cols)])
            return rows
