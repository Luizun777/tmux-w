"""QA unitarias: tmuxw/commands.py contra el Server real con panes falsos."""
import pytest

from tmuxw.commands import (CommandError, execute_command, execute_line,
                            parse_args, resolve, target_window)

from .fakes import FakeClient, FakePane, make_fake_server


# ----------------------------------------------------------------- parse_args
def test_parse_args_basics():
    flags, values, pos = parse_args(["-h", "-t", "demo", "cmd.exe"],
                                    flags="hv", valued="t")
    assert flags == {"h"}
    assert values == {"t": "demo"}
    assert pos == ["cmd.exe"]


def test_parse_args_combined_flags():
    flags, _, _ = parse_args(["-hd"], flags="hdv")
    assert flags == {"h", "d"}


def test_parse_args_attached_value():
    _, values, _ = parse_args(["-tdemo"], valued="t")
    assert values == {"t": "demo"}


def test_parse_args_double_dash():
    _, _, pos = parse_args(["--", "-h", "x"], flags="h")
    assert pos == ["-h", "x"]


def test_parse_args_errors():
    with pytest.raises(CommandError):
        parse_args(["-x"], flags="h")
    with pytest.raises(CommandError):
        parse_args(["-t"], valued="t")


def test_resolve_aliases_and_abbrev():
    assert resolve("neww") is resolve("new-window")
    assert resolve("splitw") is resolve("split-window")
    assert resolve("kill-ser") is resolve("kill-server")
    with pytest.raises(CommandError):
        resolve("li")  # ambiguo: list-*
    with pytest.raises(CommandError):
        resolve("comando-inexistente")


# ------------------------------------------------------------------- fixture
@pytest.fixture
def server():
    srv = make_fake_server()
    execute_command(srv, None, ["new-session", "-d", "-s", "main"])
    return srv


def run(srv, line, client=None):
    return execute_line(srv, client, line)


# ------------------------------------------------------------------ sesiones
def test_new_session_and_ls(server):
    out = run(server, "list-sessions")
    assert "main: 1 windows" in out


def test_new_session_duplicate(server):
    with pytest.raises(CommandError):
        run(server, "new-session -d -s main")


def test_rename_session(server):
    run(server, "rename-session -t main principal")
    assert "principal" in server.sessions
    assert "main" not in server.sessions


def test_has_session(server):
    run(server, "has-session -t main")
    with pytest.raises(CommandError):
        run(server, "has-session -t nope")


def test_kill_session_shuts_down_when_last(server):
    run(server, "kill-session -t main")
    assert server.sessions == {}
    assert server.running is False  # como tmux: sin sesiones, el servidor muere


# ------------------------------------------------------------------ ventanas
def test_new_window_and_select(server):
    run(server, "new-window -t main")
    s = server.sessions["main"]
    assert len(s.windows) == 2
    assert s.current_index == 1
    run(server, "select-window -t main:0")
    assert s.current_index == 0
    run(server, "last-window -t main")
    assert s.current_index == 1
    run(server, "next-window -t main")
    assert s.current_index == 0
    run(server, "previous-window -t main")
    assert s.current_index == 1


def test_rename_and_list_windows(server):
    run(server, "rename-window -t main compilar")
    out = run(server, "list-windows -t main")
    assert "0: compilar*" in out


def test_kill_window_keeps_session(server):
    run(server, "new-window -t main")
    run(server, "kill-window -t main:1")
    s = server.sessions["main"]
    assert list(s.windows) == [0]
    assert server.running is True


# -------------------------------------------------------------------- panes
def test_split_window(server):
    run(server, "split-window -h -t main")
    s = server.sessions["main"]
    win = s.current
    assert len(win.panes()) == 2
    assert win.active is win.panes()[1]  # el nuevo queda activo


def test_split_detached_keeps_active(server):
    s = server.sessions["main"]
    first = s.current.active
    run(server, "split-window -v -d -t main")
    assert s.current.active is first


def test_split_percent_and_list_panes(server):
    run(server, "split-window -h -p 30 -t main")
    out = run(server, "list-panes -t main")
    lines = out.splitlines()
    assert len(lines) == 2
    assert "(active)" in lines[1]


def test_select_pane_directions(server):
    run(server, "split-window -h -t main")
    s = server.sessions["main"]
    win = s.current
    left, right = win.panes()
    assert win.active is right
    run(server, "select-pane -L -t main")
    assert win.active is left
    run(server, "select-pane -R -t main")
    assert win.active is right
    run(server, "select-pane -t main:.0")
    assert win.active is left
    run(server, "select-pane -t main:.+")
    assert win.active is right


def test_kill_pane_collapses(server):
    run(server, "split-window -h -t main")
    s = server.sessions["main"]
    win = s.current
    run(server, "kill-pane -t main")
    assert len(win.panes()) == 1
    assert s.windows  # la ventana sigue


