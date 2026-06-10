"""Rutas de runtime de tmux-w (equivalente a /tmp/tmux-UID de tmux)."""
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "tmuxw"
SERVER_FILE = APP_DIR / "server.json"
LOG_FILE = APP_DIR / "server.log"


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def read_server_info() -> dict | None:
    """Lee {port, token, pid} del servidor activo, o None si no hay."""
    try:
        with open(SERVER_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
        if not isinstance(info, dict) or "port" not in info or "token" not in info:
            return None
        return info
    except (OSError, ValueError):
        return None


def write_server_info(port: int, token: str, pid: int) -> None:
    ensure_dirs()
    tmp = SERVER_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": token, "pid": pid}, f)
    os.replace(tmp, SERVER_FILE)


def clear_server_info() -> None:
    try:
        SERVER_FILE.unlink()
    except OSError:
        pass


def config_files() -> list[Path]:
    """Archivos de configuración candidatos, en orden de preferencia."""
    home = Path.home()
    for name in (".tmuxw.conf", ".tmux.conf"):
        p = home / name
        if p.is_file():
            return [p]
    return []
