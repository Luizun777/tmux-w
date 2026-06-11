"""Composición del frame ANSI: paneles + bordes + status line (screen-redraw.c de tmux)."""
import socket
import time

from .layout import Rect
from .options import parse_style, style_to_sgr

NAMED_FG = {
    "black": 30, "red": 31, "green": 32, "brown": 33, "yellow": 33, "blue": 34,
    "magenta": 35, "cyan": 36, "white": 37, "default": 39,
    "brightblack": 90, "brightred": 91, "brightgreen": 92, "brightyellow": 93,
    "brightblue": 94, "brightmagenta": 95, "brightcyan": 96, "brightwhite": 97,
}

HOSTNAME = socket.gethostname().lower()


def char_sgr(ch) -> str:
    """Parámetros SGR de un pyte.Char."""
    parts = []
    if ch.bold:
        parts.append("1")
    if ch.italics:
        parts.append("3")
    if ch.underscore:
        parts.append("4")
    if ch.blink:
        parts.append("5")
    if ch.reverse:
        parts.append("7")
    if ch.strikethrough:
        parts.append("9")
    parts.append(_color(ch.fg, fg=True))
    parts.append(_color(ch.bg, fg=False))
    return ";".join(p for p in parts if p)


def _color(value: str, fg: bool) -> str:
    if not value or value == "default":
        return ""
    base = NAMED_FG.get(value)
    if base is not None:
        return str(base if fg else base + 10)
    if len(value) == 6:
        try:
            r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
            return f"{38 if fg else 48};2;{r};{g};{b}"
        except ValueError:
            return ""
    return ""


def style_sgr(style_str: str) -> str:
    try:
        return style_to_sgr(parse_style(style_str))
    except ValueError:
        return ""


# --------------------------------------------------------------------- formats
def expand_format(fmt: str, session=None, window=None, pane=None) -> str:
    out = []
    i = 0
    while i < len(fmt):
        c = fmt[i]
        if c == "#" and i + 1 < len(fmt):
            n = fmt[i + 1]
            i += 2
            if n == "#":
                out.append("#")
            elif n == "S":
                out.append(session.name if session else "")
            elif n == "I":
                out.append(str(window.index) if window else "")
            elif n == "W":
                out.append(window.name if window else "")
            elif n == "P":
                out.append(str(pane.id) if pane else "")
            elif n == "T":
                out.append(pane.title if pane else "")
            elif n == "H" or n == "h":
                out.append(HOSTNAME)
            elif n == "F":
                out.append("*" if (session and window and session.current is window) else "")
            else:
                out.append("#" + n)
        else:
            out.append(c)
            i += 1
    return time.strftime("".join(out))


