"""Tests para tmuxw.config: tokenize y load_config."""

from tmuxw.config import load_config, tokenize

# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_tokenize_simple():
    assert tokenize("bind | split-window -h") == ["bind", "|", "split-window", "-h"]


def test_tokenize_double_quotes_and_trailing_comment():
    assert tokenize('set -g status-right "#H %H:%M" # reloj') == [
        "set",
        "-g",
        "status-right",
        "#H %H:%M",
    ]


def test_tokenize_single_quotes_with_double_quote_inside():
    assert tokenize("unbind '\"'") == ["unbind", '"']


def test_tokenize_double_quotes_with_single_quote_inside():
    assert tokenize('display "it\'s ok"') == ["display", "it's ok"]


def test_tokenize_backslash_escapes():
    assert tokenize(r"bind \; command") == ["bind", ";", "command"]
    assert tokenize(r"display \#nocomment") == ["display", "#nocomment"]
    assert tokenize(r"run a\ b") == ["run", "a b"]


def test_tokenize_backslash_literal_inside_single_quotes():
    assert tokenize(r"run 'a\b'") == ["run", "a\\b"]


def test_tokenize_hash_inside_quotes_not_comment():
    assert tokenize("set -g status-left '#S '") == ["set", "-g", "status-left", "#S "]
    assert tokenize('set x "#H"') == ["set", "x", "#H"]


def test_tokenize_comment_discards_rest():
    assert tokenize("set -g mouse on # activa raton off") == ["set", "-g", "mouse", "on"]


def test_tokenize_empty_and_comment_only():
    assert tokenize("") == []
    assert tokenize("    ") == []
    assert tokenize("# solo comentario") == []
    assert tokenize("   # comentario indentado") == []


def test_tokenize_empty_quoted_token_preserved():
    assert tokenize("send-keys ''") == ["send-keys", ""]
    assert tokenize('send-keys ""') == ["send-keys", ""]


def test_tokenize_adjacent_quoted_and_bare():
    assert tokenize('set abc"def ghi"') == ["set", "abcdef ghi"]
    assert tokenize("set 'a b'c") == ["set", "a bc"]


def test_tokenize_multiple_whitespace_and_tabs():
    assert tokenize("set\t-g   prefix\tC-a") == ["set", "-g", "prefix", "C-a"]


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_missing_file(tmp_path):
    calls = []
    errors = load_config(tmp_path / "no-existe.conf", calls.append)
    assert errors == []
    assert calls == []


def test_load_config_executes_non_empty_lines(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text(
        "# comentario inicial\n"
        "set -g prefix C-a\n"
        "\n"
        "   # otro comentario\n"
        "bind | split-window -h\n"
        "unbind '\"'\n",
        encoding="utf-8",
    )
    calls = []
    errors = load_config(conf, calls.append)
    assert errors == []
    assert calls == [
        ["set", "-g", "prefix", "C-a"],
        ["bind", "|", "split-window", "-h"],
        ["unbind", '"'],
    ]


def test_load_config_accumulates_errors_with_line_numbers(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text(
        "good one\nbad command\ngood two\nbad again\n",
        encoding="utf-8",
    )
    seen = []

    def execute(tokens):
        seen.append(tokens)
        if tokens[0] == "bad":
            raise ValueError(f"comando desconocido: {tokens[1]}")

    errors = load_config(conf, execute)
    assert len(errors) == 2
    assert errors[0] == f"{conf}:2: comando desconocido: command"
    assert errors[1] == f"{conf}:4: comando desconocido: again"
    # Un error no detiene la ejecucion de las lineas siguientes.
    assert len(seen) == 4


def test_load_config_line_continuation(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text(
        'set -g status-right \\\n"%H:%M"\nbind x kill-pane\n',
        encoding="utf-8",
    )
    calls = []
    errors = load_config(conf, calls.append)
    assert errors == []
    assert calls == [
        ["set", "-g", "status-right", "%H:%M"],
        ["bind", "x", "kill-pane"],
    ]


def test_load_config_continuation_keeps_line_numbers(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text("a \\\nb\nfail aqui\n", encoding="utf-8")

    def execute(tokens):
        if tokens[0] == "fail":
            raise RuntimeError("boom")

    errors = load_config(conf, execute)
    # La linea logica "a b" ocupa lineas 1-2; "fail" es la fisica 3.
    assert errors == [f"{conf}:3: boom"]


def test_load_config_continuation_error_reports_first_line(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text("ok\nmal \\\ncontinuada\n", encoding="utf-8")

    def execute(tokens):
        if tokens[0] == "mal":
            raise ValueError("linea mala")

    errors = load_config(conf, execute)
    assert errors == [f"{conf}:2: linea mala"]


def test_load_config_accepts_str_path(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_text("set -g mouse on\n", encoding="utf-8")
    calls = []
    errors = load_config(str(conf), calls.append)
    assert errors == []
    assert calls == [["set", "-g", "mouse", "on"]]


def test_load_config_non_utf8_bytes_replaced(tmp_path):
    conf = tmp_path / "t.conf"
    conf.write_bytes(b"set -g status-left \xff\xfe\n")
    calls = []
    errors = load_config(conf, calls.append)
    assert errors == []
    assert len(calls) == 1
    assert calls[0][:3] == ["set", "-g", "status-left"]
    assert "�" in calls[0][3]
