"""A skeleton slot's popover, shared by the Skeleton view and the overview's empty tiles.

    menu = slot_menu(session, slot, open_card=..., on_change=...)   # inside a chip or tile

It edits what the slot asks for (type, mana value, role, archetype, note) and fills it:
an empty slot offers "Create card from this slot" and the cards outside the skeleton that
fit it best (app/skeleton.suggest), plus a search over the rest; a filled one opens or
unassigns its card. Built when it opens (current values), cleared when it closes.
"""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app import skeleton as sk
from ..app.health.roles import ROLES
from ..model import Card, Slot
from . import components as c
from .widgets import card_name, number_label


def slot_title(slot: Slot) -> str:
    rarity = "" if slot.rarity is None else f" {slot.rarity.value}"
    return f"{slot.id} · {sk.column_label(slot.column)}{rarity}"


def slot_menu(session, slot: Slot, *, open_card: Callable[[Card], None],
              on_change: Callable[[], None]) -> ui.menu:
    """A popover for `slot`, anchored to the element it's created in (it opens on click)."""
    menu = ui.menu().props("anchor='bottom left' self='top left' :offset='[0, 6]'").classes("ds-slot-menu")
    changed = {"any": False}

    def toggled(e) -> None:
        menu.clear()
        if e.value:
            with menu:
                editor()
        elif changed["any"] and not menu.is_deleted:
            changed["any"] = False
            on_change()
    menu.on_value_change(toggled)

    def update(**values) -> None:
        session.update_slot(slot, **values)
        changed["any"] = True

    def fill(card: Card | None) -> None:
        session.assign(slot, card)
        changed["any"] = True
        menu.close()

    def create() -> None:
        card = session.new_card_from_slot(slot)
        changed["any"] = False                  # the editor replaces this view: no refresh
        open_card(card)                         # first: closing clears the context we're in
        menu.close()

    def add_idea() -> None:
        """A notebook idea for this slot: its colors, type and archetype, linked to it."""
        from .app import STATE
        from .notebook_capture import capture_idea
        menu.close()
        capture_idea(STATE, parent=menu.client.layout, prefill={
            "colors": "".join(x for x in slot.column if x in "WUBRG"),
            "archetypes": list(slot.archetypes),
            "sketch": {"type_line": slot.types}, "links": [{"kind": "slot", "id": slot.id}]})

    def editor() -> None:
        project = session.project
        with ui.element("div").classes("ds-part-editor").mark(f"slot-editor-{slot.id}"):
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                ui.label(slot_title(slot)).classes("ds-part-title grow")
                if slot.cycle:
                    c.badge("cycle", "info").tooltip("Placed by a cycle")
            card = next((x for x in project.cards if x.id == slot.card_id), None)
            if card is not None:
                with ui.row().classes("w-full items-center no-wrap gap-2 ds-slot-card"):
                    ui.label(number_label(card)).classes("faint num text-xs")
                    ui.label(card_name(card)).classes("grow truncate")
                    c.button("Open", kind="ghost", icon="edit",
                             on_click=lambda: (open_card(card), menu.close())).props("dense")
                    c.button("Unassign", kind="ghost", on_click=lambda: fill(None)).props("dense") \
                        .mark("slot-unassign")
            else:
                with ui.row().classes("items-center gap-2"):
                    c.button("Create card from this slot", kind="primary", icon="add", on_click=create) \
                        .props("dense").mark("slot-create")
                    c.button("Add idea", kind="ghost", icon="lightbulb", on_click=add_idea) \
                        .props("dense").mark("slot-idea").tooltip("A notebook idea for this slot")
            ui.label("What it asks for").classes("ds-label mt-2")
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.input("Type", value=slot.types, placeholder="Creature",
                         on_change=lambda e: update(types=e.value)).props("dense outlined").classes("grow")
                ui.number("Mana value", value=slot.mana_value, min=0, format="%d",
                          on_change=lambda e: update(mana_value=e.value)).props("dense outlined").classes("w-28")
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.select({"": "Any role", **{rid: r.label for rid, r in ROLES.items()}}, value=slot.role or "",
                          label="Role", on_change=lambda e: update(role=e.value)) \
                    .props("dense outlined").classes("grow")
                ui.select({a.id: a.name for a in project.archetypes}, multiple=True,
                          value=sk.slot_archetypes(slot, project), label="Archetypes",
                          on_change=lambda e: update(archetypes=e.value)) \
                    .props("dense outlined use-chips").classes("grow").mark(f"slot-archetypes-{slot.id}")
            ui.textarea("Note", value=slot.note, placeholder="2-drop flyer for the WU deck",
                        on_change=lambda e: update(note=e.value)).props("autogrow outlined").classes("w-full")
            if card is None:
                assign_section()
            with ui.row().classes("w-full justify-end mt-1"):
                c.button("Delete slot", kind="danger", icon="delete",
                         on_click=lambda: (session.delete_slot(slot), changed.update(any=True), menu.close())) \
                    .props("dense").mark("slot-delete")

    def assign_section() -> None:
        project = session.project
        skeleton = project.skeleton
        suggestions = sk.suggest(skeleton, slot, project)
        ui.label("Assign a card").classes("ds-label mt-2")
        if suggestions:
            with ui.element("div").classes("ds-slot-suggestions"):
                for card in suggestions:
                    c.button(card_name(card), kind="secondary", on_click=lambda x=card: fill(x)) \
                        .props("dense no-caps").mark(f"suggest-{card.id}")
        else:
            c.hint("No card outside the skeleton fits this slot.")
        loose = sk.outside(skeleton, project.cards)
        if loose:
            options = {x.id: f"{number_label(x)} · {card_name(x)}" for x in loose}
            ui.select(options, label="Any card outside the skeleton", with_input=True,
                      on_change=lambda e: e.value and fill(next(x for x in loose if x.id == e.value))) \
                .props("dense outlined").classes("w-full")

    return menu
