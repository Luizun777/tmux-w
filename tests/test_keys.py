"""Tests unitarios de tmuxw.keys (parse, decodificación de consola, VT)."""

from itertools import islice

import pytest

from tmuxw.keys import (
    EXTENDED_CODES,
    SPECIAL_NAMES,
    ConsoleKeyReader,
    ctrl_char_to_keyspec,
    decode_extended,
    keyspec_to_vt,
    parse_keyspec,
)

# ---------------------------------------------------------------------------
# parse_keyspec
# ---------------------------------------------------------------------------


class TestParseKeyspec:
    def test_caracter_literal(self):
        assert parse_keyspec("a") == "a"
        assert parse_keyspec("A") == "A"
        assert parse_keyspec("%") == "%"
        assert parse_keyspec("|") == "|"

    def test_notacion_caret(self):
        assert parse_keyspec("^b") == "C-b"
        assert parse_keyspec("^B") == "C-b"

    def test_ctrl_normaliza_minuscula(self):
        assert parse_keyspec("C-a") == "C-a"
        assert parse_keyspec("C-B") == "C-b"

    def test_meta_conserva_case(self):
        assert parse_keyspec("M-x") == "M-x"
        assert parse_keyspec("M-X") == "M-X"

    def test_orden_canonico_modificadores(self):
        assert parse_keyspec("C-M-a") == "C-M-a"
        assert parse_keyspec("M-C-a") == "C-M-a"
        assert parse_keyspec("M-C-B") == "C-M-b"

    def test_nombres_especiales_case_insensitive(self):
        assert parse_keyspec("UP") == "Up"
        assert parse_keyspec("up") == "Up"
        assert parse_keyspec("down") == "Down"
        assert parse_keyspec("pageup") == "PgUp"
        assert parse_keyspec("PPage") == "PgUp"
        assert parse_keyspec("npage") == "PgDn"
        assert parse_keyspec("ESC") == "Escape"
        assert parse_keyspec("return") == "Enter"
        assert parse_keyspec("cr") == "Enter"
        assert parse_keyspec("bs") == "BSpace"
        assert parse_keyspec("dc") == "Del"
        assert parse_keyspec("insert") == "Ins"
        assert parse_keyspec("f1") == "F1"
        assert parse_keyspec("F12") == "F12"

    def test_modificador_sobre_especiales(self):
        assert parse_keyspec("C-Up") == "C-Up"
        assert parse_keyspec("M-left") == "M-Left"
        assert parse_keyspec("C-M-pgup") == "C-M-PgUp"

    def test_errores(self):
        with pytest.raises(ValueError):
            parse_keyspec("")
        with pytest.raises(ValueError):
            parse_keyspec("C-")
        with pytest.raises(ValueError):
            parse_keyspec("M-")
        with pytest.raises(ValueError):
            parse_keyspec("Foo")
        with pytest.raises(ValueError):
            parse_keyspec("C-M-")

    def test_special_names_contiene_fkeys(self):
        assert SPECIAL_NAMES["f5"] == "F5"
        assert SPECIAL_NAMES["backspace"] == "BSpace"


# ---------------------------------------------------------------------------
# ctrl_char_to_keyspec
# ---------------------------------------------------------------------------


class TestCtrlCharToKeyspec:
    def test_excepciones_antes_del_rango(self):
        assert ctrl_char_to_keyspec("\r") == "Enter"
        assert ctrl_char_to_keyspec("\n") == "Enter"
        assert ctrl_char_to_keyspec("\t") == "Tab"
        assert ctrl_char_to_keyspec("\x1b") == "Escape"
        assert ctrl_char_to_keyspec("\x08") == "BSpace"
        assert ctrl_char_to_keyspec("\x7f") == "BSpace"
        assert ctrl_char_to_keyspec(" ") == "Space"

    def test_nul_es_none(self):
        assert ctrl_char_to_keyspec("\x00") is None

    def test_rango_ctrl_a_z(self):
        assert ctrl_char_to_keyspec("\x01") == "C-a"
        assert ctrl_char_to_keyspec("\x02") == "C-b"
        assert ctrl_char_to_keyspec("\x03") == "C-c"
        assert ctrl_char_to_keyspec("\x1a") == "C-z"

    def test_imprimibles_son_none(self):
        assert ctrl_char_to_keyspec("a") is None
        assert ctrl_char_to_keyspec("%") is None
        assert ctrl_char_to_keyspec("ñ") is None


