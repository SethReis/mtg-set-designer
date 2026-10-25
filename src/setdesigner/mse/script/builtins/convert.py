"""Conversions: to_int, to_real, to_number, to_string, to_boolean, to_code, type_name."""
from __future__ import annotations

from .. import values as V
from ..values import ErrorValue, ScriptError
from .registry import builtin


@builtin("to_int")
def to_int(input):
    if isinstance(input, bool):
        return int(input)
    if input == "":
        return 0
    return V.to_int(input)


@builtin("to_real")
def to_real(input):
    if isinstance(input, bool):
        return float(input)
    if input == "":
        return 0.0
    return V.to_double(input)


@builtin("to_number")
def to_number(input):
    """An integer if the value looks like one, else a real number."""
    if isinstance(input, bool):
        return int(input)
    if input is None or input == "":
        return 0
    if V.is_number(input):
        return input
    try:
        return V.to_int(input)
    except ScriptError:
        return V.to_double(input)


@builtin("to_string")
def to_string(input):
    try:
        return V.to_str(input)
    except ScriptError as e:
        return ErrorValue(str(e))           # MSE delays conversion errors


@builtin("to_boolean")
def to_boolean(input):
    if V.is_int(input):
        return input != 0
    return V.to_bool(input)


@builtin("to_code")
def to_code(input):
    return V.to_code(input)


@builtin("type_name")
def type_name(input):
    return V.type_name(input)
