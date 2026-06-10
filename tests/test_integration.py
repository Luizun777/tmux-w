"""QA integración E2E: servidor real en subproceso + ConPTY real + cliente TCP falso."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT / ".venv" / "Scripts" / "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable


class ServerHandle:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        env = dict(os.environ)
        env["LOCALAPPDATA"] = str(tmp)
        self.proc = subprocess.Popen([PYTHON, "-m", "tmuxw", "server"],
                                     env=env, cwd=str(PROJECT))
        self.info_path = tmp / "tmuxw" / "server.json"
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.info_path.exists():
                try:
                    self.info = json.loads(self.info_path.read_text())
                    break
                except ValueError:
                    pass
            time.sleep(0.1)
        else:
            self.proc.kill()
            raise RuntimeError("el servidor no arrancó")

    def connect(self):
        s = socket.create_connection(("127.0.0.1", self.info["port"]), timeout=20)
        return Conn(s, self.info["token"])

    def control(self, line: str, timeout=20):
        """Ejecuta un comando en modo control y devuelve la salida de texto."""
        c = self.connect()
        try:
            c.send({"t": "cmd", "token": c.token, "s": line})
            out = []
            while True:
                m = c.recv(timeout)
                if m["t"] == "msg":
                    out.append(m.get("s", ""))
                elif m["t"] in ("done", "exit", "error"):
                    break
            return "\n".join(x for x in out if x)
        finally:
            c.close()

    def stop(self):
        try:
            self.control("kill-server", timeout=10)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def log(self) -> str:
        p = self.tmp / "tmuxw" / "server.log"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class Conn:
    def __init__(self, sock, token):
        self.sock = sock
        self.token = token
        self.f = sock.makefile("r", encoding="utf-8", newline="\n")

    def send(self, obj):
        self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def key(self, ks):
        self.send({"t": "key", "k": ks})

    def keys(self, *specs):
        for ks in specs:
            self.key(ks)

    def type_text(self, text):
        for ch in text:
            self.key("Space" if ch == " " else ch)

    def recv(self, timeout=20):
        self.sock.settimeout(timeout)
        line = self.f.readline()
        if not line:
            raise RuntimeError("conexión cerrada")
        return json.loads(line)

    def recv_until(self, pred, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = self.recv(max(0.5, deadline - time.time()))
            if pred(m):
                return m
        raise TimeoutError("no llegó el mensaje esperado")

    def wait_frame(self, contains=None, timeout=20):
        return self.recv_until(
            lambda m: m["t"] == "frame" and (contains is None or contains in m["d"]),
            timeout)

    def attach(self, session, w=100, h=30, create=False, command="cmd.exe"):
        self.send({"t": "attach", "token": self.token, "session": session,
                   "w": w, "h": h, "create": create, "command": command})
        return self.recv_until(lambda m: m["t"] in ("attached", "error"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    handle = ServerHandle(tmp_path_factory.mktemp("e2e"))
    yield handle
    handle.stop()
    log = handle.log()
    assert "Traceback" not in log, f"tracebacks en server.log:\n{log[-3000:]}"


def test_attach_creates_session_and_frames(server):
    c = server.connect()
    m = c.attach("qa", create=True)
    assert m["t"] == "attached" and m["session"] == "qa"
    frame = c.wait_frame()["d"]
    assert "\x1b[?2026h" in frame
    c.wait_frame(contains="[qa]")
    c.send({"t": "detach"})
    c.recv_until(lambda m: m["t"] == "detached")
    c.close()


def test_send_keys_and_capture(server):
    server.control('send-keys -t qa "echo PRUEBA-123" Enter')
    deadline = time.time() + 20
    while time.time() < deadline:
        if "PRUEBA-123" in server.control("capture-pane -p -t qa"):
            break
        time.sleep(0.5)
    else:
        pytest.fail("la salida del panel no muestra PRUEBA-123")


def test_split_via_control(server):
    server.control("split-window -h -t qa")
    out = server.control("list-panes -t qa")
    assert len(out.splitlines()) == 2


def test_prefix_binding_splits(server):
    c = server.connect()
    assert c.attach("qa")["t"] == "attached"
    c.wait_frame()
    c.keys("C-b", '"')  # split vertical por binding
    deadline = time.time() + 20
    while time.time() < deadline:
        if len(server.control("list-panes -t qa").splitlines()) == 3:
            break
        time.sleep(0.5)
    else:
        pytest.fail("C-b \" no creó el tercer panel")
    c.send({"t": "detach"})
    c.recv_until(lambda m: m["t"] == "detached")
    c.close()


def test_persistence_across_detach(server):
    out = server.control("list-panes -t qa")
    assert len(out.splitlines()) == 3  # los paneles sobreviven al detach
    c = server.connect()
    assert c.attach("qa")["t"] == "attached"
    c.wait_frame(contains="[qa]")
    c.send({"t": "detach"})
    c.recv_until(lambda m: m["t"] == "detached")
    c.close()


def test_command_prompt_display_message(server):
    c = server.connect()
    assert c.attach("qa")["t"] == "attached"
    c.wait_frame()
    c.keys("C-b", ":")
    c.type_text("display-message mensaje-de-qa-#S")
    c.key("Enter")
    frame = c.wait_frame(contains="mensaje-de-qa-qa")["d"]
    assert "mensaje-de-qa-qa" in frame
    c.send({"t": "detach"})
    c.recv_until(lambda m: m["t"] == "detached")
    c.close()


def test_copy_mode_and_paste(server):
    server.control('send-keys -t qa "echo COPIA-QA-XYZ" Enter')
    time.sleep(2)
    c = server.connect()
    assert c.attach("qa")["t"] == "attached"
    c.wait_frame()
    # copy-mode: buscar la línea, seleccionar palabra y copiar
    c.keys("C-b", "[")
    time.sleep(0.5)
    c.key("?")  # búsqueda hacia atrás
    c.type_text("COPIA-QA-XYZ")
    c.key("Enter")
    time.sleep(0.5)
    c.keys("Space", "End", "Enter")  # selección hasta fin de línea y copia
    time.sleep(0.5)
    out = server.control("show-buffer")
    assert "COPIA-QA-XYZ" in out
    c.send({"t": "detach"})
    c.recv_until(lambda m: m["t"] == "detached")
    c.close()


def test_invalid_token_rejected(server):
    s = socket.create_connection(("127.0.0.1", server.info["port"]), timeout=10)
    c = Conn(s, "token-falso")
    c.send({"t": "attach", "token": "token-falso", "session": "qa",
            "w": 80, "h": 24, "create": False})
    m = c.recv_until(lambda m: m["t"] == "error")
    assert "token" in m["msg"]
    c.close()


def test_ls_and_new_detached_session(server):
    server.control("new-session -d -s segunda")
    out = server.control("list-sessions")
    assert "qa:" in out and "segunda:" in out
    server.control("kill-session -t segunda")
    out = server.control("list-sessions")
    assert "segunda" not in out


def test_zz_kill_server_cleans_up(server):
    server.control("kill-server")
    server.proc.wait(timeout=20)
    deadline = time.time() + 10
    while time.time() < deadline and server.info_path.exists():
        time.sleep(0.2)
    assert not server.info_path.exists()
