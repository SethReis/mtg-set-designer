"""Load magic.mse-game's init script (plus each target style's) and call real functions."""
from pathlib import Path

import pytest

from setdesigner.mse.script import ScriptError, ScriptFunction, run
from setdesigner.mse.script.corpus import STYLES
from setdesigner.mse.script.game import load_game, set_defaults

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")

# Definitions that call a not-yet-implemented built-in while loading: {name: built-in}.
NEEDS_BUILTIN: dict[str, str] = {}


@pytest.fixture(scope="module")
def m15():
    return load_game(PACKAGES, "magic-m15-altered")


@pytest.mark.parametrize("style", [None] + STYLES)
def test_init_scripts_load(style) -> None:
    _, report = load_game(PACKAGES, style)
    assert report.loaded > 1700
    unexpected = [f for f in report.failures
                  if not any(f"({name}): built-in '{fn}'" in f for name, fn in NEEDS_BUILTIN.items())]
    assert unexpected == []


def test_set_defaults() -> None:
    defaults = set_defaults(PACKAGES)
    assert defaults["card language"] == "English"       # first choice
    assert defaults["custom super types"] == ""


def test_call_game_functions(m15) -> None:
    ctx, _ = m15
    assert run('token_shape("emblem")', ctx=ctx) is True
    assert run('token_shape("normal")', ctx=ctx) is False
    assert run('is_blank("")', ctx=ctx) is True
    game_only, _ = load_game(PACKAGES)
    assert run("card_shape()", ctx=game_only) == "normal"
    # M15 overrides card_shape to check is_leveler(), which reads the style's settings.
    with pytest.raises(ScriptError, match="styling"):
        run("card_shape()", ctx=ctx)


def test_style_overrides_game_definitions(m15) -> None:
    ctx, _ = m15
    # M15 Main: `default_notched := is_notched` keeps the game's version, then redefines is_notched.
    assert isinstance(ctx.get("default_notched"), ScriptFunction)
    assert ctx.get("default_notched") is not ctx.get("is_notched")
    # mana_t is defined by the M15 style and reads `styling` dynamically.
    assert run("mana_t()", {"styling": {"tap symbol": "diagonal T"}}, ctx=ctx) == "older"
