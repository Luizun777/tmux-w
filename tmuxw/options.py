"""Opciones de tmux-w (ver FUNCIONALIDADES.md seccion 6).

Implementa la cadena de herencia de opciones de tmux
(window -> session -> global -> DEFAULTS), la coercion de tipos al hacer
``set``, y las utilidades de estilos (``parse_style`` / ``style_to_sgr``).
"""

import re

DEFAULTS = {
    "prefix": "C-b",
    "prefix2": "",  # prefijo secundario opcional (vacío = desactivado)
    "default-shell": "powershell.exe",
    "base-index": 0,
    "history-limit": 2000,
    "mode-keys": "emacs",
    "status": True,
    "status-style": "bg=green,fg=black",
    "status-interval": 15,
    "status-left": "[#S] ",
    "status-right": '"#H" %H:%M %d-%b-%y',
    "display-time": 750,
    "display-panes-time": 1000,
    "repeat-time": 500,
    "pane-border-style": "fg=default",
    "pane-active-border-style": "fg=green",
    "message-style": "bg=yellow,fg=black",
    "mouse": True,
}

BOOL_OPTIONS = {"status", "mouse"}
INT_OPTIONS = {"base-index", "history-limit", "status-interval", "display-time",
               "display-panes-time", "repeat-time"}

# Opciones con un conjunto cerrado de valores validos.
_ENUM_OPTIONS = {"mode-keys": {"vi", "emacs"}}

_TRUE_STRINGS = {"on", "true", "1"}
_FALSE_STRINGS = {"off", "false", "0"}


class Options:
    """Cadena de herencia: window -> session -> global -> DEFAULTS."""

    def __init__(self, parent: "Options|None" = None):
        self.parent = parent
        self._values = {}

    def get(self, name: str):
        """Busca local, luego la cadena de padres, luego DEFAULTS.

        Lanza KeyError si la opcion no existe en ninguno.
        """
        node = self
        while node is not None:
            if name in node._values:
                return node._values[name]
            node = node.parent
        if name in DEFAULTS:
            return DEFAULTS[name]
        raise KeyError(name)

    def set(self, name: str, value):
        """Asigna localmente con coercion de tipo (ver _coerce)."""
        self._values[name] = _coerce(name, value)

    def unset(self, name: str):
        """Elimina el valor local; silencioso si no estaba definido."""
        self._values.pop(name, None)

    def show(self) -> dict:
        """Dict combinado: DEFAULTS sobreescritos por toda la cadena.

        El padre mas lejano se aplica primero y el nodo local al final,
        incluyendo opciones desconocidas (user options) definidas.
        """
        chain = []
        node = self
        while node is not None:
            chain.append(node)
            node = node.parent
        result = dict(DEFAULTS)
        for node in reversed(chain):
            result.update(node._values)
        return result


def _coerce(name, value):
    """Coercion de valores al estilo tmux.

    - BOOL_OPTIONS: bool, int 0/1, o str on/off/true/false/1/0 (case-insensitive).
    - INT_OPTIONS: int (no bool) o str numerica.
    - mode-keys: solo "vi" o "emacs".
    - Resto (incluidas opciones desconocidas): str(value).
    """
    if name in BOOL_OPTIONS:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUE_STRINGS:
                return True
            if lowered in _FALSE_STRINGS:
                return False
        raise ValueError(
            f"valor booleano invalido para {name!r}: {value!r} "
            f"(se esperaba on/off/true/false/1/0)"
        )
    if name in INT_OPTIONS:
        if isinstance(value, bool):
            raise ValueError(f"valor entero invalido para {name!r}: {value!r}")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                raise ValueError(
                    f"valor entero invalido para {name!r}: {value!r}"
                ) from None
        raise ValueError(f"valor entero invalido para {name!r}: {value!r}")
    result = value if isinstance(value, str) else str(value)
    if name in _ENUM_OPTIONS and result not in _ENUM_OPTIONS[name]:
        valid = "/".join(sorted(_ENUM_OPTIONS[name]))
        raise ValueError(f"valor invalido para {name!r}: {result!r} (se esperaba {valid})")
    return result


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