def test_kill_last_pane_kills_window(server):
    run(server, "new-window -t main")
    run(server, "kill-pane -t main")  # único panel de la ventana 1
    assert list(server.sessions["main"].windows) == [0]


def test_swap_pane(server):
    run(server, "split-window -h -t main")
    win = server.sessions["main"].current
    a, b = win.panes()
    run(server, "swap-pane -U -t main")
    assert win.panes() == [b, a]


def test_resize_pane_zoom_toggle(server):
    run(server, "split-window -h -t main")
    win = server.sessions["main"].current
    run(server, "resize-pane -Z -t main")
    assert win.zoomed is True
    run(server, "resize-pane -Z -t main")
    assert win.zoomed is False


def test_resize_pane_requires_direction(server):
    run(server, "split-window -h -t main")
    with pytest.raises(CommandError):
        run(server, "resize-pane -t main")


def test_rotate_window(server):
    run(server, "split-window -h -t main")
    win = server.sessions["main"].current
    a, b = win.panes()
    run(server, "rotate-window -t main")
    assert win.panes() == [b, a]


def test_next_layout(server):
    run(server, "split-window -h -t main")
    out = run(server, "next-layout -t main")
    assert out in ("even-horizontal", "even-vertical", "main-vertical", "tiled")


# ---------------------------------------------------------------- send-keys
def test_send_keys_keyspecs_and_literals(server):
    run(server, 'send-keys -t main "echo hola" Enter')
    pane = server.sessions["main"].current.active
    assert "".join(pane.written) == "echo hola\r"


def test_send_keys_literal_flag(server):
    run(server, "send-keys -l -t main Enter")
    pane = server.sessions["main"].current.active
    assert pane.written == ["Enter"]


def test_send_keys_ctrl(server):
    run(server, "send-keys -t main C-c")
    pane = server.sessions["main"].current.active
    assert pane.written == ["\x03"]


# ------------------------------------------------------------------ opciones
def test_set_show_options(server):
    run(server, "set -g status-style bg=red,fg=white")
    assert server.options.get("status-style") == "bg=red,fg=white"
    out = run(server, "show-options -g")
    assert "status-style bg=red,fg=white" in out


def test_set_session_option_inherits(server):
    run(server, "set -t main base-index 1")
    assert server.sessions["main"].options.get("base-index") == 1
    assert server.options.get("base-index") == 0


def test_set_invalid_value(server):
    with pytest.raises(CommandError):
        run(server, "set -g mode-keys dvorak")


# ------------------------------------------------------------------- buffers
def test_buffers_and_paste(server):
    run(server, 'set-buffer "linea1\nlinea2"')
    assert run(server, "show-buffer") == "linea1\nlinea2"
    run(server, "paste-buffer -t main")
    pane = server.sessions["main"].current.active
    assert pane.written == ["linea1\rlinea2"]  # \n -> \r
    out = run(server, "list-buffers")
    assert "buffer0000" in out


# ------------------------------------------------------------------- teclas
def test_bind_unbind_list_keys(server):
    run(server, "bind | split-window -h")
    assert server.bindings["|"] == ["split-window", "-h"]
    out = run(server, "list-keys")
    assert "split-window -h" in out
    run(server, "unbind |")
    assert "|" not in server.bindings


def test_bind_root_table(server):
    run(server, "bind -n F5 next-window")
    assert server.root_bindings["F5"] == ["next-window"]


# ------------------------------------------------------------------- varios
def test_display_message_p_expands(server):
    out = run(server, "display-message -p hola-#S")
    assert out == "hola-main"


def test_capture_pane(server):
    s = server.sessions["main"]
    out = run(server, "capture-pane -p -t main")
    assert "linea 00" in out


def test_target_window_specs(server):
    run(server, "new-window -t main")
    s = server.sessions["main"]
    _, win = target_window(server, None, {"t": "main:0"})
    assert win.index == 0
    _, win = target_window(server, None, {"t": ":1"})
    assert win.index == 1
    _, win = target_window(server, None, {"t": ":-"})
    assert win.index == 0
    with pytest.raises(CommandError):
        target_window(server, None, {"t": "main:9"})


def test_client_required_commands(server):
    for line in ("copy-mode", "command-prompt", "clock-mode",
                 "choose-window", "display-panes"):
        with pytest.raises(CommandError):
            run(server, line)


def test_confirm_before_sets_state(server):
    client = FakeClient()
    server.clients.append(client)
    server.attach_client(client, server.sessions["main"])
    run(server, 'confirm-before -p "matar? (y/n)" kill-pane', client=client)
    assert client.state.mode == "confirm"
    assert client.state.confirm_cmd == ["kill-pane"]
    assert "matar?" in client.state.confirm_prompt


def test_switch_client(server):
    run(server, "new-session -d -s otra")
    client = FakeClient()
    server.clients.append(client)
    server.attach_client(client, server.sessions["main"])
    run(server, "switch-client -t otra", client=client)
    assert client.session_name == "otra"
    run(server, "switch-client -n", client=client)
    assert client.session_name == "main"
