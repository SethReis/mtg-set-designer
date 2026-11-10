"""The values Balance scores cards with, in mana: what a body, a keyword or an effect is
worth, and how far off its cost a card may be at each rarity.

    values = norms(project)          # the defaults, with the set's overrides on top
    values["keyword.flying"]

The defaults follow well-known design rules of thumb (a common 2-mana 2/2, a 3-mana 2/2
flyer, "deal 3 damage" for 2, "destroy target creature" for about 3-4). A set overrides any
of them in SetInfo.balance (the Balance view's Norms tab).
"""
from __future__ import annotations

from ...model import SetProject

# key -> (group, label, default)
NORMS: dict[str, tuple[str, str, float]] = {k: v for k, v in [
    # bodies: (power + toughness) x per_stat, less a bit for lopsided ones
    ("body.per_stat", ("Body", "Mana per point of power or toughness", 0.5)),
    ("body.lopsided", ("Body", "Less per point of power/toughness gap beyond 2", 0.25)),
    ("body.big_discount", ("Body", "Less per point of mana value beyond 4 (big bodies come cheaper)", 0.25)),
    ("card.spell", ("Body", "A noncreature spell's worth before its effects", 0.5)),
    # keywords
    ("keyword.flying", ("Keywords", "Flying (scaled by power: half at power 1)", 1.0)),
    ("keyword.reach", ("Keywords", "Reach", 0.25)),
    ("keyword.deathtouch", ("Keywords", "Deathtouch", 0.5)),
    ("keyword.first strike", ("Keywords", "First strike", 0.5)),
    ("keyword.double strike", ("Keywords", "Double strike (scaled by power)", 1.5)),
    ("keyword.haste", ("Keywords", "Haste", 0.5)),
    ("keyword.hexproof", ("Keywords", "Hexproof", 0.75)),
    ("keyword.indestructible", ("Keywords", "Indestructible", 1.5)),
    ("keyword.lifelink", ("Keywords", "Lifelink", 0.5)),
    ("keyword.menace", ("Keywords", "Menace", 0.5)),
    ("keyword.trample", ("Keywords", "Trample", 0.25)),
    ("keyword.vigilance", ("Keywords", "Vigilance", 0.25)),
    ("keyword.flash", ("Keywords", "Flash", 0.25)),
    ("keyword.defender", ("Keywords", "Defender", -1.0)),
    ("keyword.ward", ("Keywords", "Ward", 0.5)),
    # effects
    ("effect.damage", ("Effects", "Damage to a creature, per point", 0.5)),
    ("effect.damage_any", ("Effects", "Extra for any target (players too)", 0.5)),
    ("effect.sweep", ("Effects", "Damage or -N/-N to each creature, per point", 0.75)),
    ("effect.destroy_creature", ("Effects", "Destroy target creature", 3.0)),
    ("effect.exile_creature", ("Effects", "Exile target creature", 3.5)),
    ("effect.destroy_other", ("Effects", "Destroy target artifact, enchantment or other permanent", 1.5)),
    ("effect.shrink", ("Effects", "Target creature gets -N/-N, per point", 0.6)),
    ("effect.fight", ("Effects", "Fight or bite", 1.5)),
    ("effect.bounce", ("Effects", "Return target creature or permanent to hand", 1.25)),
    ("effect.counter", ("Effects", "Counter target spell", 2.5)),
    ("effect.draw", ("Effects", "Draw a card, per card", 1.0)),
    ("effect.life", ("Effects", "Gain life, per point", 0.15)),
    ("effect.token", ("Effects", "A token, per point of power or toughness", 0.45)),
    ("effect.counters", ("Effects", "+1/+1 counters, per counter", 0.5)),
    ("effect.pump", ("Effects", "Target creature gets +N/+N, per point", 0.3)),
    ("effect.surveil", ("Effects", "Surveil, per card", 0.25)),
    ("effect.scry", ("Effects", "Scry, per card", 0.2)),
    ("effect.mana", ("Effects", "A mana ability ({T}: Add)", 1.0)),
    # how an effect is reached
    ("factor.activated", ("Conditions", "Activated abilities (cost: effect) count this share", 0.6)),
    ("factor.conditional", ("Conditions", "Effects behind \"if\" or \"when\" (not entering) count this share", 0.75)),
    ("factor.mechanic", ("Conditions", "A custom mechanic without its own value", 0.5)),
    # how far off cost a card may be before it's flagged
    ("tolerance.common", ("Tolerance", "Common: flagged beyond ± this many mana", 1.0)),
    ("tolerance.uncommon", ("Tolerance", "Uncommon: flagged beyond ± this many mana", 1.5)),
    ("tolerance.rare", ("Tolerance", "Rare and mythic: flagged only above + this many mana", 2.0)),
]}

GROUPS = ["Body", "Keywords", "Effects", "Conditions", "Tolerance"]


def defaults() -> dict[str, float]:
    return {k: v[2] for k, v in NORMS.items()}


def norms(project: SetProject | None = None) -> dict[str, float]:
    """The defaults with the set's overrides (unknown keys ignored)."""
    values = defaults()
    if project is not None:
        values.update({k: v for k, v in project.info.balance.items() if k in values})
    return values
