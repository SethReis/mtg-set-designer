import pytest

from setdesigner.mse.script.tokens import ScriptSyntaxError, tokenize, tokenize_template


def kinds_values(src: str) -> list[tuple[str, object]]:
    return [(t.kind, t.value) for t in tokenize(src) if t.kind != "eof"]


def test_names_numbers_ops_and_comments() -> None:
    assert kinds_values("x := 1.5 + y_2 # comment\n") == [
        ("name", "x"), ("op", ":="), ("number", 1.5), ("op", "+"), ("name", "y_2")]


def test_digit_after_dot_is_a_name() -> None:
    assert kinds_values("colors.0") == [("name", "colors"), ("op", "."), ("name", "0")]


def test_string_escapes() -> None:
    (tok,) = [t for t in tokenize(r'"a\"b\{c\}\n\<\&"') if t.kind == "string"]
    assert tok.value == ['a"b{c}\n\x01']        # \< is the special "escaped <" character


def test_nested_interpolation() -> None:
    (tok,) = [t for t in tokenize('"a{b + "c{d}"}e"') if t.kind == "string"]
    head, inner, tail = tok.value
    assert (head, tail) == ("a", "e")
    assert [t.kind for t in inner] == ["name", "op", "string", "eof"]
    assert inner[2].value[0] == "c"
    assert [t.value for t in inner[2].value[1]] == ["d", None]


def test_starts_line() -> None:
    toks = tokenize("a\n\t+ b # x\n\n c")
    assert [(t.value, t.starts_line) for t in toks if t.kind != "eof"] == [
        ("a", True), ("+", True), ("b", False), ("c", True)]


def test_errors_report_line() -> None:
    with pytest.raises(ScriptSyntaxError, match="line 2"):
        tokenize('x\n"unterminated')
    with pytest.raises(ScriptSyntaxError, match="unknown escape"):
        tokenize(r'"\q"')


def test_template_is_one_string_token() -> None:
    tok = tokenize_template("{ 30 + x }")
    assert len(tok.value) == 1 and not isinstance(tok.value[0], str)
    assert tokenize_template("plain text").value == ["plain text"]