# Indice de los 8 colores ANSI basicos.
_NAMED_COLORS = {
    "black": 0,
    "red": 1,
    "green": 2,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
}

# Atributos sin '=' permitidos, en el orden SGR de salida.
_ATTR_SGR = {
    "bold": 1,
    "dim": 2,
    "italics": 3,
    "underscore": 4,
    "blink": 5,
    "reverse": 7,
}
_ATTR_ORDER = ("bold", "dim", "italics", "underscore", "blink", "reverse")

_COLOUR_RE = re.compile(r"^colou?r(\d{1,3})$")
_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


def _is_valid_color(value: str) -> bool:
    if value == "default":
        return True
    if value in _NAMED_COLORS:
        return True
    if value.startswith("bright") and value[len("bright"):] in _NAMED_COLORS:
        return True
    m = _COLOUR_RE.match(value)
    if m:
        return 0 <= int(m.group(1)) <= 255
    return bool(_HEX_RE.match(value))


def parse_style(style: str) -> dict:
    """\"bg=green,fg=black,bold\" -> {"bg":"green","fg":"black","bold":True}.

    Tolera espacios alrededor de comas/iguales. Atributos sin '=' permitidos:
    bold, dim, underscore, italics, reverse, blink (valor True).
    Colores validos: default, black..white, brightblack..brightwhite,
    colour0..colour255 (tambien 'color'), o #rrggbb hex.
    ValueError si el color o atributo es desconocido. Cadena vacia -> {}.
    """
    result = {}
    if not style or not style.strip():
        return result
    for part in style.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, value = part.partition("=")
            key = key.strip().lower()
            value = value.strip().lower()
            if key not in ("fg", "bg"):
                raise ValueError(f"clave de estilo desconocida: {key!r}")
            if not _is_valid_color(value):
                raise ValueError(f"color desconocido para {key!r}: {value!r}")
            result[key] = value
        else:
            attr = part.lower()
            if attr not in _ATTR_SGR:
                raise ValueError(f"atributo de estilo desconocido: {attr!r}")
            result[attr] = True
    return result


def _color_sgr(value: str, is_bg: bool) -> str:
    if value == "default":
        return "49" if is_bg else "39"
    if value in _NAMED_COLORS:
        return str((40 if is_bg else 30) + _NAMED_COLORS[value])
    if value.startswith("bright") and value[len("bright"):] in _NAMED_COLORS:
        return str((100 if is_bg else 90) + _NAMED_COLORS[value[len("bright"):]])
    m = _COLOUR_RE.match(value)
    if m and 0 <= int(m.group(1)) <= 255:
        return f"{'48' if is_bg else '38'};5;{int(m.group(1))}"
    if _HEX_RE.match(value):
        r = int(value[1:3], 16)
        g = int(value[3:5], 16)
        b = int(value[5:7], 16)
        return f"{'48' if is_bg else '38'};2;{r};{g};{b}"
    raise ValueError(f"color desconocido: {value!r}")


def style_to_sgr(style: dict) -> str:
    """Devuelve los parametros SGR (sin ESC[ ni 'm').

    Orden: atributos (bold->1, dim->2, italics->3, underscore->4, blink->5,
    reverse->7), luego fg, luego bg. Dict vacio -> ''.
    """
    parts = []
    for attr in _ATTR_ORDER:
        if style.get(attr):
            parts.append(str(_ATTR_SGR[attr]))
    if "fg" in style:
        parts.append(_color_sgr(str(style["fg"]).lower(), is_bg=False))
    if "bg" in style:
        parts.append(_color_sgr(str(style["bg"]).lower(), is_bg=True))
    return ";".join(parts)
