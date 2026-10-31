"""Mechanics: word forms, finding uses, usage counts, renaming, per-card reminders."""
import json

import pytest

from setdesigner.app.mechanics import (find_uses, reminder_preview, rename_plan, suggest_forms,
                                       usage)
from setdesigner.app.session import SetSession
from setdesigner.model import (Card, Face, Mechanic, MechanicKind, Rarity, ReminderPolicy,
                               SetInfo, SetProject)
from setdesigner.mse.mechanics import mechanic_keywords, reminder_choices, tag_reminders


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


def card(cid, text, cost="", rarity=Rarity.COMMON, number="1"):
    return Card(id=cid, rarity=rarity, collector_number=number,
                faces=[Face(name=cid.title(), mana_cost=cost, rules_text=text)])


WANT = Mechanic(id="want", name="Want", kind=MechanicKind.KEYWORD_ACTION,
                forms=["Wanted", "Wants"], reminder_text="Put a bounty counter on it.")


def project(*cards, mechanics=(WANT,)):
    return SetProject(info=SetInfo(name="P", code="P"), mechanics=list(mechanics), cards=list(cards))


def test_suggest_forms() -> None:
    assert suggest_forms("Want") == ["Wants", "Wanted", "Wanting"]
    assert suggest_forms("Explore") == ["Explores", "Explored", "Exploring"]
    assert suggest_forms("Ally") == ["Allies", "Allied", "Allying"]
    assert suggest_forms("Plot") == ["Plots", "Plotted", "Plotting"]
    assert suggest_forms("Amass") == ["Amasses", "Amassed", "Amassing"]
    assert suggest_forms("First strike") == []


def test_find_uses_with_forms_whole_words_only() -> None:
    p = project(card("hunter", "Want target creature. Draw a card.", "{1}{B}", number="2"),
                card("sheriff", "Tap a wanted creature.", "{W}", Rarity.UNCOMMON, "1"),
                card("rake", "Wantonly destroy everything."))
    uses = find_uses(p, WANT)
    assert [u.card.id for u in uses] == ["sheriff", "hunter"]                 # collector order
    assert uses[1].sentences == ["Want target creature."]
    stats = usage(p, WANT)
    assert (stats.cards, stats.by_color, stats.by_rarity) == (2, {"W": 1, "B": 1},
                                                              {"common": 1, "uncommon": 1})


def test_rename_plan_follows_forms_and_case() -> None:
    p = project(card("a", "Want target creature.\nWanted creatures can't block."),
                card("b", "Nothing to see. I want pie."))
    plan = rename_plan(p, WANT, "Hunt")
    assert [(c.card.id, c.after) for c in plan] == [
        ("a", "Hunt target creature.\nHunted creatures can't block."), ("b", "Nothing to see. I hunt pie.")]


def test_reminder_preview() -> None:
    cycling = Mechanic(id="cycling", name="Cycling", parameter="cost",
                       reminder_text="{cost}, Discard this card: Draw a card.")
    assert reminder_preview(cycling) == "Cycling {2} ({2}, Discard this card: Draw a card.)"
    assert reminder_preview(WANT) == "Want (Put a bounty counter on it.)"


def test_reminders_only_on_the_name_and_overrides_win() -> None:
    common = card("a", "Want target creature. Wanted creatures die.")
    rare = card("b", "Want target creature.", rarity=Rarity.RARE, number="2")
    p = project(common, rare)
    assert reminder_choices(p) == {"a": {"Want": True}, "b": {"Want": False}}     # commons only
    text = common.faces[0].rules_text
    assert tag_reminders(text, {"Want": True}) ==         "<kw-1>Want</kw-1> target creature. Wanted creatures die."     # without forms: name only
    # with its forms: the first mention gets the choice, later ones are hidden
    assert tag_reminders(text, {"Want": True}, {"Want": ["Wanted"]}) ==         "<kw-1>Want</kw-1> target creature. <kw-0>Wanted</kw-0> creatures die."
    assert tag_reminders("Tap a wanted creature.", {"Want": True}, {"Want": ["Wanted"]}) ==         "Tap a <kw-1>wanted</kw-1> creature."                           # a form alone gets it
    common.reminders["want"] = False
    rare.reminders["want"] = True
    assert reminder_choices(p) == {"a": {"Want": False}, "b": {"Want": True}}


# ------------------------------------------------------------------ in a session

@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", renderer_factory=builtin,
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def saved_mechanics(session):
    return json.loads((session.folder / "mechanics.json").read_text(encoding="utf-8"))


def test_session_mechanics_create_update_rename_delete(session) -> None:
    hunter = session.new_card("Hunter")
    session.update(hunter, "rules_text", "Want target creature.")
    assert hunter.mechanics == []                                  # no such mechanic yet
    want = session.new_mechanic("Want")
    assert hunter.mechanics == ["want"]                            # found on existing cards
    session.update_mechanic(want, kind="keyword_action", forms=["Wanted", " "],
                            reminder_policy="always", parameter="")
    assert want.kind == MechanicKind.KEYWORD_ACTION and want.forms == ["Wanted"]
    assert want.reminder_policy == ReminderPolicy.ALWAYS and want.parameter is None
    assert saved_mechanics(session)[0]["forms"] == ["Wanted"]

    sheriff = session.new_card("Sheriff")
    session.update(sheriff, "rules_text", "Tap a wanted creature.")
    assert sheriff.mechanics == ["want"]
    session.set_reminder(sheriff, want, False)
    assert sheriff.reminders == {"want": False}

    kept = session.rename_mechanic(want, "Hunt", update_cards=False)
    assert kept == [] and hunter.faces[0].rules_text == "Want target creature."
    assert want.name == "Hunt" and want.forms == ["Hunted"]
    session.rename_mechanic(want, "Chase", update_cards=True)      # Hunt -> Chase in the cards?
    assert hunter.faces[0].rules_text == "Want target creature."   # (they still say Want)

    session.update(hunter, "rules_text", "Chase target creature.")
    session.update(sheriff, "rules_text", "Tap a chased creature.")
    done = session.rename_mechanic(want, "Hunt", update_cards=True)
    assert len(done) == 2
    assert (hunter.faces[0].rules_text, sheriff.faces[0].rules_text) == (
        "Hunt target creature.", "Tap a hunted creature.")

    session.delete_mechanic(want)
    assert session.project.mechanics == [] and sheriff.reminders == {}
    assert hunter.mechanics == [] and hunter.faces[0].rules_text == "Hunt target creature."
    assert saved_mechanics(session) == []


def test_word_forms_become_keywords_too() -> None:
    keywords = mechanic_keywords(WANT)
    assert [k["keyword"] for k in keywords] == ["Want", "Wanted", "Wants"]
    assert {k["reminder"] for k in keywords} == {WANT.reminder_text}
    cycling = Mechanic(id="c", name="Cycling", parameter="cost", forms=["Cycled"])
    assert [k["keyword"] for k in mechanic_keywords(cycling)] == ["Cycling"]   # forms need no value
