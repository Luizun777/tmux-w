"""QA integración: estrés de resize y scroll contra el servidor REAL.

Mismo patrón que tests/test_integration.py (servidor en subproceso aislado
con LOCALAPPDATA/USERPROFILE en tmpdir, ConPTY real, cliente TCP propio).
Los frames ANSI absolutos se reconstruyen con pyte para validar que tras
resizes y scroll no quedan residuos, duplicados ni contenido descuadrado.
"""

import json
import re
import socket
import time

import pyte
import pytest

from tests.test_integration import ServerHandle

SESSION = "resz"
CLEAR = "\x1b[2J"
IND_RE = re.compile(r"\[\d+/\d+\]")  # indicador de copy-mode [N/M]


# ------------------------------------------------------------------ helpers
def apply_frames(w, h, frames):
    """Aplica frames ANSI a una pantalla pyte WxH y la devuelve."""
    screen = pyte.Screen(w, h)
    stream = pyte.Stream(screen)
    for f in frames:
        stream.feed(f)
    return screen


def row_positions(frame: str) -> set[int]:
    """Filas Y posicionadas en columna 1 (\\x1b[y;1H) dentro de un frame."""
    return {int(m) for m in re.findall(r"\x1b\[(\d+);1H", frame)}


def numbers_in_rows(rows, prefix):
    """Números N de cada PREFIX-N visible, en orden de pantalla. Ignora las
    filas donde se tecleó el comando (contienen 'echo')."""
    out = []
    rx = re.compile(rf"{prefix}-(\d+)")
    for row in rows:
        if "echo" in row:
            continue
        for m in rx.finditer(row):
            out.append(int(m.group(1)))
    return out


def assert_consecutive(nums, minimum, ctx):
    assert len(nums) >= minimum, f"{ctx}\nsolo {len(nums)} líneas numeradas visibles: {nums}"
    for a, b in zip(nums, nums[1:]):
        assert b == a + 1, f"{ctx}\nsecuencia no consecutiva (residuo/duplicado/salto): {nums}"


