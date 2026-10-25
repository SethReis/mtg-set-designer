"""Load the game's and a style's `init script` into a script Context.

    ctx, report = load_game(root, style="magic-m15-altered")
    run('token_shape("emblem")', ctx=ctx)       # -> True

Statements are evaluated one at a time, so one failing definition is reported
instead of stopping the rest from loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..reader import read_file
from ..snippets import scripts_in
from . import ast as A
from .builtins import builtin_variables
from .evaluator import Context, Evaluator
from .parser import parse
from .values import ScriptError


@dataclass
class LoadReport:
    loaded: int = 0
    failures: list[str] = field(default_factory=list)    # "source line N (name): error"


def _init_script(path: Path, root: Path, source: str) -> str:
    nodes, _ = read_file(path, root)
    for snip in scripts_in(nodes, source):
        if snip.path == "init script":
            return snip.text
    return ""


def run_init_script(text: str, source: str, ctx: Context, report: LoadReport) -> None:
    tree = parse(text)
    statements = tree.items if isinstance(tree, A.Seq) else (tree,)
    evaluator = Evaluator()
    for statement in statements:
        try:
            evaluator.eval(statement, ctx)
            report.loaded += 1
        except ScriptError as e:
            name = statement.name if isinstance(statement, A.Assign) else "?"
            report.failures.append(f"{source} line {statement.line} ({name}): {e}")


def set_defaults(root: Path, game: str = "magic") -> dict[str, object]:
    """Initial value of every set field, keyed by field name (see FieldDef.initial_value).
    Used when no project is loaded; mse.environment gives scripts a real SetObject."""
    from ..fields import game_fields          # here to avoid an import cycle
    _, set_fields = game_fields(Path(root), game)
    return {name: fd.initial_value() for name, fd in set_fields.items()}


def load_game(root: Path, style: str | None = None, game: str = "magic",
              variables: dict[str, object] | None = None) -> tuple[Context, LoadReport]:
    """Context with the built-ins, the game's init script and (optionally) a style's.
    `style` is a package name without the extension, e.g. "magic-m15-altered".

    As in MSE, the init scripts run with a set loaded: `set` defaults to the game's
    set-field defaults and `card` to nil (`card.x` is then an error *value*, which is
    harmless unless used). Pass `variables` to override them."""
    seed = {**builtin_variables(), "set": set_defaults(root, game), "card": None, **(variables or {})}
    ctx = Context(seed)
    report = LoadReport()
    game_pkg = f"{game}.mse-game"
    run_init_script(_init_script(root / game_pkg / "game", root, game_pkg), game_pkg, ctx, report)
    if style:
        style_pkg = f"{style}.mse-style"
        run_init_script(_init_script(root / style_pkg / "style", root, style_pkg), style_pkg, ctx, report)
    return ctx, report
