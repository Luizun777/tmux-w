# 🖱️ Mouse Selection Implementation Plan — Deep Analysis

## Current State (What's Already Working)

### ✅ Mouse Support Exists
- `keys.py`: `decode_mouse_event()` already detects:
  - Button events: `left`, `right`, `middle`
  - Event types: `down`, `up`, `drag`, `wheel`
  - Coordinates: `x`, `y`
- `server.py`: `handle_mouse()` processes:
  - ✅ Status line window selection
  - ✅ Panel focus (click = focus)
  - ✅ Border resize drag
  - ✅ Wheel scroll in copy-mode
- `copymode.py`: Full keyboard selection (Space/v, Enter/y, etc.)
- `clipboard.py`: `set_clipboard_text()` copies to Windows clipboard

### ❌ What's Missing
1. **Drag selection** (mouse drag to select text)
2. **Right-click menu** (copy, paste, kill pane)
3. **Get clipboard** (`get_clipboard_text()`)
4. **Paste to pane** (send clipboard text to subprocess)
5. **Kill pane** by mouse

---

## Deep Analysis

### Feature 1: Drag Text Selection

**How it should work:**
1. User drags from point A to B in any pane
2. Text between A-B gets selected (visual highlight)
3. On mouse release: copy selected text to clipboard
4. Visual feedback (highlight like copy-mode)

**Implementation:**
- **In `server.py` `handle_mouse()`**: 
  - Detect drag on panel (not border)
  - Track drag start (cx, cy in pane)
  - On `drag`: calculate selection rect
  - On `up`: if selection exists, copy to clipboard + optionally enter copy-mode
  
- **New state in `ClientState`**:
  - `mouse_drag_start`: (x, y) of drag origin
  - `mouse_drag_pane`: which pane user is dragging in
  - `mouse_selection`: current selection (like copy-mode anchor)

- **Visual feedback**:
  - Highlight selected cells (inverse video, like copy-mode)
  - Show in `render_frame()` similar to copy-mode

---

### Feature 2: Right-Click Context Menu

**How it should work:**
```
Right-click on pane:
  ┌─────────────────────┐
  │ Copy selection      │ (if text selected)
  │ Paste               │ (if clipboard has text)
  │ ─────────────────   │
  │ Kill pane           │
  └─────────────────────┘
```

**Implementation:**
- **New mode**: `ClientState.mode = "context"` (like `"choose"`, `"confirm"`)
- **Store context menu state**:
  - Which pane right-clicked
  - Menu options
  - Current selection
- **Render**: Show menu as overlay (like choose-window, confirm-before)
- **Keys**: Up/Down to navigate, Enter to select, Escape to close

---

### Feature 3: Get Clipboard (Read)

**Current issue**: `clipboard.py` only has `set_clipboard_text()`, no `get_clipboard_text()`

**Implementation**:
```python
def get_clipboard_text() -> str | None:
    """Get text from Windows clipboard (CF_UNICODETEXT)."""
    # Use GetClipboardData(CF_UNICODETEXT)
    # Similar to set but reads instead
```

---

### Feature 4: Paste to Pane

**How it should work:**
1. Detect right-click → "Paste" action
2. Read clipboard via `get_clipboard_text()`
3. Encode text to pane input
4. Write to pane.write(text)

**Implementation**:
- Hook in `handle_mouse()` right-click handler
- Or keyboard shortcut: `Ctrl+Shift+V` → paste from clipboard

---

### Feature 5: Kill Pane by Mouse

**How it should work:**
- Right-click menu → "Kill pane" option
- Calls `close_pane()` or `kill_pane()`

---

## Technical Details

### Mouse Coordinate Space
- `x, y` from ReadConsoleInputW are 0-based, relative to console
- Panel layout gives `Rect(x, y, w, h)` for each pane
- Must convert console coordinates → pane-relative coordinates:
  ```
  pane_x = console_x - pane_rect.x
  pane_y = console_y - pane_rect.y
  ```

### Selection Rendering
- Copy existing logic from `copymode.py`:
  - `_in_sel()`: Check if cell (line, col) is in selection
  - Render with inverse video (SGR code 7)
- Integrate into `render.py` frame rendering

