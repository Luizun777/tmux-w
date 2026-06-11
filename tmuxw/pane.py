"""Panel: una pseudoconsola ConPTY (pywinpty) + emulador de terminal (pyte)."""

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pyte
from winpty import PTY

DEFAULT_SHELL = "powershell.exe"


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
        self.screen = pyte.HistoryScreen(
            self.cols, self.rows, history=max(history, self.rows), ratio=0.5
        )
        self.stream = pyte.Stream(self.screen)
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
            with self.lock:
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
