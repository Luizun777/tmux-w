"""Comandos tmux (cmd-*.c): despacho, alias, targets y bindings por defecto."""
import time

from .config import tokenize, load_config
from .keys import parse_keyspec, keyspec_to_vt
from .render import expand_format


class CommandError(Exception):
    pass


# ------------------------------------------------------------------ parsing
def parse_args(tokens, flags: str = "", valued: str = ""):
    """Parser simple de opciones de un carácter. Devuelve (flags_set, values, positional)."""
    found, values, pos = set(), {}, []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            pos.extend(tokens[i + 1:])
            break
        if len(t) >= 2 and t[0] == "-" and t[1].isalpha():
            ch = t[1]
            if ch in valued:
                if len(t) > 2:
                    values[ch] = t[2:]
                else:
                    i += 1
                    if i >= len(tokens):
                        raise CommandError(f"la opción -{ch} requiere un valor")
                    values[ch] = tokens[i]
            elif ch in flags:
                for extra in t[1:]:
                    if extra in flags:
                        found.add(extra)
                    else:
                        raise CommandError(f"opción desconocida: -{extra}")
            else:
                raise CommandError(f"opción desconocida: -{ch}")
        else:
            pos.append(t)
        i += 1
    return found, values, pos


# ------------------------------------------------------------------ targets
def target_session(server, client, values):
    t = values.get("t", "")
    name = t.split(":", 1)[0] if t else ""
    if name:
        if name in server.sessions:
            return server.sessions[name]
        matches = [s for n, s in server.sessions.items() if n.startswith(name)]
        if len(matches) == 1:
            return matches[0]
        raise CommandError(f"sesión no encontrada: {name}")
    if client is not None and client.session_name in server.sessions:
        return server.sessions[client.session_name]
    if server.sessions:
        return next(reversed(server.sessions.values()))
    raise CommandError("no hay sesión actual")


def target_window(server, client, values):
    """Devuelve (session, window) a partir de -t [sesión][:ventana]."""
    session = target_session(server, client, values)
    t = values.get("t", "")
    spec = ""
    if ":" in t:
        spec = t.split(":", 1)[1]
    elif t and t.isdigit() and t not in server.sessions:
        spec = t
    win = session.current
    if spec in ("", "."):
        pass
    elif spec == "+":
        order = sorted(session.windows)
        win = session.windows[order[(order.index(session.current_index) + 1) % len(order)]]
    elif spec == "-":
        order = sorted(session.windows)
        win = session.windows[order[(order.index(session.current_index) - 1) % len(order)]]
    elif spec == "!":
        if session.last_index is None or session.last_index not in session.windows:
            raise CommandError("no hay ventana anterior")
        win = session.windows[session.last_index]
    elif spec.lstrip("+-").isdigit() and (spec.isdigit()):
        idx = int(spec)
        if idx not in session.windows:
            raise CommandError(f"ventana no encontrada: {idx}")
        win = session.windows[idx]
    elif spec.startswith("."):
        pass  # ':.' = ventana actual (el resto refiere a panel)
    else:
        named = [w for w in session.windows.values() if w.name == spec]
        if not named:
            raise CommandError(f"ventana no encontrada: {spec}")
        win = named[0]
    if win is None:
        raise CommandError("la sesión no tiene ventanas")
    return session, win


# ------------------------------------------------------------------ registry
COMMANDS: dict = {}
ALIASES: dict = {}


def command(name, *aliases):
    def deco(fn):
        COMMANDS[name] = fn
        for a in aliases:
            ALIASES[a] = name
        return fn

    return deco


def resolve(name: str):
    if name in COMMANDS:
        return COMMANDS[name]
    if name in ALIASES:
        return COMMANDS[ALIASES[name]]
    matches = sorted(n for n in COMMANDS if n.startswith(name))
    if len(matches) == 1:
        return COMMANDS[matches[0]]
    raise CommandError(f"comando desconocido: {name}" if not matches
                       else f"comando ambiguo: {name} ({', '.join(matches)})")


