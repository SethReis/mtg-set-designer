"""A set exercising keyword expansion: game keywords of every mode, parameters,
non-matches, and our own mechanics with each reminder policy. Loaded into real MSE
for tools/oracle_cases/keywords.txt (one case per card)."""
from setdesigner.model import (Card, Face, Mechanic, MechanicKind, Rarity, ReminderPolicy,
                               SetInfo, SetProject)

# (id, rarity, mana cost, type line, rules text)
CARDS = [
    ("flying", "common", "{1}{W}", "Creature — Bird", "Flying"),
    ("flying-haste", "common", "{1}{R}", "Creature — Dragon", "Flying, haste"),
    ("lowercase", "common", "{U}", "Instant", "Target creature gains flying until end of turn."),
    ("cycling", "common", "{2}{U}", "Creature — Fish", "Cycling {2}"),
    ("kicker", "common", "{R}", "Instant",
     "Kicker {1}{R}\nCARDNAME deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead."),
    ("equip", "uncommon", "{1}", "Artifact — Equipment", "Equipped creature gets +2/+0.\nEquip {3}"),
    ("ward", "rare", "{G}{G}", "Creature — Beast", "Ward—Pay 3 life."),
    ("scry", "common", "{U}", "Sorcery", "Scry 2. Draw a card."),
    ("landfall", "uncommon", "{G}", "Creature — Elf",
     "Landfall — Whenever a land you control enters, CARDNAME gets +1/+1 until end of turn."),
    ("no-match", "common", "{B}", "Sorcery", "Flyingly nonsense, unhasted."),
    ("two-keywords", "common", "{3}{W}", "Creature — Angel", "Flying, vigilance\nWhen CARDNAME enters, scry 1."),
    # our mechanics
    ("bloodpact", "rare", "{B}", "Creature — Vampire", "Bloodpact {1}{B}"),
    ("shroudwalk", "common", "{U}", "Creature — Spirit", "Shroudwalk"),
    ("glimmer-common", "common", "{W}", "Creature — Human", "Glimmer"),
    ("glimmer-rare", "rare", "{W}", "Creature — Human", "Glimmer"),
    ("scour-green-1", "common", "{G}", "Sorcery", "Scour 2."),
    ("scour-green-2", "common", "{G}", "Sorcery", "Scour 3."),
    ("scour-blue", "common", "{U}", "Sorcery", "Scour 1."),
]

MECHANICS = [
    Mechanic(id="bloodpact", name="Bloodpact", parameter="cost",
             reminder_text="{cost}, Sacrifice a creature: Draw a card.",
             reminder_policy=ReminderPolicy.ALWAYS),
    Mechanic(id="shroudwalk", name="Shroudwalk",
             reminder_text="This creature can't be blocked by creatures with power 2 or greater.",
             reminder_policy=ReminderPolicy.NEVER),
    Mechanic(id="glimmer", name="Glimmer", reminder_text="This creature has hexproof while untapped.",
             reminder_policy=ReminderPolicy.COMMONS_ONLY),
    Mechanic(id="scour", name="Scour", kind=MechanicKind.KEYWORD_ACTION, parameter="number",
             reminder_text="Mill {number} cards, then you may return a land card milled this way to your hand.",
             reminder_policy=ReminderPolicy.FIRST_PER_COLOR),
]


def keyword_project() -> SetProject:
    cards = [Card(id=cid, rarity=Rarity(rarity), collector_number=str(n + 1),
                  faces=[Face(name=cid.replace("-", " ").title(), mana_cost=cost,
                              type_line=type_line, rules_text=text,
                              power="2" if "Creature" in type_line else None,
                              toughness="2" if "Creature" in type_line else None)])
             for n, (cid, rarity, cost, type_line, text) in enumerate(CARDS)]
    return SetProject(info=SetInfo(name="Keyword Test Set", code="KWT"),
                      mechanics=MECHANICS, cards=cards)
