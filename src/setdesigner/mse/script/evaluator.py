"""Tree-walking evaluator for MSE script.

Scoping works like MSE's (src/script/context.cpp): one table of variables, a
scope level, and a stack of shadowed bindings.
  * A function call opens a scope. Assigning a variable inside it saves the old
    binding, and closing the scope restores it, so a function's `:=` are local.
  * Reading a variable sees every level, so scoping is *dynamic*: a called
    function sees its caller's variables (`input`, `card`, loop variables, ...).
"""
from __future__ import annotations

import sys
from typing import Callable

from . import ast as A
from .values import (Closure, Color, Compose, ErrorValue, HostFunction, ScriptError, ScriptFunction,
                     add, arithmetic, as_value, check, compare, equal, iterate, less, member,
                     negate, to_bool, to_double, to_int, type_name)

_UNSET = object()
MAX_DEPTH = 500                     # MSE's limit on nested calls
PYTHON_RECURSION_LIMIT = 20_000


class Context:
    """All variables of a running script, with MSE-style scope levels."""

    def __init__(self, variables: dict[str, object] | None = None):
        self.vars: dict[str, object] = {}
        self.levels: dict[str, int] = {}
        self.level = 0
        self.shadowed: list[tuple[str, object, int | None]] = []
        self.warnings: list[str] = []           # e.g. failed assert(...)
        for name, value in (variables or {}).items():
            self.set(name, as_value(value))

    def get(self, name: str) -> object:
        value = self.vars.get(name, _UNSET)
        if value is _UNSET:
            raise ScriptError(f"Variable not set: {name}")
        return value

    def has(self, name: str) -> bool:
        return name in self.vars

    def set_here(self, name: str) -> bool:
        """Was this variable set in the current (innermost) scope?"""
        return self.levels.get(name) == self.level

    def set(self, name: str, value: object) -> None:
        old_level = self.levels.get(name)
        if old_level is None or old_level < self.level:
            self.shadowed.append((name, self.vars.get(name, _UNSET), old_level))
        self.vars[name] = value
        self.levels[name] = self.level

    def open_scope(self) -> int:
        if self.level >= MAX_DEPTH:
            raise ScriptError("Stack overflow")
        self.level += 1
        return len(self.shadowed)

    def open_isolated_scope(self) -> int:
        """Like open_scope, but the new scope only sees global (level 0) variables:
        everything set by the scripts currently running is hidden until close_scope.
        Used to compute one card's field from inside another card's script without
        the outer script's local variables leaking in (dynamic scoping would let them)."""
        marker = self.open_scope()
        for name, level in list(self.levels.items()):
            if level > 0:
                self.shadowed.append((name, self.vars.pop(name), level))
                del self.levels[name]
        return marker

    def close_scope(self, marker: int) -> None:
        while len(self.shadowed) > marker:
            name, value, level = self.shadowed.pop()
            if value is _UNSET:
                del self.vars[name]
                del self.levels[name]
            else:
                self.vars[name] = value
                self.levels[name] = level
        self.level -= 1


