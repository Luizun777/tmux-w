"""Pre-filtro del flujo VT antes de pyte.

El ConPTY moderno (Win11 24H2+) deja pasar casi tal cual lo que emite la
aplicación. Apps como Claude Code usan secuencias que el parser de pyte
malinterpreta en vez de ignorar:

- ``ESC [ < u`` / ``ESC [ > 1 u`` (teclado kitty): el ``<`` aborta la CSI y
  la ``u`` siguiente se dibuja como texto literal.
- ``ESC [ > 4 ; 2 m`` (XTMODKEYS): el ``>`` se descarta y se aplica como
  SGR 4;2 -> subrayado + atenuado espurios.
- ``ESC [ ! p`` (DECSTR) y cualquier CSI con intermedios: la ``p`` acaba
  dibujada como texto.
- SGR con subparámetros ``:`` (``4:3m``): la secuencia se parte y el resto
  se dibuja como texto.
- Cadenas DCS/SOS/PM/APC: pyte no las conoce y el contenido sale como texto.

Este filtro elimina esas secuencias y retiene colas incompletas cuando una
lectura corta una secuencia a la mitad.
"""

import re

# CSI completa: ESC [ parámetros(0x30-0x3F) intermedios(0x20-0x2F) final(0x40-0x7E)
_CSI = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
# Cadenas DCS/SOS/PM/APC: ESC P/X/^/_ ... ST (ESC \) o BEL
_STRING = re.compile(r"\x1b[PX^_].*?(?:\x1b\\|\x07)", re.S)


def _scrub_csi(m: re.Match) -> str:
    params, intermediates, _final = m.groups()
    if intermediates or any(c in params for c in "<=>:"):
        return ""
    return m.group(0)


def _tail_incomplete(tail: str) -> bool:
    """¿`tail` (que empieza por ESC) es una secuencia aún sin terminar?"""
    if len(tail) == 1:
        return True
    kind = tail[1]
    if kind == "[":
        # incompleta solo si todo lo que sigue son bytes de parámetro/intermedio
        if _CSI.match(tail) is not None:
            return False
        return all("0" <= c <= "?" or " " <= c <= "/" for c in tail[2:])
    if kind == "]" or kind in "PX^_":  # OSC o cadena: terminan en BEL/ST
        return "\x07" not in tail and "\x1b\\" not in tail
    if kind in "()#%":  # designación de charset: falta el tercer byte
        return len(tail) < 3
    return False  # ESC + final: completa


class VtSanitizer:
    """Filtro con estado: una secuencia puede llegar partida entre lecturas."""

    MAX_TAIL = 4096  # tope para no retener para siempre una secuencia rota

    def __init__(self) -> None:
        self._tail = ""

    def feed(self, data: str) -> str:
        data = self._tail + data
        self._tail = ""
        i = data.rfind("\x1b")
        if i != -1 and len(data) - i <= self.MAX_TAIL and _tail_incomplete(data[i:]):
            data, self._tail = data[:i], data[i:]
        data = _STRING.sub("", data)
        return _CSI.sub(_scrub_csi, data)