def execute_command(server, client, tokens):
    if not tokens:
        return None
    return resolve(tokens[0])(server, client, tokens[1:])


def execute_line(server, client, line: str):
    return execute_command(server, client, tokenize(line))


# ----------------------------------------------------------------- sessions
@command("new-session", "new")
def cmd_new_session(server, client, args):
    flags, values, pos = parse_args(args, flags="dAD", valued="snxy")
    name = values.get("s") or server.next_session_name()
    width = int(values.get("x", client.width if client else 80))
    height = int(values.get("y", client.height if client else 24))
    cmd = " ".join(pos) or None
    if name in server.sessions:
        if "A" in flags:
            if client is not None and "d" not in flags:
                server.attach_client(client, server.sessions[name])
            return None
        raise CommandError(f"sesión duplicada: {name}")
    session = server.create_session(name, width, height, cmd)
    if client is not None and "d" not in flags:
        server.attach_client(client, session)
    return None


@command("attach-session", "attach", "a")
def cmd_attach(server, client, args):
    flags, values, pos = parse_args(args, flags="dr", valued="t")
    if client is None:
        raise CommandError("attach requiere un cliente interactivo")
    session = target_session(server, client, values)
    server.attach_client(client, session)
    return None


@command("detach-client", "detach")
def cmd_detach(server, client, args):
    if client is not None:
        server.detach_client(client)
    return None