class FrameClient:
    """Mini-cliente TCP de test: JSON-lines con buffer propio; acumula frames."""

    def __init__(self, info):
        self.sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=20)
        self.token = info["token"]
        self.buf = b""
        self.frames: list[str] = []  # todos los frames recibidos, en orden

    # --- transporte -----------------------------------------------------
    def send(self, obj):
        self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def recv_msg(self, timeout=15.0):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buf:
            rest = deadline - time.monotonic()
            if rest <= 0:
                raise TimeoutError(f"sin mensajes en {timeout:.1f}s")
            self.sock.settimeout(rest)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise TimeoutError(f"sin mensajes en {timeout:.1f}s") from None
            if not chunk:
                raise RuntimeError("conexión cerrada por el servidor")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        msg = json.loads(line)
        if msg.get("t") == "frame":
            self.frames.append(msg["d"])
        return msg

    def wait_msg(self, pred, timeout=15.0):
        deadline = time.monotonic() + timeout
        while True:
            rest = deadline - time.monotonic()
            if rest <= 0:
                raise TimeoutError("no llegó el mensaje esperado")
            msg = self.recv_msg(rest)
            if pred(msg):
                return msg

    def wait_frame(self, pred=None, timeout=15.0):
        m = self.wait_msg(lambda m: m["t"] == "frame" and (pred is None or pred(m["d"])), timeout)
        return m["d"]

    # --- protocolo --------------------------------------------------------
    def attach(self, w, h, session=SESSION):
        self.send(
            {
                "t": "attach",
                "token": self.token,
                "session": session,
                "w": w,
                "h": h,
                "create": True,
                "command": "cmd.exe",
            }
        )
        m = self.wait_msg(lambda m: m["t"] in ("attached", "error"))
        assert m["t"] == "attached", f"attach falló: {m}"
        return m

    def resize(self, w, h):
        self.send({"t": "resize", "w": w, "h": h})

    def mouse(self, e, b, x, y):
        self.send({"t": "mouse", "e": e, "b": b, "x": x, "y": y})

    def key(self, ks):
        self.send({"t": "key", "k": ks})

    def type_text(self, text):
        for ch in text:
            self.key("Space" if ch == " " else ch)

    def detach(self):
        try:
            self.send({"t": "detach"})
            self.wait_msg(lambda m: m["t"] == "detached", timeout=10)
        except Exception:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    # --- esperas de alto nivel ---------------------------------------------
    def wait_clear_frame(self, timeout=15.0, max_stale=3):
        """Primer frame con \\x1b[2J tras attach/resize. Tolera hasta max_stale
        frames viejos en vuelo (renderizados antes de procesarse el resize)."""
        stale = []
        deadline = time.monotonic() + timeout
        while True:
            f = self.wait_frame(timeout=max(0.1, deadline - time.monotonic()))
            if CLEAR in f:
                return f
            stale.append(f)
            if len(stale) > max_stale:
                pytest.fail(
                    "el primer frame tras el resize no contiene \\x1b[2J; "
                    f"llegaron {len(stale)} frames sin clear: "
                    f"{[repr(s[:150]) for s in stale]}"
                )

    def drain_quiet(self, quiet=2.0, timeout=25.0):
        """Lee frames hasta que pasen `quiet` segundos sin actividad."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.recv_msg(timeout=quiet)
            except TimeoutError:
                return
        pytest.fail(f"el servidor no se aquietó en {timeout}s (siguen llegando frames)")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    handle = ServerHandle(tmp_path_factory.mktemp("e2e-resize"))
    yield handle
    handle.stop()
    log = handle.log()
    assert "Traceback" not in log, f"tracebacks en server.log:\n{log[-3000:]}"


def gen_lines(server, prefix, n):
    """Genera n líneas numeradas PREFIX-i en el panel vía send-keys (control)."""
    server.control(f'send-keys -t {SESSION} "for /L %i in (1,1,{n}) do @echo {prefix}-%i" Enter')


# -------------------------------------------------------------------- tests
def test_resize_clears_residue(server):
    """Shrink 100x30 -> 60x20: 2J en el primer frame, sin residuos del tamaño viejo."""
    c = FrameClient(server.info)
    c.attach(100, 30)
    c.wait_frame(lambda f: f"[{SESSION}]" in f)  # status line ya pintada
    gen_lines(server, "LINEA", 40)
    c.wait_frame(lambda f: "LINEA-40" in f, timeout=20)
    c.drain_quiet(quiet=1.0, timeout=15)

    n0 = len(c.frames)
    c.resize(60, 20)
    first = c.wait_clear_frame()
    # (a) el primer frame tras el resize contiene el clear
    assert CLEAR in first, f"sin \\x1b[2J: {first[:200]!r}"
    # y solo pinta filas del tamaño nuevo (1..20)
    pos = row_positions(first)
    assert pos.issuperset(range(1, 21)), f"faltan filas: {sorted(set(range(1, 21)) - pos)}"
    assert max(pos) == 20, f"el frame posiciona filas fuera de 1..20: {sorted(pos)}"

    c.drain_quiet(quiet=1.0, timeout=15)  # deja terminar el reflow de ConPTY
    try:
        screen = apply_frames(60, 20, c.frames)
    except Exception:
        # los frames de 100 cols revientan pyte a 60: solo los posteriores al resize
        i = next(i for i in range(n0, len(c.frames)) if CLEAR in c.frames[i])
        screen = apply_frames(60, 20, c.frames[i:])
    rows = screen.display
    # (b) ninguna fila supera el ancho nuevo
    assert all(len(r) == 60 for r in rows)
    # (c) líneas LINEA-N consecutivas: sin duplicados ni saltos
    nums = numbers_in_rows(rows[:-1], "LINEA")
    assert_consecutive(nums, 5, "tras shrink 100x30 -> 60x20:\n" + "\n".join(rows))
    # (d) la última fila es la status line con el nombre de sesión
    assert f"[{SESSION}]" in rows[-1], f"status line ausente: {rows[-1]!r}"
    c.detach()


def test_resize_grow_no_garbage(server):
    """Grow 60x20 -> 120x35: 2J y el frame pinta las 35 filas (zona nueva limpia)."""
    c = FrameClient(server.info)
    c.attach(60, 20)
    c.wait_clear_frame()  # frame inicial del attach
    c.resize(120, 35)
    f = c.wait_clear_frame()
    assert CLEAR in f
    pos = row_positions(f)
    missing = set(range(1, 36)) - pos
    assert not missing, f"el frame tras crecer no pinta las filas {sorted(missing)}"
    assert max(pos) == 35, f"filas fuera de rango: {sorted(pos)}"
    # cada fila del cuerpo termina con borrado hasta fin de línea
    assert f.count("\x1b[K") >= 34, "faltan \\x1b[K de fin de fila"
    c.detach()


def test_wheel_scroll_copymode(server):
    """Rueda arriba: copy-mode con indicador [N/M] y vista consecutiva; rueda abajo: sale."""
    c = FrameClient(server.info)
    c.attach(80, 24)
    c.wait_clear_frame()
    gen_lines(server, "SCROLL", 45)
    c.wait_frame(lambda f: "SCROLL-45" in f, timeout=20)
    c.drain_quiet(quiet=1.0, timeout=15)

    for _ in range(3):
        c.mouse("wheel", "wheel-up", 5, 5)
    c.wait_frame(lambda f: IND_RE.search(f) is not None)
    screen = apply_frames(80, 24, c.frames)
    rows = screen.display
    assert IND_RE.search(rows[0]), f"indicador [N/M] no visible en la fila 0: {rows[0]!r}"
    nums = numbers_in_rows(rows[:-1], "SCROLL")
    assert_consecutive(nums, 5, "copy-mode con scroll:\n" + "\n".join(rows))
    # la vista está desplazada 9 líneas: la última generada no debe verse
    assert 45 not in nums, f"la rueda no desplazó la vista: {nums}"

    for _ in range(6):
        c.mouse("wheel", "wheel-down", 5, 5)
    c.wait_frame(lambda f: "SCROLL-45" in f and not IND_RE.search(f), timeout=15)
    screen = apply_frames(80, 24, c.frames)
    rows = screen.display
    assert not any(IND_RE.search(r) for r in rows), "el indicador sigue visible tras salir"
    assert any(r.rstrip().endswith(">") for r in rows[:-1]), (
        "el prompt no volvió a la vista live:\n" + "\n".join(rows)
    )
    c.detach()


def test_resize_exits_copymode(server):
    """Un resize mientras se está en copy-mode saca del modo y manda clear."""
    c = FrameClient(server.info)
    c.attach(80, 24)
    c.wait_clear_frame()
    c.mouse("wheel", "wheel-up", 5, 5)
    c.wait_frame(lambda f: IND_RE.search(f) is not None)

    c.resize(70, 22)
    f = c.wait_clear_frame()
    assert CLEAR in f
    assert not IND_RE.search(f), "el resize no sacó al cliente de copy-mode; frame: " + repr(
        f[:300]
    )
    c.drain_quiet(quiet=1.0, timeout=10)
    assert not IND_RE.search(c.frames[-1]), "el indicador reapareció tras el resize"
    c.detach()


def test_resize_storm_stability(server):
    """8 resizes rápidos mientras el panel imprime: el frame final queda íntegro."""
    c = FrameClient(server.info)
    c.attach(100, 30)
    c.wait_clear_frame()
    gen_lines(server, "STORM", 400)
    c.wait_frame(lambda f: "STORM-" in f, timeout=20)  # el panel ya está imprimiendo

    sizes = [(60, 20), (90, 28), (50, 15), (120, 35), (80, 24), (64, 18), (110, 32), (100, 30)]
    for w, h in sizes:
        c.resize(w, h)
        end = time.monotonic() + 0.05  # 50ms entre resizes, drenando frames
        while True:
            rest = end - time.monotonic()
            if rest <= 0:
                break
            try:
                c.recv_msg(timeout=rest)
            except TimeoutError:
                break

    c.drain_quiet(quiet=2.0, timeout=40)
    assert c.frames, "no llegó ningún frame durante la tormenta"
    last = c.frames[-1]
    pos = row_positions(last)
    missing = set(range(1, 31)) - pos
    assert not missing, f"el frame final no pinta las filas {sorted(missing)}: {last[:300]!r}"
    assert max(pos) == 30, f"el frame final posiciona filas fuera de 1..30: {sorted(pos)}"
    try:
        screen = apply_frames(100, 30, [CLEAR + last])
    except Exception as e:
        pytest.fail(f"el frame final revienta pyte: {e!r}; frame: {last[:500]!r}")
    rows = screen.display
    assert f"[{SESSION}]" in rows[-1], f"status line ausente tras la tormenta: {rows[-1]!r}"
    assert any("tmux-w>" in r for r in rows[:-1]), (
        "el prompt del shell no es visible tras la tormenta:\n" + "\n".join(rows)
    )
    c.detach()


def test_send_keys_after_shrink(server):
    """Tras achicar a 50x15 el panel sigue aceptando teclas y mostrando salida."""
    c = FrameClient(server.info)
    c.attach(100, 30)
    c.wait_clear_frame()
    n0 = len(c.frames)
    c.resize(50, 15)
    c.wait_clear_frame()
    c.drain_quiet(quiet=1.0, timeout=15)

    c.type_text("echo DESPUES-DEL-RESIZE")
    c.key("Enter")
    c.wait_frame(lambda f: "DESPUES-DEL-RESIZE" in f, timeout=20)
    c.drain_quiet(quiet=1.0, timeout=10)

    i = next(i for i in range(n0, len(c.frames)) if CLEAR in c.frames[i])
    screen = apply_frames(50, 15, c.frames[i:])
    rows = screen.display
    assert any(r.strip() == "DESPUES-DEL-RESIZE" for r in rows[:-1]), (
        "la salida tras el shrink no aparece en pantalla:\n" + "\n".join(rows)
    )
    assert f"[{SESSION}]" in rows[-1], f"status line ausente: {rows[-1]!r}"
    c.detach()
