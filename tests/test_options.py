"""Tests para tmuxw.options: herencia, coercion, estilos y SGR."""

import pytest

from tmuxw.options import (
    BOOL_OPTIONS,
    DEFAULTS,
    INT_OPTIONS,
    Options,
    parse_style,
    style_to_sgr,
)


# ---------------------------------------------------------------------------
# Options: herencia
# ---------------------------------------------------------------------------

def test_get_defaults():
    o = Options()
    assert o.get("prefix") == "C-b"
    assert o.get("history-limit") == 2000
    assert o.get("mouse") is False


def test_get_unknown_raises_keyerror():
    o = Options()
    with pytest.raises(KeyError):
        o.get("no-such-option")


def test_inheritance_chain_window_session_global():
    g = Options()
    s = Options(parent=g)
    w = Options(parent=s)
    g.set("base-index", 1)
    assert w.get("base-index") == 1  # heredado de global
    s.set("base-index", 2)
    assert w.get("base-index") == 2  # session gana a global
    w.set("base-index", 3)
    assert w.get("base-index") == 3  # local gana a todo
    assert s.get("base-index") == 2
    assert g.get("base-index") == 1


def test_unset_falls_back_through_chain():
    g = Options()
    s = Options(parent=g)
    g.set("prefix", "C-a")
    s.set("prefix", "C-x")
    assert s.get("prefix") == "C-x"
    s.unset("prefix")
    assert s.get("prefix") == "C-a"
    g.unset("prefix")
    assert s.get("prefix") == "C-b"  # vuelve a DEFAULTS


def test_unset_missing_is_silent():
    o = Options()
    o.unset("never-set-option")  # no debe lanzar
    assert o.show() == DEFAULTS


def test_set_does_not_mutate_defaults():
    o = Options()
    o.set("history-limit", 9999)
    assert DEFAULTS["history-limit"] == 2000


# ---------------------------------------------------------------------------
# Coercion bool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("on", True), ("off", False),
    ("ON", True), ("Off", False),
    ("true", True), ("FALSE", False),
    ("1", True), ("0", False),
    (True, True), (False, False),
    (1, True), (0, False),
])
def test_bool_coercion(raw, expected):
    o = Options()
    o.set("mouse", raw)
    assert o.get("mouse") is expected


@pytest.mark.parametrize("bad", ["maybe", "yes-no", "2", 5, None])
def test_bool_invalid_raises(bad):
    o = Options()
    with pytest.raises(ValueError):
        o.set("status", bad)


# ---------------------------------------------------------------------------
# Coercion int
# ---------------------------------------------------------------------------

def test_int_coercion():
    o = Options()
    o.set("history-limit", "5000")
    assert o.get("history-limit") == 5000
    o.set("base-index", 1)
    assert o.get("base-index") == 1
    o.set("status-interval", " 30 ")
    assert o.get("status-interval") == 30
    o.set("display-time", "-1")
    assert o.get("display-time") == -1


@pytest.mark.parametrize("bad", ["muchas", "1.5", "", True, None])
def test_int_invalid_raises(bad):
    o = Options()
    with pytest.raises(ValueError):
        o.set("history-limit", bad)


# ---------------------------------------------------------------------------
# mode-keys (enum) y opciones desconocidas
# ---------------------------------------------------------------------------

def test_mode_keys_valid():
    o = Options()
    o.set("mode-keys", "vi")
    assert o.get("mode-keys") == "vi"
    o.set("mode-keys", "emacs")
    assert o.get("mode-keys") == "emacs"


def test_mode_keys_invalid_raises():
    o = Options()
    with pytest.raises(ValueError):
        o.set("mode-keys", "nano")


def test_unknown_option_stored_as_str():
    o = Options()
    o.set("@my-plugin-opt", 42)
    assert o.get("@my-plugin-opt") == "42"
    o.set("@otra", "valor con espacios")
    assert o.get("@otra") == "valor con espacios"


def test_other_known_option_coerced_to_str():
    o = Options()
    o.set("status-left", 123)
    assert o.get("status-left") == "123"


# ---------------------------------------------------------------------------
# show()
# ---------------------------------------------------------------------------

