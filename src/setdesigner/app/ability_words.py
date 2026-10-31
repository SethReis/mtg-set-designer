"""Ability words with a shared throughline (Flurry, Renew, Settled): matching card lines to
the mechanic's template variants, writing lines, and keeping cards in step when the
definition changes. No UI.

A template is the text after "Name — ":
    {effect}, {cost}, {trigger}, ...   slots, filled per card (lowercase names; uppercase
                                       {G}, {T}, {2} are mana and other symbols as usual)
    {=condition}                       one of the mechanic's shared phrases

    Settled, phrases {"condition": "you control four or more lands that share a land type"}
      Activated: "{cost}: {effect}. Activate only if {=condition}."
      -> "Settled — {3}{G}, {T}: Put three +1/+1 counters on this creature. Activate only
          if you control four or more lands that share a land type."

Cards keep their full text; lines are recognized by the variants (first that fits wins).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import AbilityTemplate, Card, Mechanic, SetProject
from .mechanics import Change
from .overview import number_key

SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")              # {effect}; not {G} / {2} symbols
PHRASE = re.compile(r"\{=([A-Za-z][\w ]*)\}")              # {=condition}
DASH = r"\s*(?:—|–|--|-)\s*"                               # a typed dash counts too


def expand(template: str, phrases: dict[str, str]) -> str:
    """The template with its shared phrases written in (unknown ones are left as they are)."""
    return PHRASE.sub(lambda m: phrases.get(m.group(1).strip(), m.group(0)), template)


def slots(template: str) -> list[str]:
    """Slot names in order of first appearance."""
    return list(dict.fromkeys(SLOT.findall(template)))


def _literal(text: str, first: bool) -> str:
    """Regex for literal template text: spaces flexible, the very first letter any case."""
    out = []
    for i, ch in enumerate(text):
        if ch.isspace():
            if not out or out[-1] != r"\s+":
                out.append(r"\s+")
        elif first and i == 0 and ch.isalpha():
            out.append(f"[{ch.lower()}{ch.upper()}]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def line_regex(mechanic: Mechanic, template: str, phrases: dict[str, str] | None = None) -> re.Pattern:
    """A whole rules line: "Name — " then the expanded template, slots as named groups."""
    body = expand(template, mechanic.phrases if phrases is None else phrases)
    parts, pos, seen = [], 0, set()
    for m in SLOT.finditer(body):
        parts.append(_literal(body[pos:m.start()], first=pos == 0))
        name = m.group(1)
        parts.append(f"(?P={name})" if name in seen else f"(?P<{name}>.+?)")
        seen.add(name)
        pos = m.end()
    parts.append(_literal(body[pos:], first=pos == 0))
    return re.compile(r"^\s*(?i:" + re.escape(mechanic.name) + ")" + DASH + "".join(parts) + r"\s*$")


def starts_line(mechanic: Mechanic, line: str) -> bool:
    """Whether a line begins with the ability word and a dash."""
    return re.match(r"^\s*" + re.escape(mechanic.name) + DASH, line, re.IGNORECASE) is not None


@dataclass
class Match:
    variant: int                   # index into mechanic.templates
    label: str
    values: dict[str, str]


def parse_line(mechanic: Mechanic, line: str, templates: list[AbilityTemplate] | None = None,
               phrases: dict[str, str] | None = None) -> Match | None:
    """Which variant a line follows, and its slot values (None: it follows none)."""
    for i, template in enumerate(mechanic.templates if templates is None else templates):
        if not template.text.strip():
            continue
        m = line_regex(mechanic, template.text, phrases).match(line)
        if m:
            return Match(i, template.label, {k: v.strip() for k, v in m.groupdict().items()})
    return None


def build_line(mechanic: Mechanic, template: str, values: dict[str, str] | None = None,
               phrases: dict[str, str] | None = None) -> str:
    """The line written out; slots without a value become "[slot]"."""
    body = expand(template, mechanic.phrases if phrases is None else phrases)
    body = SLOT.sub(lambda m: (values or {}).get(m.group(1)) or f"[{m.group(1)}]", body)
    return f"{mechanic.name} — {body}"


def insertion(mechanic: Mechanic, variant: int) -> tuple[str, int, int]:
    """Text to insert for a variant, with the first placeholder to select: (text, start, length)."""
    text = build_line(mechanic, mechanic.templates[variant].text)
    m = re.search(r"\[[a-z][a-z0-9_]*\]", text)
    return (text, m.start(), m.end() - m.start()) if m else (text, len(text), 0)


@dataclass
class LineUse:
    card: Card
    face: int
    line_index: int                # index into the face's rules text lines
    line: str
    match: Match | None            # None: the line doesn't follow any variant

    @property
    def unfinished(self) -> bool:
        return bool(re.search(r"\[[a-z][a-z0-9_]*\]", self.line))


def template_uses(project: SetProject, mechanic: Mechanic) -> list[LineUse]:
    """Every card line that starts with the ability word, matched to a variant if it fits."""
    out = []
    for card in sorted(project.cards, key=number_key):
        for face_index, face in card.iter_faces():
            for i, line in enumerate(face.rules_text.split("\n")):
                if starts_line(mechanic, line):
                    out.append(LineUse(card, face_index, i, line, parse_line(mechanic, line)))
    return out


@dataclass
class DefinitionChange:
    changes: list[Change]                       # whole rules texts, before and after
    unmatched: list[LineUse] = field(default_factory=list)   # left alone
    dropped: dict[str, list[str]] = field(default_factory=dict)  # variant label -> lost slots


def definition_change_plan(project: SetProject, mechanic: Mechanic, *,
                           phrases: dict[str, str] | None = None,
                           templates: list[AbilityTemplate] | None = None) -> DefinitionChange:
    """What changing the mechanic's phrases and/or variants would do to card text. Lines are
    matched with the current definition and rewritten with the new one, keeping each line's
    own values. Variants are paired by position; a line of a removed variant is left alone."""
    new_phrases = mechanic.phrases if phrases is None else phrases
    new_templates = mechanic.templates if templates is None else templates
    plan = DefinitionChange([])
    for i, old in enumerate(mechanic.templates):
        if i < len(new_templates):
            lost = [s for s in slots(old.text) if s not in slots(new_templates[i].text)]
            if lost:
                plan.dropped[new_templates[i].label or old.label] = lost
    edits: dict[tuple[str, int], dict[int, str]] = {}
    cards: dict[str, Card] = {}
    for use in template_uses(project, mechanic):
        if use.match is None or use.match.variant >= len(new_templates):
            plan.unmatched.append(use)
            continue
        old_line = build_line(mechanic, mechanic.templates[use.match.variant].text, use.match.values)
        new_line = build_line(mechanic, new_templates[use.match.variant].text, use.match.values, new_phrases)
        if new_line != old_line:                    # the change reaches this line (not just its dash)
            edits.setdefault((use.card.id, use.face), {})[use.line_index] = new_line
            cards[use.card.id] = use.card
    for (card_id, face), lines in edits.items():
        card = cards[card_id]
        before = card.faces[face].rules_text
        after_lines = before.split("\n")
        for index, line in lines.items():
            after_lines[index] = line
        plan.changes.append(Change(card, face, before, "\n".join(after_lines)))
    return plan
