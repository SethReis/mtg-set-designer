"""Run MSE scripts against our project.

    env = ScriptEnvironment(project)
    env.card_values(card, face_index)["type"]      # the type line as MSE computes it
    env.card_object(card, 1)                        # the `card` object scripts see

One script Context is loaded per stylesheet in use (game init script + the style's),
with `set` bound to the project's SetObject. Field scripts run in a call scope of
their card's stylesheet context with card, set, styling, extra_card, stylesheet and
value bound, just as MSE runs them.
"""
from __future__ import annotations

from pathlib import Path

from ..model import Card, SetProject
from .fields import FieldDef, game_fields, style_fields
from .frames import stylesheet_package
from .mapping import face_uid, set_values
from .keywords import KeywordDatabase
from .mechanics import mechanic_keywords, project_to_mse
from .objects import CardObject, SetObject, StylesheetObject, StylingObject
from .reader import read_file
from .script import ast as A
from .script.evaluator import Context, Evaluator
from .script.game import LoadReport, load_game
from .script.images import ImageOptions
from .script.parser import parse, parse_template
from .script.values import ScriptError
from .snippets import scripts_in

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "resources" / "mse_packages"


class ScriptEnvironment:
    def __init__(self, project: SetProject, root: Path = DEFAULT_ROOT, game: str = "magic"):
        self.project = project
        self.root = Path(root)
        self.game = game
        self.card_field_defs, self.set_field_defs = game_fields(self.root, game)
        self.default_style = stylesheet_package(project.info.default_frame)
        self._contexts: dict[str, Context] = {}
        self._loading: set[str] = set()
        self._styling: dict[str, StylingObject] = {}
        self._stylesheets: dict[str, StylesheetObject] = {}
        self._game_scripts: dict[str, A.Node] | None = None
        self._entry_scripts: dict[str, dict[tuple[str, str], A.Node]] = {}
        self._keyword_db: KeywordDatabase | None = None
        self.load_reports: dict[str, LoadReport] = {}

        self.set = SetObject(self, set_values(project.info, project.resolve))
        for mse_card in project_to_mse(project):
            obj = CardObject(self, mse_card)
            self.set.cards.append(obj)
            self.set.by_uid[obj.uid] = obj

    def refresh_card(self, card: Card) -> None:
        """After `card` was edited: recompute its MSE cards (all faces), keeping the
        loaded scripts and every other card's cached values. Fast enough for a live
        preview. (Edits that change other cards, e.g. reminder policies across the
        set, need a new environment.)"""
        fresh = {c.uid: c for c in project_to_mse(self.project)}
        uids = [face_uid(card, i) for i in range(len(card.faces))]
        for uid in uids:
            obj = CardObject(self, fresh[uid])
            old = self.set.by_uid.get(uid)
            if old in self.set.cards:
                self.set.cards[self.set.cards.index(old)] = obj
            else:
                self.set.cards.append(obj)
            self.set.by_uid[uid] = obj

    def remove_card(self, card_id: str) -> None:
        """Forget a deleted card (so it no longer counts in numbering etc.)."""
        gone = [c for c in self.set.cards if c.uid == card_id or c.uid.startswith(card_id + "/")]
        for obj in gone:
            self.set.cards.remove(obj)
            self.set.by_uid.pop(obj.uid, None)

    # ------------------------------------------------------------ contexts

    def style_field_defs(self, style: str) -> tuple[dict[str, FieldDef], dict[str, FieldDef]]:
        return style_fields(self.root, style)

    def context(self, style: str) -> Context:
        """The game + style script context, loaded on first use."""
        if style not in self._contexts:
            if style in self._loading:
                raise ScriptError(f"field value needed while loading the scripts of {style}")
            self._loading.add(style)
            try:
                ctx, report = load_game(self.root, style, self.game, variables={"set": self.set})
            finally:
                self._loading.discard(style)
            # Set-wide defaults, as MSE has with a set loaded; a card's own
            # values are bound in each field script's scope.
            ctx.set("styling", self.styling(style))
            ctx.set("stylesheet", self.stylesheet(style))
            self._contexts[style] = ctx
            self.load_reports[style] = report
        return self._contexts[style]

    def evaluate(self, script: A.Node, style: str, bindings: dict[str, object]) -> object:
        """Evaluate a script in a style's context, in a new scope with these variables.
        The scope is isolated from any script already running (see open_isolated_scope)."""
        ctx = self.context(style)
        marker = ctx.open_isolated_scope()
        try:
            for name, value in bindings.items():
                ctx.set(name, value)
            return Evaluator().eval(script, ctx)
        finally:
            ctx.close_scope(marker)

    def stylesheet(self, style: str) -> StylesheetObject:
        if style not in self._stylesheets:
            nodes, _ = read_file(self.root / f"{style}.mse-style" / "style", self.root)
            info = {n.key: n.value for n in nodes if n.value and not n.block}
            self._stylesheets[style] = StylesheetObject(style, info, self.root)
        return self._stylesheets[style]

    def styling(self, style: str) -> StylingObject:
        if style not in self._styling:
            self._styling[style] = StylingObject(self, style)
        return self._styling[style]

    def keyword_db(self) -> KeywordDatabase:
        """The game's keywords plus our project's mechanics (as the set's own keywords)."""
        if self._keyword_db is None:
            nodes, _ = read_file(self.root / f"{self.game}.mse-game" / "game", self.root)
            db = KeywordDatabase.from_nodes(nodes)
            for mechanic in self.project.mechanics:
                for keyword in mechanic_keywords(mechanic):
                    db.add(keyword, from_game=False)
            self._keyword_db = db
        return self._keyword_db

    def game_script(self, key: str) -> A.Node:
        """A top-level script of the game file, e.g. "get front face script"."""
        if self._game_scripts is None:
            nodes, _ = read_file(self.root / f"{self.game}.mse-game" / "game", self.root)
            self._game_scripts = {s.path: parse(s.text) for s in scripts_in(nodes, self.game)
                                  if s.kind == "script" and " > " not in s.path}
        if key not in self._game_scripts:
            raise ScriptError(f"the game has no '{key}'")
        return self._game_scripts[key]

    # ------------------------------------------------------ style entries

    def style_entry_script(self, style: str, field: str, key: str) -> A.Node | None:
        """The script of a stylesheet's `card style > <field> > <key>` (e.g. "card color",
        "image"), or None. Repeated `card style` blocks are merged; later ones win."""
        if style not in self._entry_scripts:
            nodes, _ = read_file(self.root / f"{style}.mse-style" / "style", self.root)
            entries: dict[tuple[str, str], A.Node] = {}
            for block in nodes:
                if block.key != "card style":
                    continue
                for entry in block.children():
                    for snip in scripts_in(entry.children() if entry.block else [], style):
                        entries[(entry.key, snip.path)] = (
                            parse(snip.text) if snip.kind == "script" else parse_template(snip.text))
            self._entry_scripts[style] = entries
        return self._entry_scripts[style].get((field, key))

    def style_value(self, card: CardObject, field: str, key: str) -> object:
        """Evaluate a card style entry's script for a card, as MSE does when drawing:
        with the card's variables bound and `input` = that field's value."""
        script = self.style_entry_script(card.style, field, key)
        if script is None:
            raise ScriptError(f"{card.style} has no card style '{field} > {key}'")
        bindings = card.bindings(card.fields.get(field) if field in card.fields else None)
        bindings["input"] = bindings.pop("value")
        return self.evaluate(script, card.style, bindings)

    def image_options(self, style: str, width: int = 0, height: int = 0) -> ImageOptions:
        """How to turn a style's image values into pixels."""
        return ImageOptions(width=width, height=height, root=self.root,
                            package=self.root / f"{style}.mse-style")

    # ---------------------------------------------------------- our cards

    def card_object(self, card: Card, face_index: int = 0) -> CardObject:
        return self.set.by_uid[face_uid(card, face_index)]

    def card_values(self, card: Card, face_index: int = 0) -> dict[str, object]:
        """Every MSE card field of one face, computed."""
        return self.card_object(card, face_index).fields.all()
