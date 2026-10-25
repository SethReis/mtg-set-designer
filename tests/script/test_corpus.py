"""Parse every real script snippet from magic.mse-game and the target styles."""
from pathlib import Path

import pytest

from setdesigner.mse.script import ScriptSyntaxError
from setdesigner.mse.script import ast as A
from setdesigner.mse.script.corpus import parse_snippet, target_snippets

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


@pytest.fixture(scope="module")
def snippets():
    return target_snippets(PACKAGES)


def test_every_snippet_parses(snippets) -> None:
    failures = []
    for snip in snippets:
        try:
            parse_snippet(snip)
        except ScriptSyntaxError as e:
            failures.append(f"{snip.source} :: {snip.path} :: {e}")
    assert len(snippets) > 2000
    assert failures == [], "\n".join(failures[:20])


def test_init_scripts_are_all_definitions(snippets) -> None:
    """A structural check: each init script is a sequence of `name := ...`
    statements, so no statement was merged with or split from another."""
    for snip in snippets:
        if snip.path != "init script":
            continue
        tree = parse_snippet(snip)
        items = tree.items if isinstance(tree, A.Seq) else (tree,)
        assert all(isinstance(i, A.Assign) for i in items), snip.source
