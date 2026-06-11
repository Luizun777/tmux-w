"""Servidor tmux-w (server.c): mantiene sesiones vivas y atiende clientes por TCP loopback."""

import json
import os
import secrets
import socket
import threading
import time
import traceback

from . import paths
from .commands import (
    DEFAULT_BINDINGS,
    DEFAULT_REPEAT_BINDINGS,
    CommandError,
    execute_command,
    execute_line,
)
from .config import load_config, tokenize
from .keys import keyspec_to_vt
from .layout import Rect
from .model import Session, Window, next_pane_id
from .options import Options
from .pane import Pane
from .render import render_frame, status_window_ranges

FRAME_INTERVAL = 1 / 30.0


class ClientState:
    """Estado de UI por cliente: modo, prompt, overlays, copy-mode."""

    def __init__(self):
        self.mode = "normal"  # normal|prefix|prompt|confirm|copy|choose|page|clock|displayp|context_menu|mouse_select
        self.prefix_repeat = False  # prefijo activo por un binding repetible (bind -r)
        self.prefix_until = 0.0  # fin del estado de repetición
        self.drag = None  # arrastre de borde: {"win": Window, "node": Split}
        self.copy = None
        self.prompt_prefix = ":"
        self.prompt_prefix_len = 1
        self.prompt_buffer = ""
        self.prompt_cursor = 0
        self.prompt_template = None
        self.prompt_callback = None
        self.prompt_history_idx = None
        self.confirm_prompt = ""
        self.confirm_cmd = None
        self.chooser = None
        self.chooser_idx = 0
        self.chooser_title = ""
        self.page_lines = None
        self.page_offset = 0
        self.message = ""
        self.message_until = 0.0
        self.display_panes_until = 0.0
        self.clock = False
        # Mouse selection (drag text, right-click menu)
        self.mouse_drag_start: tuple[int, int] | None = None  # (pane_x, pane_y)
        self.mouse_drag_pane = None  # Pane being dragged in
        self.mouse_selection: tuple[tuple[int, int], tuple[int, int]] | None = (
            None  # (start, end) in pane coords
        )
        self.context_menu = None  # {"pane": Pane, "x": x, "y": y, "options": [...], "selected": 0}

    def reset_overlays(self):
        self.mode = "normal"
        self.prefix_repeat = False
        self.drag = None
        self.copy = None
        self.chooser = None
        self.page_lines = None
        self.clock = False
        self.confirm_cmd = None
        self.mouse_drag_start = None
        self.mouse_drag_pane = None
        self.mouse_selection = None
        self.context_menu = None


class Client:
    _ids = 0

    def __init__(self, sock: socket.socket):
        Client._ids += 1
        self.id = Client._ids
        self.sock = sock
        self.send_lock = threading.Lock()
        self.width = 80
        self.height = 24
        self.session_name = ""
        self.attached = False
        self.alive = True
        self.state = ClientState()
        self.last_frame = None

    def send(self, obj: dict) -> None:
        if not self.alive:
            return
        try:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            with self.send_lock:
                self.sock.sendall(data)
        except OSError:
            self.alive = False