# ---------------------------------------------------------------------------
# decode_extended / EXTENDED_CODES
# ---------------------------------------------------------------------------


class TestDecodeExtended:
    def test_flechas_y_navegacion(self):
        assert decode_extended("H") == "Up"
        assert decode_extended("P") == "Down"
        assert decode_extended("K") == "Left"
        assert decode_extended("M") == "Right"
        assert decode_extended("G") == "Home"
        assert decode_extended("O") == "End"
        assert decode_extended("I") == "PgUp"
        assert decode_extended("Q") == "PgDn"
        assert decode_extended("R") == "Ins"
        assert decode_extended("S") == "Del"

    def test_fkeys(self):
        assert decode_extended(chr(0x3B)) == "F1"
        assert decode_extended(chr(0x3C)) == "F2"
        assert decode_extended(chr(0x44)) == "F10"
        assert decode_extended("\x85") == "F11"
        assert decode_extended("\x86") == "F12"

    def test_variantes_ctrl(self):
        assert decode_extended("\x8d") == "C-Up"
        assert decode_extended("\x91") == "C-Down"
        assert decode_extended("s") == "C-Left"
        assert decode_extended("t") == "C-Right"
        assert decode_extended("w") == "C-Home"
        assert decode_extended("u") == "C-End"
        assert decode_extended("\x84") == "C-PgUp"
        assert decode_extended("v") == "C-PgDn"
        assert decode_extended("\x93") == "C-Del"
        assert decode_extended("\x92") == "C-Ins"

    def test_variantes_alt(self):
        assert decode_extended("\x98") == "M-Up"
        assert decode_extended("\xa0") == "M-Down"
        assert decode_extended("\x9b") == "M-Left"
        assert decode_extended("\x9d") == "M-Right"
        assert decode_extended("\x97") == "M-Home"
        assert decode_extended("\x9f") == "M-End"
        assert decode_extended("\x99") == "M-PgUp"
        assert decode_extended("\xa1") == "M-PgDn"

    def test_desconocido_es_none(self):
        assert decode_extended("\xff") is None
        assert decode_extended("Z") is None

    def test_mapa_coincide_con_funcion(self):
        for code, ks in EXTENDED_CODES.items():
            assert decode_extended(code) == ks


# ---------------------------------------------------------------------------
# keyspec_to_vt
# ---------------------------------------------------------------------------