class Evaluator:
    def __init__(self):
        # Each script call level uses several Python frames; make room for MSE's 500 levels.
        if sys.getrecursionlimit() < PYTHON_RECURSION_LIMIT:
            sys.setrecursionlimit(PYTHON_RECURSION_LIMIT)

    def eval(self, node: A.Node, ctx: Context) -> object:
        method = getattr(self, f"eval_{type(node).__name__}")
        return method(node, ctx)

    # ---------------------------------------------------------- basics

    def eval_Literal(self, node: A.Literal, ctx: Context) -> object:
        return node.value

    def eval_Var(self, node: A.Var, ctx: Context) -> object:
        return ctx.get(node.name)

    def eval_Assign(self, node: A.Assign, ctx: Context) -> object:
        value = self.eval(node.value, ctx)
        ctx.set(node.name, value)
        return value

    def eval_Seq(self, node: A.Seq, ctx: Context) -> object:
        result = None
        for item in node.items:
            result = self.eval(item, ctx)
        return result

    def eval_Interp(self, node: A.Interp, ctx: Context) -> object:
        # Pieces are joined with `+` exactly as MSE does, so a lone `{expr}` keeps the
        # expression's own value (a template `{ 30 + x }` is a number, not text).
        result = None
        for part in node.parts:
            result = add(result, self.eval(part, ctx))
        return result

    def eval_ListLit(self, node: A.ListLit, ctx: Context) -> object:
        if node.items and all(name is not None for name, _ in node.items):
            return {name: self.eval(value, ctx) for name, value in node.items}
        if any(name is not None for name, _ in node.items):
            raise ScriptError(f"line {node.line}: mixed named and unnamed list entries")
        return [self.eval(value, ctx) for _, value in node.items]

    # ---------------------------------------------------- control flow

    def eval_If(self, node: A.If, ctx: Context) -> object:
        if to_bool(self.eval(node.cond, ctx)):
            return self.eval(node.then, ctx)
        return self.eval(node.otherwise, ctx) if node.otherwise else None

    def eval_Case(self, node: A.Case, ctx: Context) -> object:
        subject = self.eval(node.subject, ctx)
        for value, result in node.cases:
            if equal(subject, self.eval(value, ctx)):
                return self.eval(result, ctx)
        return self.eval(node.otherwise, ctx) if node.otherwise else None

    def eval_ForEach(self, node: A.ForEach, ctx: Context) -> object:
        result = None
        for key, value in iterate(self.eval(node.collection, ctx)):
            if node.key_var:
                ctx.set(node.key_var, key)
            ctx.set(node.var, value)
            result = add(result, self.eval(node.body, ctx))
        return result

    def eval_ForRange(self, node: A.ForRange, ctx: Context) -> object:
        start = to_int(self.eval(node.start, ctx))
        end = to_int(self.eval(node.end, ctx))
        result = None
        for pos in range(start, end + 1):          # both ends included
            if node.key_var:
                ctx.set(node.key_var, pos - start)
            ctx.set(node.var, pos)
            result = add(result, self.eval(node.body, ctx))
        return result

    # -------------------------------------------------------- operators

    def eval_And(self, node: A.And, ctx: Context) -> object:
        # The left side must be a boolean; the right side's value is returned as is.
        if not to_bool(self.eval(node.left, ctx)):
            return False
        return self.eval(node.right, ctx)

    def eval_Or(self, node: A.Or, ctx: Context) -> object:
        if to_bool(self.eval(node.left, ctx)):
            return True
        return self.eval(node.right, ctx)

    def eval_Xor(self, node: A.Xor, ctx: Context) -> object:
        return to_bool(self.eval(node.left, ctx)) != to_bool(self.eval(node.right, ctx))

    def eval_OrElse(self, node: A.OrElse, ctx: Context) -> object:
        # Replaces error *values* only: not nil, and not errors that are raised.
        value = self.eval(node.left, ctx)
        return self.eval(node.right, ctx) if isinstance(value, ErrorValue) else value

    def eval_Not(self, node: A.Not, ctx: Context) -> object:
        return not to_bool(self.eval(node.operand, ctx))

    def eval_Neg(self, node: A.Neg, ctx: Context) -> object:
        return negate(self.eval(node.operand, ctx))

    def eval_BinOp(self, node: A.BinOp, ctx: Context) -> object:
        left = self.eval(node.left, ctx)
        right = self.eval(node.right, ctx)
        if node.op == "+":
            return add(left, right)
        if node.op in ("==", "!=", "<", ">", "<=", ">="):
            return compare(node.op, left, right)
        return arithmetic(node.op, left, right)

    def eval_Member(self, node: A.Member, ctx: Context) -> object:
        return member(self.eval(node.obj, ctx), self.eval(node.key, ctx))

    # -------------------------------------------------------- functions

    def eval_FuncLit(self, node: A.FuncLit, ctx: Context) -> object:
        return ScriptFunction(node.body)

    def arguments(self, args: tuple[A.Arg, ...], ctx: Context) -> list[tuple[str, object]]:
        """Evaluate call arguments. Only the first unnamed argument is used, as `input`."""
        out: list[tuple[str, object]] = []
        has_input = False
        for name, value in args:
            evaluated = self.eval(value, ctx)
            if name is None:
                if has_input:
                    continue
                name, has_input = "input", True
            out.append((name, evaluated))
        return out

    def eval_Call(self, node: A.Call, ctx: Context) -> object:
        if isinstance(node.func, A.Var) and node.func.name in SPECIAL_FORMS:
            return getattr(self, SPECIAL_FORMS[node.func.name])(node, ctx)
        func = self.eval(node.func, ctx)
        return self.call_with(func, self.arguments(node.args, ctx), ctx)

    # MSE's parser treats these names as keywords that take positional arguments.

    def special_min_max(self, node: A.Call, ctx: Context) -> object:
        values = [self.eval(value, ctx) for _, value in node.args]
        if not values:
            raise ScriptError(f"line {node.line}: {node.func.name}() needs arguments")
        pick = less if node.func.name == "min" else (lambda a, b: less(b, a))
        best = values[0]
        for value in values[1:]:
            if pick(value, best):
                best = value
        real = any(isinstance(v, float) for v in values)
        return to_double(best) if real else to_int(best)

    def special_rgb(self, node: A.Call, ctx: Context) -> object:
        values = [to_int(self.eval(value, ctx)) for _, value in node.args]
        expected = 3 if node.func.name == "rgb" else 4
        if len(values) != expected:
            raise ScriptError(f"line {node.line}: {node.func.name}() needs {expected} numbers")
        return Color(*(max(0, min(255, v)) for v in values))

    def special_assert(self, node: A.Call, ctx: Context) -> object:
        if not node.args:
            raise ScriptError(f"line {node.line}: assert() needs a condition")
        if not to_bool(self.eval(node.args[0][1], ctx)):
            ctx.warnings.append(f"Assertion failure on line {node.line}")
        return None

    def eval_Partial(self, node: A.Partial, ctx: Context) -> object:
        func = check(self.eval(node.func, ctx))
        return Closure(func, dict(self.arguments(node.args, ctx)))

    def call_with(self, func: object, args: list[tuple[str, object]], ctx: Context) -> object:
        """Call a function value with arguments, in a new scope."""
        if isinstance(func, ErrorValue):
            return func                 # calling a delayed error gives the error (MSE)
        marker = ctx.open_scope()
        try:
            for name, value in args:
                ctx.set(name, value)
            return self.call(func, ctx)
        finally:
            ctx.close_scope(marker)

    def call(self, func: object, ctx: Context) -> object:
        """Run a function inside the already opened call scope."""
        if isinstance(func, ScriptFunction):
            return self.eval(func.body, ctx)
        if isinstance(func, Closure):
            for name, value in func.bindings.items():
                if not ctx.set_here(name):          # the caller's arguments win
                    ctx.set(name, value)
            return self.call(func.func, ctx)
        if isinstance(func, Compose):
            # Each half runs in its own scope, so e.g. the bindings of
            # replace@(match: "a") don't leak into the replace@(match: "b") after it.
            ctx.set("input", self.call_with(func.first, [], ctx))
            return self.call_with(func.second, [], ctx)
        if isinstance(func, HostFunction):
            kwargs: dict[str, object] = {}
            for script_name, py_name, required in func.params:
                if ctx.has(script_name):
                    kwargs[py_name] = check(ctx.get(script_name))
                elif required:
                    raise ScriptError(f"Variable not set: {script_name} (in function {func.name})")
            if func.wants_script:
                kwargs["script"] = Caller(self, ctx)
            return func.fn(**kwargs)
        if func is None:                            # nil is the identity function
            return ctx.get("input")
        raise ScriptError(f"Can't convert from {type_name(func)} to function")


