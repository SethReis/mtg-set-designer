"""One open set: the editor's behaviour, without any UI code.

    session = SetSession.create(folder, "My Set", "MYS", "m15")    # or SetSession.open(folder)
    card = session.new_card()
    session.update(card, "rules_text", "Flying")                    # saved ~0.5 s later
    image = session.render(card)                                    # PIL image (real MSE)
    session.close()                                                 # saves anything pending

Saving is automatic: an edit marks the card dirty, and `flush_due()` (called by the UI
a few times a second) writes cards whose last edit is older than AUTOSAVE_DELAY.
`flush()` writes everything now (on close, or when switching sets).
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image

from ..model import (AbilityTemplate, Archetype, ArtCrop, Card, CheckSetting, Cycle, CycleTemplate, Face,
                     Mechanic, MechanicKind, Rarity, ReminderPolicy, SetInfo, SetProject, Status,
                     delete_card, load_project, new_card_id, save_archetypes, save_card,
                     save_cycles, save_info, save_mechanics, save_project)
from ..model.project import slug
from ..mse.mapping import join_type_line, split_type_line
from .mechanics import mechanic_ids
from .overview import matches_text, number_key

AUTOSAVE_DELAY = 0.5                    # seconds after the last edit

FACE_FIELDS = {"name", "mana_cost", "type_line", "rules_text", "flavor_text", "power",
               "toughness", "loyalty", "artist"}
TYPE_PARTS = {"types", "subtypes"}      # the two halves of type_line, edited separately
ART_FIELDS = {"art_path", "art_crop"}
CARD_FIELDS = {"rarity", "collector_number", "frame", "status", "notes", "archetypes"}
OPTIONAL = {"power", "toughness", "loyalty"}            # "" means "not set"


class SessionError(Exception):
    pass


class SetSession:
    def __init__(self, folder: Path, project: SetProject,
                 renderer_factory: Callable[[SetProject], object] | None = None,
                 thumbnail_dir: Path | None = None):
        self.folder = Path(folder)
        self._thumbnail_dir = thumbnail_dir      # None = the user's cache folder
        self.project = project
        self._renderer_factory = renderer_factory
        self._renderer = None
        self._renderer_lock = threading.Lock()
        self._pending: dict[str, float] = {}     # card id -> time of last edit
        self._edited: set[str] = set()           # edited since the renderer last saw them
        self._art_boxes: dict[str, tuple[float, float]] = {}   # stylesheet -> art box size
        self.art_version = 0                     # goes up when art is added or removed
        self.art_notice: tuple[str, str] | None = None   # (kind, message) for the page to show
        self._thumbnails = None

    # ------------------------------------------------------------ opening

    @classmethod
    def create(cls, folder: Path, name: str, code: str, frame: str = "m15", **kw) -> "SetSession":
        folder = Path(folder)
        if (folder / "set.json").exists():
            raise SessionError(f"There is already a set in {folder}")
        if not name.strip() or not code.strip():
            raise SessionError("A set needs a name and a code")
        project = SetProject(info=SetInfo(name=name.strip(), code=code.strip().upper(),
                                          default_frame=frame))
        save_project(project, folder)
        return cls(folder, project, **kw)

    @classmethod
    def open(cls, folder: Path, **kw) -> "SetSession":
        folder = Path(folder)
        if not (folder / "set.json").is_file():
            raise SessionError(f"No set found in {folder} (it has no set.json)")
        return cls(folder, load_project(folder), **kw)

    # -------------------------------------------------------------- cards

    def cards(self) -> list[Card]:
        """All cards in collector-number order."""
        return sorted(self.project.cards, key=number_key)

    def search(self, text: str) -> list[Card]:
        return [c for c in self.cards() if matches_text(c, text)]

    def card(self, card_id: str) -> Card:
        return self.project.card(card_id)

    def next_collector_number(self) -> str:
        numbers = [int(m.group()) for c in self.project.cards
                   if (m := re.match(r"\d+", c.collector_number))]
        return str(max(numbers, default=0) + 1)

    def new_card(self, name: str = "New Card") -> Card:
        card = Card(id=new_card_id(self.project, name), faces=[Face(name=name)],
                    rarity=Rarity.COMMON, collector_number=self.next_collector_number())
        self.project.cards.append(card)
        save_card(self.folder, card)
        return card

    def duplicate(self, card: Card) -> Card:
        copy = card.model_copy(deep=True)
        copy.id = new_card_id(self.project, card.faces[0].name)
        copy.collector_number = self.next_collector_number()
        self.project.cards.append(copy)
        save_card(self.folder, copy)
        return copy

    def delete(self, card: Card) -> None:
        if self._thumbnails is not None:
            self._thumbnails.forget(card.id)
            self._thumbnails.cache.remove(card.id)
        self._edited.discard(card.id)
        self.project.cards = [c for c in self.project.cards if c.id != card.id]
        self._pending.pop(card.id, None)
        delete_card(self.folder, card.id)
        if self._renderer is not None:
            with self._renderer_lock:
                self._renderer.env.remove_card(card.id)
        for cycle in self.project.cycles:               # its cycle shows it as missing now
            for member in cycle.members:
                if member.card_id == card.id:
                    member.card_id = None
                    save_cycles(self.folder, self.project.cycles)

    # ------------------------------------------------------------ editing

    def update(self, card: Card, field: str, value: object, face: int = 0) -> None:
        """Change one field and schedule saving. Face fields apply to `face`.
        "types" / "subtypes" set one side of the type line's dash (see join_type_line)."""
        if field in TYPE_PARTS:
            types, subtypes = split_type_line(card.faces[face].type_line)
            parts = {"types": types, "subtypes": subtypes, field: "" if value is None else str(value)}
            card.faces[face].type_line = join_type_line(parts["types"], parts["subtypes"])
        elif field in ART_FIELDS:                          # set by app.assets / the crop editor
            if field == "art_crop" and value is not None and not isinstance(value, ArtCrop):
                value = ArtCrop.model_validate(value)
            setattr(card.faces[face], field, value or None)
        elif field in FACE_FIELDS:
            if field in OPTIONAL:                          # "" or None = not set
                value = (str(value).strip() or None) if value is not None else None
            else:
                value = "" if value is None else str(value)
            setattr(card.faces[face], field, value)
        elif field in CARD_FIELDS:
            if field == "rarity":
                value = Rarity(value)
            elif field == "status":
                value = Status(value)
            elif field == "frame":
                value = value or None                       # "" = use the set's default
            elif field == "archetypes":
                value = list(value or [])
            setattr(card, field, value)
        else:
            raise SessionError(f"Unknown field {field!r}")
        if field in ("rules_text", "name"):             # which mechanics it uses may change
            card.mechanics = mechanic_ids(self.project, card)
        self._changed(card)

    def _changed(self, card: Card) -> None:
        """Schedule saving a card and tell the renderer and the overview pictures."""
        self._pending[card.id] = time.monotonic()
        self._edited.add(card.id)
        if self._thumbnails is not None:
            self._thumbnails.forget(card.id)

    # --------------------------------------------------------- archetypes

    def new_archetype(self, name: str, colors: str = "") -> Archetype:
        taken = {a.id for a in self.project.archetypes}
        base = slug(name)
        aid, n = base, 2
        while aid in taken:
            aid, n = f"{base}-{n}", n + 1
        archetype = Archetype(id=aid, name=name, colors=colors)
        self.project.archetypes.append(archetype)
        save_archetypes(self.folder, self.project.archetypes)
        return archetype

    def update_archetype(self, archetype: Archetype, **values: object) -> None:
        """Change name, colors, description or targets ({rarity: count}; 0 or None = no target)."""
        for key, value in values.items():
            if key == "targets":
                value = {Rarity(r): int(n) for r, n in (value or {}).items() if n}
            setattr(archetype, key, value)
        save_archetypes(self.folder, self.project.archetypes)

    def delete_archetype(self, archetype: Archetype) -> None:
        """Remove it, and its tag from every card (those cards are saved)."""
        self.project.archetypes = [a for a in self.project.archetypes if a.id != archetype.id]
        save_archetypes(self.folder, self.project.archetypes)
        for card in self.project.cards:
            if archetype.id in card.archetypes:
                card.archetypes = [a for a in card.archetypes if a != archetype.id]
                save_card(self.folder, card)

    def update_info(self, **values: object) -> None:
        """Change set-wide fields (name, code, default frame, symbol, rarity slots, ...).
        They affect every card, so the renderer starts over with the new values."""
        for key, value in values.items():
            if key == "rarity_slots":
                value = {Rarity(r): int(n) for r, n in (value or {}).items() if n}
            setattr(self.project.info, key, value)
        save_info(self.folder, self.project.info)
        self._restart_renderer()

    def set_health_check(self, check_id: str, enabled: bool, threshold: float | None) -> None:
        """Tune one set-health check (app.health.checks); None threshold = its default.
        Only the health page reads these, so the renderer keeps running."""
        self.project.info.health[check_id] = CheckSetting(enabled=enabled, threshold=threshold)
        save_info(self.folder, self.project.info)

    def set_role(self, card: Card, role: str, value: bool | None) -> None:
        """Correct a card's set-health role: True adds it, False removes a detected one,
        None goes back to what's detected from the rules text."""
        if value is None:
            card.role_overrides.pop(role, None)
        else:
            card.role_overrides[role] = value
        self._pending[card.id] = time.monotonic()       # saved; nothing to redraw

    def _restart_renderer(self) -> None:
        """Set-wide things changed (set info, mechanics): start the renderer afresh."""
        with self._renderer_lock:
            if self._renderer is not None:
                self._renderer.close()
                self._renderer = None

    # ------------------------------------------------------------ cycles

    def new_cycle(self, name: str = "New cycle", grouping: str = "mono") -> Cycle:
        from .cycles import members_for
        taken = {c.id for c in self.project.cycles}
        base = slug(name)
        cid, n = base, 2
        while cid in taken:
            cid, n = f"{base}-{n}", n + 1
        cycle = Cycle(id=cid, name=name, grouping=grouping, members=members_for(grouping))
        self.project.cycles.append(cycle)
        save_cycles(self.folder, self.project.cycles)
        return cycle

    def set_cycle_grouping(self, cycle: Cycle, grouping: str, custom: list[str] | None = None,
                           count: int = 5) -> None:
        """Change which colors the cycle covers. Members keep their card and overrides when
        their colors stay; a dropped member's card stays in the set, just unlinked."""
        from .cycles import members_for
        members = members_for(grouping, custom, count, cycle.members)
        kept = {m.card_id for m in members if m.card_id}
        for member in cycle.members:
            if member.card_id and member.card_id not in kept:
                self._unlink(member.card_id)
        cycle.grouping, cycle.members = grouping, members
        save_cycles(self.folder, self.project.cycles)

    def update_cycle(self, cycle: Cycle, update_cards: bool = False, **values: object) -> list:
        """Change a cycle's name, notes or template. With update_cards, a new template is
        carried to the members' cards (fields edited on a card stay; see
        app.cycles.template_change_plan). Returns the card changes made."""
        from .cycles import template_change_plan
        changes = []
        if "template" in values:
            values["template"] = CycleTemplate.model_validate(values["template"]) \
                if not isinstance(values["template"], CycleTemplate) else values["template"]
            if update_cards:
                changes = template_change_plan(cycle, self.project, values["template"]).changes
                for change in changes:
                    for name, (_, after) in change.fields.items():
                        self._set_card_field(change.card, name, after)
        for key, value in values.items():
            setattr(cycle, key, value)
        save_cycles(self.folder, self.project.cycles)
        return changes

    def set_member_override(self, cycle: Cycle, index: int, field: str, text: str | None) -> None:
        """A member's own text for a template field (None: follow the template again)."""
        member = cycle.members[index]
        if text is None:
            member.overrides.pop(field, None)
        else:
            member.overrides[field] = text
        save_cycles(self.folder, self.project.cycles)

    def generate_cycle(self, cycle: Cycle) -> list[Card]:
        """Create a placeholder card ("idea") for every member without one, in member order,
        with the template filled in for its colors. Returns the new cards."""
        from .cycles import matching_archetypes, member_fields
        made = []
        for n, member in enumerate(cycle.members, 1):
            if member.card_id and any(c.id == member.card_id for c in self.project.cards):
                continue
            fields = member_fields(cycle, member, n)
            card = self.new_card(fields["name"] or f"{cycle.name} {n}")
            for name, value in fields.items():
                if name != "name":
                    self._set_card_field(card, name, value)
            card.cycle = cycle.id
            if cycle.template.tag_archetypes and member.colors:
                card.archetypes = matching_archetypes(self.project, member.colors)
            card.mechanics = mechanic_ids(self.project, card)
            self._changed(card)
            member.card_id = card.id
            made.append(card)
        save_cycles(self.folder, self.project.cycles)
        self.flush()
        return made

    def delete_cycle(self, cycle: Cycle) -> None:
        """Remove a cycle. Its cards stay in the set, unlinked."""
        for member in cycle.members:
            if member.card_id:
                self._unlink(member.card_id)
        self.project.cycles = [c for c in self.project.cycles if c.id != cycle.id]
        save_cycles(self.folder, self.project.cycles)

    def _unlink(self, card_id: str) -> None:
        card = next((c for c in self.project.cards if c.id == card_id), None)
        if card is not None and card.cycle is not None:
            card.cycle = None
            self._changed(card)

    def _set_card_field(self, card: Card, name: str, value: str) -> None:
        if name == "rarity":
            self.update(card, "rarity", value or "common")
        elif name == "frame":
            self.update(card, "frame", value or None)
        else:
            self.update(card, name, value)

    # ---------------------------------------------------------- mechanics

    def new_mechanic(self, name: str = "New mechanic") -> Mechanic:
        taken = {m.id for m in self.project.mechanics}
        base = slug(name)
        mid, n = base, 2
        while mid in taken:
            mid, n = f"{base}-{n}", n + 1
        mechanic = Mechanic(id=mid, name=name)
        self.project.mechanics.append(mechanic)
        self._mechanics_changed()
        return mechanic

    def update_mechanic(self, mechanic: Mechanic, update_cards: bool = False, **values: object) -> list:
        """Change a mechanic's definition (not its name: see rename_mechanic). For an ability
        word's `phrases` / `templates`, update_cards also rewrites the card lines that follow
        it (app.ability_words.definition_change_plan). Returns the card changes made."""
        for key, value in values.items():
            if key == "kind":
                value = MechanicKind(value)
            elif key == "reminder_policy":
                value = ReminderPolicy(value)
            elif key == "parameter":
                value = value or None
            elif key == "forms":
                value = [f.strip() for f in value or [] if f.strip()]
            elif key == "phrases":
                value = {k.strip(): v for k, v in (value or {}).items() if k.strip()}
            elif key == "templates":
                value = [AbilityTemplate.model_validate(t) for t in value or []]
            values[key] = value
        changes = []
        if update_cards and ("phrases" in values or "templates" in values):
            from .ability_words import definition_change_plan
            changes = definition_change_plan(self.project, mechanic, phrases=values.get("phrases"),
                                             templates=values.get("templates")).changes
            for change in changes:
                change.card.faces[change.face].rules_text = change.after
                self._changed(change.card)
        for key, value in values.items():
            setattr(mechanic, key, value)
        self._mechanics_changed()
        return changes

    def rename_mechanic(self, mechanic: Mechanic, new_name: str, update_cards: bool) -> list:
        """Rename a mechanic (and its word forms); with update_cards, also in card text.
        Returns the card changes made (empty if cards were left alone)."""
        from .mechanics import new_forms_after_rename, rename_plan
        changes = rename_plan(self.project, mechanic, new_name) if update_cards else []
        for change in changes:
            change.card.faces[change.face].rules_text = change.after
            self._changed(change.card)
        mechanic.forms = new_forms_after_rename(mechanic, new_name)
        mechanic.name = new_name
        self._mechanics_changed()
        return changes

    def delete_mechanic(self, mechanic: Mechanic) -> None:
        """Remove a mechanic. Card text stays; per-card reminder choices for it go."""
        self.project.mechanics = [m for m in self.project.mechanics if m.id != mechanic.id]
        for card in self.project.cards:
            if mechanic.id in card.reminders:
                card.reminders.pop(mechanic.id)
                self._changed(card)
        self._mechanics_changed()

    def set_reminder(self, card: Card, mechanic: Mechanic, show: bool | None) -> None:
        """Show or hide a mechanic's reminder text on one card; None follows the policy."""
        if show is None:
            card.reminders.pop(mechanic.id, None)
        else:
            card.reminders[mechanic.id] = show
        self._changed(card)        # re-rendering the card works its reminder choices out again

    def _mechanics_changed(self) -> None:
        save_mechanics(self.folder, self.project.mechanics)
        for card in self.project.cards:             # what each card uses may have changed
            ids = mechanic_ids(self.project, card)
            if ids != card.mechanics:
                card.mechanics = ids
                self._changed(card)
        self._restart_renderer()

    # ------------------------------------------------------------- saving

    @property
    def unsaved(self) -> bool:
        return bool(self._pending)

    def flush_due(self, now: float | None = None) -> list[str]:
        """Save cards whose last edit is at least AUTOSAVE_DELAY old. Returns their ids."""
        now = time.monotonic() if now is None else now
        due = [cid for cid, t in self._pending.items() if now - t >= AUTOSAVE_DELAY]
        for cid in due:
            self._save(cid)
        return due

    def flush(self) -> None:
        for cid in list(self._pending):
            self._save(cid)

    def _save(self, card_id: str) -> None:
        self._pending.pop(card_id, None)
        card = next((c for c in self.project.cards if c.id == card_id), None)
        if card is not None:
            save_card(self.folder, card)

    # ---------------------------------------------------------- rendering

    @property
    def renderer(self):
        """The card renderer, started on first use (real MSE takes a few seconds)."""
        with self._renderer_lock:
            if self._renderer is None:
                if self._renderer_factory is None:
                    from ..render import CardRenderer
                    self._renderer = CardRenderer(self.project)
                else:
                    self._renderer = self._renderer_factory(self.project)
            return self._renderer

    def render(self, card: Card, face: int = 0) -> Image.Image:
        """Render a card as it is now. Safe to call from a worker thread."""
        renderer = self.renderer
        with self._renderer_lock:
            renderer.card_changed(card)                    # cheap; keeps numbering current
            self._edited.discard(card.id)
            return renderer.render(card, face)

    @property
    def renderer_note(self) -> str:
        """Shown in the UI when cards are not drawn by MSE."""
        r = self._renderer
        if r is None:
            return ""
        return "built-in renderer" if r.last_backend == "builtin" else ""

    def using_renderer(self, fn: Callable[[object], object]) -> object:
        """fn(renderer) under the renderer lock (for background work such as thumbnails)."""
        renderer = self.renderer
        with self._renderer_lock:
            return fn(renderer)

    def refresh_edited(self, renderer) -> None:
        """Tell the renderer about cards edited since it last drew them (call under the lock)."""
        for card_id in list(self._edited):
            card = next((c for c in self.project.cards if c.id == card_id), None)
            if card is not None:
                renderer.card_changed(card)
            self._edited.discard(card_id)

    def art_box(self, card: Card, face: int = 0) -> tuple[float, float] | None:
        """The (width, height) of the face's art box in its frame, if known yet
        (see find_art_box; frames are looked up once)."""
        return self._art_boxes.get(self._stylesheet(card, face))

    def find_art_box(self, card: Card, face: int = 0) -> tuple[float, float] | None:
        """Look up the art box (needs the renderer, so call it off the UI thread)."""
        key = self._stylesheet(card, face)
        if key not in self._art_boxes:
            def find(renderer):
                renderer.card_changed(card)
                self._edited.discard(card.id)
                return renderer.art_box(card, face)
            box = self.using_renderer(find)
            if box is None:
                return None
            self._art_boxes[key] = box
        return self._art_boxes[key]

    def _stylesheet(self, card: Card, face: int) -> str:
        """A key for the face's frame: its stylesheet plus any styling options it sets."""
        from ..mse.frames import frame_styling, stylesheet_package
        from ..mse.mapping import is_planeswalker
        frame = card.frame_for(face, self.project.info.default_frame)
        planeswalker = is_planeswalker(card.faces[face])
        return f"{stylesheet_package(frame, planeswalker=planeswalker)} {frame_styling(frame, planeswalker)}"

    @property
    def thumbnails(self):
        """Card pictures for the overview, made in the background (see thumbnails.py)."""
        if self._thumbnails is None:
            from .thumbnails import ThumbnailCache, ThumbnailWorker, default_cache_dir
            folder = self._thumbnail_dir or default_cache_dir(self.folder)
            self._thumbnails = ThumbnailWorker(self, ThumbnailCache(folder))
        return self._thumbnails

    def close(self) -> None:
        if self._thumbnails is not None:
            self._thumbnails.stop()
            self._thumbnails = None
        self.flush()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
