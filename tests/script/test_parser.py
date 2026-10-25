from setdesigner.mse.script import ast as A
from setdesigner.mse.script.parser import parse, parse_template


def shape(node: A.Node) -> object:
    """Compact form of a tree, for readable assertions."""
    if isinstance(node, A.Literal):
        return node.value
    if isinstance(node, A.Var):
        return node.name
    if isinstance(node, A.BinOp):
        return (node.op, shape(node.left), shape(node.right))
    if isinstance(node, (A.And, A.Or, A.Xor, A.OrElse)):
        return (type(node).__name__.lower(), shape(node.left), shape(node.right))
    if isinstance(node, (A.Not, A.Neg)):
        return (type(node).__name__.lower(), shape(node.operand))
    if isinstance(node, A.Assign):
        return (":=", node.name, shape(node.value))
    if isinstance(node, A.Seq):
        return ("seq",) + tuple(shape(i) for i in node.items)
    if isinstance(node, (A.Call, A.Partial)):
        tag = "call" if isinstance(node, A.Call) else "partial"
        return (tag, shape(node.func)) + tuple((n, shape(v)) for n, v in node.args)
    if isinstance(node, A.Member):
        return (".", shape(node.obj), shape(node.key))
    if isinstance(node, A.If):
        return ("if", shape(node.cond), shape(node.then),
                shape(node.otherwise) if node.otherwise else None)
    if isinstance(node, A.FuncLit):
        return ("fn", shape(node.body))
    if isinstance(node, A.ListLit):
        return ("list",) + tuple((n, shape(v)) for n, v in node.items)
    if isinstance(node, A.Interp):
        return ("interp",) + tuple(shape(p) for p in node.parts)
    return type(node).__name__


def p(src: str) -> object:
    return shape(parse(src))


# ------------------------------------------------------------ precedence

def test_arithmetic_precedence() -> None:
    assert p("1 + 2 * 3") == ("+", 1, ("*", 2, 3))
    assert p("1 - 2 - 3") == ("-", ("-", 1, 2), 3)
    assert p("2 ^ 3 ^ 2") == ("^", 2, ("^", 3, 2))           # right-associative
    assert p("a mod 2 + b div 3") == ("+", ("mod", "a", 2), ("div", "b", 3))
    assert p("-a.b") == ("neg", (".", "a", "b"))


def test_comparison_and_boolean_precedence() -> None:
    assert p("a + 1 == b and not c or d") == (
        "or", ("and", ("==", ("+", "a", 1), "b"), ("not", "c")), "d")
    assert p("a = b") == ("==", "a", "b")                     # deprecated single =
    assert p("a xor b") == ("xor", "a", "b")


def test_or_else_takes_an_additive_right_side() -> None:
    assert p("a or else b + c") == ("orelse", "a", ("+", "b", "c"))


def test_assignment_and_sequences() -> None:
    assert p("x := y := 1") == (":=", "x", (":=", "y", 1))
    assert p("a := 1; b := 2;") == ("seq", (":=", "a", 1), (":=", "b", 2))
    assert p("a := 1\nb := a + 1") == ("seq", (":=", "a", 1), (":=", "b", ("+", "a", 1)))


# --------------------------------------------------------------- newlines

def test_operator_at_line_start_continues_expression() -> None:
    src = 'f := remove_tag@(tag:"<word")\n\t+ trim'
    assert p(src) == (":=", "f", ("+", ("partial", "remove_tag", ("tag", "<word")), "trim"))
    assert p("(a\n\tand b)") == ("and", "a", "b")


def test_paren_on_next_line_is_not_a_call() -> None:
    assert p("f\n(1)") == ("seq", "f", 1)
    assert p("f(1)") == ("call", "f", (None, 1))


def test_multiline_if_and_assignment_on_next_line() -> None:
    src = "x :=\n{\n\tif a then 1\n\telse if b then 2\n\telse 3\n}"
    assert p(src) == (":=", "x", ("fn", ("if", "a", 1, ("if", "b", 2, 3))))
    assert p("if(a != 0) then b") == ("if", ("!=", "a", 0), "b", None)


# ------------------------------------------------------------ constructs

def test_calls_named_args_and_partial_application() -> None:
    assert p('contains(card.shape, match: "split")') == (
        "call", "contains", (None, (".", ("card"), "shape")), ("match", "split"))
    assert p("{ img }@(height:0)") == ("partial", ("fn", "img"), ("height", 0))


def test_lists_maps_and_member_access() -> None:
    assert p("[1, 2 3]") == ("list", (None, 1), (None, 2), (None, 3))   # commas optional
    assert p("[w: 1, u: 2][input]") == (".", ("list", ("w", 1), ("u", 2)), "input")
    assert p("nums.0") == (".", "nums", "0")


def test_case_with_else_and_trailing_semicolon() -> None:
    node = parse('{ case input of\n\t"token": true,\n\t"emblem": true,\n\telse: false;\n}').body
    assert isinstance(node, A.Case)
    assert [shape(v) for v, _ in node.cases] == ["token", "emblem"]
    assert shape(node.otherwise) is False


def test_for_loops() -> None:
    node = parse("for each k:v in map do v")
    assert isinstance(node, A.ForEach) and (node.key_var, node.var) == ("k", "v")
    node = parse("for x from 0 to 5 do x")
    assert isinstance(node, A.ForRange) and node.key_var is None


def test_string_interpolation() -> None:
    assert p('"a{x}b"') == ("interp", "a", "x", "b")
    assert p('""') == ""


def test_templates() -> None:
    assert shape(parse_template("{ 30 + name_font_vertical() }")) == (
        "+", 30, ("call", "name_font_vertical"))
    assert shape(parse_template("plain")) == "plain"
    assert shape(parse_template("Hi {name}!")) == ("interp", "Hi ", "name", "!")