class Server:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.clients: list[Client] = []
        self.options = Options()
        self.bindings = dict(DEFAULT_BINDINGS)
        self.repeat_bindings: set[str] = set(DEFAULT_REPEAT_BINDINGS)
        self.root_bindings: dict[str, list[str]] = {}
        self.buffers: list[str] = []
        self.prompt_history: list[str] = []
        self.dirty = threading.Event()
        self.running = True
        self.had_session = False
        self._session_counter = 0
        self.token = secrets.token_hex(16)
        self.listener: socket.socket | None = None

    # ------------------------------------------------------------ sesiones
    def next_session_name(self) -> str:
        while str(self._session_counter) in self.sessions:
            self._session_counter += 1
        return str(self._session_counter)

    def create_session(self, name: str, width: int, height: int, command=None) -> Session:
        opts = Options(parent=self.options)
        session = Session(name, width, height, options=opts)
        self.sessions[name] = session
        self.had_session = True
        self.create_window(session, command)
        return session

    def create_window(self, session: Session, command=None, name=None) -> Window:
        index = session.next_free_index(session.options.get("base-index"))
        pane = self.create_pane(session, command)
        win = Window(index, pane, name=name)
        session.add_window(win)
        self.relayout(session)
        return win

    def create_pane(self, session: Session, command=None) -> Pane:
        return Pane(
            next_pane_id(),
            session.width,
            max(1, session.height - 1),
            command=command,
            default_shell=session.options.get("default-shell"),
            history=session.options.get("history-limit"),
            on_dirty=lambda p: self.dirty.set(),
            on_exit=lambda p: self._pane_exited(p),
        )

    def rename_session(self, session: Session, new: str) -> None:
        old = session.name
        self.sessions.pop(old, None)
        session.name = new
        self.sessions[new] = session
        for c in self.clients:
            if c.session_name == old:
                c.session_name = new

    def kill_session(self, session: Session) -> None:
        for pane in session.all_panes():
            pane.on_exit = None
            pane.kill()
        self.sessions.pop(session.name, None)
        for c in list(self.clients):
            if c.attached and c.session_name == session.name:
                self._reattach_or_exit(c)
        self._maybe_shutdown()

    def kill_window(self, session: Session, win: Window) -> None:
        for pane in win.panes():
            pane.on_exit = None
            pane.kill()
        session.remove_window(win.index)
        if not session.windows:
            self.sessions.pop(session.name, None)
            for c in list(self.clients):
                if c.attached and c.session_name == session.name:
                    self._reattach_or_exit(c)
            self._maybe_shutdown()
        else:
            self.relayout(session)

    def close_pane(self, pane: Pane, kill_process: bool = False) -> None:
        pane.on_exit = None
        if kill_process:
            pane.kill()
        for session in list(self.sessions.values()):
            win = session.window_of_pane(pane)
            if win is None:
                continue
            if len(win.panes()) == 1:
                self.kill_window(session, win)
            else:
                if win.active is pane:
                    panes = win.panes()
                    idx = panes.index(pane)
                    win.layout.remove(pane)
                    remaining = win.panes()
                    win.set_active(
                        win.last_pane
                        if win.last_pane in remaining
                        else remaining[min(idx, len(remaining) - 1)]
                    )
                else:
                    win.layout.remove(pane)
                win.zoomed = False
                self.relayout(session)
            return

    def _pane_exited(self, pane: Pane) -> None:
        with self.lock:
            self.close_pane(pane, kill_process=False)
            self.dirty.set()

    def _reattach_or_exit(self, client: Client) -> None:
        others = [n for n in self.sessions if n != client.session_name]
        if others:
            self.attach_client(client, self.sessions[others[-1]])
        else:
            client.attached = False
            client.send({"t": "exit", "msg": "la sesión ha terminado"})
            client.alive = False

    def _maybe_shutdown(self) -> None:
        if self.had_session and not self.sessions:
            self.shutdown()

    # ------------------------------------------------------------ clientes
    def attach_client(self, client: Client, session: Session) -> None:
        client.session_name = session.name
        client.attached = True
        client.state.reset_overlays()
        client.last_frame = None
        self._resize_session(session)
        client.send({"t": "attached", "session": session.name})
        self.dirty.set()

    def detach_client(self, client: Client) -> None:
        client.attached = False
        client.send({"t": "detached", "session": client.session_name})
        client.alive = False

    def _resize_session(self, session: Session) -> None:
        sizes = [
            (c.width, c.height)
            for c in self.clients
            if c.attached and c.alive and c.session_name == session.name
        ]
        if sizes:
            session.resize(min(w for w, _ in sizes), min(h for _, h in sizes))
        self.relayout(session)

    def relayout(self, session: Session) -> None:
        body_h = session.height - (1 if session.options.get("status") else 0)
        for win in session.windows.values():
            rects = win.layout.compute(session.width, max(1, body_h))
            for pane, rect in rects.items():
                if win.zoomed and pane is win.active:
                    pane.resize(session.width, max(1, body_h))
                elif not win.zoomed:
                    pane.resize(rect.w, rect.h)
        self.dirty.set()

    def relayout_all(self) -> None:
        for s in self.sessions.values():
            self.relayout(s)

    def shutdown(self) -> None:
        self.running = False
        for session in list(self.sessions.values()):
            for pane in session.all_panes():
                pane.on_exit = None
                pane.kill()
        self.sessions.clear()
        for c in list(self.clients):
            if c.alive:
                c.send({"t": "exit", "msg": "servidor terminado"})
                c.alive = False
        paths.clear_server_info()
        self.dirty.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass

    # --------------------------------------------------------------- teclas
    def handle_key(self, client: Client, ks: str) -> None:
        st = client.state
        session = self.sessions.get(client.session_name)
        if session is None:
            return
        win = session.current
        try:
            if st.mode == "copy":
                self._copy_key(client, st, ks)
            elif st.mode == "prompt":
                self._prompt_key(client, st, ks)
            elif st.mode == "confirm":
                cmd, st.confirm_cmd = st.confirm_cmd, None
                st.mode = "normal"
                st.message, st.message_until = "", 0
                if ks in ("y", "Y") and cmd:
                    self._run(client, cmd)
            elif st.mode == "choose":
                self._chooser_key(client, st, ks)
            elif st.mode == "page":
                self._page_key(st, ks)
            elif st.mode == "clock":
                st.clock = False
                st.mode = "normal"
            elif st.mode == "displayp":
                st.mode = "normal"
                st.display_panes_until = 0
                if ks.isdigit() and win is not None:
                    body_h = session.height - (1 if session.options.get("status") else 0)
                    rects = win.layout.compute(session.width, body_h)
                    ordered = [
                        p for p, _ in sorted(rects.items(), key=lambda kv: (kv[1].y, kv[1].x))
                    ]
                    i = int(ks)
                    if i < len(ordered):
                        win.set_active(ordered[i])
            elif st.mode == "context_menu":
                self._context_menu_key(client, st, ks)
            elif st.mode == "mouse_select":
                if ks == "Escape":
                    st.mode = "normal"
                    st.mouse_selection = None
            elif st.mode == "prefix":
                repeating = st.prefix_repeat and time.time() <= st.prefix_until
                was_repeat = st.prefix_repeat
                st.mode = "normal"
                st.prefix_repeat = False
                if was_repeat:
                    # estado de repetición (bind -r): la tecla repetible se
                    # re-ejecuta sin prefijo; cualquier otra vuelve al panel
                    if repeating and ks in self.bindings and ks in self.repeat_bindings:
                        self._run(client, self.bindings[ks])
                        self._arm_repeat(client, session)
                    else:
                        self._normal_key(client, session, win, ks)
                else:
                    prefixes = (session.options.get("prefix"), session.options.get("prefix2"))
                    if ks in prefixes and win is not None:
                        win.active.write(keyspec_to_vt(ks))
                    elif ks in self.bindings:
                        self._run(client, self.bindings[ks])
                        if ks in self.repeat_bindings:
                            self._arm_repeat(client, session)
                    else:
                        self._flash(client, f"tecla sin asignar: {ks}")
            else:  # normal
                self._normal_key(client, session, win, ks)
        except CommandError as e:
            self._flash(client, str(e))
        self.dirty.set()

    # --------------------------------------------------------------- ratón
    def handle_mouse(self, client: Client, ev: dict) -> None:
        """Click: foco de panel / ventana en status line. Arrastre de borde:
        redimensionar. Rueda: scroll (copy-mode). Geometría igual que render_frame."""
        st = client.state
        session = self.sessions.get(client.session_name)
        if session is None or not session.options.get("mouse"):
            return
        win = session.current
        try:
            x, y = int(ev.get("x", -1)), int(ev.get("y", -1))
        except (TypeError, ValueError):
            return
        etype, btn = ev.get("e", ""), ev.get("b", "")
        if win is None or x < 0 or y < 0:
            return
        w, h = client.width, client.height
        status_on = bool(session.options.get("status"))
        body_h = max(1, h - (1 if status_on else 0))

        if st.mode == "copy" and st.copy is not None:
            if etype == "wheel":
                if btn == "wheel-up":
                    st.copy.scroll(-3)
                elif st.copy.scroll(3) and st.copy.anchor is None:
                    st.copy = None  # al llegar abajo sin selección, salir
                    st.mode = "normal"
            return
        if st.mode not in ("normal", "prefix", "mouse_select"):
            return
        if etype == "down" and st.mode == "prefix":
            st.mode = "normal"  # un click cancela el prefijo
            st.prefix_repeat = False

        if win.zoomed and win.active in win.panes():
            rects = {win.active: Rect(0, 0, w, body_h)}
        else:
            rects = win.layout.compute(w, body_h)

        if etype == "up":
            st.drag = None
            if st.mode == "mouse_select":
                # fin de la selección de texto: copiar al portapapeles
                if (
                    st.mouse_drag_pane is not None
                    and st.mouse_selection is not None
                    and btn == "left"
                ):
                    selection_text = self._get_pane_selection_text(
                        st.mouse_drag_pane, st.mouse_selection
                    )
                    if selection_text:
                        from .clipboard import set_clipboard_text

                        set_clipboard_text(selection_text)
                        st.message = "[texto copiado]"
                        st.message_until = time.time() + 0.5
                st.mouse_drag_start = None
                st.mouse_drag_pane = None
                st.mouse_selection = None
                st.mode = "normal"
                self.dirty.set()
            return
        if etype == "drag":
            drag = st.drag
            if drag is not None and drag["win"] is win and btn == "left":
                node = drag["node"]
                if any(n is node for n, _ in win.layout.node_rects(w, body_h)):
                    if win.layout.drag_divider(node, x, y, w, body_h):
                        self.relayout(session)
                else:
                    st.drag = None
            elif st.mode == "mouse_select" and st.mouse_drag_pane is not None and btn == "left":
                pane_rect = rects.get(st.mouse_drag_pane)
                if pane_rect and st.mouse_drag_start:
                    start_x, start_y = st.mouse_drag_start
                    st.mouse_selection = ((start_y, start_x), (y - pane_rect.y, x - pane_rect.x))
                    self.dirty.set()
            return

        # un nuevo click mientras quedaba selección pendiente la cancela
        if etype == "down" and st.mode == "mouse_select":
            st.mode = "normal"
            st.mouse_drag_start = None
            st.mouse_drag_pane = None
            st.mouse_selection = None

        # status line: click selecciona la ventana, la rueda las rota
        if status_on and y >= h - 1:
            if etype == "down" and btn == "left":
                for start, end, idx in status_window_ranges(session, w):
                    if start <= x < end:
                        session.select_window(idx)
                        self.relayout(session)
                        break
            elif etype == "wheel":
                session.cycle_window(1 if btn == "wheel-down" else -1)
                self.relayout(session)
            return

        target = None
        for pane, r in rects.items():
            if r.x <= x < r.x + r.w and r.y <= y < r.y + r.h:
                target = pane
                break

        if etype == "down":
            st.drag = None
            st.mouse_drag_start = None
            st.mouse_drag_pane = None
            if target is not None:
                win.set_active(target)
                if btn == "left":
                    # Prepare for text drag selection
                    st.mouse_drag_pane = target
                    st.mouse_drag_start = (x - rects[target].x, y - rects[target].y)
                    st.mode = "mouse_select"
                elif btn == "right":
                    # Right-click context menu
                    self._show_context_menu(
                        client, target, x - rects[target].x, y - rects[target].y
                    )
                self.relayout(session)
            elif btn == "left" and not win.zoomed:
                node = win.layout.split_at(x, y, w, body_h)
                if node is not None:
                    st.drag = {"win": win, "node": node}
                    if win.layout.drag_divider(node, x, y, w, body_h):
                        self.relayout(session)
        elif etype == "wheel" and btn == "wheel-up" and target is not None:
            # rueda arriba sobre un panel: copy-mode con scroll (como tmux)
            from .copymode import CopyMode

            win.set_active(target)
            st.copy = CopyMode(target, session.options.get("mode-keys"), scroll_up=3)
            st.mode = "copy"
            self.relayout(session)

    def _show_context_menu(self, client: Client, pane, pane_x: int, pane_y: int) -> None:
        """Show right-click context menu."""
        st = client.state
        from .clipboard import get_clipboard_text

        options = []
        if st.mouse_selection:
            options.append("copy")
        if get_clipboard_text():
            options.append("paste")
        options.append("kill-pane")
        if options:
            st.context_menu = {
                "pane": pane,
                "x": pane_x,
                "y": pane_y,
                "options": options,
                "selected": 0,
            }
            st.mode = "context_menu"

    def _context_menu_key(self, client: Client, st: ClientState, ks: str) -> None:
        """Handle key in context menu mode."""
        menu = st.context_menu
        if not menu:
            st.mode = "normal"
            return
        if ks in ("Escape", "q"):
            st.mode = "normal"
            st.context_menu = None
        elif ks in ("Up", "k"):
            menu["selected"] = max(0, menu["selected"] - 1)
        elif ks in ("Down", "j"):
            menu["selected"] = min(len(menu["options"]) - 1, menu["selected"] + 1)
        elif ks in ("Enter", " "):
            option = menu["options"][menu["selected"]]
            st.mode = "normal"
            st.context_menu = None
            pane = menu["pane"]
            if option == "copy":
                if st.mouse_selection:
                    text = self._get_pane_selection_text(pane, st.mouse_selection)
                    if text:
                        from .clipboard import set_clipboard_text

                        set_clipboard_text(text)
                        st.message = "[texto copiado]"
                        st.message_until = time.time() + 0.5
            elif option == "paste":
                from .clipboard import get_clipboard_text

                text = get_clipboard_text()
                if text:
                    pane.write(text)
                    st.message = "[pegado]"
                    st.message_until = time.time() + 0.5
            elif option == "kill-pane":
                # Kill the pane
                session = self.sessions.get(client.session_name)
                if session:
                    self.close_pane(pane, kill_process=True)
                    st.message = "[panel cerrado]"
                    st.message_until = time.time() + 0.5

    def _get_pane_selection_text(self, pane, selection: tuple) -> str:
        """Extract text from pane selection. selection = ((start_y, start_x), (end_y, end_x))."""
        try:
            with pane.lock:
                lines = pane.snapshot_lines()
            (start_y, start_x), (end_y, end_x) = selection
            if start_y > end_y or (start_y == end_y and start_x > end_x):
                (start_y, start_x), (end_y, end_x) = (end_y, end_x), (start_y, start_x)
            out = []
            for line_idx in range(max(0, start_y), min(len(lines), end_y + 1)):
                if line_idx < 0 or line_idx >= len(lines):
                    continue
                line = lines[line_idx]
                text = "".join(ch.data or " " for ch in line).rstrip()
                s = start_x if line_idx == start_y else 0
                e = end_x + 1 if line_idx == end_y else len(text)
                out.append(text[max(0, s) : min(len(text), e)])
            return "\n".join(out)
        except Exception:
            return ""

    def _normal_key(self, client: Client, session: Session, win, ks: str) -> None:
        st = client.state
        if ks == session.options.get("prefix") or ks == session.options.get("prefix2"):
            st.mode = "prefix"
        elif ks in self.root_bindings:
            self._run(client, self.root_bindings[ks])
        elif ks == "C-M-v" and win is not None:
            # Paste from clipboard: Ctrl+Shift+V
            from .clipboard import get_clipboard_text

            text = get_clipboard_text()
            if text:
                win.active.write(text)
        elif win is not None:
            win.active.write(keyspec_to_vt(ks))

    def _arm_repeat(self, client: Client, session: Session) -> None:
        """Tras un binding repetible, deja el prefijo activo durante repeat-time."""
        st = client.state
        if st.mode != "normal":  # el comando abrió un prompt/overlay
            return
        st.mode = "prefix"
        st.prefix_repeat = True
        st.prefix_until = time.time() + session.options.get("repeat-time") / 1000.0

    def _run(self, client: Client, tokens: list[str]) -> None:
        try:
            out = execute_command(self, client, tokens)
            if out:
                self._flash(client, out.split("\n")[0] if client.attached else out)
        except CommandError as e:
            self._flash(client, str(e))

    def _flash(self, client: Client, msg: str) -> None:
        st = client.state
        st.message = msg
        st.message_until = time.time() + self.options.get("display-time") / 1000.0

    # --- prompt -------------------------------------------------------
    def _prompt_key(self, client: Client, st: ClientState, ks: str) -> None:
        if ks in ("Escape", "C-c", "C-g"):
            st.mode = "copy" if st.copy is not None else "normal"
            st.prompt_callback = None
        elif ks == "Enter":
            text = st.prompt_buffer
            callback, st.prompt_callback = st.prompt_callback, None
            template = st.prompt_template
            st.prompt_buffer, st.prompt_cursor, st.prompt_template = "", 0, None
            st.mode = "copy" if st.copy is not None else "normal"
            if callback is not None:
                callback(text)
                return
            if text.strip():
                self.prompt_history.append(text)
            if template:
                quoted = '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
                line = template.replace("%%", quoted)
                self._run(client, tokenize(line))
            elif text.strip():
                self._run(client, tokenize(text))
        elif ks == "BSpace":
            if st.prompt_cursor > 0:
                st.prompt_buffer = (
                    st.prompt_buffer[: st.prompt_cursor - 1] + st.prompt_buffer[st.prompt_cursor :]
                )
                st.prompt_cursor -= 1
        elif ks == "Left":
            st.prompt_cursor = max(0, st.prompt_cursor - 1)
        elif ks == "Right":
            st.prompt_cursor = min(len(st.prompt_buffer), st.prompt_cursor + 1)
        elif ks == "Home":
            st.prompt_cursor = 0
        elif ks == "End":
            st.prompt_cursor = len(st.prompt_buffer)
        elif ks == "C-u":
            st.prompt_buffer, st.prompt_cursor = "", 0
        elif ks == "Up":
            if self.prompt_history:
                if st.prompt_history_idx is None:
                    st.prompt_history_idx = len(self.prompt_history)
                st.prompt_history_idx = max(0, st.prompt_history_idx - 1)
                st.prompt_buffer = self.prompt_history[st.prompt_history_idx]
                st.prompt_cursor = len(st.prompt_buffer)
        elif ks == "Down":
            if self.prompt_history and st.prompt_history_idx is not None:
                st.prompt_history_idx = min(len(self.prompt_history) - 1, st.prompt_history_idx + 1)
                st.prompt_buffer = self.prompt_history[st.prompt_history_idx]
                st.prompt_cursor = len(st.prompt_buffer)
        elif ks == "Space":
            self._prompt_insert(st, " ")
        elif len(ks) == 1:
            self._prompt_insert(st, ks)

    def _prompt_insert(self, st: ClientState, ch: str) -> None:
        st.prompt_buffer = (
            st.prompt_buffer[: st.prompt_cursor] + ch + st.prompt_buffer[st.prompt_cursor :]
        )
        st.prompt_cursor += 1

    # --- copy-mode ------------------------------------------------------
    def _copy_key(self, client: Client, st: ClientState, ks: str) -> None:
        if st.copy is None:
            st.mode = "normal"
            return
        result = st.copy.handle_key(ks)
        if result is None:
            return
        action, payload = result
        if action == "exit":
            st.copy = None
            st.mode = "normal"
        elif action == "copy":
            if payload:
                self.buffers.insert(0, payload)
                try:
                    from .clipboard import set_clipboard_text

                    set_clipboard_text(payload)
                except Exception:
                    pass
            st.copy = None
            st.mode = "normal"
            self._flash(client, f"copiadas {len(payload or '')} letras")
        elif action == "search":
            direction = payload
            st.mode = "prompt"
            st.prompt_prefix = "/" if direction > 0 else "?"
            st.prompt_prefix_len = 1
            st.prompt_buffer, st.prompt_cursor = "", 0
            st.prompt_template = None

            def do_search(text, copy=st.copy, d=direction):
                if text:
                    copy.search(text, d)

            st.prompt_callback = do_search

    # --- otros modos ------------------------------------------------------
    def _chooser_key(self, client: Client, st: ClientState, ks: str) -> None:
        if ks in ("q", "Escape"):
            st.chooser = None
            st.mode = "normal"
        elif ks == "Up":
            st.chooser_idx = max(0, st.chooser_idx - 1)
        elif ks == "Down":
            st.chooser_idx = min(len(st.chooser) - 1, st.chooser_idx + 1)
        elif ks == "Enter":
            entry = st.chooser[st.chooser_idx] if st.chooser else None
            st.chooser = None
            st.mode = "normal"
            if entry:
                self._run(client, entry[1])
        elif ks.isdigit() and st.chooser and int(ks) < len(st.chooser):
            entry = st.chooser[int(ks)]
            st.chooser = None
            st.mode = "normal"
            self._run(client, entry[1])

    def _page_key(self, st: ClientState, ks: str) -> None:
        page = 10
        if ks in ("q", "Escape", "Enter"):
            st.page_lines = None
            st.mode = "normal"
        elif ks == "Up":
            st.page_offset = max(0, st.page_offset - 1)
        elif ks == "Down":
            st.page_offset = min(max(0, len(st.page_lines) - 1), st.page_offset + 1)
        elif ks == "PgUp":
            st.page_offset = max(0, st.page_offset - page)
        elif ks == "PgDn":
            st.page_offset = min(max(0, len(st.page_lines) - 1), st.page_offset + page)

    # ------------------------------------------------------------- red/io
    def serve(self) -> None:
        paths.ensure_dirs()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        port = self.listener.getsockname()[1]
        paths.write_server_info(port, self.token, os.getpid())
        self._load_config()
        threading.Thread(target=self._render_loop, daemon=True, name="render").start()
        try:
            while self.running:
                try:
                    sock, _ = self.listener.accept()
                except OSError:
                    break
                client = Client(sock)
                threading.Thread(
                    target=self._client_loop,
                    args=(client,),
                    daemon=True,
                    name=f"client-{client.id}",
                ).start()
        finally:
            paths.clear_server_info()

    def _load_config(self) -> None:
        for path in paths.config_files():
            errors = load_config(path, lambda toks: execute_command(self, None, toks))
            for e in errors:
                self._log(f"config: {e}")

    def _client_loop(self, client: Client) -> None:
        with self.lock:
            self.clients.append(client)
        try:
            authed = False
            f = client.sock.makefile("r", encoding="utf-8", newline="\n")
            for line in f:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not authed:
                    if msg.get("token") != self.token:
                        client.send({"t": "error", "msg": "token inválido"})
                        break
                    authed = True
                with self.lock:
                    if not self._dispatch(client, msg):
                        break
                if not client.alive:
                    break
        except OSError:
            pass
        except Exception:
            self._log(traceback.format_exc())
        finally:
            with self.lock:
                client.alive = False
                client.attached = False
                if client in self.clients:
                    self.clients.remove(client)
                for s in self.sessions.values():
                    self._resize_session(s)
            try:
                client.sock.close()
            except OSError:
                pass

    def _dispatch(self, client: Client, msg: dict) -> bool:
        t = msg.get("t")
        if t == "attach":
            client.width = int(msg.get("w", 80))
            client.height = int(msg.get("h", 24))
            name = msg.get("session")
            try:
                if name:
                    session = self.sessions.get(name)
                    if session is None:
                        matches = [s for n, s in self.sessions.items() if n.startswith(name)]
                        session = matches[0] if len(matches) == 1 else None
                    if session is None:
                        if msg.get("create"):
                            session = self.create_session(
                                name, client.width, client.height, msg.get("command")
                            )
                        else:
                            client.send({"t": "error", "msg": f"sesión no encontrada: {name}"})
                            return False
                else:
                    if msg.get("create"):
                        session = self.create_session(
                            self.next_session_name(),
                            client.width,
                            client.height,
                            msg.get("command"),
                        )
                    elif self.sessions:
                        session = next(reversed(self.sessions.values()))
                    else:
                        client.send({"t": "error", "msg": "no hay sesiones (usa: tmuxw new)"})
                        return False
                self.attach_client(client, session)
            except Exception as e:
                client.send({"t": "error", "msg": str(e)})
                return False
        elif t == "key":
            self.handle_key(client, msg.get("k", ""))
        elif t == "mouse":
            self.handle_mouse(client, msg)
            self.dirty.set()
        elif t == "text":
            session = self.sessions.get(client.session_name)
            if session and session.current:
                session.current.active.write(msg.get("s", ""))
                self.dirty.set()
        elif t == "resize":
            client.width = int(msg.get("w", client.width))
            client.height = int(msg.get("h", client.height))
            client.last_frame = None
            session = self.sessions.get(client.session_name)
            if session:
                self._resize_session(session)
        elif t == "cmd":
            try:
                out = execute_line(self, client if client.attached else None, msg.get("s", ""))
                client.send({"t": "msg", "s": out if out is not None else ""})
            except CommandError as e:
                client.send({"t": "msg", "s": f"error: {e}", "err": True})
            client.send({"t": "done"})
            self.dirty.set()
        elif t == "detach":
            self.detach_client(client)
            return False
        return client.alive or client.attached

    # ------------------------------------------------------------- render
    def _render_loop(self) -> None:
        while self.running:
            self.dirty.wait(timeout=0.5)
            self.dirty.clear()
            time.sleep(FRAME_INTERVAL)
            with self.lock:
                targets = [
                    (c, self.sessions.get(c.session_name))
                    for c in self.clients
                    if c.attached and c.alive
                ]
                frames = []
                for client, session in targets:
                    if session is None:
                        continue
                    try:
                        frame = render_frame(session, client, client.state)
                    except Exception:
                        self._log(traceback.format_exc())
                        continue
                    if frame != client.last_frame:
                        client.last_frame = frame
                        frames.append((client, frame))
            for client, frame in frames:
                client.send({"t": "frame", "d": frame})

    def _log(self, text: str) -> None:
        try:
            paths.ensure_dirs()
            with open(paths.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
        except OSError:
            pass


def main() -> None:
    server = Server()
    try:
        server.serve()
    except Exception:
        server._log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
