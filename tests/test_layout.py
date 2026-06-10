"""QA unitarias: tmuxw/layout.py."""
import pytest

from tmuxw.layout import Layout, Rect

W, H = 80, 23


def cells(rect):
    return {(x, y) for x in range(rect.x, rect.x + rect.w)
            for y in range(rect.y, rect.y + rect.h)}


def assert_tessellates(layout, w=W, h=H):
    """Los rects no se solapan y junto con los bordes cubren el área exacta."""
    rects = layout.compute(w, h)
    covered = set()
    for r in rects.values():
        c = cells(r)
        assert not (covered & c), "rects solapados"
        covered |= c
    total = {(x, y) for x in range(w) for y in range(h)}
    border = total - covered
    # cada panel ocupa al menos el mínimo
    for r in rects.values():
        assert r.w >= 2 and r.h >= 1
    # los bordes son exactamente las celdas no cubiertas
    assert covered | border == total
    return rects, border


def test_single_pane_full_area():
    lay = Layout("A")
    rects, border = assert_tessellates(lay)
    assert rects["A"] == Rect(0, 0, W, H)
    assert border == set()


def test_split_h_order_and_border():
    lay = Layout("A")
    lay.split("A", "h", "B")
    assert lay.panes() == ["A", "B"]
    rects, border = assert_tessellates(lay)
    assert rects["A"].x == 0
    assert rects["B"].x == rects["A"].w + 1  # 1 columna de borde
    assert len(border) == H


def test_split_v_order_and_border():
    lay = Layout("A")
    lay.split("A", "v", "B")
    rects, border = assert_tessellates(lay)
    assert rects["A"].y == 0
    assert rects["B"].y == rects["A"].h + 1
    assert len(border) == W


def test_split_percent():
    lay = Layout("A")
    lay.split("A", "h", "B", percent=25)  # B se queda con ~25%
    rects, _ = assert_tessellates(lay)
    assert rects["B"].w < rects["A"].w


def test_nested_splits_tessellate():
    lay = Layout("A")
    lay.split("A", "h", "B")
    lay.split("A", "v", "C")
    lay.split("B", "v", "D")
    assert set(lay.panes()) == {"A", "B", "C", "D"}
    assert_tessellates(lay)


def test_remove_collapses():
    lay = Layout("A")
    lay.split("A", "h", "B")
    lay.split("B", "v", "C")
    lay.remove("C")
    assert lay.panes() == ["A", "B"]
    rects, _ = assert_tessellates(lay)
    assert rects["B"].h == H  # B recupera toda la altura


def test_remove_last_pane_raises():
    lay = Layout("A")
    with pytest.raises(ValueError):
        lay.remove("A")


def test_remove_root_child_promotes_sibling():
    lay = Layout("A")
    lay.split("A", "h", "B")
    lay.remove("A")
    assert lay.panes() == ["B"]
    rects, _ = assert_tessellates(lay)
    assert rects["B"] == Rect(0, 0, W, H)


def test_swap():
    lay = Layout("A")
    lay.split("A", "h", "B")
    ra = lay.compute(W, H)["A"]
    lay.swap("A", "B")
    assert lay.compute(W, H)["B"] == ra


def grid_2x2():
    lay = Layout("A")
    lay.split("A", "h", "B")
    lay.split("A", "v", "C")
    lay.split("B", "v", "D")
    return lay


def test_neighbor_directions():
    lay = grid_2x2()
    assert lay.neighbor("A", "R", W, H) == "B"
    assert lay.neighbor("A", "D", W, H) == "C"
    assert lay.neighbor("B", "L", W, H) == "A"
    assert lay.neighbor("B", "D", W, H) == "D"
    assert lay.neighbor("D", "U", W, H) == "B"
    assert lay.neighbor("D", "L", W, H) == "C"
    assert lay.neighbor("A", "L", W, H) is None
    assert lay.neighbor("A", "U", W, H) is None


def test_resize_changes_ratio():
    lay = Layout("A")
    lay.split("A", "h", "B")
    before = lay.compute(W, H)["A"].w
    assert lay.resize("A", "R", 5, W, H)
    after = lay.compute(W, H)["A"].w
    assert after > before
    assert_tessellates(lay)


def test_resize_clamps():
    lay = Layout("A")
    lay.split("A", "h", "B")
    for _ in range(50):
        lay.resize("A", "R", 10, W, H)
    rects, _ = assert_tessellates(lay)
    assert rects["B"].w >= 2


def test_resize_no_matching_ancestor():
    lay = Layout("A")
    lay.split("A", "h", "B")
    # no hay split vertical: redimensionar U/D no hace nada
    assert lay.resize("A", "U", 3, W, H) is False


@pytest.mark.parametrize("preset", Layout.PRESETS)
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_presets_tessellate(preset, n):
    panes = [chr(ord("A") + i) for i in range(n)]
    lay = Layout(panes[0])
    for p in panes[1:]:
        lay.split(panes[0], "h" if len(lay.panes()) % 2 else "v", p)
    lay.apply_preset(preset, panes)
    assert set(lay.panes()) == set(panes)
    assert_tessellates(lay, 120, 40)


def test_can_split_minimal_area():
    lay = Layout("A")
    assert lay.can_split("A", "h", 5, 5)
    assert not lay.can_split("A", "h", 4, 5)
    assert lay.can_split("A", "v", 5, 3)
    assert not lay.can_split("A", "v", 5, 2)
