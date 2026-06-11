"""Modelo: Session -> Window -> Pane (equivalente a session.c / window.c de tmux)."""

import itertools
import time

from .layout import Layout
from .pane import Pane

_pane_ids = itertools.count(0)


class Window:
    def __init__(self, index: int, pane: Pane, name: str | None = None):
        self.index = index
        self.layout = Layout(pane)
        self.active = pane
        self.last_pane: Pane | None = None
        self.custom_name = name
        self.zoomed = False
        self._preset_idx = 0

    @property
    def name(self) -> str:
        return self.custom_name or self.active.title

    def panes(self) -> list[Pane]:
        return self.layout.panes()

    def set_active(self, pane: Pane) -> None:
        if pane is not self.active:
            self.last_pane = self.active
            self.active = pane

    def next_preset(self) -> str:
        self._preset_idx = (self._preset_idx + 1) % len(Layout.PRESETS)
        name = Layout.PRESETS[self._preset_idx]
        self.zoomed = False
        self.layout.apply_preset(name, self.panes())
        return name


class Session:
    def __init__(self, name: str, width: int = 80, height: int = 24, options=None):
        self.name = name
        self.width = width
        self.height = height
        self.created = time.time()
        self.options = options
        self.windows: dict[int, Window] = {}
        self.current_index: int | None = None
        self.last_index: int | None = None

    # ------------------------------------------------------------ windows
    @property
    def current(self) -> Window | None:
        if self.current_index is None:
            return None
        return self.windows.get(self.current_index)

    def next_free_index(self, base_index: int = 0) -> int:
        i = base_index
        while i in self.windows:
            i += 1
        return i

    def add_window(self, window: Window) -> None:
        self.windows[window.index] = window
        self.select_window(window.index)

    def select_window(self, index: int) -> bool:
        if index not in self.windows:
            return False
        if index != self.current_index:
            self.last_index = self.current_index
            self.current_index = index
        return True

    def remove_window(self, index: int) -> None:
        self.windows.pop(index, None)
        if self.last_index == index:
            self.last_index = None
        if self.current_index == index:
            remaining = sorted(self.windows)
            if self.last_index in self.windows:
                self.current_index = self.last_index
                self.last_index = None
            elif remaining:
                lower = [i for i in remaining if i < index]
                self.current_index = lower[-1] if lower else remaining[0]
            else:
                self.current_index = None

    def cycle_window(self, step: int) -> bool:
        order = sorted(self.windows)
        if not order or self.current_index is None:
            return False
        pos = order.index(self.current_index)
        return self.select_window(order[(pos + step) % len(order)])

    # -------------------------------------------------------------- panes
    def all_panes(self) -> list[Pane]:
        out: list[Pane] = []
        for w in self.windows.values():
            out.extend(w.panes())
        return out

    def window_of_pane(self, pane: Pane) -> Window | None:
        for w in self.windows.values():
            if pane in w.panes():
                return w
        return None

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height


def next_pane_id() -> int:
    return next(_pane_ids)
