# 🤝 Contributing to tmux-w

Thank you for considering contributing! Here's how to get started.

## Code of Conduct

- Be respectful and inclusive
- Assume good intent
- Focus on the code, not the person

## Getting Started

1. **Fork & clone** the repository
2. **Run setup**:
   ```powershell
   & .\scripts\setup.ps1
   ```
3. **Read** [DEVELOPMENT.md](DEVELOPMENT.md)

## Making Changes

### Before You Start

- Check [existing issues](https://github.com/luisacosta360/tmux-w/issues) for duplicates
- For large changes, open an issue first to discuss
- Test locally: `& .\scripts\dev.ps1`

### Code Style

All code is automatically formatted with **Ruff**. Before submitting:

```powershell
# Auto-fix style issues
& .\scripts\lint.ps1 -Fix

# or use pre-commit hooks (optional but recommended)
pre-commit install
pre-commit run --all-files
```

No manual style debates—Ruff decides!

### Commit Messages

Keep messages clear and concise:

```
Fix Ctrl+C not working in panes

When Ctrl+C was pressed in a pane, the console was ignoring the Ctrl
modifier for printable characters, causing SIGINT not to be sent to
the subprocess. Now decode_key_event correctly generates C-c keyspecs
which are converted to \x03 and delivered to the pane.
```

**Format**:
- **Title**: one line, imperative mood (fix, add, update, not fixes/fixed)
- **Body**: explain the why, not the what (code shows what)

### Testing

All new features must have tests:

```powershell
# Run existing tests
& .\scripts\test.ps1

# Run your tests only
& .\scripts\test.ps1 -Pattern "your_feature"

# With coverage
& .\scripts\test.ps1 -Coverage
```

Test structure:
```python
# tests/test_myfeature.py
class TestMyFeature:
    def test_basic_case(self):
        # Arrange
        # Act
        # Assert
        assert result == expected
    
    def test_edge_case(self):
        ...
```

## Pull Request Process

1. **Create a branch**: `git checkout -b fix/ctrl-c-issue`
2. **Make changes** & commit locally
3. **Push**: `git push origin fix/ctrl-c-issue`
4. **Open PR** with:
   - Clear title & description
   - Reference any related issues (#123)
   - Brief test plan ("Tested with Angular dev server...")

### PR Checklist

- [ ] Code passes linting (`& .\scripts\lint.ps1`)
- [ ] Tests pass (`& .\scripts\test.ps1`)
- [ ] New tests for new code
- [ ] No breaking changes (or documented)
- [ ] Updated docs if needed (DEVELOPMENT.md, FUNCIONALIDADES.md)

### Automated Checks

Once you open a PR:
- **tests.yml** runs tests on Python 3.10/3.11/3.12
- **lint.yml** checks code style with Ruff
- **build.yml** verifies packaging

All must pass. If they fail:
1. Check the logs (click on the workflow)
2. Fix locally: `& .\scripts\dev.ps1`
3. Push again

## Types of Contributions

### 🐛 Bug Reports

Open an issue with:
- **Title**: "Ctrl+C not working in panes"
- **Reproduction steps**
- **Expected behavior**
- **Actual behavior**
- **Environment**: Windows version, Python version, tmux-w version

Example:
```
## Bug
Ctrl+C doesn't close Angular dev server in a tmux-w pane

## Steps
1. Run: tmuxw new -s test
2. Inside pane: ng serve
3. Press Ctrl+C
4. Server doesn't stop

## Expected
Server stops (like in regular PowerShell)

## Actual
Nothing happens; Ctrl+C is ignored

## Environment
- Windows 11 Pro, build 26200
- Python 3.12.1
- tmux-w v0.1.0
```

### ✨ Feature Requests

Open an issue with:
- **Title**: "Add mouse wheel scroll support"
- **Motivation**: Why do you need this?
- **Proposed solution**: If you have ideas

Example:
```
## Motivation
Scrolling in copy-mode is tedious with arrow keys

## Proposed Solution
Support mouse wheel to scroll up/down in copy-mode
(similar to tmux real)
```

### 📚 Documentation

Improvements to docs are welcome!
- Typo fixes
- Clarifications
- New examples

Just edit `.md` files and open a PR.

### ♻️ Refactoring

Code cleanups are welcome, but:
- No changes to behavior
- No new features
- Keep commits small & focused
- Comment why (non-obvious refactors)

## Development Tips

### Running Specific Tests

```powershell
# Just keyboard tests
& .\scripts\test.ps1 -Pattern "key"

# Just one file
python -m pytest tests/test_keys.py -v

# Just one test
python -m pytest tests/test_keys.py::TestParseKeyspec::test_ctrl_normaliza_minuscula -v
```

### Debugging

```powershell
# Server logs (if enabled)
cat $env:LOCALAPPDATA\tmuxw\server.log

# Console output during test
python -m pytest tests/ -vv -s

# Breakpoint (with pdb)
import pdb; pdb.set_trace()
```

### Code Review Tips

When reviewing your own code:
- Read the diff carefully (not just commit messages)
- Test locally with edge cases
- Check for consistency with existing code
- Ask yourself: "Will future me understand this?"

## Questions?

- 📖 Read [DEVELOPMENT.md](DEVELOPMENT.md)
- 📋 Check [FUNCIONALIDADES.md](FUNCIONALIDADES.md) (Spanish) for full spec
- 💬 Open an issue to ask
- 📧 Contact maintainer

---

**Thank you for contributing!** 🎉
