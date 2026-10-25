"""Keyword engine details and our mechanics' mapping. Exact agreement with real MSE is
checked by the `keywords` oracle cases (tests/script/test_oracle.py)."""
from pathlib import Path

import pytest

from fixtures.keyword_project import keyword_project
from setdesigner.model import Mechanic, MechanicKind, Rarity, ReminderPolicy
from setdesigner.mse.keywords import (KeywordDatabase, ParamType, TaggedText, make_non_capturing,
                                      remove_keyword_tags)
from setdesigner.mse.mapping import mse_text
from setdesigner.mse.mechanics import mechanic_keyword, reminder_choices, tag_reminders
from setdesigner.mse.script import run

PACKAGES = Path(__file__).resolve().parents[1] / "resources" / "mse_packages"
needs_packages = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")

COST = ParamType("cost", r"[ ][0-9WUBRG]*|[-—][^(\r\n]*", separator_before="[ —-]",
                 separator_after="[.]", optional=False)


def db_with(*keywords: dict) -> KeywordDatabase:
    db = KeywordDatabase([], {"cost": COST})
    for k in keywords:
        db.add(k)
    return db


# ---------------------------------------------------------------- engine

def test_make_non_capturing() -> None:
    assert make_non_capturing(r"(a|b)[(]\(x(?:y)") == r"(?:a|b)[(]\(x(?:y)"


def test_separator_before_a_parameter_is_eaten_from_the_literal() -> None:
    kw = db_with({"keyword": "Cycling", "match": "Cycling <atom-param>cost</atom-param>"}).keywords[0]
    assert kw.literals == ["Cycling", ""] and kw.valid
    m = kw.regex.search("Cycling 2")
    assert m and m.group(0) == "Cycling 2"
    assert not kw.regex.search("Landcyclingx 2")


def test_whole_words_only() -> None:
    kw = db_with({"keyword": "Flying", "match": "Flying"}).keywords[0]
    assert kw.regex.search("gains flying until")
    assert not kw.regex.search("Flyingly") and not kw.regex.search("unflying")


def test_keywords_matching_empty_text_are_invalid() -> None:
    assert not db_with({"keyword": "x", "match": ""}).keywords[0].valid


def test_tagged_slice_keeps_tags_balanced() -> None:
    text = TaggedText("Cycling <sym>2</sym> now")
    assert text.untagged == "Cycling 2 now"
    assert text.tagged_slice(7, 9) == " <sym>2</sym>"


def test_old_output_is_removed_before_expanding() -> None:
    old = "<kw-A><key>Cycling 2</key><atom-reminder-expert> (x)</atom-reminder-expert></kw-A>"
    assert remove_keyword_tags(old) == "<kw-A><key>Cycling 2</key></kw-A>"


# -------------------------------------------------------------- mechanics

def test_mechanic_becomes_set_keyword() -> None:
    m = Mechanic(id="b", name="Bloodpact", parameter="cost",
                 reminder_text="{cost}, Sacrifice a creature: Draw a card.")
    assert mechanic_keyword(m) == {"keyword": "Bloodpact",
                                   "match": "Bloodpact <atom-param>cost</atom-param>",
                                   "reminder": "{param1}, Sacrifice a creature: Draw a card.",
                                   "mode": "custom"}
    action = Mechanic(id="s", name="Scour", kind=MechanicKind.KEYWORD_ACTION)
    assert mechanic_keyword(action)["mode"] == "action"


def test_reminder_policies() -> None:
    choices = reminder_choices(keyword_project())
    assert choices["bloodpact"] == {"Bloodpact": True}             # always
    assert choices["shroudwalk"] == {"Shroudwalk": False}          # never
    assert choices["glimmer-common"]["Glimmer"] is True            # commons only
    assert choices["glimmer-rare"]["Glimmer"] is False
    assert choices["scour-green-1"]["Scour"] is True               # first green card
    assert choices["scour-green-2"]["Scour"] is False              # second green card
    assert choices["scour-blue"]["Scour"] is True                  # first blue card
    assert choices["flying"] == {}


def test_policy_tags_and_mana_symbols() -> None:
    assert tag_reminders("Bloodpact {1}{B}", {"Bloodpact": False}) == "<kw-0>Bloodpact</kw-0> {1}{B}"
    assert mse_text("Cycling {2}{U}. {T}: Add {G}.") == "Cycling <sym>2U</sym>. <sym>T</sym>: Add <sym>G</sym>."


# ----------------------------------------------------------- whole stack

@pytest.fixture(scope="module")
def env():
    from setdesigner.mse.environment import ScriptEnvironment
    return ScriptEnvironment(keyword_project(), PACKAGES)


@needs_packages
def test_expanding_twice_gives_the_same_text(env) -> None:
    ctx = env.context(env.default_style)
    card = env.card_object(env.project.card("cycling"))
    once = card.fields.get("rule text")
    marker = ctx.open_scope()
    try:
        twice = run("text_filter(value, card_styling: styling, card_name: card.name, margin_code: \"text\")",
                    card.bindings(once), ctx=ctx)
    finally:
        ctx.close_scope(marker)
    assert twice == once


@needs_packages
def test_no_field_script_falls_back(env) -> None:
    for card in env.set.cards:
        card.fields.all()
        card.extra_card.fields.all()
        assert card.warnings == [], card.uid


@needs_packages
def test_reminder_text_reads_well(env) -> None:
    from setdesigner.mse.script.builtins.tags import to_text
    text = env.card_object(env.project.card("bloodpact")).fields.get("rule text")
    assert to_text(text) == "Bloodpact 1B (1B, Sacrifice a creature: Draw a card.)"
    rare = env.card_object(env.project.card("glimmer-rare")).fields.get("rule text")
    assert to_text(rare) == "Glimmer"