### State Management
- ClientState gets new fields:
  - `mouse_drag`: dict with start point, pane, etc.
  - `context_menu`: dict with menu state (visible, options, selected_idx)
- Clean up on mode change, click elsewhere, etc.

---

## Implementation Order

### Phase 1: Foundation (30 min)
1. **Add `get_clipboard_text()` to `clipboard.py`**
   - Use Windows GetClipboardData API
   - Return None if clipboard empty/not text

2. **Extend `ClientState`** with mouse selection fields
   ```python
   self.mouse_drag_start: tuple[int, int] | None = None
   self.mouse_drag_pane: Pane | None = None
   self.mouse_selection: tuple[tuple[int, int], tuple[int, int]] | None = None
   ```

### Phase 2: Drag Selection (45 min)
1. **Modify `handle_mouse()` to detect drag on panel**
   - On `down`: record drag start if over pane
   - On `drag`: calculate selection (world coords → pane coords)
   - On `up`: save selection, copy to clipboard

2. **Render drag selection** in `render_frame()`
   - Highlight selected cells (inverse video like copy-mode)

3. **Helper function**: world_to_pane_coords(x, y, pane_rect)

### Phase 3: Right-Click Menu (60 min)
1. **Detect right-click in `handle_mouse()`**
   - Set mode to `"context_menu"`
   - Store which pane, position, etc.

2. **Render menu** in `render_frame()`
   - Overlay box with options
   - Show which option is highlighted

3. **Handle keys** in `handle_key()`
   - Mode `"context_menu"`: Up/Down navigate, Enter select, Escape close
   - Dispatch: copy, paste, kill

4. **Implement actions**:
   - Copy: `set_clipboard_text(selection_text)`
   - Paste: `pane.write(get_clipboard_text())`
   - Kill: `close_pane(pane)`

### Phase 4: Polish (30 min)
1. Test edge cases (empty clipboard, no selection, etc.)
2. Keyboard shortcut for paste (Ctrl+Shift+V)
3. Visual feedback (beep on invalid action?)

---

## Files to Modify/Create

| File | Changes |
|------|---------|
| `clipboard.py` | Add `get_clipboard_text()` |
| `server.py` | Extend `handle_mouse()`, `ClientState.reset_overlays()` |
| `render.py` | Render mouse selection highlight + context menu |
| `client.py` | No changes (mouse events already handled) |
| `keys.py` | No changes (mouse decode already works) |

---

## Testing Strategy

```python
# tests/test_mouse_selection.py
def test_drag_selection_copies_to_clipboard():
    # Simulate drag event from (10, 5) to (20, 5)
    # Verify clipboard contains selected text

def test_right_click_menu_navigation():
    # Show menu, press Up/Down, verify highlighted option

def test_paste_from_clipboard():
    # Set clipboard, right-click paste, verify text in pane

def test_kill_pane_from_menu():
    # Right-click, select kill, verify pane closes
```

---

## User Experience

### Scenario 1: Copy Text by Drag
```
[User drags over text in terminal]
→ Text highlights (inverse video)
[Mouse up]
→ Text copied to Windows clipboard
→ Can paste elsewhere (Notepad, etc.)
```

### Scenario 2: Paste from Clipboard
```
[Text in Windows clipboard]
[User right-click on pane]
→ Menu appears: Copy selection | Paste | Kill pane
[User clicks "Paste"]
→ Text appears in terminal (as if typed)
```

### Scenario 3: Kill Terminal
```
[User right-click on hanging pane]
→ Menu appears
[User clicks "Kill pane"]
→ Pane terminates, window redraws
```

---

## Why This Matters

1. **Copy**: No more `Ctrl+B [` → navigate → Enter. Just drag & paste.
2. **Paste**: No more copy-paste to clipboard then manual input. Direct paste.
3. **Kill**: Force-close hung terminal from mouse (not just keyboard).
4. **Consistency**: Matches Windows Terminal / ConEmu UX.

---

## Complexity Assessment

- **Moderate** (not trivial, but straightforward)
- Main work: coordinate conversion, menu rendering, state management
- No new external dependencies
- Reuses existing selection rendering (from copymode)

---

**Estimated total time: 2-3 hours implementation + testing**

