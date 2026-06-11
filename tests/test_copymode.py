"""QA unitarias: tmuxw/copymode.py."""

from tmuxw.copymode import CopyMode

from .fakes import FakePane


def make_copy(n_lines=30, rows=10, cols=40, mode="emacs"):
    lines = [f"linea {i:02d}" for i in range(n_lines)]
    pane = FakePane(cols=cols, rows=rows, lines=lines)
    return CopyMode(pane, mode_keys=mode)


def test_initial_position_bottom():
    cm = make_copy()
    assert cm.total == 30
    assert cm.top == 20  # últimas 10 líneas visibles


def test_cursor_movement_and_scroll():
    cm = make_copy()
    start = cm.abs_line
    cm.handle_key("Up")
    assert cm.abs_line == start - 1
    # subir más allá de la vista desplaza top
    for _ in range(40):
        cm.handle_key("Up")
    assert cm.abs_line == 0
    assert cm.top == 0
    cm.handle_key("Up")  # clamp
    assert cm.abs_line == 0


def test_vi_keys():
    cm = make_copy(mode="vi")
    y0 = cm.abs_line
    cm.handle_key("k")
    assert cm.abs_line == y0 - 1
    cm.handle_key("j")
    assert cm.abs_line == y0
    cm.handle_key("l")
    assert cm.cx == 1
    cm.handle_key("h")
    assert cm.cx == 0
    cm.handle_key("g")
    assert cm.abs_line == 0
    cm.handle_key("G")
    assert cm.abs_line == cm.total - 1
    cm.handle_key("$")
    assert cm.cx == len("linea 29") - 1
    cm.handle_key("0")
    assert cm.cx == 0


def test_pgup_clamps():
    cm = make_copy()
    cm.handle_key("PgUp")
    cm.handle_key("PgUp")
    cm.handle_key("PgUp")
    assert cm.top == 0


def test_exit_keys():
    assert make_copy().handle_key("q") == ("exit", None)
    assert make_copy().handle_key("Escape") == ("exit", None)


def test_escape_cancels_selection_first():
    cm = make_copy()
    cm.handle_key("Space")
    assert cm.anchor is not None
    assert cm.handle_key("Escape") is None
    assert cm.anchor is None
    assert cm.handle_key("Escape") == ("exit", None)


def test_select_and_copy_single_line():
    cm = make_copy()
    cm.handle_key("Home")
    cm.handle_key("Space")
    for _ in range(4):
        cm.handle_key("Right")
    action, text = cm.handle_key("Enter")
    assert action == "copy"
    assert text == "linea"


def test_select_multiline():
    cm = make_copy()
    cm.handle_key("Up")
    cm.handle_key("Home")
    cm.handle_key("Space")
    cm.handle_key("Down")
    cm.handle_key("End")
    action, text = cm.handle_key("Enter")
    assert action == "copy"
    assert text.splitlines() == ["linea 28", "linea 29"]


def test_select_reverse_charwise():
    # selección hacia atrás: el texto sale en orden normal, recortado por columnas
    cm = make_copy()
    cm.handle_key("Home")
    cm.handle_key("Space")  # ancla en (29, 0)
    cm.handle_key("Up")
    cm.handle_key("End")  # cursor en (28, fin)
    action, text = cm.handle_key("Enter")
    assert action == "copy"
    lines = text.splitlines()
    assert lines[0].endswith("8")  # cola de "linea 28" desde la columna del cursor
    assert lines[1] == "l"  # cabeza de "linea 29" hasta el ancla


def test_enter_without_selection_exits():
    cm = make_copy()
    assert cm.handle_key("Enter") == ("exit", None)


def test_copy_vi_y():
    cm = make_copy(mode="vi")
    cm.handle_key("0")
    cm.handle_key("v")
    cm.handle_key("$")
    action, text = cm.handle_key("y")
    assert action == "copy" and text == "linea 29"


def test_search_request_and_execution():
    cm = make_copy()
    assert cm.handle_key("/") == ("search", 1)
    assert cm.handle_key("?") == ("search", -1)
    assert cm.search("linea 05", -1) is True
    assert cm.abs_line == 5
    assert cm.search("no-existe", -1) is False


def test_repeat_search():
    lines = ["aguja"] + ["paja"] * 10 + ["aguja"] + ["paja"] * 10
    pane = FakePane(cols=20, rows=5, lines=lines)
    cm = CopyMode(pane)
    cm.search("aguja", -1)
    assert cm.abs_line == 11
    cm.repeat_search(1)  # otra vez hacia atrás
    assert cm.abs_line == 0
    cm.repeat_search(-1)  # invertida: hacia adelante
    assert cm.abs_line == 11


def test_visible_rows_marks_selection():
    cm = make_copy()
    cm.handle_key("Home")
    cm.handle_key("Space")
    cm.handle_key("Right")
    rows = cm.visible_rows(40, 10)
    assert len(rows) == 10 and len(rows[0]) == 40
    sel_row = rows[cm.cy]
    assert "7" in sel_row[0][1]  # SGR reverse en la selección
    assert "7" not in rows[0][5][1] or cm.cy == 0


def test_indicator():
    cm = make_copy()
    assert cm.indicator() == "[30/30]"
    cm.handle_key("PgUp")
    assert cm.indicator() == "[20/30]"


def test_word_motion_vi():
    pane = FakePane(cols=40, rows=5, lines=["uno dos tres", "", "", "", ""])
    cm = CopyMode(pane, mode_keys="vi")
    cm.cy, cm.cx = 0, 0
    cm.top = 0
    cm.handle_key("w")
    assert cm.cx == 4
    cm.handle_key("w")
    assert cm.cx == 8
    cm.handle_key("b")
    assert cm.cx == 4