SPECIAL_FORMS = {"min": "special_min_max", "max": "special_min_max", "assert": "special_assert",
                 "rgb": "special_rgb", "rgba": "special_rgb"}


class Caller:
    """Handed to host functions that take a `script` parameter."""

    def __init__(self, evaluator: Evaluator, ctx: Context):
        self.evaluator = evaluator
        self.ctx = ctx

    def call(self, func: object, **args: object) -> object:
        """Call a script function value, e.g. script.call(fn, input="x", _1="y")."""
        return self.evaluator.call_with(func, list(args.items()), self.ctx)

    def var(self, name: str, default: object = None) -> object:
        """A variable's value if it is set, else default."""
        return self.ctx.vars.get(name, default)

    def warn(self, message: str) -> None:
        self.ctx.warnings.append(message)


def evaluate(node: A.Node, variables: dict[str, object] | None = None,
             functions: dict[str, Callable] | None = None, ctx: Context | None = None) -> object:
    """Evaluate a parsed script. Pass `ctx` to run in an existing context (e.g. one
    with the game scripts loaded); otherwise a new one is made from the given
    variables and host functions."""
    if ctx is None:
        ctx = Context({**(functions or {}), **(variables or {})})
    else:
        for name, value in {**(functions or {}), **(variables or {})}.items():
            ctx.set(name, as_value(value))
    return Evaluator().eval(node, ctx)
