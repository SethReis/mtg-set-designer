"""Live preview budget: re-rendering a card after an edit must feel instant.
Target 300 ms on a normal desktop; the test allows some slack for slow CI machines
(tools/render_cards.py prints real timings)."""
import time
from pathlib import Path

import pytest

from fixtures.keyword_project import keyword_project

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
BUDGET_SECONDS = 0.6


@pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")
def test_edit_then_render_is_fast() -> None:
    from setdesigner.mse.environment import ScriptEnvironment
    from setdesigner.render import render_card
    project = keyword_project()
    env = ScriptEnvironment(project, PACKAGES)
    card = project.card("kicker")
    render_card(env, card)                                  # warm up: scripts loaded once
    timings = []
    for text in ("Kicker {2}{R}\nCARDNAME deals 3 damage to any target.", "Flying, haste"):
        card.faces[0].rules_text = text
        start = time.perf_counter()
        env.refresh_card(card)
        image = render_card(env, card)
        timings.append(time.perf_counter() - start)
    assert image.size == (375, 523)
    assert min(timings) <= BUDGET_SECONDS, timings
