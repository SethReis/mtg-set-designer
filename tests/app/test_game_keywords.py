"""Magic's own keywords: found on cards without being added, reminder text like real sets
(core never, the rest on commons), the set's policy and each card's choice."""
from pathlib import Path

import pytest

from setdesigner.app.session import SetSession
from setdesigner.mse import game_keywords as gk
from setdesigner.mse.mechanics import reminder_choices as all_choices


def reminder_choices(project):
    return all_choices(project, all_keywords=True)

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


def made(s, name, text, rarity="common"):
    card = s.new_card(name)
    s.update(card, "rules_text", text)
    s.update(card, "rarity", rarity)
    return card


def test_keywords_are_found_and_read_well() -> None:
    names = {k.name for k in gk.game_keywords()}
    assert {"Flying", "Cycling", "Ward", "Kicker"} <= names
    assert gk.find("flying").preview() == "This creature can't be blocked except by creatures with flying or reach."
    assert gk.find("Cycling").preview() == "N, Discard this card: Draw a card."


def test_like_real_sets_and_overrides(tmp_path) -> None:
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    bird = made(s, "Gull", "Flying")
    fish = made(s, "Carp", "Cycling {2}")
    rare = made(s, "Hydra", "Ward {2}", "rare")
    assert [k.name for k in gk.used(fish, s.project)] == ["Cycling"]
    choices = reminder_choices(s.project)
    assert choices[bird.id] == {"Flying": False}           # core: never
    assert choices[fish.id] == {"Cycling": True}           # the rest: on commons
    assert choices[rare.id] == {"Ward": False}
    s.set_keyword_reminder(bird, "Flying", True)           # a card's own choice
    s.set_keyword_policy("Ward", "always")                 # the set's policy
    choices = reminder_choices(s.project)
    assert choices[bird.id]["Flying"] and choices[rare.id]["Ward"]
    s.set_keyword_policy("Ward", None)
    assert reminder_choices(s.project)[rare.id]["Ward"] is False
    assert all_choices(s.project)[fish.id] == {}           # as MSE does anyway: left to it
    assert all_choices(s.project)[rare.id] == {"Ward": False}


def test_a_set_mechanic_replaces_the_keyword(tmp_path) -> None:
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    fish = made(s, "Carp", "Cycling {2}")
    mechanic = s.new_mechanic("Cycling")
    s.update_mechanic(mechanic, reminder_text="Pay {param}, discard this: draw.")
    assert gk.used(fish, s.project) == []


def test_explore_reads_this_creature_and_the_set_can_replace_it(tmp_path) -> None:
    from setdesigner.mse.environment import ScriptEnvironment
    from setdesigner.mse.script.builtins.tags import to_text
    from setdesigner.model import load_project
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    scout = made(s, "Scout", "When this creature enters, it explores.")
    other = made(s, "Guide", "When this creature enters, target creature you control explores.")

    def drawn(card) -> str:
        return to_text(ScriptEnvironment(s.project).card_object(card).fields.get("rule text"))
    assert "+1/+1 counter on this creature," in drawn(scout)
    assert "+1/+1 counter on that creature," in drawn(other)
    assert drawn(scout).count("(") == 1                    # MSE's own reminder is switched off
    s.set_keyword_text("Explore", "Look at the top card; keep it or not.")
    assert drawn(scout).endswith("it explores. (Look at the top card; keep it or not.)")
    assert gk.reminder_text(s.project.info, gk.find("explore")) == "Look at the top card; keep it or not."
    assert load_project(s.folder).info.keyword_text == {"explore": "Look at the top card; keep it or not."}
    s.set_keyword_text("Explore", None)
    assert "on this creature," in drawn(scout)


def test_replaced_text_fills_in_the_value(tmp_path) -> None:
    from setdesigner.mse.environment import ScriptEnvironment
    from setdesigner.mse.script.builtins.tags import to_text
    s = SetSession.create(tmp_path / "s", "Test", "TST")
    fish = made(s, "Carp", "Cycling {2}")
    s.set_keyword_text("Cycling", "{N}, Discard this card: Draw a card. Then scry 1.")
    text = to_text(ScriptEnvironment(s.project).card_object(fish).fields.get("rule text"))
    assert text == "Cycling 2 (2, Discard this card: Draw a card. Then scry 1.)"
