"""Script values and the conversions/operators on them.

Values are plain Python objects: None (nil), bool, int, float, str, list, dict
(a map; iterated and printed in sorted key order, like MSE's std::map), plus the
function types below and ErrorValue.

The rules follow MSE's src/script/value.cpp and context.cpp and are verified
against the real program: see tools/oracle_cases.txt and tests/script/test_oracle.py.
Known deviations are listed in docs/interpreter_stages.md.
"""
from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from typing import Callable

from . import ast as A
from .tokens import ESCAPED_LANGLE


class ScriptError(Exception):
    """A runtime error while evaluating a script."""


@dataclass(frozen=True)
class ErrorValue:
    """MSE's "delayed error": e.g. a missing map key. It only fails when the value is
    used, and `x or else y` replaces it with y."""
    message: str

    def fail(self):
        raise ScriptError(self.message)


# ---------------------------------------------------------------- colors

@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: int = 255

    def code(self) -> str:
        if self.a == 255:
            return f"rgb({self.r},{self.g},{self.b})"
        return f"rgba({self.r},{self.g},{self.b},{self.a})"

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)


def to_color(value: object) -> Color:
    """A Color from a color value or text: rgb(...), rgba(...), #rrggbb or a color name."""
    check(value)
    if isinstance(value, Color):
        return value
    if isinstance(value, str):
        from PIL import ImageColor          # names and #hex as in CSS
        text = value.strip()
        try:
            parts = ImageColor.getrgb(text)
        except ValueError:
            raise ScriptError(f"Can't convert {value!r} to color") from None
        return Color(*parts) if len(parts) == 4 else Color(*parts, 255)
    raise conversion_error(value, "color")


# ------------------------------------------------------------- functions

@dataclass
class ScriptFunction:
    """A `{ ... }` function literal."""
    body: A.Node


@dataclass
class Closure:
    """`f@(name: value, ...)`: f with default arguments. A default applies only if the
    caller did not pass that argument."""
    func: object
    bindings: dict[str, object] = field(default_factory=dict)


@dataclass
class Compose:
    """`f + g`: call f, then g with f's result as `input`."""
    first: object
    second: object


@dataclass
class HostFunction:
    """A function written in Python. Like MSE's built-ins, it reads its parameters from
    the script's variables, matched by parameter name (`input`, `match`, ...).

    A Python parameter named `script` isn't read from the variables; it receives a
    Caller (see evaluator.py) for calling script functions back and reading variables."""
    fn: Callable
    params: list[tuple[str, str, bool]]     # (script name, Python name, required)
    name: str = ""
    wants_script: bool = False

    @classmethod
    def wrap(cls, fn: Callable, name: str = "",
             rename: dict[str, str] | None = None) -> "HostFunction":
        """`rename` maps Python parameter names to script names, e.g. {"in_": "in"}."""
        rename = rename or {}
        params, wants_script = [], False
        for p in inspect.signature(fn).parameters.values():
            if p.name == "script":
                wants_script = True
                continue
            params.append((rename.get(p.name, p.name), p.name, p.default is inspect.Parameter.empty))
        return cls(fn, params, name or getattr(fn, "__name__", ""), wants_script)


FUNCTION_TYPES = (ScriptFunction, Closure, Compose, HostFunction)


def as_value(value: object) -> object:
    """Wrap plain Python callables passed in from outside as host functions."""
    if callable(value) and not isinstance(value, FUNCTION_TYPES) and not isinstance(value, type):
        return HostFunction.wrap(value)
    return value


def is_function(value: object) -> bool:
    return isinstance(value, FUNCTION_TYPES)


# ----------------------------------------------------------- conversions

def type_name(value: object) -> str:
    """Type names as MSE prints them in error messages."""
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer number"
    if isinstance(value, float):
        return "real number"
    if isinstance(value, str):
        return f'string ("{value}")'
    if isinstance(value, (list, dict)):
        return "collection"
    if isinstance(value, HostFunction):
        return f"built-in function '{value.name}'"
    if is_function(value):
        return "function"
    if isinstance(value, ErrorValue):
        return "error"
    if isinstance(value, Color):
        return "color"
    return getattr(value, "type_label", type(value).__name__)


def check(value: object) -> object:
    """Raise if value is an ErrorValue (using a delayed error makes it fail)."""
    if isinstance(value, ErrorValue):
        value.fail()
    return value


def conversion_error(value: object, target: str) -> ScriptError:
    return ScriptError(f"Can't convert from {type_name(value)} to {target}")


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: object) -> bool:
    return is_int(value) or isinstance(value, float)


def format_double(value: float) -> str:
    return format(value, "g")                   # C's %g, as MSE prints doubles


def to_bool(value: object) -> bool:
    check(value)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value in ("yes", "true"):
            return True
        if value in ("no", "false", ""):
            return False
    raise conversion_error(value, "boolean")   # numbers too: `if 1` is an error in MSE


def to_int(value: object) -> int:
    check(value)
    if value is None:
        return 0
    if is_int(value):
        return value
    if isinstance(value, float):
        return int(value)                       # truncates, like C
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    raise conversion_error(value, "integer number")


def to_double(value: object) -> float:
    check(value)
    if value is None:
        return 0.0
    if is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    raise conversion_error(value, "real number")


