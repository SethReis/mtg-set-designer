"""List Magic keywords whose MSE reminder text reads wrong on a modern card.

Each keyword is put on a common creature the way cards say it today ("Ward {2}",
"When this creature enters, it explores.", "Scry 2."), its reminder text forced on, and
the text our engine draws is checked for leftovers of MSE's scripts, a self-reference
that says "that creature", and missing text. Fixes go in src/setdesigner/mse/keyword_fixes.py.

    .venv/Scripts/python tools/keyword_survey.py
"""
from __future__ import annotations

import re

from setdesigner.model import Card, Face, Rarity, SetInfo, SetProject
from setdesigner.mse import game_keywords as gk
from setdesigner.mse.environment import ScriptEnvironment
from setdesigner.mse.script.builtins.tags import to_text


# read right: they're done to another creature ("goad target creature", "have it connive")
KNOWN_OK = {"goad", "connive"}


def sample(kw: gk.GameKeyword) -> str:
    """How a modern card uses the keyword."""
    words = kw.literal + (" {2}" if kw.has_param else "")
    if kw.mode == "action":
        verb = words[0].lower() + words[1:]
        third_person = kw.literal.lower().endswith("s")         # "explores", "connives 2"
        return f"When this creature enters, {'it ' if third_person else ''}{verb}."
    return words


def survey() -> list[tuple[str, str, str]]:
    keywords = gk.game_keywords()
    cards = [Card(id=f"k{i}", rarity=Rarity.COMMON, reminders={kw.card_key: True},
                  faces=[Face(name="Sample", mana_cost="{2}{G}", type_line="Creature — Elf",
                              rules_text=sample(kw), power="2", toughness="2")])
             for i, kw in enumerate(keywords)]
    env = ScriptEnvironment(SetProject(info=SetInfo(name="Survey", code="SRV"), cards=cards))
    problems = []
    for kw, card in zip(keywords, cards):
        try:
            text = to_text(env.card_object(card).fields.get("rule text"))
        except Exception as e:                      # noqa: BLE001 - a survey reports, never stops
            problems.append((kw.name, "error", str(e)))
            continue
        reminder = text[text.find("("):] if "(" in text else ""
        if not reminder or kw.key in KNOWN_OK:
            continue                                # not drawn here (e.g. needs another wording)
        if re.search(r"_|\w\(|\{|\}", reminder):
            problems.append((kw.name, "script leftovers", reminder))
        elif "this creature" in card.faces[0].rules_text and re.search(r"\bthat creature\b", reminder):
            problems.append((kw.name, "says 'that creature' about itself", reminder))
    return problems


if __name__ == "__main__":
    found = survey()
    for name, why, text in found:
        print(f"{name}: {why}\n    {text}")
    print(f"{len(found)} of {len(gk.game_keywords())} keywords look wrong")
