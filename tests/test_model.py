"""QA unitarias: tmuxw/model.py."""

from tmuxw.model import Session, Window

from .fakes import FakePane


def make_session(n_windows=3, base=0):
    s = Session("s", 80, 24)
    for i in range(n_windows):
        s.add_window(Window(s.next_free_index(base), FakePane()))
    return s


def test_next_free_index_base():
    s = Session("s")
    assert s.next_free_index(0) == 0
    assert s.next_free_index(1) == 1
    s.add_window(Window(1, FakePane()))
    assert s.next_free_index(1) == 2
    assert s.next_free_index(0) == 0


def test_add_select_last():
    s = make_session(3)
    assert s.current_index == 2
    assert s.last_index == 1
    s.select_window(0)
    assert (s.current_index, s.last_index) == (0, 2)
    # seleccionar la actual no toca last
    s.select_window(0)
    assert (s.current_index, s.last_index) == (0, 2)


def test_remove_current_goes_to_last():
    s = make_session(3)
    s.select_window(0)  # current=0, last=2
    s.remove_window(0)
    assert s.current_index == 2


def test_remove_current_without_last_picks_lower():
    s = make_session(3)  # current=2, last=1
    s.remove_window(1)  # borra la last
    assert s.current_index == 2
    s.remove_window(2)  # borra la actual sin last
    assert s.current_index == 0


def test_remove_all():
    s = make_session(1)
    s.remove_window(0)
    assert s.current is None
    assert s.windows == {}


def test_cycle_non_contiguous():
    s = Session("s")
    for i in (0, 3, 7):
        s.add_window(Window(i, FakePane()))
    s.select_window(0)
    s.cycle_window(1)
    assert s.current_index == 3
    s.cycle_window(1)
    assert s.current_index == 7
    s.cycle_window(1)  # envuelve
    assert s.current_index == 0
    s.cycle_window(-1)
    assert s.current_index == 7


def test_window_of_pane_and_all_panes():
    s = make_session(2)
    win = s.windows[1]
    pane = win.active
    assert s.window_of_pane(pane) is win
    assert pane in s.all_panes()
    assert s.window_of_pane(FakePane()) is None


def test_window_name_custom_overrides_title():
    p = FakePane(title="powershell")
    w = Window(0, p)
    assert w.name == "powershell"
    w.custom_name = "build"
    assert w.name == "build"


def test_window_set_active_tracks_last():
    p1, p2 = FakePane(), FakePane()
    w = Window(0, p1)
    w.layout.split(p1, "h", p2)
    w.set_active(p2)
    assert w.active is p2 and w.last_pane is p1
    w.set_active(p2)  # sin cambio
    assert w.last_pane is p1
