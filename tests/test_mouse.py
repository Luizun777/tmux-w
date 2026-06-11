"""QA unitarias: soporte de ratón (click, arrastre de bordes, rueda) y
bindings repetibles (bind -r / repeat-time)."""

import time

import pytest

from tmuxw.commands import execute_command, execute_line
from tmuxw.keys import decode_key_event, decode_mouse_event, keyspec_to_vt
from tmuxw.layout import Layout

from .fakes import FakeClient, make_fake_server


# ------------------------------------------------------- decode_key_event
def test_decode_plain_char():
    assert decode_key_event(True, 0x41, "a", 0) == "a"


def test_decode_keyup_ignored():
    assert decode_key_event(False, 0x41, "a", 0) is None


def test_decode_modifier_alone_ignored():
    assert decode_key_event(True, 0x11, "", 0x0008) is None  # Ctrl solo


def test_decode_nav_keys_with_modifiers():
    assert decode_key_event(True, 0x25, "", 0) == "Left"
    assert decode_key_event(True, 0x25, "", 0x0008) == "C-Left"  # Ctrl izq
    assert decode_key_event(True, 0x25, "", 0x0004) == "C-Left"  # Ctrl der
    assert decode_key_event(True, 0x26, "", 0x0002) == "M-Up"  # Alt izq
    assert decode_key_event(True, 0x28, "", 0x0008 | 0x0002) == "C-M-Down"


def test_decode_function_keys():
    assert decode_key_event(True, 0x74, "", 0) == "F5"
    assert decode_key_event(True, 0x7B, "", 0) == "F12"


def test_decode_ctrl_letter():
    assert decode_key_event(True, 0x41, "\x01", 0x0008) == "C-a"


def test_decode_alt_char():
    assert decode_key_event(True, 0x58, "x", 0x0002) == "M-x"


def test_decode_altgr_produces_literal_char():
    # AltGr = Alt derecho + Ctrl izquierdo; AltGr+2 en teclado español = @
    assert decode_key_event(True, 0x32, "@", 0x0001 | 0x0008) == "@"


def test_decode_enter_tab_escape():
    assert decode_key_event(True, 0x0D, "\r", 0) == "Enter"
    assert decode_key_event(True, 0x09, "\t", 0) == "Tab"
    assert decode_key_event(True, 0x1B, "\x1b", 0) == "Escape"


def test_decode_ctrl_space():
    assert decode_key_event(True, 0x20, " ", 0x0008) == "C-Space"
    assert decode_key_event(True, 0x20, "\x00", 0x0008) == "C-Space"


# ----------------------------------------------------- decode_mouse_event
def test_mouse_press_release():
    ev, st = decode_mouse_event(0, 0x1, 10, 5, 0)
    assert ev == {"e": "down", "b": "left", "x": 10, "y": 5}
    assert st == 0x1
    ev, st = decode_mouse_event(0, 0x0, 11, 5, st)
    assert ev == {"e": "up", "b": "left", "x": 11, "y": 5}
    assert st == 0


def test_mouse_right_button():
    ev, _ = decode_mouse_event(0, 0x2, 1, 1, 0)
    assert ev["e"] == "down" and ev["b"] == "right"


def test_mouse_drag_and_hover():
    ev, _ = decode_mouse_event(0x1, 0x1, 12, 6, 0x1)  # move con botón
    assert ev == {"e": "drag", "b": "left", "x": 12, "y": 6}
    ev, _ = decode_mouse_event(0x1, 0x0, 12, 6, 0)  # move sin botón
    assert ev is None


def test_mouse_wheel():
    ev, _ = decode_mouse_event(0x4, 0x00780000, 3, 3, 0)  # delta +120
    assert ev["e"] == "wheel" and ev["b"] == "wheel-up"
    ev, _ = decode_mouse_event(0x4, 0xFF880000, 3, 3, 0)  # delta -120
    assert ev["b"] == "wheel-down"


