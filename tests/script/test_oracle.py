"""Compare our evaluator with real MSE on the recorded cases in tests/script/oracle/*.json.

The JSON files are produced by `python tools/mse_oracle.py` from tools/oracle_cases/*.txt.
Plain cases run in a fresh context with the built-in functions (as MSE's CLI does).
Cases with a "project" ran in MSE with that fixture project loaded as a set; here
they run in a ScriptEnvironment built from the same fixture.
"""
import importlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

from setdesigner.mse.script import Context, ScriptError, ScriptSyntaxError, run, to_code
from setdesigner.mse.script.builtins import builtin_variables

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"

def _load(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if any("image" in case for case in cases):
        return []                   # image-mode files: compared in test_image_oracle.py
    return [{**case, "file": path.stem} for case in cases]


CASES = [case for path in sorted((Path(__file__).parent / "oracle").glob("*.json"))
         for case in _load(path)]

# Cases where we knowingly differ from MSE, with the reason.
DEVIATIONS = {
    # Maps are Python dicts, so concatenating maps can't keep duplicate keys.
    "[a: 1] + [a: 2]",
    # MSE wraps field values in "value" objects; ours are plain strings.
    "type_name(set.curly_quotes)",
    "type_name(set.cards.0.image)",
    "type_name(set.border_color)",
    # Symbol values (set.symbol, an .mse-symbol file) come with the renderer.
    "set.symbol",
    # MSE spellchecks with a hunspell dictionary and marks unknown words; we don't.
    "keywords: set.cards.9.rule_text",          # "Flyingly nonsense, unhasted."
    "keywords: set.cards.9.text",
}


@lru_cache(maxsize=None)
def environment(project: str):
    from setdesigner.mse.environment import ScriptEnvironment
    fixture = getattr(importlib.import_module(f"fixtures.{project}"), project)
    return ScriptEnvironment(fixture(), PACKAGES)


def evaluate(case) -> str:
    if "project" not in case:
        return to_code(run(case["expr"], ctx=Context(builtin_variables())))
    env = environment(case["project"])
    ctx = env.context(env.default_style)
    marker = ctx.open_scope()                   # keep loop variables etc. out of later cases
    try:
        return to_code(run(case["expr"], ctx=ctx))
    finally:
        ctx.close_scope(marker)


def is_message_then_value(case) -> bool:
    """assert() failures and trace() print a message, then the value. (The CLI shows
    trace messages with error status, but evaluation succeeds.)"""
    return case["status"] == "warning" or case["output"].startswith("ERROR: Trace:")


@pytest.mark.parametrize("case", CASES, ids=[f"{c['file']}: {c['expr']}" for c in CASES])
def test_matches_mse(case) -> None:
    if case["expr"] in DEVIATIONS or f"{case['file']}: {case['expr']}" in DEVIATIONS:
        pytest.skip("known deviation")
    if "project" in case and not PACKAGES.is_dir():
        pytest.skip("resources/mse_packages not populated")
    if is_message_then_value(case):
        assert evaluate(case) == case["output"].splitlines()[-1]
    elif case["status"] == "error":
        with pytest.raises((ScriptError, ScriptSyntaxError)):
            evaluate(case)
    else:
        assert evaluate(case) == case["output"]
