"""Typing helpers for rules text and mana costs (pure functions, no UI).

    suggestions("Draw a card. {", 14, mechanics)    -> symbols to finish the "{"
    suggestions("Bloo", 4, mechanics)               -> the "Bloodpact {cost}" mechanic
    apply(text, caret, suggestion)                  -> (new text, new caret)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..model import Mechanic, MechanicKind

COLORS = "WUBRG"
BASIC_SYMBOLS = [*COLORS, "C", "X", "T", "Q", "S", "E"]
SYMBOL_LABELS = {"T": "tap", "Q": "untap", "S": "snow", "E": "energy", "C": "colorless", "X": "X"}
HYBRIDS = [f"{a}/{b}" for a, b in ("WU", "UB", "BR", "RG", "GW", "WB", "UR", "BG", "RW", "GU")]
SYMBOLS = BASIC_SYMBOLS + [str(n) for n in range(0, 11)] + HYBRIDS + [f"{c}/P" for c in COLORS] \
    + [f"2/{c}" for c in COLORS]


@dataclass(frozen=True)
class Suggestion:
    label: str              # shown to the user
    replace: int            # characters before the caret it replaces
    insert: str             # text inserted instead
    caret_back: int = 0     # leave the caret this many characters before the end of `insert`
    select: int = 0         # then select this many characters after the caret (a placeholder)


def symbol_suggestions(prefix: str) -> list[Suggestion]:
    """After an unclosed "{" + `prefix` (e.g. "", "W", "W/"): symbols starting with it."""
    upper = prefix.upper()
    matches = [s for s in SYMBOLS if s.startswith(upper)]
    return [Suggestion(f"{{{s}}}" + (f"  {SYMBOL_LABELS[s]}" if s in SYMBOL_LABELS else ""),
                       len(prefix) + 1, f"{{{s}}}") for s in matches[:24]]


PARAMETER_PLACEHOLDERS = {"cost": "{1}", "mana": "{1}", "number": "1", "name": "NAME"}


def mechanic_insert(mechanic: Mechanic) -> tuple[str, int]:
    """Text for a mechanic and how far back the caret goes (into its parameter)."""
    if not mechanic.parameter:
        return mechanic.name, 0
    placeholder = PARAMETER_PLACEHOLDERS.get(mechanic.parameter, "")
    return f"{mechanic.name} {placeholder}".rstrip() + ("" if placeholder else " "), 0


def ability_word_inserts(mechanic: Mechanic) -> list[tuple[str, str, int, int]]:
    """For an ability word with template variants: (label, text, select start, select length)
    per variant, e.g. ("Settled — Activated", "Settled — [cost]: [effect]. Activate only if
    …", 10, 6): the line with its shared phrases written in, first placeholder selected."""
    if mechanic.kind != MechanicKind.ABILITY_WORD:
        return []
    from .ability_words import insertion
    out = []
    for i, template in enumerate(mechanic.templates):
        if template.text.strip():
            text, start, length = insertion(mechanic, i)
            label = f"{mechanic.name} — {template.label}" if len(mechanic.templates) > 1 else mechanic.name
            out.append((label, text, start, length))
    return out


def suggestions(text: str, caret: int, mechanics: list[Mechanic] = ()) -> list[Suggestion]:
    before = text[:max(0, min(caret, len(text)))]
    # an unclosed "{" before the caret: mana and other symbols
    brace = before.rfind("{")
    if brace >= 0 and "}" not in before[brace:]:
        prefix = before[brace + 1:]
        if re.fullmatch(r"[0-9A-Za-z/]{0,4}", prefix):
            return symbol_suggestions(prefix)
        return []
    # a partial word at the caret (not in the middle of a word): our mechanics
    after = text[len(before):len(before) + 1]
    m = re.search(r"([A-Za-z][A-Za-z'\-]*)$", before)
    if not m or (after and after.isalpha()) or len(m.group(1)) < 2:
        return []
    word = m.group(1)
    out = []
    for mechanic in mechanics:
        if mechanic.name.lower().startswith(word.lower()) and mechanic.name.lower() != word.lower():
            variants = ability_word_inserts(mechanic)
            if variants:                            # one suggestion per variant
                for label, insert, start, length in variants:
                    out.append(Suggestion(label, len(word), insert, len(insert) - start, length))
                continue
            insert, back = mechanic_insert(mechanic)
            label = mechanic.name + (f" {{{mechanic.parameter}}}" if mechanic.parameter else "")
            out.append(Suggestion(label, len(word), insert, back))
    return out


def apply(text: str, caret: int, suggestion: Suggestion) -> tuple[str, int]:
    """Replace the typed part before the caret with the suggestion."""
    caret = max(0, min(caret, len(text)))
    start = max(0, caret - suggestion.replace)
    new_text = text[:start] + suggestion.insert + text[caret:]
    return new_text, start + len(suggestion.insert) - suggestion.caret_back


def insert(text: str, caret: int, snippet: str) -> tuple[str, int]:
    """Insert a snippet (e.g. "{W}" from the symbol palette, or "CARDNAME") at the caret."""
    caret = max(0, min(caret, len(text)))
    return text[:caret] + snippet + text[caret:], caret + len(snippet)
