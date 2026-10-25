"""Acceptance test: magic.mse-game ships its own `unit_tests` script (asserts about
`cmc`, `card_color_color_count`, ...). Run every assert with the game loaded."""
from pathlib import Path

import pytest

from setdesigner.mse.script import ast as A
from setdesigner.mse.script import Evaluator, parse
from setdesigner.mse.script.game import load_game

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
UNIT_TESTS = PACKAGES / "magic.mse-game" / "unit_tests"
pytestmark = pytest.mark.skipif(not UNIT_TESTS.is_file(), reason="resources/mse_packages not populated")


def statements() -> list[tuple[str, A.Node]]:
    if not UNIT_TESTS.is_file():
        return []
    text = UNIT_TESTS.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    tree = parse(text)
    items = tree.items if isinstance(tree, A.Seq) else (tree,)
    return [(lines[s.line - 1].strip(), s) for s in items]


@pytest.fixture(scope="module")
def game_ctx():
    ctx, report = load_game(PACKAGES)
    assert report.failures == []
    return ctx


@pytest.mark.parametrize("source, statement", statements(), ids=[s for s, _ in statements()])
def test_game_unit_test(game_ctx, source, statement) -> None:
    game_ctx.warnings.clear()
    Evaluator().eval(statement, game_ctx)
    assert game_ctx.warnings == [], source
