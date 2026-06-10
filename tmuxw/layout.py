"""Árbol de splits de una ventana (equivalente a layout-*.c de tmux).

kind 'h': los hijos quedan lado a lado (split-window -h).
kind 'v': los hijos quedan uno encima del otro (split-window -v).
Entre hermanos siempre hay 1 celda de borde.
"""
from collections import namedtuple

Rect = namedtuple("Rect", "x y w h")

MIN_W = 2
MIN_H = 1


class Leaf:
    __slots__ = ("pane", "parent")

    def __init__(self, pane, parent=None):
        self.pane = pane
        self.parent = parent


class Split:
    __slots__ = ("kind", "children", "ratio", "parent")

    def __init__(self, kind, a, b, ratio=0.5, parent=None):
        assert kind in ("h", "v")
        self.kind = kind
        self.children = [a, b]
        self.ratio = ratio
        self.parent = parent
        a.parent = self
        b.parent = self


class Layout:
    def __init__(self, pane):
        self.root = Leaf(pane)

    # ------------------------------------------------------------- queries
    def panes(self) -> list:
        out = []

        def walk(node):
            if isinstance(node, Leaf):
                out.append(node.pane)
            else:
                for c in node.children:
                    walk(c)

        walk(self.root)
        return out

    def _find_leaf(self, pane):
        def walk(node):
            if isinstance(node, Leaf):
                return node if node.pane is pane else None
            for c in node.children:
                found = walk(c)
                if found:
                    return found
            return None

        leaf = walk(self.root)
        if leaf is None:
            raise KeyError(f"pane {pane!r} no está en el layout")
        return leaf

    def node_rects(self, w: int, h: int):
        """Genera (nodo, Rect) de todo el árbol dentro de un área w×h."""

        def walk(node, rect):
            yield node, rect
            if isinstance(node, Split):
                x, y, rw, rh = rect
                if node.kind == "h":
                    left = max(MIN_W, min(rw - 1 - MIN_W, round((rw - 1) * node.ratio)))
                    yield from walk(node.children[0], Rect(x, y, left, rh))
                    yield from walk(node.children[1], Rect(x + left + 1, y, rw - left - 1, rh))
                else:
                    top = max(MIN_H, min(rh - 1 - MIN_H, round((rh - 1) * node.ratio)))
                    yield from walk(node.children[0], Rect(x, y, rw, top))
                    yield from walk(node.children[1], Rect(x, y + top + 1, rw, rh - top - 1))

        yield from walk(self.root, Rect(0, 0, max(w, MIN_W), max(h, MIN_H)))

    def compute(self, w: int, h: int) -> dict:
        """pane -> Rect dentro de un área w×h (0,0 arriba-izquierda)."""
        return {node.pane: rect for node, rect in self.node_rects(w, h)
                if isinstance(node, Leaf)}

    def can_split(self, pane, kind, w, h) -> bool:
        rect = self.compute(w, h)[pane]
        return rect.w >= 2 * MIN_W + 1 if kind == "h" else rect.h >= 2 * MIN_H + 1

    # ----------------------------------------------------------- mutations
    def split(self, pane, kind, new_pane, percent: int | None = None) -> None:
        """Divide el leaf de `pane`; el nuevo panel queda a la derecha/abajo."""
        leaf = self._find_leaf(pane)
        ratio = 1 - (percent / 100.0) if percent else 0.5
        ratio = min(0.9, max(0.1, ratio))
        parent = leaf.parent
        new_leaf = Leaf(new_pane)
        node = Split(kind, leaf, new_leaf, ratio)
        if parent is None:
            self.root = node
            node.parent = None
        else:
            parent.children[parent.children.index(leaf)] = node
            node.parent = parent

    def remove(self, pane) -> None:
        """Quita el leaf y colapsa el split padre dejando al hermano en su lugar."""
        leaf = self._find_leaf(pane)
        parent = leaf.parent
        if parent is None:
            raise ValueError("no se puede quitar el último panel")
        sibling = parent.children[1 - parent.children.index(leaf)]
        grand = parent.parent
        sibling.parent = grand
        if grand is None:
            self.root = sibling
        else:
            grand.children[grand.children.index(parent)] = sibling

    def swap(self, pane_a, pane_b) -> None:
        la, lb = self._find_leaf(pane_a), self._find_leaf(pane_b)
        la.pane, lb.pane = lb.pane, la.pane

    def resize(self, pane, direction: str, amount: int, w: int, h: int) -> bool:
        """Mueve el borde del panel en `direction` ('L','R','U','D') `amount` celdas."""
        kind = "h" if direction in ("L", "R") else "v"
        node = self._find_leaf(pane)
        # ancestro split del tipo adecuado más cercano
        child = node
        parent = node.parent
        while parent is not None and parent.kind != kind:
            child = parent
            parent = parent.parent
        if parent is None:
            return False
        # tamaño del eje del split padre
        span = self._node_span(parent, w, h, kind)
        if span <= 2:
            return False
        idx = parent.children.index(child)
        # 'R'/'D' agrandan el primer hijo si somos el primero, etc.
        grow_first = (direction in ("R", "D")) == (idx == 0)
        delta = (amount / span) * (1 if grow_first else -1)
        parent.ratio = min(0.95, max(0.05, parent.ratio + delta))
        return True

    def _node_span(self, target, w, h, kind):
        rect = self.node_rect(target, w, h)
        if rect is None:
            return w if kind == "h" else h
        return rect.w if kind == "h" else rect.h

    def node_rect(self, target, w: int, h: int):
        """Rect de un nodo concreto (Leaf o Split), o None si no está en el árbol."""
        for node, rect in self.node_rects(w, h):
            if node is target:
                return rect
        return None

    # -------------------------------------------------------------- ratón
    def split_at(self, x: int, y: int, w: int, h: int):
        """Split cuyo divisor pasa por la celda (x, y), o None si no hay borde ahí."""
        for node, rect in self.node_rects(w, h):
            if not isinstance(node, Split):
                continue
            rx, ry, rw, rh = rect
            if node.kind == "h":
                left = max(MIN_W, min(rw - 1 - MIN_W, round((rw - 1) * node.ratio)))
                if x == rx + left and ry <= y < ry + rh:
                    return node
            else:
                top = max(MIN_H, min(rh - 1 - MIN_H, round((rh - 1) * node.ratio)))
                if y == ry + top and rx <= x < rx + rw:
                    return node
        return None

    def drag_divider(self, node, x: int, y: int, w: int, h: int) -> bool:
        """Coloca el divisor del split `node` en la celda del ratón (x, y)."""
        rect = self.node_rect(node, w, h)
        if rect is None:
            return False
        if node.kind == "h":
            if rect.w < 2 * MIN_W + 1:
                return False
            left = max(MIN_W, min(rect.w - 1 - MIN_W, x - rect.x))
            node.ratio = left / (rect.w - 1)
        else:
            if rect.h < 2 * MIN_H + 1:
                return False
            top = max(MIN_H, min(rect.h - 1 - MIN_H, y - rect.y))
            node.ratio = top / (rect.h - 1)
        return True

    # ----------------------------------------------------------- direction
    def neighbor(self, pane, direction: str, w: int, h: int):
        """Panel adyacente geométricamente en 'L','R','U','D', o None."""
        rects = self.compute(w, h)
        cur = rects[pane]
        best, best_overlap = None, -1
        for other, r in rects.items():
            if other is pane:
                continue
            if direction == "L":
                adjacent = r.x + r.w == cur.x - 1
                overlap = _overlap(r.y, r.h, cur.y, cur.h)
            elif direction == "R":
                adjacent = cur.x + cur.w == r.x - 1
                overlap = _overlap(r.y, r.h, cur.y, cur.h)
            elif direction == "U":
                adjacent = r.y + r.h == cur.y - 1
                overlap = _overlap(r.x, r.w, cur.x, cur.w)
            else:  # D
                adjacent = cur.y + cur.h == r.y - 1
                overlap = _overlap(r.x, r.w, cur.x, cur.w)
            if adjacent and overlap > best_overlap:
                best, best_overlap = other, overlap
        return best

    # ------------------------------------------------------------- presets
    PRESETS = ("even-horizontal", "even-vertical", "main-vertical", "tiled")

    def apply_preset(self, name: str, panes: list) -> None:
        if name not in self.PRESETS:
            raise ValueError(f"layout desconocido: {name}")
        if len(panes) == 1:
            self.root = Leaf(panes[0])
            return
        if name == "even-horizontal":
            self.root = _balanced(panes, "h")
        elif name == "even-vertical":
            self.root = _balanced(panes, "v")
        elif name == "main-vertical":
            main = Leaf(panes[0])
            rest = _balanced(panes[1:], "v")
            self.root = Split("h", main, rest, ratio=0.6)
        else:  # tiled
            import math
            ncols = math.ceil(math.sqrt(len(panes)))
            rows = [panes[i:i + ncols] for i in range(0, len(panes), ncols)]
            row_nodes = [_balanced(r, "h") for r in rows]
            self.root = _balanced_nodes(row_nodes, "v")
        self.root.parent = None


def _overlap(a0, alen, b0, blen) -> int:
    return max(0, min(a0 + alen, b0 + blen) - max(a0, b0))


def _balanced(panes: list, kind: str):
    return _balanced_nodes([Leaf(p) for p in panes], kind)


def _balanced_nodes(nodes: list, kind: str):
    if len(nodes) == 1:
        return nodes[0]
    mid = len(nodes) // 2
    left = _balanced_nodes(nodes[:mid], kind)
    right = _balanced_nodes(nodes[mid:], kind)
    return Split(kind, left, right, ratio=mid / len(nodes))
