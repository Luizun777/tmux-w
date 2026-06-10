"""Cliente interactivo: consola Windows en modo raw + VT (client.c / tty.c de tmux)."""
import ctypes
import json
import socket
import subprocess
import sys
import threading
import time
from ctypes import wintypes

from . import paths
from .keys import ConsoleInputReader

STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
ENABLE_PROCESSED_INPUT = 0x0001
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_MOUSE_INPUT = 0x0010
ENABLE_QUICK_EDIT = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
ENABLE_VT_PROCESSING = 0x0004
DISABLE_NEWLINE_AUTO_RETURN = 0x0008

_k32 = ctypes.windll.kernel32


class _Coord(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _SmallRect(ctypes.Structure):
    _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]


class _ConsoleInfo(ctypes.Structure):
    _fields_ = [("dwSize", _Coord), ("dwCursorPosition", _Coord),
                ("wAttributes", wintypes.WORD), ("srWindow", _SmallRect),
                ("dwMaximumWindowSize", _Coord)]


def console_size() -> tuple[int, int]:
    h = _k32.GetStdHandle(STD_OUTPUT_HANDLE)
    info = _ConsoleInfo()
    if _k32.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
        return (info.srWindow.Right - info.srWindow.Left + 1,
                info.srWindow.Bottom - info.srWindow.Top + 1)
    return 80, 24


class RawConsole:
    """Activa VT en salida y modo raw en entrada; restaura al salir."""

    def __enter__(self):
        self.hin = _k32.GetStdHandle(STD_INPUT_HANDLE)
        self.hout = _k32.GetStdHandle(STD_OUTPUT_HANDLE)
        self.old_in = wintypes.DWORD()
        self.old_out = wintypes.DWORD()
        _k32.GetConsoleMode(self.hin, ctypes.byref(self.old_in))
        _k32.GetConsoleMode(self.hout, ctypes.byref(self.old_out))
        new_in = (self.old_in.value & ~(ENABLE_PROCESSED_INPUT | ENABLE_LINE_INPUT
                                        | ENABLE_ECHO_INPUT | ENABLE_QUICK_EDIT))
        new_in |= ENABLE_EXTENDED_FLAGS | ENABLE_MOUSE_INPUT
        _k32.SetConsoleMode(self.hin, new_in)
        _k32.SetConsoleMode(self.hout, self.old_out.value | ENABLE_VT_PROCESSING
                            | DISABLE_NEWLINE_AUTO_RETURN)
        sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")
        sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        sys.stdout.write("\x1b[?1049l\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        _k32.SetConsoleMode(self.hin, self.old_in.value)
        _k32.SetConsoleMode(self.hout, self.old_out.value)


# ----------------------------------------------------------------- conexión
def spawn_server() -> None:
    paths.ensure_dirs()
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
             | subprocess.CREATE_NO_WINDOW)
    with open(paths.LOG_FILE, "a", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, "-m", "tmuxw", "server"],
                         creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, close_fds=True)


def connect(autostart: bool = True, timeout: float = 6.0):
    """Devuelve (socket, token). Arranca el servidor si hace falta."""
    info = paths.read_server_info()
    sock = _try_connect(info)
    if sock is not None:
        return sock, info["token"]
    if not autostart:
        return None, None
    paths.clear_server_info()
    spawn_server()
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = paths.read_server_info()
        sock = _try_connect(info)
        if sock is not None:
            return sock, info["token"]
        time.sleep(0.1)
    raise RuntimeError("no se pudo arrancar el servidor tmuxw")


def _try_connect(info):
    if not info:
        return None
    try:
        sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=2.0)
        sock.settimeout(None)
        return sock
    except OSError:
        return None


def _send(sock, obj) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


# ------------------------------------------------------------------ attach
def run_attach(session: str | None, create: bool, command: str | None = None,
               detach_others: bool = False) -> int:
    try:
        sock, token = connect(autostart=create)
    except RuntimeError as e:
        print(f"tmuxw: {e}", file=sys.stderr)
        return 1
    if sock is None:
        print("tmuxw: el servidor no está corriendo", file=sys.stderr)
        return 1

    w, h = console_size()
    _send(sock, {"t": "attach", "token": token, "session": session,
                 "w": w, "h": h, "create": create, "command": command})

    stop = threading.Event()
    exit_msg = [""]

    def input_loop():
        reader = ConsoleInputReader()
        try:
            for kind, data in reader.read_events():
                if stop.is_set():
                    break
                if kind == "key":
                    _send(sock, {"t": "key", "k": data})
                else:  # mouse
                    _send(sock, {"t": "mouse", **data})
        except (OSError, ValueError):
            pass

    def resize_loop():
        last = (w, h)
        while not stop.is_set():
            time.sleep(0.2)
            cur = console_size()
            if cur != last:
                last = cur
                try:
                    _send(sock, {"t": "resize", "w": cur[0], "h": cur[1]})
                except OSError:
                    break

    rc = 0
    with RawConsole():
        threading.Thread(target=input_loop, daemon=True).start()
        threading.Thread(target=resize_loop, daemon=True).start()
        try:
            f = sock.makefile("r", encoding="utf-8", newline="\n")
            for line in f:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                t = msg.get("t")
                if t == "frame":
                    sys.stdout.write(msg["d"])
                    sys.stdout.flush()
                elif t == "detached":
                    exit_msg[0] = f"[detached (from session {msg.get('session', '')})]"
                    break
                elif t == "exit":
                    exit_msg[0] = f"[exited: {msg.get('msg', '')}]"
                    break
                elif t == "error":
                    exit_msg[0] = f"tmuxw: {msg.get('msg', '')}"
                    rc = 1
                    break
        except (OSError, KeyboardInterrupt):
            exit_msg[0] = "[conexión perdida]"
            rc = 1
        finally:
            stop.set()
            try:
                sock.close()
            except OSError:
                pass
    if exit_msg[0]:
        print(exit_msg[0])
    return rc


# ------------------------------------------------------------- modo control
def run_control(command_line: str, autostart: bool = False) -> int:
    try:
        sock, token = connect(autostart=autostart)
    except RuntimeError as e:
        print(f"tmuxw: {e}", file=sys.stderr)
        return 1
    if sock is None:
        print("tmuxw: el servidor no está corriendo", file=sys.stderr)
        return 1
    rc = 0
    try:
        _send(sock, {"t": "cmd", "token": token, "s": command_line})
        f = sock.makefile("r", encoding="utf-8", newline="\n")
        for line in f:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            t = msg.get("t")
            if t == "msg":
                if msg.get("s"):
                    print(msg["s"])
                if msg.get("err"):
                    rc = 1
            elif t in ("done", "exit", "error"):
                if t == "error":
                    print(f"tmuxw: {msg.get('msg', '')}", file=sys.stderr)
                    rc = 1
                break
    except OSError:
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return rc