# ----------------------------------------------------------------------- frame
class Grid:
    """Matriz de celdas (char, sgr) para componer el frame."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.chars = [[" "] * w for _ in range(h)]
        self.sgrs = [[""] * w for _ in range(h)]

    def put(self, x: int, y: int, ch: str, sgr: str = "") -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.chars[y][x] = ch
            self.sgrs[y][x] = sgr

    def put_text(self, x: int, y: int, text: str, sgr: str = "") -> int:
        for ch in text:
            if x >= self.w:
                break
            self.put(x, y, ch, sgr)
            x += 1
        return x

    def to_ansi(self) -> str:
        out = []
        for y in range(self.h):
            out.append(f"\x1b[{y + 1};1H\x1b[0m")
            cur = ""
            row_chars, row_sgrs = self.chars[y], self.sgrs[y]
            for x in range(self.w):
                sgr = row_sgrs[x]
                if sgr != cur:
                    out.append(f"\x1b[0m\x1b[{sgr}m" if sgr else "\x1b[0m")
                    cur = sgr
                ch = row_chars[x]
                if ch:  # "" = continuación de carácter ancho
                    out.append(ch)
            out.append("\x1b[0m\x1b[K")
        return "".join(out)


def render_frame(session, client, state) -> str:
    """Frame completo para un cliente. `state` es el ClientState (modos/overlays)."""
    w, h = client.width, client.height
    status_on = bool(session.options.get("status"))
    body_h = h - 1 if status_on else h
    grid = Grid(w, max(1, body_h))

    window = session.current
    cursor = None  # (x, y, visible)
    if window is not None:
        if window.zoomed and window.active in window.panes():
            rects = {window.active: Rect(0, 0, w, body_h)}
        else:
            rects = window.layout.compute(w, body_h)
        covered = set()
        for pane, rect in rects.items():
            for yy in range(rect.y, min(rect.y + rect.h, body_h)):
                for xx in range(rect.x, min(rect.x + rect.w, w)):
                    covered.add((xx, yy))

        # --- contenido de paneles
        for pane, rect in rects.items():
            if state.copy is not None and pane is window.active:
                _blit_copy_mode(grid, rect, state.copy)
                cc = state.copy.cursor_in_view()
                if cc:
                    cursor = (rect.x + cc[0], rect.y + cc[1], True)
                continue
            _blit_pane(grid, rect, pane)
            # Render mouse text selection if active
            if state.mode == "mouse_select" and pane is state.mouse_drag_pane and state.mouse_selection:
                _blit_mouse_selection(grid, rect, state.mouse_selection)
            if pane is window.active and cursor is None:
                with pane.lock:
                    cx, cy = pane.screen.cursor.x, pane.screen.cursor.y
                    hidden = pane.screen.cursor.hidden
                if cx < rect.w and cy < rect.h:
                    cursor = (rect.x + cx, rect.y + cy, not hidden)

        # --- bordes
        border_sgr = style_sgr(session.options.get("pane-border-style"))
        active_sgr = style_sgr(session.options.get("pane-active-border-style"))
        ar = rects.get(window.active)
        for yy in range(body_h):
            for xx in range(w):
                if (xx, yy) in covered:
                    continue
                ch = _border_char(xx, yy, covered, w, body_h)
                near_active = ar is not None and (
                    ar.x - 1 <= xx <= ar.x + ar.w and ar.y - 1 <= yy <= ar.y + ar.h)
                grid.put(xx, yy, ch, active_sgr if near_active else border_sgr)

        # --- overlay display-panes
        if state.display_panes_until and time.time() < state.display_panes_until:
            for i, (pane, rect) in enumerate(sorted(rects.items(), key=lambda kv: (kv[1].y, kv[1].x))):
                _blit_big_text(grid, rect, str(i), "1;34")

    # --- overlays de ventana completa
    if state.page_lines is not None:
        _blit_page(grid, state)
        cursor = None
    elif state.chooser is not None:
        _blit_chooser(grid, state)
        cursor = None
    elif state.context_menu is not None:
        _blit_context_menu(grid, state)
        cursor = None
    elif state.clock:
        _blit_clock(grid, session)
        cursor = None

    parts = ["\x1b[?2026h\x1b[?25l\x1b[H", grid.to_ansi()]

    # --- status line
    if status_on:
        parts.append(f"\x1b[{h};1H\x1b[0m")
        parts.append(_status_line(session, client, state, w))
        if state.mode == "prompt":
            cursor = (min(w - 1, state.prompt_prefix_len + state.prompt_cursor), h - 1, True)

    if cursor and cursor[2]:
        parts.append(f"\x1b[{cursor[1] + 1};{cursor[0] + 1}H\x1b[?25h")
    parts.append("\x1b[?2026l")
    return "".join(parts)


def _blit_pane(grid: Grid, rect, pane) -> None:
    with pane.lock:
        buf = pane.screen.buffer
        for ry in range(rect.h):
            if ry >= pane.rows:
                break
            line = buf[ry]
            for rx in range(min(rect.w, pane.cols)):
                ch = line[rx]
                grid.put(rect.x + rx, rect.y + ry, ch.data, char_sgr(ch))
    if pane.dead:
        msg = "[panel terminado, pulsa q o Enter]"
        grid.put_text(rect.x, rect.y + rect.h - 1, msg[:rect.w], "7")


def _blit_copy_mode(grid: Grid, rect, copy) -> None:
    rows = copy.visible_rows(rect.w, rect.h)
    for ry, row in enumerate(rows):
        for rx, (ch, sgr) in enumerate(row[:rect.w]):
            grid.put(rect.x + rx, rect.y + ry, ch, sgr)
    ind = copy.indicator()
    grid.put_text(max(rect.x, rect.x + rect.w - len(ind)), rect.y, ind, "7;33")


def _border_char(x, y, covered, w, h) -> str:
    def is_b(xx, yy):
        if xx < 0 or yy < 0 or xx >= w or yy >= h:
            return False
        return (xx, yy) not in covered

    l, r = is_b(x - 1, y), is_b(x + 1, y)
    u, d = is_b(x, y - 1), is_b(x, y + 1)
    if l and r and u and d:
        return "┼"
    if l and r and u:
        return "┴"
    if l and r and d:
        return "┬"
    if u and d and l:
        return "┤"
    if u and d and r:
        return "├"
    if u or d:
        return "│"
    return "─"


def status_window_ranges(session, w: int) -> list[tuple[int, int, int]]:
    """Rangos [inicio, fin) en columnas de cada etiqueta de ventana de la
    status line, como (inicio, fin, índice de ventana). Para clicks de ratón."""
    left = expand_format(session.options.get("status-left"), session)
    used = len(left)
    ranges = []
    for idx in sorted(session.windows):
        win = session.windows[idx]
        flag = "*" if idx == session.current_index else ("-" if idx == session.last_index else "")
        chunk = f" {idx}:{win.name}{flag}"
        if used + len(chunk) > w:
            break
        ranges.append((used, used + len(chunk), idx))
        used += len(chunk)
    return ranges


def _status_line(session, client, state, w: int) -> str:
    opts = session.options
    msg_sgr = style_sgr(opts.get("message-style"))
    if state.mode == "prompt":
        text = (state.prompt_prefix + state.prompt_buffer)[:w]
        return f"\x1b[{msg_sgr}m{text}{' ' * max(0, w - len(text))}\x1b[0m"
    if state.mode == "confirm":
        text = state.confirm_prompt[:w]
        return f"\x1b[{msg_sgr}m{text}{' ' * max(0, w - len(text))}\x1b[0m"
    if state.message and time.time() < state.message_until:
        text = state.message[:w]
        return f"\x1b[{msg_sgr}m{text}{' ' * max(0, w - len(text))}\x1b[0m"

    sgr = style_sgr(opts.get("status-style"))
    left = expand_format(opts.get("status-left"), session)
    right = expand_format(opts.get("status-right"), session)

    items = []
    for idx in sorted(session.windows):
        win = session.windows[idx]
        flag = "*" if idx == session.current_index else ("-" if idx == session.last_index else "")
        label = f"{idx}:{win.name}{flag}"
        items.append((label, idx == session.current_index))

    # como tmux: la lista de ventanas tiene prioridad; status-right se trunca
    out = [f"\x1b[{sgr}m", left]
    used = len(left)
    for label, current in items:
        chunk = f" {label}"
        if used + len(chunk) > w:
            break
        if current:
            out.append(f"\x1b[7m{chunk}\x1b[27m")
        else:
            out.append(chunk)
        used += len(chunk)
    right = right[:max(0, w - used)]
    pad = max(0, w - used - len(right))
    out.append(" " * pad)
    out.append(right)
    out.append("\x1b[0m")
    return "".join(out)


# ------------------------------------------------------------------- overlays
def _blit_page(grid: Grid, state) -> None:
    lines = state.page_lines[state.page_offset:state.page_offset + grid.h - 1]
    for y in range(grid.h):
        for x in range(grid.w):
            grid.put(x, y, " ", "")
    for y, line in enumerate(lines):
        grid.put_text(0, y, line[:grid.w], "")
    hint = f"[{state.page_offset + 1}-{state.page_offset + len(lines)}/{len(state.page_lines)}] q:salir ↑↓:mover"
    grid.put_text(0, grid.h - 1, hint[:grid.w], "7")


def _blit_chooser(grid: Grid, state) -> None:
    for y in range(grid.h):
        for x in range(grid.w):
            grid.put(x, y, " ", "")
    grid.put_text(1, 0, state.chooser_title, "1")
    for i, (label, _action) in enumerate(state.chooser):
        if i + 2 >= grid.h:
            break
        sgr = "7" if i == state.chooser_idx else ""
        grid.put_text(2, i + 2, f"({i}) {label}"[:grid.w - 2], sgr)


_DIGITS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"], "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "2": ["███", "  █", "███", "█  ", "███"], "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"], "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"], "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"], "9": ["███", "█ █", "███", "  █", "███"],
    ":": [" ", "█", " ", "█", " "],
}


def _blit_big_text(grid: Grid, rect, text: str, sgr: str) -> None:
    width = sum(len(_DIGITS.get(c, ["   "])[0]) + 1 for c in text) - 1
    x0 = rect.x + max(0, (rect.w - width) // 2)
    y0 = rect.y + max(0, (rect.h - 5) // 2)
    for ch in text:
        glyph = _DIGITS.get(ch)
        if glyph is None:
            continue
        for dy, row in enumerate(glyph):
            for dx, cell in enumerate(row):
                if cell != " " and x0 + dx < rect.x + rect.w and y0 + dy < rect.y + rect.h:
                    grid.put(x0 + dx, y0 + dy, " ", sgr.replace("3", "4", 1) + ";7")
        x0 += len(glyph[0]) + 1


def _blit_clock(grid: Grid, session) -> None:
    for y in range(grid.h):
        for x in range(grid.w):
            grid.put(x, y, " ", "")
    _blit_big_text(grid, Rect(0, 0, grid.w, grid.h), time.strftime("%H:%M"), "1;32")


def _blit_mouse_selection(grid: Grid, rect, selection: tuple) -> None:
    """Highlight mouse selection with inverse video."""
    (start_y, start_x), (end_y, end_x) = selection
    if start_y > end_y or (start_y == end_y and start_x > end_x):
        (start_y, start_x), (end_y, end_x) = (end_y, end_x), (start_y, start_x)
    for y in range(max(0, start_y), min(rect.h, end_y + 1)):
        for x in range(rect.w):
            s = start_x if y == start_y else 0
            e = end_x if y == end_y else rect.w - 1
            if s <= x <= e:
                sgr = grid.sgrs[rect.y + y][rect.x + x]
                grid.sgrs[rect.y + y][rect.x + x] = (sgr + ";" if sgr else "") + "7"


def _blit_context_menu(grid: Grid, state) -> None:
    """Render right-click context menu overlay."""
    for y in range(grid.h):
        for x in range(grid.w):
            grid.put(x, y, " ", "")
    menu = state.context_menu
    options = menu.get("options", [])
    title = "Opciones"
    menu_width = max(len(title), max((len(opt) for opt in options), default=0)) + 4
    menu_x = max(0, min(grid.w - menu_width, menu.get("x", 0)))
    menu_y = max(0, min(grid.h - len(options) - 3, menu.get("y", 0)))
    grid.put_text(menu_x + 1, menu_y, title, "1;33")
    for i, opt in enumerate(options):
        sgr = "7" if i == menu["selected"] else ""
        grid.put_text(menu_x + 2, menu_y + i + 2, opt[:menu_width - 2], sgr)
