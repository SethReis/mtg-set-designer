"""How strong a card is for its cost, worked out from its rules text: no AI, just patterns.

    s = score(card, project)          # None for lands
    s.effective, s.actual, s.delta    # what it's worth in mana, what it costs, the gap
    s.parts                           # [("3/3 body", 3.0), ("Flying", 1.0), ...]
    s.unscored                        # lines the scorer didn't understand
    s.verdict                         # "above", "on" or "below" (curve, for its rarity)

A creature is worth its body plus its keywords plus its effects; a noncreature spell a
small base plus its effects. Effects reached through an activated ability or a condition
count only a share. Values come from norms.norms(project); a card's balance_adjust is
added on top. Lines it doesn't understand are listed, so a score is never silently partial.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from ...model import Card, Rarity, SetProject
from ..health.roles import plain_text
from ..overview import card_type, mana_value
from .norms import norms as get_norms

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "x": 2}
N = r"(a|an|one|two|three|four|five|six|x|\d+)"


def _n(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS.get(word, 1)


@dataclass
class Score:
    card_id: str
    actual: int
    effective: float
    parts: list[tuple[str, float]] = field(default_factory=list)
    unscored: list[str] = field(default_factory=list)
    tolerance: float = 1.0
    strict_below: bool = True             # rares and mythics aren't flagged for being weak

    @property
    def delta(self) -> float:
        return round(self.effective - self.actual, 2)

    @property
    def verdict(self) -> str:
        if self.delta > self.tolerance:
            return "above"
        if self.strict_below and self.delta < -self.tolerance:
            return "below"
        return "on"


# ---------------------------------------------------------------------- effects
# (pattern, function(match, norms) -> (label, mana))
def _damage(m, v):
    n, target = _n(m.group(1)), m.group(2)
    if target.startswith("each"):
        return f"{n} damage to {target}", n * v["effect.sweep"]
    extra = v["effect.damage_any"] if "any target" in target or "player" in target else 0
    return f"{n} damage", n * v["effect.damage"] + extra


EFFECTS: list[tuple[re.Pattern, callable]] = [(re.compile(p, re.IGNORECASE), f) for p, f in [
    (r"deals? " + N + r" damage to (any target|each (?:other )?creature[\w ]*|target [\w ,]+|each opponent)", _damage),
    (r"\bdestroy (?:up to one )?target (?:\w+ )?(creature|nonland permanent)",
     lambda m, v: ("Destroy a creature", v["effect.destroy_creature"])),
    (r"\bdestroy (?:up to one )?target (artifact|enchantment|land|planeswalker)",
     lambda m, v: (f"Destroy an {m.group(1)}", v["effect.destroy_other"])),
    (r"\bexile (?:up to one )?target (?:\w+ )?(creature|nonland permanent)",
     lambda m, v: ("Exile a creature", v["effect.exile_creature"])),
    (r"\bexile (?:up to one )?target (artifact|enchantment|card)",
     lambda m, v: (f"Exile {m.group(1)}", v["effect.destroy_other"])),
    (r"\b(?:all|each) (?:other )?creatures? gets? -(\d+|x)/-\d+",
     lambda m, v: (f"-{m.group(1)}/-{m.group(1)} to each creature", _n(m.group(1)) * v["effect.sweep"])),
    (r"\btarget creature(?: an opponent controls)? gets -(\d+|x)/-\d+",
     lambda m, v: (f"-{m.group(1)}/-{m.group(1)}", _n(m.group(1)) * v["effect.shrink"])),
    (r"\bfights?\b|deals? damage equal to (?:its|this creature's) power to",
     lambda m, v: ("Fight", v["effect.fight"])),
    (r"\breturn (?:up to one )?target [\w ]*?(?:creature|permanent)[\w ]* to (?:its|their) owner",
     lambda m, v: ("Bounce", v["effect.bounce"])),
    (r"\bcounter target [\w ]*?spell", lambda m, v: ("Counter a spell", v["effect.counter"])),
    (r"\bdraws? " + N + r" cards?", lambda m, v: (f"Draw {_n(m.group(1))}", _n(m.group(1)) * v["effect.draw"])),
    (r"\bgain " + N + r" life", lambda m, v: (f"Gain {_n(m.group(1))} life", _n(m.group(1)) * v["effect.life"])),
    (r"\bcreates? " + N + r" (\d+)/(\d+)[\w ]*tokens?",
     lambda m, v: (f"{_n(m.group(1))}× {m.group(2)}/{m.group(3)} token",
                   _n(m.group(1)) * (int(m.group(2)) + int(m.group(3))) * v["effect.token"])),
    (r"\bput " + N + r" \+1/\+1 counters?",
     lambda m, v: (f"{_n(m.group(1))} +1/+1 counter", _n(m.group(1)) * v["effect.counters"])),
    (r"\btarget creature gets \+(\d+|x)/\+(\d+)",
     lambda m, v: (f"+{m.group(1)}/+{m.group(2)}", max(_n(m.group(1)), int(m.group(2))) * v["effect.pump"])),
    (r"\bsurveil (\d+)", lambda m, v: (f"Surveil {m.group(1)}", int(m.group(1)) * v["effect.surveil"])),
    (r"\bscry (\d+)", lambda m, v: (f"Scry {m.group(1)}", int(m.group(1)) * v["effect.scry"])),
    (r"\}: add \{", lambda m, v: ("Mana ability", v["effect.mana"])),
]]

KEYWORD_LINE = re.compile(r"[a-z][a-z ]*(?: \{[^}]+\})?(?:, [a-z][a-z ]*(?: \{[^}]+\})?)*")
ACTIVATED = re.compile(r"^[^\"]*?\}[^\"]*?:\s|^[^:\"]{0,40}, \{t\}:|^\{t\}:")
CONDITIONAL = re.compile(r"^(?:whenever|when|at the)\b(?!.*\benters\b)|\bif\b")


def _power(card: Card) -> int | None:
    p = card.faces[0].power
    return int(p) if p and p.strip().isdigit() else None


def _keyword(word: str, card: Card, v: dict[str, float]) -> tuple[str, float] | None:
    key = f"keyword.{word.split(' {')[0]}"
    if key not in v:
        return None
    value = v[key]
    power = _power(card) or 0
    if key == "keyword.flying":
        value *= min(1.0, 0.5 + 0.25 * max(power - 1, 0))
    elif key == "keyword.double strike":
        value *= min(power, 3) / 2
    return word.split(" {")[0].capitalize(), value


def _mechanic(line: str, card: Card, project: SetProject | None, v) -> tuple[str, float] | None:
    for mechanic in project.mechanics if project is not None else []:
        names = [mechanic.name.lower(), *(f.lower() for f in mechanic.forms)]
        if mechanic.id in card.mechanics and any(line.startswith(n) for n in names):
            return mechanic.name, mechanic.value
    return None


def _effects(line: str, v: dict[str, float]) -> list[tuple[str, float]]:
    found = []
    for pattern, value_of in EFFECTS:
        for m in pattern.finditer(line):
            found.append(value_of(m, v))
    if not found:
        return []
    share = 1.0
    if all(label == "Mana ability" for label, _ in found):
        pass                                              # its value already assumes the {T}
    elif ACTIVATED.search(line):
        share *= v["factor.activated"]
    elif CONDITIONAL.search(line):
        share *= v["factor.conditional"]
    return [(label + ("" if share == 1 else f" (×{share:g})"), value * share) for label, value in found]


def score(card: Card, project: SetProject | None = None, values: dict[str, float] | None = None) -> Score | None:
    """The card's score, or None for lands."""
    if card_type(card) == "Land":
        return None
    v = values or get_norms(project)
    face = card.faces[0]
    actual = mana_value(face.mana_cost)
    parts: list[tuple[str, float]] = []
    unscored: list[str] = []
    if card_type(card) == "Creature":
        p, t = face.power, face.toughness
        if p and t and p.strip().isdigit() and t.strip().isdigit():
            p, t = int(p), int(t)
            body = (p + t) * v["body.per_stat"] - v["body.lopsided"] * max(0, abs(p - t) - 2)
            parts.append((f"{p}/{t} body", body))
            if actual > 4:
                parts.append(("Big body discount", v["body.big_discount"] * (actual - 4)))
        else:
            unscored.append(f"{p or '?'}/{t or '?'} body")
    else:
        parts.append(("Spell", v["card.spell"]))
    for raw in plain_text(card).split("\n"):
        line = raw.strip().lower()
        if not line:
            continue
        line = re.sub(r"^[\w' ]+ — ", "", line)                    # ability words: the rest counts
        mechanic = _mechanic(line, card, project, v)
        if mechanic:
            parts.append(mechanic)
            continue
        if KEYWORD_LINE.fullmatch(line):
            words = [_keyword(w.strip(), card, v) for w in line.split(", ")]
            if all(words):
                parts.extend(words)
                continue
        effects = _effects(line, v)
        if effects:
            parts.extend(effects)
        else:
            unscored.append(raw.strip())
    if card.balance_adjust:
        parts.append(("Adjustment" + (f": {card.balance_note}" if card.balance_note else ""), card.balance_adjust))
    effective = round(sum(x for _, x in parts), 2)
    rare = card.rarity in (Rarity.RARE, Rarity.MYTHIC, Rarity.SPECIAL)
    tolerance = v["tolerance.rare"] if rare else v[f"tolerance.{card.rarity.value}"]
    return Score(card.id, actual, effective, [(l, round(x, 2)) for l, x in parts], unscored, tolerance, not rare)


def scores(project: SetProject) -> dict[str, Score]:
    """Every scored card in the set, by card id."""
    v = get_norms(project)
    return {s.card_id: s for s in (score(c, project, v) for c in project.cards) if s is not None}


def set_offset(all_scores: dict[str, Score]) -> float:
    """The set's typical delta: a card's "vs. your set" is its delta less this."""
    return median(s.delta for s in all_scores.values()) if all_scores else 0.0


def similar(card: Card, project: SetProject, all_scores: dict[str, Score], n: int = 5) -> list[Card]:
    """The set's cards closest to this one: same type and mana value first, then by worth."""
    me = all_scores.get(card.id)
    if me is None:
        return []
    kind = card_type(card)
    others = [c for c in project.cards if c.id != card.id and c.id in all_scores]
    others.sort(key=lambda c: (card_type(c) != kind, abs(all_scores[c.id].actual - me.actual),
                               abs(all_scores[c.id].effective - me.effective)))
    return others[:n]
