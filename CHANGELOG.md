# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Mouse selection, copy, paste support
- Right-click context menu (copy, paste, kill pane)
- Ctrl+Shift+V keyboard shortcut for paste
- CI/CD automation (GitHub Actions workflows)
- Development scripts (setup, test, lint)
- Pre-commit hooks
- Test parallelization with pytest-xdist
- Release automation workflow

### Changed
- Improved `decode_key_event()` to handle Ctrl+letter combos
- Restructured clipboard module with `get_clipboard_text()`

### Fixed
- Ctrl+C not working in panes (fixed key event decoding)

---

## [0.1.0] - 2026-06-11

### Added
- Initial release: tmux-w (tmux clone for Windows)
- Server + client architecture with TCP loopback
- Sessions → windows → panes on ConPTY
- Keyboard shortcuts (C-b prefix, all tmux commands)
- Copy-mode with keyboard selection
- Mouse support (click, drag, scroll)
- Configuration file (~/.tmuxw.conf)
- Status line, borders, layouts
- Full specification (FUNCIONALIDADES.md)

---

## Release Notes

### Version Format
- **Major.Minor.Patch** (e.g., 0.2.0)
- Bump major for breaking changes
- Bump minor for new features
- Bump patch for bug fixes

### Release Checklist
Before release:
1. Update CHANGELOG.md (unreleased → version)
2. Run tests locally: `& .\scripts\dev.ps1`
3. Commit and push: `git push origin main`
4. Run release script: `& .\scripts\release.ps1 -Version patch`
5. Push tag: `git push origin v*`
6. GitHub Actions handles the rest

### What's Automated
- ✅ Tests on Python 3.10/3.11/3.12
- ✅ Linting (ruff)
- ✅ Building (wheel + sdist)
- ✅ GitHub Release creation
- ✅ Artifact upload

---

## Guidelines for Contributors

When submitting changes, update CHANGELOG.md under `[Unreleased]`:

### Added
- New features (mouse selection, new commands, etc.)

### Changed
- Modifications to existing features
- Breaking changes

### Fixed
- Bug fixes

### Deprecated
- Features that are being phased out

### Removed
- Features that were removed

### Security
- Security vulnerability fixes

---

**Format Example:**
```markdown
### Added
- Mouse selection with auto-copy to clipboard (#123)
- Right-click context menu for copy/paste/kill

### Fixed
- Ctrl+C not working in panes (#120)

### Changed
- Improved import performance with lazy-loading
```

---

See git tags for historical versions:
```
git tag -l    # List all releases
git show v0.1.0  # View specific release
```