# ------------------------------------------------ layout: bordes y arrastre
def test_split_at_finds_border():
    lay = Layout("A")
    lay.split("A", "h", "B")
    border_x = lay.compute(80, 23)["A"].w
    node = lay.split_at(border_x, 5, 80, 23)
    assert node is lay.root
    assert lay.split_at(border_x - 1, 5, 80, 23) is None  # dentro de A
    assert lay.split_at(border_x + 1, 5, 80, 23) is None  # dentro de B


def test_split_at_vertical():
    lay = Layout("A")
    lay.split("A", "v", "B")
    border_y = lay.compute(80, 23)["A"].h
    assert lay.split_at(10, border_y, 80, 23) is lay.root
    assert lay.split_at(10, border_y - 1, 80, 23) is None


def test_drag_divider_moves_border():
    lay = Layout("A")
    lay.split("A", "h", "B")
    assert lay.drag_divider(lay.root, 20, 5, 80, 23)
    rects = lay.compute(80, 23)
    assert rects["A"].w == 20
    assert rects["B"].x == 21


def test_drag_divider_clamps_to_minimums():
    lay = Layout("A")
    lay.split("A", "v", "B")
    assert lay.drag_divider(lay.root, 0, 0, 80, 23)
    assert lay.compute(80, 23)["A"].h == 1  # MIN_H
    assert lay.drag_divider(lay.root, 0, 200, 80, 23)
    assert lay.compute(80, 23)["B"].h == 1


# -------------------------------------------------------------- fixtures
@pytest.fixture
def server():
    srv = make_fake_server()
    execute_command(srv, None, ["new-session", "-d", "-s", "main"])
    return srv


@pytest.fixture
def client(server):
    c = FakeClient()
    server.attach_client(c, server.sessions["main"])
    return c


def mouse(server, client, e, b, x, y):
    server.handle_mouse(client, {"e": e, "b": b, "x": x, "y": y})


# --------------------------------------------------- click: foco de panel
def test_click_selects_pane(server, client):
    execute_line(server, client, "split-window -h")
    session = server.sessions["main"]
    win = session.current
    first, second = win.panes()
    assert win.active is second  # split deja activo al nuevo
    mouse(server, client, "down", "left", 2, 2)  # click en el panel izquierdo
    assert win.active is first
    rects = win.layout.compute(client.width, client.height - 1)
    r = rects[second]
    mouse(server, client, "down", "left", r.x + 1, r.y + 1)
    assert win.active is second


def test_click_ignored_when_mouse_off(server, client):
    execute_line(server, client, "split-window -h")
    session = server.sessions["main"]
    win = session.current
    session.options.set("mouse", False)
    active = win.active
    mouse(server, client, "down", "left", 2, 2)
    assert win.active is active


# ------------------------------------------------ click: status line
def test_status_click_selects_window(server, client):
    from tmuxw.render import status_window_ranges

    execute_line(server, client, "new-window")
    session = server.sessions["main"]
    assert session.current_index == 1
    ranges = status_window_ranges(session, client.width)
    start, end, idx = next(r for r in ranges if r[2] == 0)
    mouse(server, client, "down", "left", start, client.height - 1)
    assert session.current_index == 0


def test_status_wheel_cycles_windows(server, client):
    execute_line(server, client, "new-window")
    session = server.sessions["main"]
    mouse(server, client, "wheel", "wheel-down", 0, client.height - 1)
    assert session.current_index == 0
    mouse(server, client, "wheel", "wheel-down", 0, client.height - 1)
    assert session.current_index == 1


# ------------------------------------------------ arrastre de bordes
def test_border_drag_resizes(server, client):
    execute_line(server, client, "split-window -h")
    session = server.sessions["main"]
    win = session.current
    body_h = client.height - 1
    first = win.panes()[0]
    border_x = win.layout.compute(client.width, body_h)[first].w
    mouse(server, client, "down", "left", border_x, 5)
    assert client.state.drag is not None
    mouse(server, client, "drag", "left", 30, 5)
    assert win.layout.compute(client.width, body_h)[first].w == 30
    mouse(server, client, "drag", "left", 25, 8)  # sigue aunque cambie y
    assert win.layout.compute(client.width, body_h)[first].w == 25
    mouse(server, client, "up", "left", 25, 8)
    assert client.state.drag is None


