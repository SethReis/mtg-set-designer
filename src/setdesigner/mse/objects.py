"""The objects MSE scripts see: `card`, `set`, `styling`, `extra_card`, `stylesheet`.

Field values are computed lazily, the way MSE computes them:
    value  = the user's value, else the field's `default:` script, else its initial value
    value  = the field's `script:` applied to that value (bound as `value`)
Text-like fields are stored as text, so a script returning 2 gives "2" (as in MSE).
Results are cached. A field that is needed while it is being computed returns its
unscripted value, and a script that fails (e.g. it needs a built-in we don't have
yet) falls back to the unscripted value and adds a warning instead of raising.

Scripts reach members with `card.casting_cost` or `card["casting cost"]`:
underscores and spaces are interchangeable, as in MSE.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .fields import FieldDef
from .mapping import MSECard
from .script import ast as A
from .script.spec_sort import SpecError
from .script.values import ErrorValue, ScriptError, to_str

if TYPE_CHECKING:
    from .environment import ScriptEnvironment

TEXT_TYPES = {"text", "choice", "multiple choice", "boolean", "package choice"}
MAX_LINKS = 32

# evaluate(script, value) -> result, with the object's variables (card, set, ...) bound
Evaluate = Callable[[A.Node, object], object]


def canonical(name: object) -> str:
    return to_str(name).replace("_", " ")


class ScriptObject:
    """Base for objects with members. `values.member` calls `script_member`."""
    type_label = "object"

    def script_member(self, name: object) -> object:
        raise NotImplementedError

    def no_member(self, name: object) -> ErrorValue:
        return ErrorValue(f"{self.type_label} has no member '{to_str(name)}'")


class FieldValues:
    """Lazily computed values of a set of fields (see module docstring)."""

    def __init__(self, defs: dict[str, FieldDef], raw: dict[str, str], evaluate: Evaluate,
                 label: str):
        self.defs = defs
        self.raw = raw
        self.evaluate = evaluate
        self.label = label
        self.cache: dict[str, object] = {}
        self.computing: set[str] = set()
        self.warnings: list[str] = []

    def __contains__(self, name: str) -> bool:
        return name in self.defs

    def unscripted(self, name: str) -> object:
        return self.raw.get(name, self.defs[name].initial_value())

    def get(self, name: str) -> object:
        if name in self.cache:
            return self.cache[name]
        if name in self.computing:          # needed while being computed
            return self.unscripted(name)
        fd = self.defs[name]
        self.computing.add(name)
        try:
            value = self._compute(fd)
        finally:
            self.computing.discard(name)
        self.cache[name] = value
        return value

    def _compute(self, fd: FieldDef) -> object:
        value = self.unscripted(fd.name)
        try:
            if fd.name not in self.raw and fd.default_script is not None:
                value = self.evaluate(fd.default_script, value)
            if fd.script is not None:
                value = self.evaluate(fd.script, value)
            if fd.type in TEXT_TYPES and not isinstance(value, ErrorValue):
                value = to_str(value)
        except (ScriptError, SpecError, RecursionError) as e:
            self.warnings.append(f"{self.label} field '{fd.name}': {e}")
            value = self.unscripted(fd.name)
        return value

    def all(self) -> dict[str, object]:
        return {name: self.get(name) for name in self.defs}


class StylesheetObject(ScriptObject):
    """A stylesheet package: its folder name and the simple values at the top of its
    style file (short name, full name, card width, ...)."""
    type_label = "stylesheet"

    def __init__(self, package: str, info: dict[str, str], root: Path | None = None):
        self.package = package                  # e.g. "magic-m15-altered"
        self.info = info
        self.root = root                        # folder holding all packages (for image files)

    def script_member(self, name: object) -> object:
        key = canonical(name)
        if key == "folder name":
            return f"{self.package}.mse-style"
        if key in self.info:
            return self.info[key]
        return self.no_member(name)


class SetObject(ScriptObject):
    type_label = "set"

    def __init__(self, env: ScriptEnvironment, raw: dict[str, str]):
        self.env = env
        self.fields = FieldValues(env.set_field_defs, raw, self._evaluate, "set")
        self.cards: list[CardObject] = []
        self.by_uid: dict[str, CardObject] = {}

    def _evaluate(self, script: A.Node, value: object) -> object:
        return self.env.evaluate(script, self.env.default_style, {"set": self, "value": value})

    def card_by_uid(self, uid: str) -> CardObject | None:
        return self.by_uid.get(uid)

    def script_items(self) -> list[tuple[int, CardObject]]:
        """A set used as a collection is its cards (`for each c in set`, length(set))."""
        return list(enumerate(self.cards))

    def script_member(self, name: object) -> object:
        key = canonical(name)
        if key == "cards":
            return list(self.cards)
        if key in self.fields:
            return self.fields.get(key)
        if key == "stylesheet":
            return self.env.stylesheet(self.env.default_style)
        if key == "set info":                   # MSE's set.set_info: the set fields
            return self
        return self.no_member(name)


class StylingObject(ScriptObject):
    """A stylesheet's options (`styling field`s): their defaults for now."""
    type_label = "styling"

    def __init__(self, env: ScriptEnvironment, style: str, raw: dict[str, str] | None = None):
        defs, _ = env.style_field_defs(style)
        self.fields = FieldValues(defs, raw or {}, self._evaluate, f"styling of {style}")
        self.env, self.style = env, style

    def _evaluate(self, script: A.Node, value: object) -> object:
        return self.env.evaluate(script, self.style, {"styling": self, "value": value})

    def script_member(self, name: object) -> object:
        key = canonical(name)
        return self.fields.get(key) if key in self.fields else self.no_member(name)


