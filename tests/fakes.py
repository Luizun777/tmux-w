"""Dobles de prueba: panel sin ConPTY, cliente sin socket."""

import threading
from collections import defaultdict
from types import SimpleNamespace

from pyte.screens import Char


def make_char(data=" ", fg="default", bg="default", **kw):
    return Char(
        data,
        fg,
        bg,
        kw.get("bold", False),
        kw.get("italics", False),
        kw.get("underscore", False),
        kw.get("strikethrough", False),
        kw.get("reverse", False),
        kw.get("blink", False),
    )


def text_rows(lines, cols):
    """Lista de strings -> filas de Char rellenadas a `cols`."""
    rows = []
    for text in lines:
        padded = text[:cols].ljust(cols)
        rows.append([make_char(c) for c in padded])
    return rows


class FakePane:
    """Compatible con la interfaz que usan model/layout/commands/render/copymode."""

    _next_id = 1000

    def __init__(self, pane_id=None, cols=80, rows=24, lines=None, title=None):
        if pane_id is None:
            FakePane._next_id += 1
            pane_id = FakePane._next_id
        self.id = pane_id
        self.cols = cols
        self.rows = rows
        self.lock = threading.RLock()
        self.dead = False
        self.pid = 99999
        self.command = "fake.exe"
        self.written = []
        self.on_dirty = None
        self.on_exit = None
        self.title = title or f"fake{pane_id}"
        self._hist_lines = lines or [f"linea {i:02d}" for i in range(rows)]
        buffer = defaultdict(lambda: defaultdict(lambda: make_char(" ")))
        visible = self._hist_lines[-rows:]
        for y, text in enumerate(visible):
            for x, c in enumerate(text[:cols]):
                buffer[y][x] = make_char(c)
        self.screen = SimpleNamespace(
            cursor=SimpleNamespace(x=0, y=min(len(visible), rows) - 1, hidden=False),
            title="",
            buffer=buffer,
        )

    def write(self, data):
        self.written.append(data)

    def resize(self, cols, rows):
        self.cols, self.rows = max(2, cols), max(1, rows)

    def kill(self):
        self.dead = True

    def alive(self):
        return not self.dead

    def snapshot_lines(self):
        return text_rows(self._hist_lines, self.cols)


class FakeClient:
    """Cliente del servidor sin socket: acumula lo enviado."""

    def __init__(self, width=80, height=24):
        from tmuxw.server import ClientState

        self.id = 1
        self.width = width
        self.height = height
        self.session_name = ""
        self.attached = False
        self.alive = True
        self.state = ClientState()
        self.last_frame = None
        self.sent = []

    def send(self, obj):
        self.sent.append(obj)


def make_fake_server(monkeypatch=None):
    """Server real con create_pane stubeado a FakePane (sin ConPTY)."""
    from tmuxw.server import Server

    server = Server()

    def fake_create_pane(session, command=None):
        return FakePane(cols=session.width, rows=max(1, session.height - 1))

    server.create_pane = fake_create_pane
    return server
