"""CLI de tmuxw: new / attach / ls / kill-server / server / comando arbitrario."""
import sys

from .commands import parse_args, CommandError


def main(argv=None) -> int:
    # la consola puede estar en cp1252; el render usa bordes unicode
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        # como tmux: crea una sesión nueva con nombre automático
        return _new_session([])

    cmd, rest = args[0], args[1:]

    if cmd == "server":
        from . import server
        server.main()
        return 0

    if cmd in ("new", "new-session"):
        return _new_session(rest)

    if cmd in ("a", "attach", "attach-session"):
        try:
            _, values, _ = parse_args(rest, flags="dr", valued="t")
        except CommandError as e:
            print(f"tmuxw: {e}", file=sys.stderr)
            return 1
        from .client import run_attach
        return run_attach(values.get("t"), create=False)

    if cmd in ("-V", "--version", "version"):
        from . import __version__
        print(f"tmuxw {__version__}")
        return 0

    if cmd in ("-h", "--help", "help"):
        print(_USAGE)
        return 0

    # cualquier otro comando va al servidor en modo control
    from .client import run_control
    line = " ".join(_quote(t) for t in args)
    return run_control(line, autostart=False)


def _new_session(rest: list[str]) -> int:
    try:
        flags, values, pos = parse_args(rest, flags="dAD", valued="snxy")
    except CommandError as e:
        print(f"tmuxw: {e}", file=sys.stderr)
        return 1
    command = " ".join(pos) or None
    if "d" in flags:
        from .client import run_control
        line = "new-session -d"
        if "A" in flags:
            line += " -A"
        if "s" in values:
            line += f' -s "{values["s"]}"'
        if "x" in values:
            line += f' -x {values["x"]}'
        if "y" in values:
            line += f' -y {values["y"]}'
        if command:
            line += f' {command}'
        return run_control(line, autostart=True)
    from .client import run_attach
    return run_attach(values.get("s"), create=True, command=command)


def _quote(token: str) -> str:
    if not token or " " in token or '"' in token:
        return '"' + token.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return token


_USAGE = """uso: tmuxw [comando] [opciones]

  tmuxw                         nueva sesión (nombre automático)
  tmuxw new -s nombre [-d]      nueva sesión [desacoplada]
  tmuxw attach -t nombre        conectar a una sesión
  tmuxw ls                      listar sesiones
  tmuxw kill-session -t nombre  matar una sesión
  tmuxw kill-server             matar el servidor y todas las sesiones
  tmuxw <comando tmux> [...]    ejecutar cualquier comando en el servidor
                                (split-window, send-keys, set, bind, ...)

Dentro de una sesión: prefijo C-b (C-b ? lista los atajos).
"""


if __name__ == "__main__":
    sys.exit(main())
