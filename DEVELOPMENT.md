# 👨‍💻 Development Guide — tmux-w

Quick start for developers working on tmux-w.

## Prerequisites

- **Windows 10/11** (ConPTY support required)
- **Python 3.10+** (3.12 recommended; 3.13/3.14 have pywinpty issues)
- **PowerShell 5.1+** (for dev scripts)

## Quick Setup

```powershell
# One-time setup (30 seconds)
& .\scripts\setup.ps1

# or manual:
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Development Workflow

### Running Tests

```powershell
# All tests
& .\scripts\test.ps1

# Filter by pattern
& .\scripts\test.ps1 -Pattern "keys"

# With coverage
& .\scripts\test.ps1 -Coverage
```

### Linting & Formatting

```powershell
# Check code style
& .\scripts\lint.ps1

# Auto-fix issues
& .\scripts\lint.ps1 -Fix
```

### Full Dev Cycle

```powershell
# Setup + lint + test (all in one)
& .\scripts\dev.ps1

# Quick test only
& .\scripts\dev.ps1 -Mode quick
```

### Pre-commit Hooks (Optional)

Install hooks to auto-fix code before commit:

```powershell
pip install pre-commit
pre-commit install
```

Now every `git commit` will check/fix formatting automatically.

## Project Structure

```
tmuxw-w/
├── tmuxw/
│   ├── __main__.py       # Entry point (CLI)
│   ├── cli.py            # Command parsing
│   ├── server.py         # Server loop (TCP, sessions, rendering)
│   ├── client.py         # Interactive client (console raw+VT)
│   ├── pane.py           # Panel: ConPTY + pyte screen
│   ├── keys.py           # Keyboard: decode console → keyspec → VT
│   ├── model.py          # Data: Session, Window, Pane
│   ├── layout.py         # Split tree & pane resize
│   ├── render.py         # Frame render (ANSI output)
│   ├── commands.py       # Tmux command dispatcher
│   ├── config.py         # Config file parsing (~/.tmuxw.conf)
│   ├── copymode.py       # Copy-mode state & selection
│   ├── options.py        # User settings
│   └── ...
├── tests/
│   ├── test_keys.py      # Keyboard decoding tests
│   ├── test_commands.py  # Command execution tests
│   ├── test_integration.py
│   └── ...
├── scripts/
│   ├── setup.ps1         # Env setup
│   ├── test.ps1          # Run tests
│   ├── lint.ps1          # Check code style
│   └── dev.ps1           # Master dev script
├── FUNCIONALIDADES.md    # Full spec (Spanish)
├── AUTOMATION_CHECKLIST.md
└── ...
```

## Key Concepts

### Architecture

- **Server** (`server.py`): TCP loopback `127.0.0.1:<port>`, maintains sessions/windows/panes
- **Pane** (`pane.py`): ConPTY subprocess + `pyte.HistoryScreen` (VT100 emulator) + scrollback
- **Client** (`client.py`): Raw console mode + VT rendering, sends keystrokes → server
- **Protocol**: JSON-lines over TCP (keystrokes, mouse, frames)

### Important Files

| File | Purpose |
|------|---------|
| `keys.py` | Keyboard: console input → keyspec → VT sequence |
| `pane.py` | Panel execution via ConPTY |
| `server.py` | Main loop, key handling, command dispatch |
| `render.py` | Frame rendering (status line, panes, overlays) |
| `commands.py` | Tmux commands (split-window, select-pane, etc.) |

### Common Tasks

#### Adding a New Command

1. Define it in `commands.py` → `execute_command()`
2. Add to `DEFAULT_BINDINGS` for default keybinding
3. Test in `tests/test_commands.py`

Example:
```python
# commands.py
def cmd_my_command(server, client, args):
    """Do something."""
    # Implement
    return None  # or error message
```

#### Adding a New Keybinding

1. In `~/.tmuxw.conf`:
   ```tmux
   bind -n C-g select-window -t :1
   ```

2. Or in code (`server.py` → `DEFAULT_BINDINGS`):
   ```python
   DEFAULT_BINDINGS["my-key"] = ["command", "args"]
   ```

#### Debugging a Pane

1. Check `pane.py`: How ConPTY subprocess is spawned
2. Check `keys.py`: How input is decoded → sent to pane
3. Check `render.py`: Screen content rendering
4. Print debugging:
   ```python
   import sys
   print("Debug:", thing, file=sys.stderr)  # stderr won't interfere with ANSI output
   ```

#### Testing Keyboard Input

Look at `tests/test_keys.py`:

```python
from tmuxw.keys import decode_key_event, keyspec_to_vt

# ReadConsoleInputW delivers: vk=0x43 (C), ch='c', state with Ctrl
result = decode_key_event(key_down=True, vk=0x43, ch='c', state=0x0008)
assert result == "C-c"

# Convert to VT sequence
vt = keyspec_to_vt("C-c")
assert vt == "\x03"  # SIGINT
```

## Performance Notes

### Slow Operations

- **First attach**: Server startup (not cached yet)
- **Large scrollback**: History rendering for copy-mode (history-limit default 2000)
- **Integration tests**: They spawn real ConPTY + subprocesses (slow)

### Optimization Tips

- Keep `history-limit` reasonable (default 2000)
- Use `set -g status off` to reduce frame rendering if needed
- Test-only changes? Run `pytest tests/test_keys.py` instead of full suite
- Pre-commit hooks cache fixes between hooks (faster)

## CI/CD

Workflows run automatically on push/PR:

- **tests.yml**: `pytest` on Python 3.10/3.11/3.12
- **lint.yml**: `ruff` code style check
- **build.yml**: Verify packaging (wheel, sdist)

Check GitHub Actions tab for results.

## Tips & Tricks

### Interactive Testing

```powershell
# Start a dev server
.\tmuxw.cmd new -s test

# In another terminal, test commands
.\tmuxw.cmd send-keys -t test "echo hello" Enter
.\tmuxw.cmd split-window -h -t test
```

### Debugging Server

```powershell
# Kill server
.\tmuxw.cmd kill-server

# Start with logging (if implemented)
# Check %LOCALAPPDATA%\tmuxw\server.log
```

### Code Style

- Ruff enforces: PEP8, import sorting, unused var detection
- Line length: 100 chars
- Format: `black`-style (via ruff format)
- Pre-commit auto-fixes before commit

---

**Last updated**: 2026-06-11  
**Questions?** Check FUNCIONALIDADES.md or GitHub Issues
