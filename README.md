# tmux-w

[![Tests](https://github.com/luisacosta360/tmux-w/actions/workflows/tests.yml/badge.svg)](https://github.com/luisacosta360/tmux-w/actions/workflows/tests.yml)
[![Lint](https://github.com/luisacosta360/tmux-w/actions/workflows/lint.yml/badge.svg)](https://github.com/luisacosta360/tmux-w/actions/workflows/lint.yml)
[![Build](https://github.com/luisacosta360/tmux-w/actions/workflows/build.yml/badge.svg)](https://github.com/luisacosta360/tmux-w/actions/workflows/build.yml)

Clon de **tmux** 100% nativo para **Windows**, usable desde PowerShell / Windows Terminal.
Servidor persistente + sesiones + ventanas + paneles sobre **ConPTY** (la pseudoconsola de
Windows), con emulación VT por panel ([pyte](https://github.com/selectel/pyte)) y render ANSI.

> 📖 Especificación completa: **[FUNCIONALIDADES.md](FUNCIONALIDADES.md)**  
> 👨‍💻 Desarrollo: **[DEVELOPMENT.md](DEVELOPMENT.md)**  
> 🤝 Contribuir: **[CONTRIBUTING.md](CONTRIBUTING.md)**  
> 🔧 Automatización: **[AUTOMATION_CHECKLIST.md](AUTOMATION_CHECKLIST.md)**  
> 🖱️ Mouse Support: **[MOUSE_SELECTION_GUIDE.md](MOUSE_SELECTION_GUIDE.md)**  
> 📋 Changelog: **[CHANGELOG.md](CHANGELOG.md)**

## Requisitos

- Windows 10 1809+ (ConPTY). Recomendado Windows Terminal.
- Python 3.10 – 3.12 (pywinpty no carga en 3.13/3.14 en algunas instalaciones).

## Quick Start

### Installation (30 seconds)

```powershell
cd tmux-w

# Automated setup (recommended)
& .\scripts\setup.ps1

# or manual:
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
```

### Development (contribute code)

```powershell
# Full check: setup + lint + test
& .\scripts\dev.ps1

# Just run tests
& .\scripts\test.ps1

# Check code style
& .\scripts\lint.ps1
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for details.

## Release Process

To cut a new release:

```powershell
# Auto-bump version, commit, tag
& .\scripts\release.ps1 -Version patch

# Then push (GitHub Actions handles the rest)
git push origin main
git push origin v*
```

**What happens automatically:**
- ✅ Tests on Python 3.10/3.11/3.12
- ✅ Lint check (ruff)
- ✅ Build wheel + sdist
- ✅ Create GitHub Release
- ✅ Upload artifacts

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Uso rápido

```powershell
.\tmuxw.cmd new -s trabajo      # nueva sesión interactiva
# ... dentro: C-b % divide, C-b " divide en vertical, C-b d desconecta ...
.\tmuxw.cmd ls                  # lista sesiones (siguen vivas tras detach)
.\tmuxw.cmd attach -t trabajo   # vuelve a conectar
.\tmuxw.cmd kill-server         # mata todo
```

Cualquier comando tmux funciona también desde fuera (modo control):

```powershell
.\tmuxw.cmd split-window -h -t trabajo
.\tmuxw.cmd send-keys -t trabajo "dir" Enter
.\tmuxw.cmd capture-pane -p -t trabajo
.\tmuxw.cmd set -g prefix C-a
```

## Atajos esenciales (prefijo `C-b`)

| | |
|---|---|
| `c` nueva ventana · `n/p` siguiente/anterior · `0-9` ir a ventana | `%` split horizontal · `"` split vertical |
| `←↑→↓` moverse entre paneles · `z` zoom · `x` matar panel | `d` detach · `[` copy-mode · `]` pegar |
| `:` prompt de comandos · `?` lista de atajos · `w` selector de ventanas | `C-←↑→↓` redimensionar |

## Configuración

`~/.tmuxw.conf` (o `~/.tmux.conf`), sintaxis tmux:

```tmux
set -g prefix C-a
set -g mode-keys vi
set -g status-style bg=blue,fg=white
bind | split-window -h
bind - split-window -v
```

## Arquitectura

```
cliente (consola raw+VT) ⇄ TCP 127.0.0.1 (JSON-lines, token) ⇄ servidor
                                                  └─ sesiones → ventanas → paneles (ConPTY + pyte)
```

El servidor arranca solo con el primer `tmuxw new` y muere al cerrar la última sesión.
Estado en `%LOCALAPPDATA%\tmuxw\` (`server.json`, `server.log`).

## Desarrollo y pruebas

```powershell
.venv\Scripts\python -m pytest tests -q
```

El proyecto se construyó con un equipo de agentes IA (orquestador + agentes dev + agentes QA);
el flujo y los criterios de aceptación están en [FUNCIONALIDADES.md §13](FUNCIONALIDADES.md).
Los hallazgos de QA se documentan en `QA_REPORT.md`.

## Automatización ✅

**Estado**: Todos los 6 Tiers de automatización completados ✅
- ✅ CI/CD Workflows (tests, lint, build, release + tests-integration)
- ✅ Local Dev Scripts (setup, test, lint, dev orchestrator, release, profile)
- ✅ Pre-commit Hooks (ruff format + lint + linters)
- ✅ Performance Optimizations (parallel tests, split matrix, import profiling)
- ✅ Developer Documentation (DEVELOPMENT.md, CONTRIBUTING.md, MOUSE_SELECTION_GUIDE.md)
- ✅ Release Automation (auto-bump version, tag, GitHub Release)

Detalles:
- 📋 Checklist: [AUTOMATION_CHECKLIST.md](AUTOMATION_CHECKLIST.md)
- 🔍 Auditoría completa: [CHECKLIST_AUDIT.md](CHECKLIST_AUDIT.md)
