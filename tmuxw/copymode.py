"""Copy-mode: navegación del scrollback con selección (window-copy.c de tmux)."""
from .render import char_sgr


class CopyMode:
    """Vista congelada del historial+pantalla de un panel.

    handle_key() devuelve:
      None              -> seguir en copy-mode
      ("exit", None)    -> salir sin copiar
      ("copy", texto)   -> copiar y salir
      ("search", dir)   -> el cliente debe abrir un prompt de búsqueda ('/' o '?')
    """

    def __init__(self, pane, mode_keys: str = "emacs", scroll_up: int = 0):
        self.lines = pane.snapshot_lines()
        self.cols = pane.cols
        self.rows = pane.rows
        self.total = len(self.lines)
        self.top = max(0, self.total - self.rows)  # primera línea visible
        with pane.lock:
            self.cy = min(pane.screen.cursor.y, self.rows - 1)
            self.cx = min(pane.screen.cursor.x, self.cols - 1)
        self.anchor: tuple[int, int] | None = None  # (línea absoluta, col)
        self.mode_keys = mode_keys
        self.last_search: tuple[str, int] | None = None
        if scroll_up:
            self._move_view(-scroll_up)

    # ------------------------------------------------------------ helpers
    @property
    def abs_line(self) -> int:
        return self.top + self.cy

    def _line_text(self, idx: int) -> str:
        if 0 <= idx < self.total:
            return "".join(ch.data or " " for ch in self.lines[idx]).rstrip()
        return ""

    def _move_view(self, delta: int) -> None:
        self.top = max(0, min(self.total - self.rows, self.top + delta))

    def _move_cursor(self, dy: int, dx: int) -> None:
        if dx:
            self.cx = max(0, min(self.cols - 1, self.cx + dx))
        if dy:
            new_abs = max(0, min(self.total - 1, self.abs_line + dy))
            if new_abs < self.top:
                self.top = new_abs
            elif new_abs >= self.top + self.rows:
                self.top = new_abs - self.rows + 1
            self.cy = new_abs - self.top

    # ---------------------------------------------------------------- keys
    def handle_key(self, ks: str):
        vi = self.mode_keys == "vi"
        if ks in ("q", "Escape"):
            if self.anchor is not None and ks == "Escape":
                self.anchor = None
                return None
            return ("exit", None)
        if ks == "Up" or (vi and ks == "k"):
            self._move_cursor(-1, 0)
        elif ks == "Down" or (vi and ks == "j"):
            self._move_cursor(1, 0)
        elif ks == "Left" or (vi and ks == "h"):
            self._move_cursor(0, -1)
        elif ks == "Right" or (vi and ks == "l"):
            self._move_cursor(0, 1)
        elif ks == "PgUp":
            self._move_view(-self.rows)  # el cursor viaja con la vista (cy fijo)
        elif ks == "PgDn":
            self._move_view(self.rows)
        elif ks in ("C-u", "M-Up"):
            self._move_cursor(-(self.rows // 2), 0)
        elif ks in ("C-d", "M-Down"):
            self._move_cursor(self.rows // 2, 0)
        elif ks == "Home" or (vi and ks == "0"):
            self.cx = 0
        elif ks == "End" or (vi and ks == "$"):
            self.cx = max(0, len(self._line_text(self.abs_line)) - 1)
        elif vi and ks == "g":
            self._move_cursor(-self.total, 0)
        elif vi and ks == "G":
            self._move_cursor(self.total, 0)
        elif vi and ks == "w":
            self._word(1)
        elif vi and ks == "b":
            self._word(-1)
        elif ks == "Space" or (vi and ks == "v") or ks == "C-Space":
            self.anchor = (self.abs_line, self.cx)
        elif ks == "Enter" or (vi and ks == "y") or ks == "C-w":
            if self.anchor is None:
                return ("exit", None)
            return ("copy", self.selection_text())
        elif ks == "/" or (not vi and ks == "C-s"):
            return ("search", 1)
        elif ks == "?" or (not vi and ks == "C-r"):
            return ("search", -1)
        elif ks == "n":
            self.repeat_search(1)
        elif ks == "N":
            self.repeat_search(-1)
        return None

    def _word(self, direction: int) -> None:
        text = self._line_text(self.abs_line)
        x = self.cx
        if direction > 0:
            while x < len(text) and not text[x].isspace():
                x += 1
            while x < len(text) and text[x].isspace():
                x += 1
            if x >= len(text) and self.abs_line < self.total - 1:
                self._move_cursor(1, 0)
                self.cx = 0
                return
        else:
            while x > 0 and (x >= len(text) or x > 0 and text[x - 1].isspace()):
                x -= 1
            while x > 0 and not text[x - 1].isspace():
                x -= 1
        self.cx = max(0, min(self.cols - 1, x))

    # -------------------------------------------------------------- search
    def search(self, term: str, direction: int) -> bool:
        if not term:
            return False
        self.last_search = (term, direction)
        return self._do_search(term, direction)

    def repeat_search(self, sign: int) -> bool:
        if not self.last_search:
            return False
        term, direction = self.last_search
        return self._do_search(term, direction * sign)

    def _do_search(self, term: str, direction: int) -> bool:
        rng = (range(self.abs_line + 1, self.total) if direction > 0
               else range(self.abs_line - 1, -1, -1))
        for idx in rng:
            col = self._line_text(idx).find(term)
            if col >= 0:
                self._move_cursor(idx - self.abs_line, 0)
                self.cx = min(self.cols - 1, col)
                return True
        return False

    # ----------------------------------------------------------- selection
    def selection_text(self) -> str:
        if self.anchor is None:
            return ""
        a, b = sorted([self.anchor, (self.abs_line, self.cx)])
        out = []
        for idx in range(a[0], b[0] + 1):
            text = self._line_text(idx)
            start = a[1] if idx == a[0] else 0
            end = b[1] + 1 if idx == b[0] else len(text)
            out.append(text[start:end])
        return "\n".join(out)

    # ------------------------------------------------------------- render
    def visible_rows(self, w: int, h: int) -> list[list[tuple[str, str]]]:
        sel = None
        if self.anchor is not None:
            sel = tuple(sorted([self.anchor, (self.abs_line, self.cx)]))
        rows = []
        for ry in range(h):
            idx = self.top + ry
            row = []
            line = self.lines[idx] if 0 <= idx < self.total else []
            for rx in range(w):
                if rx < len(line):
                    ch = line[rx]
                    data, sgr = (ch.data, char_sgr(ch))
                else:
                    data, sgr = " ", ""
                if sel and _in_sel(sel, idx, rx):
                    sgr = (sgr + ";" if sgr else "") + "7"
                row.append((data, sgr))
            rows.append(row)
        return rows

    def cursor_in_view(self) -> tuple[int, int] | None:
        return (self.cx, self.cy)

    def indicator(self) -> str:
        return f"[{self.top + self.rows}/{self.total}]"


def _in_sel(sel, line: int, col: int) -> bool:
    (al, ac), (bl, bc) = sel
    if line < al or line > bl:
        return False
    if al == bl:
        return ac <= col <= bc
    if line == al:
        return col >= ac
    if line == bl:
        return col <= bc
    return True
