"""MSE script: tokenizer, parser and evaluator.

    from setdesigner.mse.script import run
    run("30 + name_font_vertical()", functions={"name_font_vertical": lambda: 4})   # -> 34
"""
from __future__ import annotations

from typing import Callable

from .evaluator import Context, Evaluator, evaluate
from .parser import parse, parse_template
from .tokens import ScriptSyntaxError
from .values import ErrorValue, HostFunction, ScriptError, ScriptFunction, to_code

__all__ = ["parse", "parse_template", "evaluate", "run", "Evaluator", "Context", "ErrorValue",
           "HostFunction", "ScriptError", "ScriptSyntaxError", "ScriptFunction", "to_code"]


def run(source: str, variables: dict[str, object] | None = None,
        functions: dict[str, Callable] | None = None, ctx: Context | None = None) -> object:
    """Parse and evaluate script code in one step."""
    return evaluate(parse(source), variables, functions, ctx)
