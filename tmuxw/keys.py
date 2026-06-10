"""Manejo de teclado de tmux-w.

Este módulo define la representación canónica de teclas ("keyspec" al estilo
tmux: ``a``, ``C-a``, ``M-x``, ``C-M-a``, ``Up``, ``F5``...) y las conversiones
entre las tres capas implicadas:

1. Notación de usuario (config / send-keys)  -> keyspec      (`parse_keyspec`)
2. Entrada de la consola Windows (msvcrt)    -> keyspec      (`ctrl_char_to_keyspec`,
                                                              `decode_extended`,
                                                              `ConsoleKeyReader`)
3. keyspec -> secuencia VT que se escribe al ConPTY del panel (`keyspec_to_vt`)

El módulo es importable sin consola: ``msvcrt`` solo se importa dentro de los
métodos de `ConsoleKeyReader`.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Nombres especiales: alias (case-insensitive, en minúsculas) -> canónico
# ---------------------------------------------------------------------------

SPECIAL_NAMES: dict[str, str] = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pgup": "PgUp",
    "pageup": "PgUp",
    "ppage": "PgUp",
    "pgdn": "PgDn",
    "pagedown": "PgDn",
    "npage": "PgDn",
    "ins": "Ins",
    "insert": "Ins",
    "del": "Del",
    "delete": "Del",
    "dc": "Del",
    "enter": "Enter",
    "return": "Enter",
    "cr": "Enter",
    "space": "Space",
    "tab": "Tab",
    "bspace": "BSpace",
    "backspace": "BSpace",
    "bs": "BSpace",
    "escape": "Escape",
    "esc": "Escape",
}
SPECIAL_NAMES.update({f"f{i}": f"F{i}" for i in range(1, 13)})


def parse_keyspec(s: str) -> str:
    """Normaliza la notación de usuario a keyspec canónico.

    - ``^b`` / ``^B``        -> ``C-b``
    - Prefijos ``C-``/``M-`` en cualquier orden -> orden canónico ``C-M-``
    - La letra tras ``C-`` se normaliza a minúscula; tras ``M-`` conserva case.
    - Nombres especiales case-insensitive (``UP`` -> ``Up``, ``pageup`` -> ``PgUp``).
    - Un solo carácter imprimible se devuelve tal cual.
    - ValueError si no es reconocible.
    """
    if not isinstance(s, str) or not s:
        raise ValueError(f"keyspec vacío o inválido: {s!r}")

    # Notación caret: ^b == C-b
    if len(s) == 2 and s[0] == "^":
        s = "C-" + s[1]

    ctrl = False
    alt = False
    rest = s
    while True:
        head = rest[:2].upper()
        if head == "C-":
            ctrl = True
            rest = rest[2:]
        elif head == "M-":
            alt = True
            rest = rest[2:]
        else:
            break

    if not rest:
        raise ValueError(f"keyspec no reconocible: {s!r}")

    lowered = rest.lower()
    if lowered in SPECIAL_NAMES:
        base = SPECIAL_NAMES[lowered]
    elif len(rest) == 1 and rest.isprintable():
        # Tras C- la letra se normaliza a minúscula; tras M- (solo) conserva case.
        base = rest.lower() if ctrl else rest
    else:
        raise ValueError(f"keyspec no reconocible: {s!r}")

    prefix = ("C-" if ctrl else "") + ("M-" if alt else "")
    return prefix + base


# ---------------------------------------------------------------------------
# Caracteres de control de consola -> keyspec
# ---------------------------------------------------------------------------

_CTRL_EXCEPTIONS: dict[str, str] = {
    "\r": "Enter",
    "\n": "Enter",
    "\t": "Tab",
    "\x1b": "Escape",
    "\x08": "BSpace",
    "\x7f": "BSpace",
    " ": "Space",
}


def ctrl_char_to_keyspec(ch: str) -> str | None:
    """Carácter de control de consola -> keyspec, o None si no es control conocido.

    Las excepciones (Enter/Tab/Escape/BSpace/Space) tienen prioridad sobre el
    rango genérico ``\\x01``..``\\x1a`` -> ``C-a``..``C-z``. ``\\x00`` -> None.
    Caracteres imprimibles -> None.
    """
    if not ch:
        return None
    if ch in _CTRL_EXCEPTIONS:
        return _CTRL_EXCEPTIONS[ch]
    if ch == "\x00":
        return None
    code = ord(ch)
    if 1 <= code <= 26:
        return "C-" + chr(code + 96)  # \x01 -> 'a' ... \x1a -> 'z'
    return None


# ---------------------------------------------------------------------------
# Códigos extendidos de msvcrt.getwch() (segundo char tras '\x00' o '\xe0')
# ---------------------------------------------------------------------------

EXTENDED_CODES: dict[str, str] = {
    # Navegación
    "H": "Up",
    "P": "Down",
    "K": "Left",
    "M": "Right",
    "G": "Home",
    "O": "End",
    "I": "PgUp",
    "Q": "PgDn",
    "R": "Ins",
    "S": "Del",
    # F11/F12 (F1..F10 se añaden abajo)
    "\x85": "F11",
    "\x86": "F12",
    # Con Ctrl
    "\x8d": "C-Up",
    "\x91": "C-Down",
    "s": "C-Left",
    "t": "C-Right",
    "w": "C-Home",
    "u": "C-End",
    "\x84": "C-PgUp",
    "v": "C-PgDn",
    "\x93": "C-Del",
    "\x92": "C-Ins",
    # Con Alt
    "\x98": "M-Up",
    "\xa0": "M-Down",
    "\x9b": "M-Left",
    "\x9d": "M-Right",
    "\x97": "M-Home",
    "\x9f": "M-End",
    "\x99": "M-PgUp",
    "\xa1": "M-PgDn",
}
# F1..F10: scan codes 0x3B..0x44
EXTENDED_CODES.update({chr(0x3B + i): f"F{i + 1}" for i in range(10)})


def decode_extended(code: str) -> str | None:
    """Segundo carácter de una secuencia extendida -> keyspec, o None."""
    return EXTENDED_CODES.get(code)


# ---------------------------------------------------------------------------
# keyspec -> secuencia VT para el ConPTY del panel
# ---------------------------------------------------------------------------

_VT_PLAIN: dict[str, str] = {
    "Enter": "\r",
    "Tab": "\t",
    "Escape": "\x1b",
    "Space": " ",
    "BSpace": "\x7f",
}

# Teclas CSI con letra final (admiten modificador xterm: ESC [ 1 ; m X)
_VT_CSI_FINAL: dict[str, str] = {
    "Up": "A",
    "Down": "B",
    "Right": "C",
    "Left": "D",
    "Home": "H",
    "End": "F",
}

# Teclas CSI con tilde (admiten modificador: ESC [ n ; m ~)
_VT_TILDE: dict[str, str] = {
    "Ins": "2",
    "Del": "3",
    "PgUp": "5",
    "PgDn": "6",
}

_VT_SS3: dict[str, str] = {"F1": "P", "F2": "Q", "F3": "R", "F4": "S"}

_VT_FN_TILDE: dict[str, str] = {
    "F5": "15",
    "F6": "17",
    "F7": "18",
    "F8": "19",
    "F9": "20",
    "F10": "21",
    "F11": "23",
    "F12": "24",
}


def keyspec_to_vt(ks: str) -> str:
    """Keyspec -> secuencia de bytes (str) que se escribe al ConPTY del panel.

    Devuelve '' (cadena vacía) si el keyspec no tiene traducción conocida.
    """
    if not ks:
        return ""
    if len(ks) == 1:
        return ks  # carácter literal

    ctrl = False
    alt = False
    rest = ks
    while len(rest) > 2:
        if rest.startswith("C-"):
            ctrl = True
            rest = rest[2:]
        elif rest.startswith("M-"):
            alt = True
            rest = rest[2:]
        else:
            break

    # Parámetro de modificador xterm: 1 + 4(Ctrl) + 2(Alt)
    mod = 1 + (4 if ctrl else 0) + (2 if alt else 0)

    if rest in _VT_CSI_FINAL:
        final = _VT_CSI_FINAL[rest]
        if ctrl or alt:
            return f"\x1b[1;{mod}{final}"
        return "\x1b[" + final

    if rest in _VT_TILDE:
        num = _VT_TILDE[rest]
        if ctrl or alt:
            return f"\x1b[{num};{mod}~"
        return f"\x1b[{num}~"

    if ctrl and alt:
        inner = keyspec_to_vt("C-" + rest)
        return "\x1b" + inner if inner else ""

    if ctrl:
        if rest == "Space":
            return "\x00"
        if len(rest) == 1:
            low = rest.lower()
            if "a" <= low <= "z":
                return chr(ord(low) - 96)
        return ""

    if alt:
        inner = keyspec_to_vt(rest)
        return "\x1b" + inner if inner else ""

    if rest in _VT_PLAIN:
        return _VT_PLAIN[rest]
    if rest in _VT_SS3:
        return "\x1bO" + _VT_SS3[rest]
    if rest in _VT_FN_TILDE:
        return "\x1b[" + _VT_FN_TILDE[rest] + "~"

    return ""


# ---------------------------------------------------------------------------
# Lector de teclado de la consola Windows
# ---------------------------------------------------------------------------


class ConsoleKeyReader:
    """Lee teclas de la consola Windows y las convierte en keyspecs.

    Única parte del módulo que usa ``msvcrt``; el import se hace dentro del
    método para que el módulo sea importable y testeable sin consola. Se puede
    inyectar un ``getwch`` alternativo (callable sin args que devuelve un
    carácter) para tests.
    """

    def __init__(self, getwch=None):
        self._getwch = getwch

    def read_keys(self):
        """Generador infinito de keyspecs (bloqueante en getwch)."""
        getwch = self._getwch
        if getwch is None:
            import msvcrt

            getwch = msvcrt.getwch
        while True:
            ch = getwch()
            if ch in ("\x00", "\xe0"):
                # Tecla extendida: el siguiente char identifica la tecla.
                code = getwch()
                ks = decode_extended(code)
                if ks is not None:
                    yield ks
                continue
            ks = ctrl_char_to_keyspec(ch)
            if ks is not None:
                yield ks
            else:
                yield ch  # carácter unicode tal cual (acentos, ñ, etc.)