class TestKeyspecToVt:
    def test_literales(self):
        assert keyspec_to_vt("a") == "a"
        assert keyspec_to_vt("%") == "%"
        assert keyspec_to_vt("|") == "|"

    def test_especiales_simples(self):
        assert keyspec_to_vt("Enter") == "\r"
        assert keyspec_to_vt("Tab") == "\t"
        assert keyspec_to_vt("Escape") == "\x1b"
        assert keyspec_to_vt("Space") == " "
        assert keyspec_to_vt("BSpace") == "\x7f"

    def test_controles(self):
        assert keyspec_to_vt("C-a") == "\x01"
        assert keyspec_to_vt("C-b") == "\x02"
        assert keyspec_to_vt("C-z") == "\x1a"
        assert keyspec_to_vt("C-Space") == "\x00"

    def test_meta_prefija_esc(self):
        assert keyspec_to_vt("M-x") == "\x1bx"
        assert keyspec_to_vt("M-A") == "\x1bA"
        assert keyspec_to_vt("M-Enter") == "\x1b\r"

    def test_ctrl_meta(self):
        assert keyspec_to_vt("C-M-a") == "\x1b\x01"
        assert keyspec_to_vt("C-M-z") == "\x1b\x1a"

    def test_flechas_y_navegacion(self):
        assert keyspec_to_vt("Up") == "\x1b[A"
        assert keyspec_to_vt("Down") == "\x1b[B"
        assert keyspec_to_vt("Right") == "\x1b[C"
        assert keyspec_to_vt("Left") == "\x1b[D"
        assert keyspec_to_vt("Home") == "\x1b[H"
        assert keyspec_to_vt("End") == "\x1b[F"

    def test_paginas_ins_del(self):
        assert keyspec_to_vt("PgUp") == "\x1b[5~"
        assert keyspec_to_vt("PgDn") == "\x1b[6~"
        assert keyspec_to_vt("Ins") == "\x1b[2~"
        assert keyspec_to_vt("Del") == "\x1b[3~"

    def test_fkeys(self):
        assert keyspec_to_vt("F1") == "\x1bOP"
        assert keyspec_to_vt("F2") == "\x1bOQ"
        assert keyspec_to_vt("F3") == "\x1bOR"
        assert keyspec_to_vt("F4") == "\x1bOS"
        assert keyspec_to_vt("F5") == "\x1b[15~"
        assert keyspec_to_vt("F6") == "\x1b[17~"
        assert keyspec_to_vt("F7") == "\x1b[18~"
        assert keyspec_to_vt("F8") == "\x1b[19~"
        assert keyspec_to_vt("F9") == "\x1b[20~"
        assert keyspec_to_vt("F10") == "\x1b[21~"
        assert keyspec_to_vt("F11") == "\x1b[23~"
        assert keyspec_to_vt("F12") == "\x1b[24~"

    def test_modificadores_sobre_flechas(self):
        assert keyspec_to_vt("C-Up") == "\x1b[1;5A"
        assert keyspec_to_vt("C-Down") == "\x1b[1;5B"
        assert keyspec_to_vt("M-Left") == "\x1b[1;3D"
        assert keyspec_to_vt("M-Right") == "\x1b[1;3C"
        assert keyspec_to_vt("C-M-Up") == "\x1b[1;7A"
        assert keyspec_to_vt("C-Home") == "\x1b[1;5H"
        assert keyspec_to_vt("M-End") == "\x1b[1;3F"

    def test_modificadores_sobre_tilde(self):
        assert keyspec_to_vt("C-PgUp") == "\x1b[5;5~"
        assert keyspec_to_vt("C-PgDn") == "\x1b[6;5~"
        assert keyspec_to_vt("M-PgDn") == "\x1b[6;3~"
        assert keyspec_to_vt("C-Del") == "\x1b[3;5~"
        assert keyspec_to_vt("C-Ins") == "\x1b[2;5~"
        assert keyspec_to_vt("C-M-Del") == "\x1b[3;7~"

    def test_desconocido_cadena_vacia(self):
        assert keyspec_to_vt("Foo") == ""
        assert keyspec_to_vt("C-") == ""
        assert keyspec_to_vt("") == ""
        assert keyspec_to_vt("C-%") == ""
        assert keyspec_to_vt("M-Foo") == ""


# ---------------------------------------------------------------------------
# ConsoleKeyReader (con getwch inyectado)
# ---------------------------------------------------------------------------


def make_reader(chars):
    it = iter(chars)
    return ConsoleKeyReader(getwch=lambda: next(it))


class TestConsoleKeyReader:
    def test_secuencia_mixta(self):
        reader = make_reader(["a", "\x00", "H", "\xe0", "s", "\x03", "\r"])
        keys = list(islice(reader.read_keys(), 5))
        assert keys == ["a", "Up", "C-Left", "C-c", "Enter"]

    def test_caracter_simple(self):
        reader = make_reader(["a"])
        assert next(reader.read_keys()) == "a"

    def test_extendida_x00(self):
        reader = make_reader(["\x00", "H"])
        assert next(reader.read_keys()) == "Up"

    def test_extendida_xe0(self):
        reader = make_reader(["\xe0", "s"])
        assert next(reader.read_keys()) == "C-Left"

    def test_control(self):
        reader = make_reader(["\x03"])
        assert next(reader.read_keys()) == "C-c"

    def test_enter(self):
        reader = make_reader(["\r"])
        assert next(reader.read_keys()) == "Enter"

    def test_extendida_desconocida_se_ignora(self):
        reader = make_reader(["\x00", "\xff", "b"])
        assert next(reader.read_keys()) == "b"

    def test_unicode_pasa_tal_cual(self):
        reader = make_reader(["ñ", "á"])
        keys = list(islice(reader.read_keys(), 2))
        assert keys == ["ñ", "á"]

    def test_fkey_extendida(self):
        reader = make_reader(["\x00", chr(0x3B)])
        assert next(reader.read_keys()) == "F1"
