"""Regresión: "Claude se deforma cuando la pantalla está dividida".

Al dividir la ventana, el panel se redimensiona de ancho completo a la mitad.
Las TUI full-screen (Claude Code) repintan posicionando el cursor y escribiendo
los espacios como CUF (ESC[<n>C); además suelen emitir primero un frame al ancho
VIEJO antes de repintar al nuevo. pyte no reflowa, así que:

1. las celdas viejas DENTRO del nuevo ancho sobreviven al resize y se filtran
   entre el texto repintado (guiones/restos de bordes), y
2. el frame al ancho viejo (más ancho que el panel) hace wrap+scroll y deja
   filas residuales que el repintado incremental ya no borra.

Pane.resize() corrige ambas: limpia la pantalla visible y desactiva el autowrap
durante una ventana de settle (RESIZE_SETTLE); _read_loop lo restaura al expirar.
"""

import time

import pyte

from tmuxw.pane import RESIZE_SETTLE, Pane, PaneScreen, PaneStream


def _kill(pane: Pane) -> None:
    try:
        pane.kill()
    except Exception:
        pass


# ----------------------------------------------- código real de Pane.resize
def test_resize_limpia_pantalla_y_desactiva_autowrap():
    pane = Pane(0, 100, 30, command="cmd.exe")
    try:
        with pane.lock:
            pane.stream.feed("\x1b[5;1Hbasura del tamaño viejo")
        assert pyte.modes.DECAWM in pane.screen.mode  # autowrap on por defecto

        assert pane.resize(50, 20) is True

        with pane.lock:
            # (1) la pantalla visible quedó en blanco (sin restos del ancho viejo)
            assert all(
                (pane.screen.buffer[y][x].data or " ") == " "
                for y in range(pane.rows)
                for x in range(pane.cols)
            )
            # (2) autowrap desactivado durante la ventana de settle
            assert pyte.modes.DECAWM not in pane.screen.mode
            assert pane._wrap_resume_at > time.monotonic()
    finally:
        _kill(pane)


def test_resize_sin_cambio_no_toca_autowrap():
    pane = Pane(0, 80, 24, command="cmd.exe")
    try:
        assert pane.resize(80, 24) is False
        assert pyte.modes.DECAWM in pane.screen.mode
        assert pane._wrap_resume_at == 0.0
    finally:
        _kill(pane)


# --------------------------------------------- mecanismo (determinista, sin proc)
def _residue_rows(screen: PaneScreen, first_blank: int) -> list[int]:
    """Filas >= first_blank que NO están en blanco (residuo del frame viejo)."""
    out = []
    for y in range(first_blank, screen.lines):
        if any((screen.buffer[y][x].data or " ") != " " for x in range(screen.columns)):
            out.append(y)
    return out


def test_frame_ancho_viejo_con_autowrap_deja_residuo():
    """Contraste: con autowrap ON, una línea al ancho viejo hace wrap y deja
    una segunda fila de residuo (el bug)."""
    screen = PaneScreen(60, 10, history=50)
    stream = PaneStream(screen)
    stream.feed("\x1b[H" + "─" * 120)  # frame al ancho viejo (120) en panel de 60
    assert _residue_rows(screen, 1), "se esperaba residuo con autowrap activo"


def test_frame_ancho_viejo_sin_autowrap_no_deja_residuo():
    """Como Pane.resize: con autowrap OFF, la línea al ancho viejo NO hace wrap;
    se queda en una sola fila y no deja residuo para el repintado siguiente."""
    screen = PaneScreen(60, 10, history=50)
    screen.mode.discard(pyte.modes.DECAWM)
    stream = PaneStream(screen)
    stream.feed("\x1b[H" + "─" * 120)  # mismo frame al ancho viejo
    assert _residue_rows(screen, 1) == [], "con autowrap OFF no debe haber residuo"


def test_resize_settle_es_positivo():
    assert RESIZE_SETTLE > 0
