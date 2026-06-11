Primera versión pública de **tmux-w**: un clon de tmux 100% nativo para Windows sobre ConPTY, usable desde PowerShell / Windows Terminal.

## Funcionalidades

- **Servidor persistente** con sesiones → ventanas → paneles; las sesiones siguen vivas tras `detach` y puedes volver con `attach`.
- **Emulación VT por panel** con [pyte](https://github.com/selectel/pyte) y render ANSI.
- **Atajos tmux** con prefijo `C-b` (configurable): splits (`%`, `"`), zoom (`z`), copy-mode con scrollback (`[`), selector de ventanas (`w`), prompt de comandos (`:`) y más.
- **Soporte de ratón**: clic para enfocar panel, arrastre para redimensionar, rueda para scroll.
- **Modo control**: cualquier comando tmux desde fuera de la sesión — `split-window`, `send-keys`, `capture-pane`, `set`, etc.
- **Archivo de configuración** `~/.tmuxw.conf` (o `~/.tmux.conf`) con sintaxis tmux: `set -g`, `bind`, estilos de status line, `mode-keys vi`...
- **Status line** configurable.

## Requisitos

- Windows 10 1809+ (ConPTY). Recomendado Windows Terminal.
- Python 3.10 – 3.12.

## Instalación

```powershell
git clone https://github.com/Luizun777/tmux-w
cd tmux-w
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.\tmuxw.cmd new -s trabajo
```

## Calidad

274 tests pasando. Especificación completa en [FUNCIONALIDADES.md](https://github.com/Luizun777/tmux-w/blob/main/FUNCIONALIDADES.md); hallazgos de QA en `QA_REPORT.md`.
