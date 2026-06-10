# tmux-w — Especificación funcional completa

**tmux-w** es un clon de [tmux](https://github.com/tmux/tmux) 100% nativo para Windows, usable desde
PowerShell / Windows Terminal. Replica la arquitectura y las funcionalidades de tmux usando
**ConPTY** (la API de pseudoconsola de Windows) en lugar de PTYs de Unix.

Comando: `tmuxw` (alias del módulo Python `tmuxw`).

---

## 1. Arquitectura (idéntica en concepto a tmux)

tmux real es un programa C con un **servidor** que mantiene todo el estado y **clientes** que se
conectan por un socket Unix en `/tmp`. tmux-w replica esto:

| Concepto tmux | Implementación tmux-w |
|---|---|
| Servidor (`server.c`) | Proceso Python en segundo plano (`tmuxw server`), sobrevive al cierre de la consola |
| Socket Unix `/tmp/tmux-UID/default` | TCP loopback `127.0.0.1:<puerto>` + token de autenticación en `%LOCALAPPDATA%\tmuxw\server.json` |
| PTY (forkpty) | **ConPTY** vía `pywinpty` — cada panel es una pseudoconsola con su proceso (PowerShell por defecto) |
| Emulación de terminal (`grid.c`, `screen-write.c`) | `pyte.HistoryScreen` — un emulador VT100/ANSI por panel con scrollback |
| Cliente (`client.c`) | `tmuxw attach` — pone la consola en modo raw + VT, reenvía teclas al servidor y pinta los frames que recibe |
| Protocolo imsg | JSON por líneas sobre TCP (ver §10) |

```
┌────────────┐  teclas →   ┌──────────────────────────────────────────┐
│  cliente   │             │  SERVIDOR tmuxw                           │
│ (consola   │             │  Session "main"                           │
│  PowerShell│  ← frames   │   ├─ Window 0: powershell ┌─────┬─────┐  │
│  en raw+VT)│   ANSI      │   │   panes (ConPTY+pyte) │ ps1 │ ps2 │  │
└────────────┘             │   └─ Window 1: build      └─────┴─────┘  │
      ⋮ N clientes         │  Session "otra" …                        │
└──────────────────────────└──────────────────────────────────────────┘
```

- El servidor **arranca automáticamente** con el primer `tmuxw new` y **muere** cuando se cierra la
  última sesión (igual que tmux).
- Las sesiones siguen vivas al desconectar el cliente (**detach**) — los procesos siguen corriendo.
- Varios clientes pueden conectarse a la misma sesión simultáneamente (vista espejada).

## 2. Jerarquía: sesiones → ventanas → paneles

- **Sesión**: grupo nombrado de ventanas (nombres por defecto `0`, `1`, …). Tiene ventana actual y
  ventana anterior (`last`).
- **Ventana**: pantalla completa con nombre e índice (`base-index`, 0 por defecto), contiene 1+
  paneles en un **árbol binario de splits** con ratios ajustables. Una ventana tiene panel activo,
  flag de **zoom** (`-Z`) y layouts predefinidos rotables.
- **Panel**: una pseudoconsola ConPTY corriendo un proceso (PowerShell por defecto, configurable con
  `default-shell`), con scrollback de `history-limit` líneas, título, PID y estado vivo/muerto.

## 3. CLI

```
tmuxw                              # new-session si no hay servidor; si hay, attach a la última
tmuxw new  [-s nombre] [-n vent] [-d] [comando]
tmuxw attach|a [-t sesión]
tmuxw ls                           # list-sessions
tmuxw kill-server
tmuxw kill-session -t sesión
tmuxw <cualquier-comando> [args]   # modo control: ejecuta el comando en el servidor (p.ej.
                                   # tmuxw split-window -h -t main; tmuxw send-keys -t main "dir" Enter)
```

## 4. Tecla prefijo y atajos por defecto

Prefijo: **`C-b`** (configurable con `set -g prefix`). `C-b C-b` envía `C-b` literal al panel.

| Atajo | Acción | Comando equivalente |
|---|---|---|
| `C-b c` | Nueva ventana | `new-window` |
| `C-b ,` | Renombrar ventana | `rename-window` (prompt) |
| `C-b &` | Matar ventana (confirma y/n) | `kill-window` |
| `C-b %` | Dividir en izquierda/derecha | `split-window -h` |
| `C-b "` | Dividir en arriba/abajo | `split-window -v` |
| `C-b x` | Matar panel (confirma y/n) | `kill-pane` |
| `C-b d` | Desconectar cliente | `detach-client` |
| `C-b $` | Renombrar sesión | `rename-session` (prompt) |
| `C-b n` / `C-b p` | Ventana siguiente / anterior | `next-window` / `previous-window` |
| `C-b l` | Última ventana | `last-window` |
| `C-b 0`–`9` | Ir a ventana por índice | `select-window -t :N` |
| `C-b w` | Selector de ventanas (overlay) | `choose-window` |
| `C-b s` | Selector de sesiones (overlay) | `choose-session` |
| `C-b o` | Siguiente panel | `select-pane -t :.+` |
| `C-b ;` | Panel anterior (alternar) | `last-pane` |
| `C-b ←↑→↓` | Moverse entre paneles | `select-pane -L/-U/-R/-D` |
| `C-b C-←↑→↓` | Redimensionar panel (1 celda) | `resize-pane -L/-U/-R/-D` |
| `C-b M-←↑→↓` | Redimensionar panel (5 celdas) | `resize-pane -L/-U/-R/-D 5` |
| `C-b z` | Zoom/unzoom panel | `resize-pane -Z` |
| `C-b Space` | Siguiente layout predefinido | `next-layout` |
| `C-b {` / `C-b }` | Intercambiar panel con anterior/siguiente | `swap-pane -U` / `-D` |
| `C-b C-o` | Rotar paneles | `rotate-window` |
| `C-b q` | Mostrar números de panel (saltar con dígito) | `display-panes` |
| `C-b [` | Entrar en copy-mode | `copy-mode` |
| `C-b ]` | Pegar buffer | `paste-buffer` |
| `C-b PgUp` | Copy-mode + página arriba | `copy-mode -u` |
| `C-b :` | Prompt de comandos en la status line | `command-prompt` |
| `C-b ?` | Listar atajos | `list-keys` |
| `C-b t` | Reloj | `clock-mode` |
| `C-b (` / `C-b )` | Sesión anterior / siguiente | `switch-client -p/-n` |

Todos los atajos son redefinibles con `bind-key` / `unbind-key`.

## 5. Comandos (con alias, como tmux)

Sesiones: `new-session`(new) `attach-session`(attach,a) `detach-client`(detach) `kill-session`
`rename-session`(rename) `list-sessions`(ls) `has-session`(has) `switch-client`(switchc) `kill-server`

Ventanas: `new-window`(neww) `kill-window`(killw) `select-window`(selectw) `next-window`(next)
`previous-window`(prev) `last-window`(last) `rename-window`(renamew) `list-windows`(lsw)
`next-layout`(nextl) `rotate-window`(rotatew) `choose-window` `choose-session`

Paneles: `split-window`(splitw) `-h|-v [-p %] [-t destino] [comando]` · `select-pane`(selectp)
`-L -R -U -D` · `last-pane`(lastp) · `kill-pane`(killp) · `swap-pane`(swapp) `-U|-D` ·
`resize-pane`(resizep) `-L -R -U -D -Z [n]` · `list-panes`(lsp) · `display-panes`(displayp)

Buffers/copy: `copy-mode [-u]` `paste-buffer`(pasteb) `set-buffer`(setb) `show-buffer`(showb)
`list-buffers`(lsb) `send-keys`(send) `[-t destino] tecla|texto …`

Config/varios: `set-option`(set) `[-g] opción valor` · `show-options`(show) · `bind-key`(bind) ·
`unbind-key`(unbind) · `list-keys`(lsk) · `command-prompt` · `display-message`(display) `[-p] [msg]` ·
`source-file`(source) · `clock-mode` · `kill-server`

**Destinos** (`-t`): `sesión`, `sesión:ventana`, `:índice`, `:nombre` — subconjunto práctico de la
sintaxis de tmux.

## 6. Opciones (`set -g opción valor`)

| Opción | Defecto | Descripción |
|---|---|---|
| `prefix` | `C-b` | Tecla prefijo |
| `default-shell` | `powershell.exe` | Programa de los paneles nuevos (admite `pwsh.exe`, `cmd.exe`…) |
| `base-index` | `0` | Primer índice de ventana |
| `history-limit` | `2000` | Líneas de scrollback por panel |
| `mode-keys` | `emacs` | Estilo de teclas en copy-mode (`vi`/`emacs`) |
| `status` | `on` | Mostrar status line |
| `status-style` | `bg=green,fg=black` | Colores de la status line |
| `status-interval` | `15` | Segundos entre refrescos del reloj |
| `status-left` | `[#S] ` | Formato izquierdo |
| `status-right` | `"#H" %H:%M %d-%b-%y` | Formato derecho |
| `display-time` | `750` | ms que dura un `display-message` |
| `display-panes-time` | `1000` | ms que dura `display-panes` |
| `pane-border-style` | `fg=default` | Color de bordes |
| `pane-active-border-style` | `fg=green` | Color del borde del panel activo |
| `message-style` | `bg=yellow,fg=black` | Estilo de mensajes/prompt |
| `mouse` | `off` | (roadmap, ver §12) |

Estilos: `bg=color,fg=color,bold` con colores con nombre (`black…white`, `bright*`), `colour0-255` y `default`.

**Formatos** en status-left/right: `#S` sesión, `#I` índice ventana, `#W` nombre ventana, `#P` índice
panel, `#H` host, `#T` título del panel, `#F` flags, y `strftime` (`%H:%M`, `%d-%b-%y`…).

## 7. Status line

Línea inferior verde (estilo tmux): `[sesión] 0:powershell* 1:build-  …  "host" 19:42 10-jun-26`

- Ventana actual marcada `*`, anterior `-`, con campana/actividad `!` (roadmap).
- La status line se convierte en **prompt** con `C-b :` (edición con cursor, historial ↑↓, Esc cancela)
  y en **mensaje** temporal con `display-message`.
- Confirmaciones `y/n` para `kill-pane`/`kill-window` (`confirm-before`).

## 8. Copy-mode (scrollback)

`C-b [` congela la vista del panel y permite navegar el historial. Indicador `[pos/total]` arriba a
la derecha. Teclas (modo `emacs` y `vi` según `mode-keys`):

| Acción | emacs | vi |
|---|---|---|
| Salir | `q` / `Escape` | `q` / `Escape` |
| Mover | flechas, `PgUp/PgDn`, `Home/End` | `h j k l`, `C-u/C-d`, `g/G`, `0/$`, `w/b` |
| Iniciar selección | `Space` | `Space` / `v` |
| Copiar y salir | `Enter` / `C-w` | `Enter` / `y` |
| Buscar | `C-s` / `C-r` | `/` `?` + `n`/`N` |
| Media página | `M-Up/M-Down` | `C-u` / `C-d` |

Lo copiado va a la **pila de buffers** interna *y al portapapeles de Windows*. `C-b ]` pega el último
buffer en el panel activo (`\n`→`\r`).

## 9. Archivo de configuración

`~/.tmuxw.conf` (también acepta `~/.tmux.conf` si el primero no existe) se ejecuta al arrancar el
servidor. Sintaxis tmux: comentarios `#`, comillas simples/dobles, una orden por línea.

```tmux
# ejemplo
set -g prefix C-a
set -g base-index 1
set -g mode-keys vi
set -g status-style bg=blue,fg=white
bind | split-window -h
bind - split-window -v
unbind '"'
```

`source-file ruta` recarga un archivo en caliente.

## 10. Protocolo cliente⇄servidor (JSON-lines sobre TCP loopback)

Cliente→servidor: `attach {session,w,h,create}` · `key {k:"C-b"|"a"|"Up"…}` · `text {s}` ·
`resize {w,h}` · `cmd {s:"split-window -h"}` (modo control) · `detach`
Servidor→cliente: `frame {d:"<ANSI completo>"}` · `msg {s}` · `detached` · `exit {msg}` · `error {msg}`

El primer mensaje debe llevar el `token` de `server.json` (auth). El servidor renderiza el frame
compuesto (paneles+bordes+status) al tamaño de cada cliente, con *synchronized output*
(`CSI ?2026h/l`) para evitar parpadeo, y solo cuando hay cambios (~30 fps máx).

## 11. Cliente: requisitos de consola

- Windows 10 1809+ (ConPTY). Recomendado **Windows Terminal**; funciona en conhost.
- El cliente activa `ENABLE_VIRTUAL_TERMINAL_PROCESSING` (salida ANSI), desactiva
  línea/eco/`PROCESSED_INPUT` (para capturar `C-c`), usa pantalla alternativa (`CSI ?1049h`) y
  detecta redimensionado de la consola (repropaga a las sesiones).
- Las teclas se decodifican de la consola Windows (incl. `\x00/\xe0` extendidas, F1-F12,
  Ctrl/Alt+flechas) a *keyspecs* tipo tmux (`C-b`, `M-x`, `Up`, `F5`…).

## 12. Diferencias conocidas con tmux real (roadmap)

| Área | Estado |
|---|---|
| Mouse (click panel, arrastrar bordes, rueda→copy-mode) | Roadmap |
| Hooks, `if-shell`, `run-shell`, formatos `#{…}` completos | Roadmap (formatos: subconjunto `#X`) |
| `link-window`, sesiones agrupadas, `move-pane` entre ventanas | Roadmap |
| Plugins (tpm), `popup`, `menu` | Fuera de alcance v1 |
| Layouts: `next-layout` rota 4 presets (even-h, even-v, main-v, tiled) | Subconjunto |
| ConPTY añade su propio repintado VT; apps TUI complejas pueden parpadear | Limitación de ConPTY |

Todo lo demás de §§3-9 está **implementado y probado**.

---

## 13. Equipo de agentes de desarrollo y QA

El proyecto se construye y mantiene con un equipo de agentes IA coordinados por un **orquestador**:

```
                      ┌──────────────────────┐
                      │  ORQUESTADOR (lead)  │  diseña la arquitectura, integra, decide
                      └─────┬──────────┬─────┘
              ┌─────────────┘          └──────────────┐
      ┌───────┴────────┐                    ┌─────────┴─────────┐
      │   AGENTES DEV  │                    │    AGENTES QA     │
      ├────────────────┤                    ├───────────────────┤
      │ dev-config     │ config.py/options  │ qa-unit           │ pytest unitarios
      │ dev-keys       │ keys.py decodific. │ qa-integration    │ servidor+cliente+ConPTY real
      │ dev-fix        │ corrige bugs de QA │ qa-revalidación   │ re-ejecuta tras cada fix
      └────────────────┘                    └───────────────────┘
```

**Flujo conjunto dev ⇄ QA:**
1. El orquestador escribe esta especificación (contrato) y el núcleo acoplado (panes, servidor, render).
2. Los **agentes dev** implementan módulos aislados contra el contrato, *con sus propias pruebas unitarias*.
3. Los **agentes QA** (con subagentes por área) escriben y ejecutan la suite completa:
   unitarias (layout, config, opciones, teclas, comandos, protocolo) + integración (servidor real,
   cliente falso por TCP, panel ConPTY real ejecutando PowerShell) y emiten `QA_REPORT.md`
   con cada bug: severidad, reproducción, módulo.
4. El **agente dev-fix** corrige cada hallazgo; QA re-valida. Se itera hasta suite en verde.
5. El orquestador hace la verificación final de humo en consola real.

**Criterios de aceptación QA:**
- `pytest` 100% en verde en Windows.
- Crear sesión, dividir 2×2, ejecutar `dir` en cada panel y verificar salida en el frame.
- Detach → los procesos siguen vivos → attach recupera la pantalla.
- `tmuxw ls`, `kill-session`, `kill-server` limpian procesos y `server.json`.
- Config con `prefix C-a`, `bind | split-window -h` funciona.
- Copy-mode: copiar texto del scrollback y pegarlo en otro panel.
