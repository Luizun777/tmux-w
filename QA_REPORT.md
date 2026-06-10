# QA_REPORT — tmux-w

Informe del ciclo dev ⇄ QA descrito en FUNCIONALIDADES.md §13.
Equipo: orquestador + 2 agentes dev (config/opciones, teclado) + QA (suite completa) + dev-fix.

## Resultado final

| Suite | Tests | Estado |
|---|---|---|
| `test_options.py` / `test_config.py` (agente dev-config) | 98 | ✅ |
| `test_keys.py` (agente dev-keys) | 39 | ✅ |
| `test_layout.py` (teselado, splits, neighbor, resize, presets) | 36 | ✅ |
| `test_model.py` (ventanas/sesiones, índices, current/last) | 9 | ✅ |
| `test_copymode.py` (navegación, selección, búsqueda, vi/emacs) | 16 | ✅ |
| `test_commands.py` (Server real + panes falsos, ~40 comandos) | 33 | ✅ |
| `test_render.py` (SGR, formatos, status, overlays, zoom) | 14 | ✅ |
| `test_integration.py` (**E2E**: servidor real + ConPTY real + cliente TCP) | 10 | ✅ |
| **Total** | **241** | **✅ 100% en verde** |

E2E cubre los criterios de aceptación de la spec: attach crea sesión y llegan frames con
status `[qa]`; `send-keys`+`capture-pane` ve la salida real de cmd.exe; split por comando y por
binding `C-b "`; persistencia de paneles tras detach/re-attach; prompt de comandos con
`display-message` y formato `#S`; copy-mode con búsqueda `?`, selección y `show-buffer`;
rechazo de token inválido; `ls`/`kill-session`; `kill-server` borra `server.json` y termina el
proceso. El fixture verifica además **0 tracebacks** en `server.log`.

## Bugs encontrados y corregidos

| ID | Sev. | Módulo | Descripción | Detección |
|---|---|---|---|---|
| BUG-1 | Alta | `config.py` | `#` en mitad de token cortaba la línea (`display-message hola-#S` → `hola-`); tmux solo abre comentario a inicio de token | E2E manual del orquestador |
| BUG-2 | Media | `render.py` | La status line priorizaba `status-right` y omitía la lista de ventanas en anchos pequeños; tmux prioriza las ventanas y trunca el right | `test_render_frame_basic` |
| BUG-3 | Alta | `commands.py` | `bind \| split-window -h` fallaba: el parser de opciones consumía el `-h` del comando a vincular | `test_bind_unbind_list_keys` |
| BUG-4 | Media | `copymode.py` | `PgUp`/`PgDn` avanzaban 2 páginas (movían vista y cursor por separado) | `test_indicator` |
| BUG-5 | Alta | `pane.py` | `shutil.which` devuelve None con PATH estilo unix (Git Bash): los paneles no arrancaban; añadido fallback a System32/PATH `:` | smoke test |
| BUG-6 | Alta | `cli.py` | Consola cp1252 crasheaba con salida unicode (bordes/emoji); se fuerza stdout/stderr UTF-8 | smoke test |
| BUG-7 | Media | `render.py` | El prompt de confirmación (`kill-pane y/n`) no se mostraba en la status line | revisión del orquestador |
| BUG-8 | Baja | `pane.py` | Modo LNM forzado en pyte podía alterar saltos de línea de apps que emiten `\n` puro | revisión del orquestador |

Todos verificados con re-ejecución completa de la suite tras cada fix.

## Cobertura no automatizada (verificación manual pendiente del usuario)

- Cliente interactivo real (modo raw de consola + msvcrt) — requiere consola física;
  verificado el protocolo completo con cliente TCP simulado.
- Portapapeles de Windows en copy-mode (API ctypes probada como unidad aislada).

## Veredicto

**APTO.** Criterios de aceptación de FUNCIONALIDADES.md §13 cumplidos.
Ejecutar: `.venv\Scripts\python -m pytest tests -q` → 241 passed.