class CardObject(ScriptObject):
    """One MSE card, i.e. one face of one of our cards."""
    type_label = "card"

    def __init__(self, env: ScriptEnvironment, mse_card: MSECard):
        self.env = env
        self.mse = mse_card
        self.style = mse_card.stylesheet
        self.stylesheet = env.stylesheet(self.style)
        self.fields = FieldValues(env.card_field_defs, mse_card.values, self._evaluate,
                                  f"card {mse_card.uid}")
        _, extra_defs = env.style_field_defs(self.style)
        self.extra_card = ExtraCardObject(self, extra_defs)

    @property
    def uid(self) -> str:
        return self.mse.uid

    @property
    def links(self) -> list[tuple[str, str]]:
        return self.mse.links

    @property
    def warnings(self) -> list[str]:
        return self.fields.warnings + self.extra_card.fields.warnings

    def bindings(self, value: object) -> dict[str, object]:
        """The variables a script about this card runs with."""
        return {"card": self, "value": value, "set": self.env.set,
                "styling": self.env.styling(self.style), "extra_card": self.extra_card,
                "stylesheet": self.stylesheet,
                "last_change": ""}              # what the user just edited; no live editor here

    def _evaluate(self, script: A.Node, value: object) -> object:
        return self.env.evaluate(script, self.style, self.bindings(value))

    def script_member(self, name: object) -> object:
        key = canonical(name)
        if key in self.fields:
            return self.fields.get(key)
        if key == "uid":
            return self.uid
        if key == "notes":
            return self.mse.notes
        if key == "stylesheet":
            return self.stylesheet
        if key == "styling":
            return self.env.styling(self.style)
        if key.startswith(("linked card ", "linked relation ")):
            number = key.rsplit(" ", 1)[1]
            if number.isdigit() and 1 <= int(number) <= MAX_LINKS:
                n = int(number)
                if n > len(self.links):
                    return ""
                uid, relation = self.links[n - 1]
                return uid if key.startswith("linked card") else relation
        return self.no_member(name)


class ExtraCardObject(ScriptObject):
    """A stylesheet's extra per-card fields (`extra card field`s), e.g. M15's pt box."""
    type_label = "extra card"

    def __init__(self, card: CardObject, defs: dict[str, FieldDef]):
        self.card = card
        self.fields = FieldValues(defs, {}, card._evaluate, f"extra card {card.uid}")

    def script_member(self, name: object) -> object:
        key = canonical(name)
        return self.fields.get(key) if key in self.fields else self.no_member(name)