@command("kill-session")
def cmd_kill_session(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    server.kill_session(target_session(server, client, values))
    return None


@command("rename-session", "rename")
def cmd_rename_session(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    if not pos:
        raise CommandError("uso: rename-session nombre")
    session = target_session(server, client, values)
    new = pos[0]
    if new in server.sessions and server.sessions[new] is not session:
        raise CommandError(f"sesión duplicada: {new}")
    server.rename_session(session, new)
    return None


@command("list-sessions", "ls")
def cmd_list_sessions(server, client, args):
    if not server.sessions:
        return "no hay sesiones"
    lines = []
    for name, s in server.sessions.items():
        n = len(s.windows)
        created = time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(s.created))
        attached = sum(1 for c in server.clients if c.attached and c.session_name == name)
        suffix = " (attached)" if attached else ""
        lines.append(f"{name}: {n} windows (created {created}) [{s.width}x{s.height}]{suffix}")
    return "\n".join(lines)


@command("has-session", "has")
def cmd_has_session(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    target_session(server, client, values)
    return None


@command("switch-client", "switchc")
def cmd_switch_client(server, client, args):
    flags, values, pos = parse_args(args, flags="np", valued="t")
    if client is None or not client.attached:
        raise CommandError("switch-client requiere un cliente")
    names = list(server.sessions)
    if not names:
        raise CommandError("no hay sesiones")
    if "n" in flags or "p" in flags:
        cur = names.index(client.session_name) if client.session_name in names else 0
        step = 1 if "n" in flags else -1
        session = server.sessions[names[(cur + step) % len(names)]]
    else:
        session = target_session(server, client, values)
    server.attach_client(client, session)
    return None


@command("kill-server")
def cmd_kill_server(server, client, args):
    server.shutdown()
    return None


# ------------------------------------------------------------------ windows
@command("new-window", "neww")
def cmd_new_window(server, client, args):
    flags, values, pos = parse_args(args, flags="d", valued="tn")
    session = target_session(server, client, values)
    cmd = " ".join(pos) or None
    win = server.create_window(session, cmd, name=values.get("n"))
    if "d" in flags:
        session.select_window(session.last_index if session.last_index is not None else win.index)
    server.relayout(session)
    return None


@command("kill-window", "killw")
def cmd_kill_window(server, client, args):
    flags, values, pos = parse_args(args, flags="a", valued="t")
    session, win = target_window(server, client, values)
    server.kill_window(session, win)
    return None


@command("select-window", "selectw")
def cmd_select_window(server, client, args):
    flags, values, pos = parse_args(args, flags="npl", valued="t")
    session = target_session(server, client, values)
    if "n" in flags:
        session.cycle_window(1)
    elif "p" in flags:
        session.cycle_window(-1)
    elif "l" in flags:
        _last_window(session)
    else:
        _, win = target_window(server, client, values)
        session.select_window(win.index)
    server.relayout(session)
    return None


def _last_window(session):
    if session.last_index is None or session.last_index not in session.windows:
        raise CommandError("no hay ventana anterior")
    session.select_window(session.last_index)


@command("next-window", "next")
def cmd_next_window(server, client, args):
    session = target_session(server, client, dict(parse_args(args, valued="t")[1]))
    session.cycle_window(1)
    server.relayout(session)
    return None


@command("previous-window", "prev")
def cmd_previous_window(server, client, args):
    session = target_session(server, client, parse_args(args, valued="t")[1])
    session.cycle_window(-1)
    server.relayout(session)
    return None


@command("last-window", "last")
def cmd_last_window(server, client, args):
    session = target_session(server, client, parse_args(args, valued="t")[1])
    _last_window(session)
    server.relayout(session)
    return None


@command("rename-window", "renamew")
def cmd_rename_window(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    if not pos:
        raise CommandError("uso: rename-window nombre")
    _, win = target_window(server, client, values)
    win.custom_name = pos[0]
    return None


@command("list-windows", "lsw")
def cmd_list_windows(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    session = target_session(server, client, values)
    lines = []
    for idx in sorted(session.windows):
        w = session.windows[idx]
        flag = "*" if idx == session.current_index else ("-" if idx == session.last_index else " ")
        lines.append(f"{idx}: {w.name}{flag} ({len(w.panes())} panes) [{session.width}x{session.height}]")
    return "\n".join(lines) or "no hay ventanas"


@command("next-layout", "nextl")
def cmd_next_layout(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    session, win = target_window(server, client, values)
    name = win.next_preset()
    server.relayout(session)
    return name


@command("rotate-window", "rotatew")
def cmd_rotate_window(server, client, args):
    flags, values, pos = parse_args(args, flags="DU", valued="t")
    session, win = target_window(server, client, values)
    panes = win.panes()
    if len(panes) > 1:
        if "D" in flags:
            rotated = panes[-1:] + panes[:-1]
        else:
            rotated = panes[1:] + panes[:1]
        active_pos = panes.index(win.active)
        _assign_leaves(win.layout, rotated)
        win.set_active(rotated[active_pos])
    server.relayout(session)
    return None


def _assign_leaves(layout, panes):
    leaves = []

    def walk(node):
        if hasattr(node, "pane"):
            leaves.append(node)
        else:
            for c in node.children:
                walk(c)

    walk(layout.root)
    for leaf, pane in zip(leaves, panes):
        leaf.pane = pane


# -------------------------------------------------------------------- panes
@command("split-window", "splitw")
def cmd_split_window(server, client, args):
    flags, values, pos = parse_args(args, flags="hvdb", valued="tpc")
    session, win = target_window(server, client, values)
    kind = "h" if "h" in flags else "v"
    percent = int(values["p"]) if "p" in values else None
    body_h = session.height - (1 if session.options.get("status") else 0)
    if not win.layout.can_split(win.active, kind, session.width, body_h):
        raise CommandError("no hay espacio para el panel")
    cmd = " ".join(pos) or None
    pane = server.create_pane(session, cmd)
    win.zoomed = False
    win.layout.split(win.active, kind, pane, percent)
    if "d" not in flags:
        win.set_active(pane)
    server.relayout(session)
    return None


@command("select-pane", "selectp")
def cmd_select_pane(server, client, args):
    flags, values, pos = parse_args(args, flags="LRUDl", valued="t")
    session, win = target_window(server, client, values)
    body_h = session.height - (1 if session.options.get("status") else 0)
    if "l" in flags:
        return cmd_last_pane(server, client, [])
    t = values.get("t", "")
    pane = None
    for d in "LRUD":
        if d in flags:
            pane = win.layout.neighbor(win.active, d, session.width, body_h)
            break
    else:
        spec = t.split(".", 1)[1] if "." in t else ""
        panes = win.panes()
        if spec == "+":
            pane = panes[(panes.index(win.active) + 1) % len(panes)]
        elif spec == "-":
            pane = panes[(panes.index(win.active) - 1) % len(panes)]
        elif spec.isdigit():
            idx = int(spec)
            if idx >= len(panes):
                raise CommandError(f"panel no encontrado: {idx}")
            pane = panes[idx]
        else:
            raise CommandError("select-pane: falta -L/-R/-U/-D o -t")
    if pane is not None:
        win.set_active(pane)
        win.zoomed = False
        server.relayout(session)
    return None


@command("last-pane", "lastp")
def cmd_last_pane(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    session, win = target_window(server, client, values)
    if win.last_pane is None or win.last_pane not in win.panes():
        raise CommandError("no hay panel anterior")
    win.set_active(win.last_pane)
    server.relayout(session)
    return None


@command("kill-pane", "killp")
def cmd_kill_pane(server, client, args):
    flags, values, pos = parse_args(args, flags="a", valued="t")
    session, win = target_window(server, client, values)
    server.close_pane(win.active, kill_process=True)
    return None


@command("swap-pane", "swapp")
def cmd_swap_pane(server, client, args):
    flags, values, pos = parse_args(args, flags="UD", valued="t")
    session, win = target_window(server, client, values)
    panes = win.panes()
    if len(panes) < 2:
        return None
    i = panes.index(win.active)
    j = (i - 1) % len(panes) if "U" in flags or not flags else (i + 1) % len(panes)
    win.layout.swap(panes[i], panes[j])
    server.relayout(session)
    return None


@command("resize-pane", "resizep")
def cmd_resize_pane(server, client, args):
    flags, values, pos = parse_args(args, flags="LRUDZ", valued="t")
    session, win = target_window(server, client, values)
    if "Z" in flags:
        win.zoomed = not win.zoomed
        server.relayout(session)
        return None
    amount = int(pos[0]) if pos and pos[0].isdigit() else 1
    body_h = session.height - (1 if session.options.get("status") else 0)
    for d in "LRUD":
        if d in flags:
            win.layout.resize(win.active, d, amount, session.width, body_h)
            break
    else:
        raise CommandError("resize-pane: falta -L/-R/-U/-D/-Z")
    server.relayout(session)
    return None


@command("list-panes", "lsp")
def cmd_list_panes(server, client, args):
    flags, values, pos = parse_args(args, valued="t")
    session, win = target_window(server, client, values)
    body_h = session.height - (1 if session.options.get("status") else 0)
    rects = win.layout.compute(session.width, body_h)
    lines = []
    for i, p in enumerate(win.panes()):
        r = rects[p]
        mark = " (active)" if p is win.active else ""
        lines.append(f"{i}: [{r.w}x{r.h}] [pid {p.pid}] %{p.id}{mark}")
    return "\n".join(lines)


@command("display-panes", "displayp")
def cmd_display_panes(server, client, args):
    if client is None:
        raise CommandError("display-panes requiere un cliente")
    st = client.state
    st.mode = "displayp"
    st.display_panes_until = time.time() + server.options.get("display-panes-time") / 1000.0
    return None


# ------------------------------------------------------------------ buffers
@command("copy-mode")
def cmd_copy_mode(server, client, args):
    flags, values, pos = parse_args(args, flags="u", valued="t")
    if client is None:
        raise CommandError("copy-mode requiere un cliente")
    from .copymode import CopyMode
    session, win = target_window(server, client, values)
    st = client.state
    if st.copy is None:
        st.copy = CopyMode(win.active, session.options.get("mode-keys"),
                           scroll_up=win.active.rows if "u" in flags else 0)
        st.mode = "copy"
    return None


@command("paste-buffer", "pasteb")
def cmd_paste_buffer(server, client, args):
    flags, values, pos = parse_args(args, flags="d", valued="tb")
    session, win = target_window(server, client, values)
    idx = int(values.get("b", 0))
    if idx >= len(server.buffers):
        raise CommandError("no hay buffer")
    text = server.buffers[idx].replace("\r\n", "\r").replace("\n", "\r")
    win.active.write(text)
    if "d" in flags:
        server.buffers.pop(idx)
    return None


@command("set-buffer", "setb")
def cmd_set_buffer(server, client, args):
    flags, values, pos = parse_args(args, valued="b")
    if not pos:
        raise CommandError("uso: set-buffer texto")
    server.buffers.insert(0, " ".join(pos))
    return None


@command("show-buffer", "showb")
def cmd_show_buffer(server, client, args):
    flags, values, pos = parse_args(args, valued="b")
    idx = int(values.get("b", 0))
    if idx >= len(server.buffers):
        raise CommandError("no hay buffer")
    return server.buffers[idx]


@command("list-buffers", "lsb")
def cmd_list_buffers(server, client, args):
    lines = [f"buffer{i:04d}: {len(b)} bytes: {b[:50]!r}" for i, b in enumerate(server.buffers)]
    return "\n".join(lines) or "no hay buffers"


@command("capture-pane", "capturep")
def cmd_capture_pane(server, client, args):
    flags, values, pos = parse_args(args, flags="pJ", valued="tSE")
    session, win = target_window(server, client, values)
    pane = win.active
    rows = pane.snapshot_lines()  # historial + pantalla
    if "S" not in values:
        rows = rows[-pane.rows:]  # solo la pantalla visible
    else:
        try:
            start = int(values["S"])
            if start < 0:  # -S -N = N líneas de historial extra
                rows = rows[max(0, len(rows) - pane.rows + start):]
        except ValueError:
            pass
    lines = ["".join(ch.data or " " for ch in row).rstrip() for row in rows]
    text = "\n".join(lines)
    if "p" in flags or client is None or not client.attached:
        return text
    server.buffers.insert(0, text)
    return None


@command("send-keys", "send")
def cmd_send_keys(server, client, args):
    flags, values, pos = parse_args(args, flags="lR", valued="t")
    session, win = target_window(server, client, values)
    pane = win.active
    out = []
    for token in pos:
        if "l" in flags:
            out.append(token)
            continue
        try:
            ks = parse_keyspec(token)
            vt = keyspec_to_vt(ks)
            out.append(vt if vt else token)
        except ValueError:
            out.append(token)
    pane.write("".join(out))
    return None


# ------------------------------------------------------- opciones y teclas
@command("set-option", "set", "setw", "set-window-option")
def cmd_set_option(server, client, args):
    flags, values, pos = parse_args(args, flags="gu", valued="t")
    if not pos:
        raise CommandError("uso: set [-g] opción valor")
    name = pos[0]
    if "u" in flags:
        opts = server.options if "g" in flags else _session_opts(server, client, values)
        opts.unset(name)
        return None
    if len(pos) < 2:
        raise CommandError("uso: set [-g] opción valor")
    value = " ".join(pos[1:])
    opts = server.options if "g" in flags else _session_opts(server, client, values)
    try:
        opts.set(name, value)
    except ValueError as e:
        raise CommandError(str(e))
    if name == "history-limit":
        return None
    server.relayout_all()
    return None


def _session_opts(server, client, values):
    try:
        return target_session(server, client, values).options
    except CommandError:
        return server.options


@command("show-options", "show")
def cmd_show_options(server, client, args):
    flags, values, pos = parse_args(args, flags="g", valued="t")
    opts = server.options if "g" in flags else _session_opts(server, client, values)
    merged = opts.show()
    return "\n".join(f"{k} {_fmt_opt(v)}" for k, v in sorted(merged.items()))


def _fmt_opt(v):
    if isinstance(v, bool):
        return "on" if v else "off"
    return str(v)


@command("bind-key", "bind")
def cmd_bind_key(server, client, args):
    # solo se parsean flags ANTES de la tecla; el resto es el comando verbatim
    args = list(args)
    root = False
    repeat = False
    while args and args[0].startswith("-") and len(args[0]) > 1:
        if args[0] == "-n":
            root = True
            args.pop(0)
        elif args[0] == "-r":
            repeat = True
            args.pop(0)
        elif args[0] == "-T":
            if len(args) < 2:
                raise CommandError("la opción -T requiere un valor")
            root = args[1] == "root"
            del args[:2]
        elif args[0] == "--":
            args.pop(0)
            break
        else:
            raise CommandError(f"opción desconocida: {args[0]}")
    if len(args) < 2:
        raise CommandError("uso: bind-key [-r] tecla comando [args]")
    try:
        ks = parse_keyspec(args[0])
    except ValueError as e:
        raise CommandError(str(e))
    table = server.root_bindings if root else server.bindings
    table[ks] = args[1:]
    if not root:
        if repeat:
            server.repeat_bindings.add(ks)
        else:
            server.repeat_bindings.discard(ks)
    return None


@command("unbind-key", "unbind")
def cmd_unbind_key(server, client, args):
    flags, values, pos = parse_args(args, flags="an", valued="T")
    root = "n" in flags or values.get("T") == "root"
    table = server.root_bindings if root else server.bindings
    if "a" in flags:
        table.clear()
        if not root:
            server.repeat_bindings.clear()
        return None
    if not pos:
        raise CommandError("uso: unbind-key tecla")
    try:
        ks = parse_keyspec(pos[0])
    except ValueError as e:
        raise CommandError(str(e))
    table.pop(ks, None)
    if not root:
        server.repeat_bindings.discard(ks)
    return None


@command("list-keys", "lsk")
def cmd_list_keys(server, client, args):
    lines = []
    for ks in sorted(server.root_bindings):
        lines.append(f"bind-key -T root      {ks:12s} {' '.join(server.root_bindings[ks])}")
    for ks in sorted(server.bindings):
        rep = "-r " if ks in server.repeat_bindings else "   "
        lines.append(f"bind-key {rep}-T prefix {ks:12s} {' '.join(server.bindings[ks])}")
    text = "\n".join(lines)
    if client is not None and client.attached:
        st = client.state
        st.page_lines = text.split("\n")
        st.page_offset = 0
        st.mode = "page"
        return None
    return text


# ---------------------------------------------------------------- varios
@command("command-prompt")
def cmd_command_prompt(server, client, args):
    flags, values, pos = parse_args(args, valued="pI")
    if client is None:
        raise CommandError("command-prompt requiere un cliente")
    st = client.state
    st.mode = "prompt"
    st.prompt_prefix = (values.get("p", ":") + " ") if "p" in values else ":"
    st.prompt_prefix_len = len(st.prompt_prefix)
    st.prompt_buffer = values.get("I", "")
    st.prompt_cursor = len(st.prompt_buffer)
    st.prompt_template = " ".join(pos) if pos else None
    st.prompt_callback = None
    st.prompt_history_idx = None
    return None


@command("confirm-before", "confirm")
def cmd_confirm_before(server, client, args):
    flags, values, pos = parse_args(args, valued="p")
    if client is None:
        raise CommandError("confirm-before requiere un cliente")
    if not pos:
        raise CommandError("uso: confirm-before [-p prompt] comando")
    st = client.state
    session = server.sessions.get(client.session_name)
    win = session.current if session else None
    pane = win.active if win else None
    prompt = values.get("p", f"Confirmar {pos[0]}? (y/n)")
    st.confirm_prompt = expand_format(prompt, session, win, pane)
    st.confirm_cmd = list(pos)
    st.mode = "confirm"
    return None


@command("display-message", "display")
def cmd_display_message(server, client, args):
    flags, values, pos = parse_args(args, flags="p", valued="t")
    session = None
    try:
        session = target_session(server, client, values)
    except CommandError:
        pass
    win = session.current if session else None
    pane = win.active if win else None
    msg = expand_format(" ".join(pos), session, win, pane) if pos else ""
    if "p" in flags or client is None or not client.attached:
        return msg
    st = client.state
    st.message = msg
    st.message_until = time.time() + server.options.get("display-time") / 1000.0
    return None


@command("source-file", "source")
def cmd_source_file(server, client, args):
    flags, values, pos = parse_args(args, flags="q")
    if not pos:
        raise CommandError("uso: source-file ruta")
    errors = load_config(pos[0], lambda toks: execute_command(server, None, toks))
    if errors and "q" not in flags:
        return "\n".join(errors)
    return None


@command("clock-mode")
def cmd_clock_mode(server, client, args):
    if client is None:
        raise CommandError("clock-mode requiere un cliente")
    client.state.mode = "clock"
    client.state.clock = True
    return None


@command("choose-window")
def cmd_choose_window(server, client, args):
    if client is None:
        raise CommandError("choose-window requiere un cliente")
    session = target_session(server, client, parse_args(args, valued="t")[1])
    entries = []
    for idx in sorted(session.windows):
        w = session.windows[idx]
        entries.append((f"{idx}: {w.name} ({len(w.panes())} panes)",
                        ["select-window", "-t", f":{idx}"]))
    _open_chooser(client, "Ventanas", entries)
    return None


@command("choose-session", "choose-tree")
def cmd_choose_session(server, client, args):
    if client is None:
        raise CommandError("choose-session requiere un cliente")
    entries = [(f"{name}: {len(s.windows)} windows", ["switch-client", "-t", name])
               for name, s in server.sessions.items()]
    _open_chooser(client, "Sesiones", entries)
    return None


def _open_chooser(client, title, entries):
    st = client.state
    st.chooser = entries
    st.chooser_idx = 0
    st.chooser_title = title
    st.mode = "choose"


# ----------------------------------------------------------- default binds
DEFAULT_BINDINGS: dict[str, list[str]] = {
    "c": ["new-window"],
    ",": ["command-prompt", "-p", "(rename-window)", "-I", "#W", "rename-window %%"],
    "$": ["command-prompt", "-p", "(rename-session)", "-I", "#S", "rename-session %%"],
    "&": ["confirm-before", "-p", "kill-window #W? (y/n)", "kill-window"],
    "x": ["confirm-before", "-p", "kill-pane #P? (y/n)", "kill-pane"],
    "%": ["split-window", "-h"],
    '"': ["split-window", "-v"],
    "d": ["detach-client"],
    "n": ["next-window"],
    "p": ["previous-window"],
    "l": ["last-window"],
    "w": ["choose-window"],
    "s": ["choose-session"],
    "o": ["select-pane", "-t", ":.+"],
    ";": ["last-pane"],
    "Up": ["select-pane", "-U"],
    "Down": ["select-pane", "-D"],
    "Left": ["select-pane", "-L"],
    "Right": ["select-pane", "-R"],
    "C-Up": ["resize-pane", "-U"],
    "C-Down": ["resize-pane", "-D"],
    "C-Left": ["resize-pane", "-L"],
    "C-Right": ["resize-pane", "-R"],
    "M-Up": ["resize-pane", "-U", "5"],
    "M-Down": ["resize-pane", "-D", "5"],
    "M-Left": ["resize-pane", "-L", "5"],
    "M-Right": ["resize-pane", "-R", "5"],
    "z": ["resize-pane", "-Z"],
    "Space": ["next-layout"],
    "{": ["swap-pane", "-U"],
    "}": ["swap-pane", "-D"],
    "C-o": ["rotate-window"],
    "q": ["display-panes"],
    "[": ["copy-mode"],
    "]": ["paste-buffer"],
    "PgUp": ["copy-mode", "-u"],
    ":": ["command-prompt"],
    "?": ["list-keys"],
    "t": ["clock-mode"],
    "(": ["switch-client", "-p"],
    ")": ["switch-client", "-n"],
}
for _d in "0123456789":
    DEFAULT_BINDINGS[_d] = ["select-window", "-t", f":{_d}"]

# Bindings repetibles (bind -r): tras ejecutarse, el prefijo sigue activo
# durante repeat-time ms, como en tmux (mantener Ctrl+flecha redimensiona seguido).
DEFAULT_REPEAT_BINDINGS: set[str] = {
    "Up", "Down", "Left", "Right",
    "C-Up", "C-Down", "C-Left", "C-Right",
    "M-Up", "M-Down", "M-Left", "M-Right",
}
