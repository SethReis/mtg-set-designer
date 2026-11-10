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
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from PIL import Image

from ..model import (LAYOUTS, AbilityTemplate, Archetype, ArtCrop, Card, CheckSetting, Cycle, CycleTemplate,
                     Face, FaceRole, Idea, IdeaLink, IdeaSketch, Layout, Mechanic, MechanicKind, Rarity, ReminderPolicy, SetInfo,
                     SetProject, Skeleton, Slot, Status,
                     delete_card, load_project, new_card_id, save_archetypes, save_card,
                     save_cycles, save_info, save_mechanics, save_notebook, save_project,
                     save_skeleton)
from ..model.project import slug
from ..mse.mapping import join_type_line, split_type_line
from .mechanics import mechanic_ids
from .overview import matches_text, number_key

AUTOSAVE_DELAY = 0.5                    # seconds after the last edit

FACE_FIELDS = {"name", "mana_cost", "type_line", "rules_text", "flavor_text", "power",
               "toughness", "loyalty", "artist", "color_indicator"}
TYPE_PARTS = {"types", "subtypes"}      # the two halves of type_line, edited separately
ART_FIELDS = {"art_path", "art_crop"}
CARD_FIELDS = {"rarity", "collector_number", "frame", "status", "notes", "archetypes", "print_copies",
               "transform_symbol", "balance_adjust", "balance_note"}
OPTIONAL = {"power", "toughness", "loyalty"}            # "" means "not set"


class SessionError(Exception):
    pass


