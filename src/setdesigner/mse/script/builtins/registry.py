"""The table of implemented built-in functions, filled by the @builtin decorator."""
from __future__ import annotations

from typing import Callable

from ..values import HostFunction

IMPLEMENTED: dict[str, HostFunction] = {}


def builtin(*names: str, rename: dict[str, str] | None = None) -> Callable:
    """Register a Python function as MSE built-in(s). Its parameter names are the
    script's argument names; `rename` maps Python names to script names where the
    script name is a Python keyword (e.g. {"in_": "in"})."""
    def register(fn: Callable) -> Callable:
        for name in names:
            IMPLEMENTED[name] = HostFunction.wrap(fn, name, rename)
        return fn
    return register