def to_str(value: object) -> str:
    check(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if is_int(value):
        return str(value)
    if isinstance(value, float):
        return format_double(value)
    if isinstance(value, str):
        return value
    if isinstance(value, Color):
        return value.code()
    if hasattr(value, "script_string"):         # e.g. a keyword parameter
        return value.script_string()
    raise conversion_error(value, "string")


def _quote(text: str) -> str:
    escaped = (text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
               .replace("\t", "\\t").replace(ESCAPED_LANGLE, "\\<"))
    return f'"{escaped}"'


def to_code(value: object) -> str:
    """A value as MSE prints it (its toCode form): `"text"`, `[1,"b"]`, `["k":1]`, `nil`."""
    check(value)
    if value is None:
        return "nil"
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list):
        return "[" + ",".join(to_code(v) for v in value) + "]"
    if isinstance(value, dict):
        return "[" + ",".join(f"{_quote(str(k))}:{to_code(v)}" for k, v in sorted(value.items())) + "]"
    if isinstance(value, Color):
        return value.code()
    return to_str(value)


# ---------------------------------------------------------- collections

def iterate(value: object) -> list[tuple[object, object]]:
    """(key, value) pairs: list items by index, then map entries in sorted key order."""
    check(value)
    if hasattr(value, "script_items"):          # e.g. a set: its cards
        return value.script_items()
    if isinstance(value, list):
        return list(enumerate(value))
    if isinstance(value, dict):
        return sorted(value.items())
    raise conversion_error(value, "collection")


def is_object(value: object) -> bool:
    """Objects with members of their own (card, set, styling, ...; see mse/objects.py)."""
    return hasattr(value, "script_member")


def member(obj: object, key: object) -> object:
    """obj.key / obj[key]. A missing member is an ErrorValue, not an exception."""
    if isinstance(obj, ErrorValue):
        return obj
    check(key)
    if is_object(obj):
        return obj.script_member(key)
    if isinstance(obj, dict):
        name = to_str(key)
        if name in obj:
            return obj[name]
        if name.replace("_", " ") in obj:      # MSE names: `tap_symbol` finds "tap symbol"
            return obj[name.replace("_", " ")]
        return ErrorValue(f"collection has no member '{name}'")
    if isinstance(obj, (list, str)):
        try:
            index = to_int(key)
        except ScriptError:
            index = None
        if index is not None and 0 <= index < len(obj):
            return obj[index]
        return ErrorValue(f"{'collection' if isinstance(obj, list) else 'string'} has no member '{to_str(key)}'")
    if obj is not None and isinstance(key, str):
        for attr in (key, key.replace(" ", "_")):
            if hasattr(obj, attr):
                return getattr(obj, attr)
    return ErrorValue(f"{type_name(obj)} has no member '{to_str(key)}'")


# ------------------------------------------------------------ operators

def add(a: object, b: object) -> object:
    """`+`: nil is the identity (loops add up their results starting from nil)."""
    check(a)
    check(b)
    if a is None:
        return b
    if b is None:
        return a
    if is_function(a) and is_function(b):
        return Compose(a, b)
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if isinstance(a, dict) and isinstance(b, dict):
        return {**b, **a}                       # first wins on lookup, as in MSE
    if is_int(a) and is_int(b):
        return a + b
    if is_number(a) and is_number(b):
        return float(a) + float(b)
    return to_str(a) + to_str(b)


def arithmetic(op: str, a: object, b: object) -> int | float:
    check(a)
    check(b)
    real = isinstance(a, float) or isinstance(b, float)
    if op == "/":
        x, y = to_double(a), to_double(b)
        if y == 0:
            raise ScriptError("Division by zero")
        return x / y
    if op == "^":
        if not real and to_int(b) >= 0:
            return to_int(a) ** to_int(b)
        return to_double(a) ** to_double(b)
    x, y = (to_double(a), to_double(b)) if real else (to_int(a), to_int(b))
    if op == "-":
        return x - y
    if op == "*":
        return x * y
    if y == 0:
        raise ScriptError("Division by zero")
    if op == "div":
        return int(x / y) if real else _trunc_div(x, y)
    if op == "mod":
        return math.fmod(x, y) if real else x - y * _trunc_div(x, y)
    raise ScriptError(f"unknown operator {op}")


def _trunc_div(x: int, y: int) -> int:
    """Integer division rounding toward zero, like C (Python's // rounds down)."""
    q = abs(x) // abs(y)
    return q if (x >= 0) == (y >= 0) else -q


def negate(value: object) -> int | float:
    check(value)
    return -value if isinstance(value, float) else -to_int(value)


def equal(a: object, b: object) -> bool:
    check(a)
    check(b)
    if a is b:
        return True
    if is_object(a) or is_object(b):
        return False                            # cards etc. are equal only to themselves
    if is_int(a) and is_int(b) or isinstance(a, bool) and isinstance(b, bool):
        return a == b
    if is_number(a) and is_number(b):
        return math.isclose(a, b, rel_tol=1e-14, abs_tol=1e-14)
    if isinstance(a, (list, dict)) and isinstance(b, (list, dict)):
        # MSE compares element values in iteration order; map keys are ignored.
        xs, ys = iterate(a), iterate(b)
        return len(xs) == len(ys) and all(equal(x, y) for (_, x), (_, y) in zip(xs, ys))
    return to_code(a) == to_code(b)


def less(a: object, b: object) -> bool:
    """Ordering is numeric only; strings are converted to numbers."""
    check(a)
    check(b)
    if isinstance(a, float) or isinstance(b, float):
        return to_double(a) < to_double(b)
    return to_int(a) < to_int(b)


def compare(op: str, a: object, b: object) -> bool:
    if op == "==":
        return equal(a, b)
    if op == "!=":
        return not equal(a, b)
    if op == "<":
        return less(a, b)
    if op == ">":
        return less(b, a)
    if op == "<=":
        return not less(b, a)
    if op == ">=":
        return not less(a, b)
    raise ScriptError(f"unknown comparison {op}")
