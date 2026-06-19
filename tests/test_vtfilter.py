"""QA unitarias: tmuxw/vtfilter.py y PaneScreen/PaneStream (pane.py).

Las secuencias de los tests son las que Claude Code v2.x emite bajo el
ConPTY de Win11 24H2+ (passthrough), capturadas con scripts/capture_pty.py.
"""

from tmuxw.pane import PaneScreen, PaneStream
from tmuxw.vtfilter import VtSanitizer


def feed_all(*chunks: str) -> str:
    s = VtSanitizer()
    return "".join(s.feed(c) for c in chunks)


# ------------------------------------------------------------------ filtro
def test_kitty_keyboard_y_xtmodkeys_eliminadas():
    # ESC[<u / ESC[>1u (teclado kitty) y ESC[>4;2m / ESC[>0q (XTMODKEYS):
    # pyte dibujaría una "u" literal y aplicaría SGR 4;2 (subrayado+atenuado)
    assert feed_all("\x1b[<u\x1b[>1u\x1b[>4;2m\x1b[>0q") == ""


def test_secuencias_normales_pasan_intactas():
    s = '\x1b[19;3H\x1b[38;2;215;119;87m\x1b[1mTry\x1b[1C"algo"\x1b[m\x1b[K\r\n'
    assert feed_all(s) == s


def test_modos_privados_pasan_intactos():
    s = "\x1b[?2026h\x1b[?25l\x1b[?2004h\x1b[?1004h\x1b[?9001h\x1b[?2026l"
    assert feed_all(s) == s


def test_csi_con_intermedios_eliminadas():
    assert feed_all("\x1b[!p") == ""  # DECSTR: pyte dibujaría "p"
    assert feed_all("\x1b[2 q") == ""  # DECSCUSR


def test_sgr_con_subparametros_colon_eliminada():
    assert feed_all("\x1b[4:3m") == ""  # subrayado ondulado


def test_cadenas_dcs_eliminadas():
    assert feed_all("\x1bP+q544e\x1b\\hola") == "hola"
    assert feed_all("\x1b_apc-payload\x1b\\x") == "x"


def test_secuencia_partida_entre_lecturas():
    s = '\x1b[19;3H\x1b[m\x1b[<u\x1b[>1u\x1b[>4;2mTry "algo"'
    expected = '\x1b[19;3H\x1b[mTry "algo"'
    for i in range(len(s) + 1):
        assert feed_all(s[:i], s[i:]) == expected, f"corte en {i}"


def test_cola_esc_retenida_hasta_completarse():
    s = VtSanitizer()
    assert s.feed("abc\x1b") == "abc"
    assert s.feed("[<") == ""
    assert s.feed("u") == ""
    assert s.feed("hola") == "hola"


def test_osc_retenida_hasta_terminador():
    s = VtSanitizer()
    assert s.feed("\x1b]0;titulo lar") == ""
    assert s.feed("go\x07texto") == "\x1b]0;titulo largo\x07texto"


def test_texto_plano_intacto():
    s = "Windows PowerShell\r\nCopyright (C)\r\n"
    assert feed_all(s) == s


# ----------------------------------------------------- pantalla del panel
def make_screen(w: int = 80, h: int = 24) -> tuple[PaneScreen, PaneStream]:
    screen = PaneScreen(w, h, history=50)
    return screen, PaneStream(screen)


def row_text(screen: PaneScreen, y: int) -> str:
    line = screen.buffer[y]
    return "".join(line[x].data or " " for x in range(screen.columns)).rstrip()


def test_prologo_claude_no_corrompe_pantalla():
    # regresión: tras ESC[<u ESC[>1u ESC[>4;2m la "T" de "Try" se volvía
    # "u" ("ury ...") y el texto quedaba subrayado
    screen, stream = make_screen()
    san = VtSanitizer()
    stream.feed(san.feed('\x1b[5;3H\x1b[m\x1b[<u\x1b[>1u\x1b[>4;2mTry "algo"'))
    assert row_text(screen, 4) == '  Try "algo"'
    ch = screen.buffer[4][2]
    assert ch.data == "T"
    assert not ch.underscore


def test_csi_s_scroll_arriba():
    screen, stream = make_screen(10, 4)
    stream.feed("A\r\nB\r\nC\r\nD")
    stream.feed("\x1b[2S")
    assert [row_text(screen, y) for y in range(4)] == ["C", "D", "", ""]
    # las filas desplazadas pasan al historial (scrollback)
    hist = ["".join(line[x].data for x in range(2)).rstrip() for line in screen.history.top]
    assert hist[-2:] == ["A", "B"]


def test_csi_t_scroll_abajo():
    screen, stream = make_screen(10, 4)
    stream.feed("A\r\nB\r\nC\r\nD")
    stream.feed("\x1b[T")
    assert [row_text(screen, y) for y in range(4)] == ["", "A", "B", "C"]


def test_csi_s_respeta_margenes():
    screen, stream = make_screen(10, 4)
    stream.feed("A\r\nB\r\nC\r\nD")
    before = len(screen.history.top)
    stream.feed("\x1b[2;3r\x1b[1S")  # región = filas 2-3 (1-based)
    assert [row_text(screen, y) for y in range(4)] == ["A", "C", "", "D"]
    assert len(screen.history.top) == before  # región parcial: sin scrollback
