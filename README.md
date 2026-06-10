# tmux-w

Clon de **tmux** 100% nativo para **Windows**, usable desde PowerShell / Windows Terminal.
Servidor persistente + sesiones + ventanas + paneles sobre **ConPTY** (la pseudoconsola de
Windows), con emulación VT por panel ([pyte](https://github.com/selectel/pyte)) y render ANSI.

> Especificación completa de funcionalidades, atajos, comandos y arquitectura: **[FUNCIONALIDADES.md](FUNCIONALIDADES.md)**

## Requisitos

- Windows 10 1809+ (ConPTY). Recomendado Windows Terminal.
- Python 3.10 – 3.12 (pywinpty no carga en 3.13/3.14 en algunas instalaciones).

## Instalación

```powershell
cd tmux-w
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
# opcional: añade la carpeta al PATH para usar tmuxw.cmd desde cualquier sitio
```

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