def test_drag_without_press_does_nothing(server, client):
    execute_line(server, client, "split-window -h")
    session = server.sessions["main"]
    win = session.current
    first = win.panes()[0]
    before = win.layout.compute(client.width, client.height - 1)[first].w
    mouse(server, client, "drag", "left", 10, 5)
    assert win.layout.compute(client.width, client.height - 1)[first].w == before


# ------------------------------------------------ rueda: copy-mode
def test_wheel_up_enters_copy_mode(server, client):
    mouse(server, client, "wheel", "wheel-up", 5, 5)
    assert client.state.mode == "copy"
    assert client.state.copy is not None
    # rueda abajo hasta el final: sale de copy-mode (sin selección)
    mouse(server, client, "wheel", "wheel-down", 5, 5)
    assert client.state.mode == "normal"
    assert client.state.copy is None


# ------------------------------------------------ bindings repetibles
def active_ratio(server):
    return server.sessions["main"].current.layout.root.ratio


def test_resize_repeats_without_prefix(server, client):
    execute_line(server, client, "split-window -h")
    st = client.state
    server.handle_key(client, "C-b")
    assert st.mode == "prefix"
    server.handle_key(client, "C-Left")
    r1 = active_ratio(server)
    assert r1 != 0.5
    assert st.mode == "prefix" and st.prefix_repeat  # repeat armado
    server.handle_key(client, "C-Left")  # sin volver a pulsar C-b
    assert active_ratio(server) != r1
    assert st.mode == "prefix" and st.prefix_repeat


def test_repeat_state_ends_with_other_key(server, client):
    execute_line(server, client, "split-window -h")
    st = client.state
    win = server.sessions["main"].current
    server.handle_key(client, "C-b")
    server.handle_key(client, "C-Left")
    assert st.prefix_repeat
    server.handle_key(client, "x")  # no repetible: va al panel, sin confirm
    assert st.mode == "normal"
    assert win.active.written[-1] == "x"
    assert win in server.sessions["main"].windows.values()  # no se mató nada


def test_repeat_state_expires(server, client):
    execute_line(server, client, "split-window -h")
    st = client.state
    win = server.sessions["main"].current
    server.handle_key(client, "C-b")
    server.handle_key(client, "C-Left")
    r1 = active_ratio(server)
    st.prefix_until = time.time() - 1  # caducado
    server.handle_key(client, "C-Left")
    assert active_ratio(server) == r1  # ya no redimensiona
    assert win.active.written[-1] == keyspec_to_vt("C-Left")  # fue al panel


def test_non_repeat_binding_does_not_arm(server, client):
    st = client.state
    server.handle_key(client, "C-b")
    server.handle_key(client, "c")  # new-window: no repetible
    assert st.mode == "normal"
    assert not st.prefix_repeat


def test_prefix2_acts_as_prefix(server, client):
    execute_line(server, client, "set -g prefix C-a")
    execute_line(server, client, "set -g prefix2 C-b")
    st = client.state
    server.handle_key(client, "C-b")  # prefijo secundario
    assert st.mode == "prefix"
    server.handle_key(client, "c")  # new-window
    assert len(server.sessions["main"].windows) == 2


def test_setw_is_set_option_alias(server, client):
    execute_line(server, client, "setw -g pane-base-index 1")  # no debe fallar
    from tmuxw.commands import resolve

    assert resolve("setw") is resolve("set-option")
    assert resolve("set-window-option") is resolve("set-option")


def test_bind_r_flag_and_unbind(server, client):
    execute_line(server, client, "bind-key -r h resize-pane -L")
    assert "h" in server.repeat_bindings
    execute_line(server, client, "bind-key h resize-pane -L")  # sin -r: lo quita
    assert "h" not in server.repeat_bindings
    execute_line(server, client, "bind-key -r h resize-pane -L")
    execute_line(server, client, "unbind-key h")
    assert "h" not in server.repeat_bindings
