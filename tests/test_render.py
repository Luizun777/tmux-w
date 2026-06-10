"""QA unitarias: tmuxw/render.py."""
import time

from tmuxw.model import Session, Window
from tmuxw.options import Options
from tmuxw.render import Grid, _border_char, char_sgr, expand_format, render_frame

from .fakes import FakeClient, FakePane, make_char


def test_char_sgr_named_and_attrs():
    assert char_sgr(make_char("a")) == ""
    assert char_sgr(make_char("a", fg="red")) == "31"
    assert char_sgr(make_char("a", bg="green")) == "42"
    assert char_sgr(make_char("a", fg="brightblue")) == "94"
    assert "1" in char_sgr(make_char("a", bold=True))
    assert "7" in char_sgr(make_char("a", reverse=True))


def test_char_sgr_hex():
    sgr = char_sgr(make_char("a", fg="00ff7f"))
    assert sgr == "38;2;0;255;127"


def test_expand_format():
    s = Session("trabajo")
    w = Window(2, FakePane(title="shell"))
    s.add_window(w)
    out = expand_format("#S/#I/#W/##", s, w)
    assert out == "trabajo/2/shell/#"
    assert expand_format("%H") == time.strftime("%H")


def test_grid_to_ansi_positions():
    g = Grid(10, 2)
    g.put_text(0, 0, "hola", "31")
    out = g.to_ansi()
    assert "\x1b[1;1H" in out and "\x1b[2;1H" in out
    assert "\x1b[31m" in out and "hola" in out


def test_border_char_shapes():
    # cruz: borde en las 4 direcciones
    covered = set()
    assert _border_char(1, 1, covered, 3, 3) == "┼"
    # vertical: solo arriba/abajo son borde
    covered = {(0, 1), (2, 1)}
    assert _border_char(1, 1, covered, 3, 3) == "│"
    # horizontal: solo izquierda/derecha son borde
    covered = {(1, 0), (1, 2)}
    assert _border_char(1, 1, covered, 3, 3) == "─"


def make_world(w=40, h=12):
    opts = Options()
    session = Session("s", w, h, options=Options(parent=opts))
    pane = FakePane(cols=w, rows=h - 1, lines=["contenido-visible"] + [""] * (h - 2))
    session.add_window(Window(0, pane))
    client = FakeClient(w, h)
    client.session_name = "s"
    client.attached = True
    return session, client


def test_render_frame_basic():
    session, client = make_world()
    frame = render_frame(session, client, client.state)
    assert frame.startswith("\x1b[?2026h")
    assert frame.endswith("\x1b[?2026l")
    assert "contenido-visible" in frame
    assert "[s]" in frame          # status-left
    assert "0:" in frame           # lista de ventanas


def test_render_frame_status_off():
    session, client = make_world()
    session.options.set("status", "off")
    frame = render_frame(session, client, client.state)
    assert "[s]" not in frame


def test_render_frame_split_has_border():
    session, client = make_world()
    win = session.current
    p2 = FakePane(cols=19, rows=11)
    win.layout.split(win.active, "h", p2)
    frame = render_frame(session, client, client.state)
    assert "│" in frame


def test_render_frame_zoom_no_border():
    session, client = make_world()
    win = session.current
    p2 = FakePane(cols=19, rows=11)
    win.layout.split(win.active, "h", p2)
    win.zoomed = True
    frame = render_frame(session, client, client.state)
    assert "│" not in frame


def test_render_frame_message():
    session, client = make_world()
    client.state.message = "AVISO-QA"
    client.state.message_until = time.time() + 10
    frame = render_frame(session, client, client.state)
    assert "AVISO-QA" in frame


def test_render_frame_prompt_and_cursor():
    session, client = make_world()
    st = client.state
    st.mode = "prompt"
    st.prompt_prefix = ":"
    st.prompt_prefix_len = 1
    st.prompt_buffer = "split"
    st.prompt_cursor = 5
    frame = render_frame(session, client, st)
    assert ":split" in frame
    assert "\x1b[?25h" in frame  # cursor visible en el prompt


def test_render_frame_confirm():
    session, client = make_world()
    st = client.state
    st.mode = "confirm"
    st.confirm_prompt = "kill-pane? (y/n)"
    frame = render_frame(session, client, st)
    assert "kill-pane? (y/n)" in frame


def test_render_frame_clock():
    session, client = make_world()
    client.state.mode = "clock"
    client.state.clock = True
    frame = render_frame(session, client, client.state)
    assert "\x1b[?2026h" in frame  # no crash y frame válido


def test_render_frame_page_overlay():
    session, client = make_world()
    st = client.state
    st.mode = "page"
    st.page_lines = [f"linea-ayuda-{i}" for i in range(30)]
    st.page_offset = 0
    frame = render_frame(session, client, st)
    assert "linea-ayuda-0" in frame
    assert "q:salir" in frame


def test_render_frame_chooser():
    session, client = make_world()
    st = client.state
    st.mode = "choose"
    st.chooser = [("uno", ["select-window", "-t", ":0"]), ("dos", ["kill-server"])]
    st.chooser_idx = 1
    st.chooser_title = "Ventanas"
    frame = render_frame(session, client, st)
    assert "Ventanas" in frame and "(0) uno" in frame and "(1) dos" in frame