class PriorityLock:
    """The renderer's lock: callers the user is waiting on (the editor's preview, Print)
    go before background work (overview pictures, warming up) that is waiting too.

        with lock: ...                       # interactive
        with lock.background(): ...          # waits while anyone interactive is waiting
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._held = False
        self._waiting = 0                        # interactive callers waiting for the lock

    def acquire(self, background: bool = False) -> None:
        with self._cond:
            if background:
                while self._held or self._waiting:
                    self._cond.wait()
            else:
                self._waiting += 1
                try:
                    while self._held:
                        self._cond.wait()
                finally:
                    self._waiting -= 1
            self._held = True

    def release(self) -> None:
        with self._cond:
            self._held = False
            self._cond.notify_all()

    def __enter__(self) -> "PriorityLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    @contextmanager
    def background(self) -> Iterator[None]:
        self.acquire(background=True)
        try:
            yield
        finally:
            self.release()


class SetSession:
    def __init__(self, folder: Path, project: SetProject,
                 renderer_factory: Callable[[SetProject], object] | None = None,
                 thumbnail_dir: Path | None = None):
        self.folder = Path(folder)
        self._thumbnail_dir = thumbnail_dir      # None = the user's cache folder
        self.project = project
        self._renderer_factory = renderer_factory
        self._renderer = None
        self._renderer_lock = PriorityLock()
        self._pending: dict[str, float] = {}     # card id -> time of last edit
        self._edited: set[str] = set()           # edited since the renderer last saw them
        self._art_boxes: dict[str, tuple[float, float]] = {}   # stylesheet -> art box size
        self.art_version = 0                     # goes up when art is added or removed
        self.art_notice: tuple[str, str] | None = None   # (kind, message) for the page to show
        self._thumbnails = None
        self._warming: threading.Thread | None = None    # see warm_up

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
        if self.project.skeleton is not None and (slot := self.project.skeleton.slot_of(card.id)):
            slot.card_id, slot.cycle = None, None
            self._save_skeleton()
        delete_card(self.folder, card.id)
        self._drop_links("card", card.id)
        if self._renderer is not None:
            with self._renderer_lock:
                self._renderer.env.remove_card(card.id)
        for cycle in self.project.cycles:               # its cycle shows it as missing now
            for member in cycle.members:
                if member.card_id == card.id:
                    member.card_id = None
                    save_cycles(self.folder, self.project.cycles)

    def set_layout(self, card: Card, layout: Layout | str) -> None:
        """Make a card single-faced, transform or modal double-faced (MDFC). Adds an empty
        back face, or drops it (ask the user first if it has content); a transform back
        has no mana cost, so it is cleared."""
        layout = Layout(layout)
        if layout == card.layout:
            return
        roles = LAYOUTS[layout].face_roles
        if len(roles) > len(card.faces):
            card.faces.append(Face(name="", role=FaceRole.BACK))
        del card.faces[len(roles):]
        for face, role in zip(card.faces, roles):
            face.role = role
        for index, fields in LAYOUTS[layout].forbidden.items():
            for field in fields:
                setattr(card.faces[index], field, "")
        card.layout = layout
        if layout != Layout.TRANSFORM:
            card.transform_symbol = ""
        card.mechanics = mechanic_ids(self.project, card)
        if self._renderer is not None:              # its MSE cards (one per face) change
            with self._renderer_lock:
                self._renderer.env.remove_card(card.id)
                self._renderer.env.refresh_card(card)
        self._changed(card)

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
            elif field == "print_copies":                   # None / "" = follow the rarity
                value = None if value in (None, "") else max(0, int(value))
            elif field == "balance_adjust":                 # None / "" = no adjustment
                value = 0.0 if value in (None, "") else float(value)
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

    def set_balance_norm(self, key: str, value: float | None) -> None:
        """Override one Balance norm (app.balance.norms) for this set; None = the default."""
        if value is None:
            self.project.info.balance.pop(key, None)
        else:
            self.project.info.balance[key] = float(value)
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
            self._place_in_skeleton(card, cycle=cycle.id)
            made.append(card)
        save_cycles(self.folder, self.project.cycles)
        self.flush()
        return made

    # ------------------------------------------------------------ skeleton

    def create_skeleton(self, preset: str, columns: list[str], counts: dict[str, dict[str, int]]) -> list[Card]:
        """Make the set's skeleton and put existing cards where they fit. Returns the cards
        left outside it."""
        from . import skeleton as sk
        self.flush()
        skeleton = Skeleton(preset=preset, columns=list(columns), counts={c: dict(counts.get(c, {})) for c in columns},
                            slots=sk.generate(columns, counts, self.project.archetypes))
        self.project.skeleton = skeleton
        left = sk.place_cards(skeleton, self.project)
        self._save_skeleton()
        return left

    def adjust_skeleton(self, columns: list[str], counts: dict[str, dict[str, int]],
                        remove_filled: bool = False) -> list[Slot]:
        """New counts (or columns) for the skeleton, in place: see app.skeleton.adjust.
        Returns filled slots that would have to go (kept unless `remove_filled`)."""
        from . import skeleton as sk
        blocked = sk.adjust(self.project.skeleton, columns, counts, self.project.archetypes, remove_filled)
        self._save_skeleton()
        return blocked

    def delete_skeleton(self) -> None:
        self.project.skeleton = None
        self._save_skeleton()

    def update_slot(self, slot: Slot, **values: object) -> None:
        """Change a slot's description: types, mana_value, role, archetypes, note. A filled
        slot's archetypes are its card's, so changing them re-tags the card too."""
        for key, value in values.items():
            if key not in ("types", "mana_value", "role", "archetypes", "note"):
                raise SessionError(f"Unknown slot field {key!r}")
            if key == "mana_value":
                value = None if value in (None, "") else max(0, int(value))
            elif key == "role":
                value = value or None
            elif key == "archetypes":
                value = [a for a in (value or []) if a]
                card = next((c for c in self.project.cards if c.id == slot.card_id), None)
                if card is not None:
                    self.update(card, "archetypes", list(value))
            else:
                value = str(value or "")
            setattr(slot, key, value)
        self._save_skeleton()

    def add_slot(self, column: str, rarity: str) -> Slot:
        """One more slot at the end of a cell (rarity: a Rarity value, or "any" in a cube)."""
        from . import skeleton as sk
        skeleton = self.project.skeleton
        counts = {c: dict(r) for c, r in skeleton.counts.items()}
        counts.setdefault(column, {})[rarity] = len(sk.cell(skeleton, column, rarity)) + 1
        columns = skeleton.columns if column in skeleton.columns else             sorted([*skeleton.columns, column], key=sk.column_order)
        sk.adjust(skeleton, columns, counts, self.project.archetypes)
        self._save_skeleton()
        return sk.cell(skeleton, column, rarity)[-1]

    def delete_slot(self, slot: Slot) -> None:
        skeleton = self.project.skeleton
        skeleton.slots.remove(slot)
        self._drop_links("slot", slot.id)
        key = "any" if slot.rarity is None else slot.rarity.value
        if slot.column in skeleton.counts and key in skeleton.counts[slot.column]:
            skeleton.counts[slot.column][key] = max(0, skeleton.counts[slot.column][key] - 1)
        self._save_skeleton()

    def assign(self, slot: Slot, card: Card | None) -> None:
        """Fill a slot with a card (or empty it with None). A card is in one slot at most:
        moving it from another slot leaves that one empty, or holding this slot's card
        if it was filled (a swap)."""
        skeleton = self.project.skeleton
        if card is not None:
            previous = skeleton.slot_of(card.id)
            if previous is slot:
                return
            if previous is not None:
                previous.card_id = slot.card_id         # a swap (or empty)
                previous.cycle = slot.cycle if slot.card_id else None
        slot.card_id = card.id if card is not None else None
        slot.cycle = card.cycle if card is not None else None
        self._save_skeleton()

    def new_card_from_slot(self, slot: Slot) -> Card:
        """A new card asked for by a slot: its rarity, type, archetype and note, in the slot."""
        card = self.new_card("New Card")
        if slot.rarity is not None:
            self.update(card, "rarity", slot.rarity)
        if slot.types:
            self.update(card, "types", slot.types)
        if slot.archetypes:
            self.update(card, "archetypes", list(slot.archetypes))
        if slot.note:
            self.update(card, "notes", slot.note)
        self.assign(slot, card)
        return card

    def _place_in_skeleton(self, card: Card, cycle: str | None = None) -> Slot | None:
        """Put a new card (e.g. a cycle's) in the empty slot that fits it best, if any."""
        from . import skeleton as sk
        skeleton = self.project.skeleton
        if skeleton is None or skeleton.slot_of(card.id) is not None:
            return None
        scored = [(sk.fits(card, s, skeleton.columns, self.project), s) for s in skeleton.slots if s.card_id is None]
        scored = [(score, s) for score, s in scored if score is not None]
        if not scored:
            return None
        slot = max(scored, key=lambda p: p[0])[1]
        slot.card_id, slot.cycle = card.id, cycle
        self._save_skeleton()
        return slot

    def _save_skeleton(self) -> None:
        save_skeleton(self.folder, self.project.skeleton)

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

    # ----------------------------------------------------------- notebook

    def _save_notebook(self) -> None:
        save_notebook(self.folder, self.project.notebook)

    def idea(self, idea_id: str) -> Idea | None:
        return next((i for i in self.project.notebook if i.id == idea_id), None)

    def new_idea(self, kind: str = "card", title: str = "", author: str = "", **values: object) -> Idea:
        """A new idea at the top of the Inbox. `values`: any Idea field (body, tags, colors,
        archetypes, sketch, links)."""
        import uuid
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        for key in ("tags", "archetypes"):
            if key in values:
                values[key] = [str(v).strip() for v in values[key] or [] if str(v).strip()]
        if "colors" in values:
            values["colors"] = "".join(c for c in "WUBRG" if c in str(values["colors"] or "").upper())
        idea = Idea.model_validate({"id": uuid.uuid4().hex[:10], "kind": kind, "title": title.strip(),
                                    "author": author, "created": now, "updated": now, **values})
        self.project.notebook.insert(0, idea)
        self._save_notebook()
        return idea

    def update_idea(self, idea: Idea, **values: object) -> None:
        from datetime import datetime
        for key, value in values.items():
            if key == "sketch" and not isinstance(value, IdeaSketch):
                value = IdeaSketch.model_validate(value or {})
            elif key in ("tags", "archetypes"):
                value = [str(v).strip() for v in value or [] if str(v).strip()]
            elif key == "colors":
                value = "".join(c for c in "WUBRG" if c in str(value or "").upper())
            setattr(idea, key, value)
        idea.updated = datetime.now().isoformat(timespec="seconds")
        self._save_notebook()

    def move_idea(self, idea: Idea, lane: str, index: int | None = None) -> None:
        """Put an idea in a lane, at a place among that lane's ideas (None: the end)."""
        ideas = [i for i in self.project.notebook if i is not idea]
        idea.lane = lane
        in_lane = [n for n, i in enumerate(ideas) if i.lane == lane]
        if index is None or index >= len(in_lane):
            at = (in_lane[-1] + 1) if in_lane else len(ideas)
        else:
            at = in_lane[max(0, index)]
        ideas.insert(at, idea)
        self.project.notebook = ideas
        self._save_notebook()

    def delete_idea(self, idea: Idea) -> None:
        self.project.notebook = [i for i in self.project.notebook if i is not idea]
        self._save_notebook()

    def ideas_for(self, kind: str, target_id: str) -> list[Idea]:
        """The ideas linked to a card, slot or mechanic."""
        return [i for i in self.project.notebook
                if any(link.kind == kind and link.id == target_id for link in i.links)]

    def _link(self, idea: Idea, kind: str, target_id: str) -> None:
        if not any(link.kind == kind and link.id == target_id for link in idea.links):
            idea.links.append(IdeaLink(kind=kind, id=target_id))
        if idea.lane != "used":
            self.move_idea(idea, "used", 0)
        else:
            self._save_notebook()

    def _drop_links(self, kind: str, target_id: str) -> None:
        changed = False
        for idea in self.project.notebook:
            kept = [link for link in idea.links if not (link.kind == kind and link.id == target_id)]
            if len(kept) != len(idea.links):
                idea.links, changed = kept, True
        if changed:
            self._save_notebook()

    def promote_to_card(self, idea: Idea, slot: Slot | None = None) -> Card:
        """A new card (status Idea) from an idea's sketch, archetypes and notes; in `slot`
        if given (which also sets its rarity). The idea links to it and goes to Used."""
        sketch = idea.sketch
        card = self.new_card(sketch.name or idea.title or "New Card")
        self.update(card, "status", Status.IDEA)
        for field in ("mana_cost", "type_line", "rules_text", "power", "toughness"):
            if getattr(sketch, field):
                self.update(card, field, getattr(sketch, field))
        if idea.archetypes:
            self.update(card, "archetypes", idea.archetypes)
        notes = "\n\n".join(x for x in (idea.title if sketch.name else "", idea.body) if x)
        if notes:
            self.update(card, "notes", notes)
        if slot is not None:
            if slot.rarity is not None:
                self.update(card, "rarity", slot.rarity)
            if slot.types and not sketch.type_line:
                self.update(card, "types", slot.types)
            if slot.archetypes and not idea.archetypes:
                self.update(card, "archetypes", list(slot.archetypes))
            self.assign(slot, card)
            self._link(idea, "slot", slot.id)
        self._link(idea, "card", card.id)
        return card

    def slots_for_idea(self, idea: Idea, n: int = 12) -> list[Slot]:
        """Empty skeleton slots for an idea, best first: its colors' (or its sketch's)
        column, then the sketch's type and its archetypes."""
        from . import skeleton as sk
        skeleton = self.project.skeleton
        if skeleton is None:
            return []
        probe = Card(id="_idea", faces=[Face(name=idea.sketch.name, mana_cost=idea.sketch.mana_cost,
                                              type_line=idea.sketch.type_line)])
        column = sk.canonical(idea.colors) if idea.colors else sk.column_of(probe, skeleton.columns)
        types = split_type_line(idea.sketch.type_line)[0].lower()

        def score(slot: Slot) -> tuple:
            return (slot.column == column,
                    bool(types and slot.types and slot.types.lower() in types),
                    bool(set(slot.archetypes) & set(idea.archetypes)),
                    len(set(slot.column) & set(column)))

        empty = [s for s in skeleton.slots if s.card_id is None]
        return sorted(empty, key=score, reverse=True)[:n]

    def promote_to_mechanic(self, idea: Idea) -> Mechanic:
        """A new mechanic named after the idea, its reminder text from the idea's notes."""
        mechanic = self.new_mechanic(idea.title or "New mechanic")
        if idea.body:
            self.update_mechanic(mechanic, reminder_text=idea.body)
        self._link(idea, "mechanic", mechanic.id)
        return mechanic

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
            elif key == "roles":
                from .health.roles import ROLES
                value = [r for r in ROLES if r in (value or [])]
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
        self._drop_links("mechanic", mechanic.id)
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

    def using_renderer(self, fn: Callable[[object], object], background: bool = False) -> object:
        """fn(renderer) under the renderer lock. `background` work (overview pictures,
        warming up) lets anything the user is waiting on go first."""
        renderer = self.renderer
        if background:
            with self._renderer_lock.background():
                return fn(renderer)
        with self._renderer_lock:
            return fn(renderer)

    def warm_up(self) -> None:
        """Get the slow first steps out of the way in the background, while the user looks
        at the overview: MSE's start and templates (about 2 s, outside the renderer lock, so
        the editor can work out a card's parts meanwhile), then the set-wide values every
        preview needs (a few seconds for a big set, once; background priority)."""
        if self._warming is not None:
            return

        def work() -> None:
            from ..render.mse_service import MSEBlocked, MSEError
            from .thumbnails import chunked_keys
            try:
                renderer = self.renderer
                mse = getattr(renderer, "mse", None)
                if mse is not None and not getattr(renderer, "blocked", ""):
                    try:
                        mse.warm()
                    except MSEBlocked as e:
                        renderer.blocked = str(e)
                    except MSEError:
                        pass
                chunked_keys(self, list(self.project.cards))
            except Exception:                       # only a head start: the real work reports errors
                pass
        self._warming = threading.Thread(target=work, name="warm-up", daemon=True)
        self._warming.start()

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

    def field_boxes(self, card: Card, face: int = 0) -> dict[str, tuple[float, float, float, float]]:
        """Where the face's editable parts are on the card (the editor's hotspots), as
        fractions of its size; see CardRenderer.field_boxes. Call it off the UI thread."""
        def find(renderer):
            self.refresh_edited(renderer)
            return renderer.field_boxes(card, face) if hasattr(renderer, "field_boxes") else {}
        return self.using_renderer(find)

    def _stylesheet(self, card: Card, face: int) -> str:
        """A key for the face's frame: its stylesheet plus any styling options it sets."""
        from ..mse.frames import frame_styling, stylesheet_package
        from ..mse.mapping import is_planeswalker
        frame = card.frame_for(face, self.project.info.default_frame)
        planeswalker = is_planeswalker(card.faces[face])
        return f"{stylesheet_package(frame, planeswalker=planeswalker)} {frame_styling(frame, planeswalker)}"

    @property
    def cache_folder(self) -> Path:
        """Where this set's card pictures are cached (outside the set folder)."""
        from .thumbnails import default_cache_dir
        return Path(self._thumbnail_dir or default_cache_dir(self.folder))

    @property
    def thumbnails(self):
        """Card pictures for the overview, made in the background (see thumbnails.py)."""
        if self._thumbnails is None:
            from .thumbnails import ThumbnailCache, ThumbnailWorker
            self._thumbnails = ThumbnailWorker(self, ThumbnailCache(self.cache_folder))
        return self._thumbnails

    def mse_problem(self) -> str:
        """Why Magic Set Editor can't draw the cards ("" when it can; see CardRenderer)."""
        return self.mse_status()[1]

    def mse_status(self) -> tuple[str, str]:
        """("ok" | "off" | "missing" | "blocked" | "failed", why): see CardRenderer.mse_status.
        May start MSE: call it off the UI thread."""
        return self.using_renderer(lambda r: r.mse_status() if hasattr(r, "mse_status") else ("off", ""))

    @property
    def mse_blocked(self) -> bool:
        """Windows blocked MSE (cheap: starts nothing, for the UI's timers)."""
        return bool(getattr(self._renderer, "blocked", ""))

    def retry_mse(self) -> tuple[str, str]:
        """Try MSE again after the user renewed Windows' trust; the new status."""
        return self.using_renderer(lambda r: r.retry_mse() if hasattr(r, "retry_mse") else ("off", ""))

    def mse_gui(self) -> Path | None:
        """MSE's windowed program (for renewing Windows' trust), if there is one."""
        return self.using_renderer(lambda r: r.gui_exe() if hasattr(r, "gui_exe") else None)

    @property
    def uses_builtin_renderer(self) -> bool:
        """True when our own renderer draws the cards: MSE is missing, or its last
        render failed (e.g. Windows blocked it)."""
        return self.using_renderer(lambda r: getattr(r, "mse", None) is None
                                   or getattr(r, "last_backend", "") == "builtin")

    def close(self) -> None:
        if self._thumbnails is not None:
            self._thumbnails.stop()
            self._thumbnails = None
        self.flush()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