def test_show_combines_chain_and_defaults():
    g = Options()
    s = Options(parent=g)
    g.set("base-index", 1)
    g.set("mode-keys", "emacs")
    s.set("mode-keys", "vi")  # local gana a parent
    s.set("@custom", "x")
    combined = s.show()
    assert combined["base-index"] == 1
    assert combined["mode-keys"] == "vi"
    assert combined["@custom"] == "x"
    assert combined["prefix"] == "C-b"  # default intacto
    assert set(DEFAULTS) <= set(combined)


def test_show_plain_equals_defaults():
    assert Options().show() == DEFAULTS


# ---------------------------------------------------------------------------
# parse_style
# ---------------------------------------------------------------------------

def test_parse_style_basic():
    assert parse_style("bg=green,fg=black,bold") == {
        "bg": "green", "fg": "black", "bold": True,
    }


def test_parse_style_tolerates_spaces():
    assert parse_style(" bg = green ,  fg = black ") == {"bg": "green", "fg": "black"}


def test_parse_style_empty_string():
    assert parse_style("") == {}
    assert parse_style("   ") == {}


def test_parse_style_color_kinds():
    assert parse_style("fg=brightred")["fg"] == "brightred"
    assert parse_style("bg=brightwhite")["bg"] == "brightwhite"
    assert parse_style("fg=colour200")["fg"] == "colour200"
    assert parse_style("bg=color17")["bg"] == "color17"  # grafia 'color'
    assert parse_style("fg=#1a2B3C")["fg"] == "#1a2b3c"
    assert parse_style("fg=default")["fg"] == "default"


def test_parse_style_all_attributes():
    s = parse_style("bold,dim,underscore,italics,reverse,blink")
    assert s == {
        "bold": True, "dim": True, "underscore": True,
        "italics": True, "reverse": True, "blink": True,
    }


@pytest.mark.parametrize("bad", [
    "fg=verde",        # color desconocido
    "fg=colour256",    # fuera de rango
    "fg=colour300",
    "fg=#12345",       # hex corto
    "fg=#zzzzzz",      # hex invalido
    "fg=brightorange", # bright de color inexistente
    "blinking",        # atributo desconocido
    "weight=bold",     # clave desconocida
])
def test_parse_style_invalid_raises(bad):
    with pytest.raises(ValueError):
        parse_style(bad)


# ---------------------------------------------------------------------------
# style_to_sgr
# ---------------------------------------------------------------------------

def test_sgr_named_colors():
    assert style_to_sgr({"fg": "black", "bg": "green"}) == "30;42"
    assert style_to_sgr({"fg": "white"}) == "37"
    assert style_to_sgr({"bg": "red"}) == "41"


def test_sgr_attribute_order_then_fg_then_bg():
    assert style_to_sgr({"reverse": True, "bold": True, "fg": "red", "bg": "blue"}) == "1;7;31;44"


def test_sgr_all_attributes_order():
    style = {
        "blink": True, "reverse": True, "bold": True,
        "underscore": True, "italics": True, "dim": True,
    }
    assert style_to_sgr(style) == "1;2;3;4;5;7"


def test_sgr_bright_colors():
    assert style_to_sgr({"fg": "brightred"}) == "91"
    assert style_to_sgr({"fg": "brightblack"}) == "90"
    assert style_to_sgr({"bg": "brightwhite"}) == "107"
    assert style_to_sgr({"bg": "brightblack"}) == "100"


def test_sgr_colour_256():
    assert style_to_sgr({"fg": "colour200"}) == "38;5;200"
    assert style_to_sgr({"bg": "colour16"}) == "48;5;16"
    assert style_to_sgr({"fg": "color0"}) == "38;5;0"


def test_sgr_hex_truecolor():
    assert style_to_sgr({"fg": "#ff0080"}) == "38;2;255;0;128"
    assert style_to_sgr({"bg": "#010203"}) == "48;2;1;2;3"


def test_sgr_default():
    assert style_to_sgr({"fg": "default", "bg": "default"}) == "39;49"


def test_sgr_empty_dict():
    assert style_to_sgr({}) == ""


def test_sgr_roundtrip_with_parse_style():
    assert style_to_sgr(parse_style("bg=green,fg=black")) == "30;42"
    assert style_to_sgr(parse_style(DEFAULTS["message-style"])) == "30;43"


# ---------------------------------------------------------------------------
# Consistencia de los conjuntos exportados
# ---------------------------------------------------------------------------

def test_option_sets_are_subset_of_defaults():
    assert BOOL_OPTIONS <= set(DEFAULTS)
    assert INT_OPTIONS <= set(DEFAULTS)
