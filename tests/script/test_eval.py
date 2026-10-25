"""Evaluator tests. Snippets marked "real" are copied from the MSE packages."""
import pytest

from setdesigner.mse.script import ErrorValue, ScriptError, evaluate, parse, parse_template, run


def test_template_with_host_function() -> None:
    # real: magic-m15-altered style, name box `top`
    node = parse_template("{ 30 + name_font_vertical() }")
    assert evaluate(node, functions={"name_font_vertical": lambda: 4}) == 34


def test_mana_t_if_chain() -> None:
    # real: magic-m15-altered init script (body of `mana_t := { ... }`)
    src = '''
        if      styling.tap_symbol == "old"        then "old"
        else if styling.tap_symbol == "diagonal T" then "older"
        else                                            "new"
    '''
    for symbol, expected in [("old", "old"), ("diagonal T", "older"), ("modern", "new")]:
        assert run(src, {"styling": {"tap symbol": symbol}}) == expected


def test_case_expression() -> None:
    # real: magic.mse-game script, body of `token_shape`
    src = '''
        case input of
            "token": true,
            "emblem": true,
            "counter": true,
            else: false;
    '''
    assert run(src, {"input": "emblem"}) is True
    assert run(src, {"input": "normal"}) is False


def test_or_else_replaces_error_values_only() -> None:
    def missing_image(input):
        return ErrorValue("no such image")      # built-ins report soft failures as values

    def broken(input):
        raise ScriptError("hard failure")

    assert run('import_image("x") or else "fallback"', functions={"import_image": missing_image}) == "fallback"
    assert run("nil or else 2") is None
    with pytest.raises(ScriptError, match="hard failure"):
        run('import_image("x") or else "fallback"', functions={"import_image": broken})


def test_assignment_and_sequence_scope() -> None:
    assert run("a := 2\nb := a * 3\nb + 1") == 7


def test_short_circuit() -> None:
    calls = []
    assert run("false and boom()", functions={"boom": lambda: calls.append(1)}) is False
    assert run("true or boom()", functions={"boom": lambda: calls.append(1)}) is True
    assert calls == []


def test_member_and_index_reads() -> None:
    assert run("[w: 1, u: 2][input]", {"input": "u"}) == 2
    assert run("nums.0 + nums.1", {"nums": [10, 5]}) == 15


def test_interpolation_and_concatenation() -> None:
    assert run('"x{1 + 1}y"') == "x2y"
    assert run('"{n}"', {"n": 5}) == 5          # lone {expr} keeps its type
    assert run('"n=" + 3') == "n=3"


def test_errors() -> None:
    # Value rules in general are checked against real MSE in test_oracle.py.
    with pytest.raises(ScriptError, match="not set"):
        run("missing + 1")
    with pytest.raises(ScriptError, match="boolean"):
        run('if "maybe" then 1')
    with pytest.raises(ScriptError, match="Stack overflow"):
        run("f := { f() }; f()")


def test_host_functions_read_arguments_by_name() -> None:
    def pad(input, width=3, fill="0"):
        return str(input).rjust(width, fill)

    assert run("pad(7)", functions={"pad": pad}) == "007"
    assert run('pad(7, fill: "-", width: 4)', functions={"pad": pad}) == "---7"
    assert run("p2 := pad@(width: 5); p2(1)", functions={"pad": pad}) == "00001"
    # Built-ins see the caller's variables too (dynamic scope), like MSE's.
    assert run("f := { pad(input) }; width := 2; f(5)", functions={"pad": pad}) == "05"


def test_partial_chain_with_composition() -> None:
    # real shape: magic.mse-game `split_sub_type := remove_tag@(...) + split_text@(...)`
    funcs = {"upper": lambda input: input.upper(), "suffix": lambda input, s: input + s}
    assert run('t := upper + suffix@(s: "!"); t("hi")', functions=funcs) == "HI!"


def test_parse_is_reusable() -> None:
    node = parse("x * 2")
    assert [evaluate(node, {"x": i}) for i in range(3)] == [0, 2, 4]
