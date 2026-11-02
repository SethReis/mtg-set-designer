"""The archetype manager: a dialog to define the set's archetypes (saved as you type)."""
from __future__ import annotations

from nicegui import ui

from ..model import Archetype, Rarity
from . import components as c

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def archetype_manager(session, *, parent, on_close=None) -> c.Modal:
    """Open the dialog (an lg modal in `parent`). `on_close` runs after it closes (e.g. to
    refresh the workspace)."""

    def toggle_color(archetype: Archetype, color: str) -> None:
        colors = set(archetype.colors) ^ {color}
        session.update_archetype(archetype, colors="".join(x for x in "WUBRG" if x in colors))
        rows.refresh()

    def set_target(archetype: Archetype, rarity: Rarity, value) -> None:
        targets = {r.value: n for r, n in archetype.targets.items()}
        targets[rarity.value] = int(value or 0)
        session.update_archetype(archetype, targets=targets)

    def add() -> None:
        session.new_archetype(f"Archetype {len(session.project.archetypes) + 1}")
        rows.refresh()

    async def delete(archetype: Archetype) -> None:
        tagged = sum(archetype.id in card.archetypes for card in session.project.cards)
        if await c.confirm(m.body, f"Delete “{archetype.name}”?",
                           f"It is removed from {tagged} card{'s' * (tagged != 1)}." if tagged else "") \
                == "confirm":
            session.delete_archetype(archetype)
            rows.refresh()

    with c.modal("lg", "Archetypes", parent=parent, footer=True, persistent=False,
                 on_close=on_close) as m:
        c.hint("Draft archetypes or any groups you plan around. Tag cards with them in the "
               "card editor; targets are how many cards you want of each rarity.")

        @ui.refreshable
        def rows() -> None:
            if not session.project.archetypes:
                c.empty_state("hub", "No archetypes yet", "Two-color draft archetypes are the usual start.")
            for archetype in session.project.archetypes:
                tagged = sum(archetype.id in card.archetypes for card in session.project.cards)
                with ui.element("div").classes("ds-section w-full mt-3 flex flex-col gap-2"):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.input("Name", value=archetype.name,
                                 on_change=lambda e, a=archetype: session.update_archetype(a, name=e.value)) \
                            .classes("w-48")
                        for color, name in COLOR_NAMES.items():
                            on = color in archetype.colors
                            with ui.button(on_click=lambda a=archetype, col=color: toggle_color(a, col)) \
                                    .props("flat round dense").classes("ds-color-toggle" + (" on" if on else "")) \
                                    .tooltip(name):
                                c.mana_cost(f"{{{color}}}")
                        ui.label(f"{tagged} card{'s' * (tagged != 1)}").classes("muted grow")
                        c.button(icon="delete", kind="icon", on_click=lambda a=archetype: delete(a),
                                 tooltip="Delete archetype")
                    ui.input("Description", value=archetype.description,
                             on_change=lambda e, a=archetype: session.update_archetype(a, description=e.value)) \
                        .classes("w-full")
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Targets").classes("muted")
                        for rarity in Rarity:
                            ui.number(rarity.value.title(), value=archetype.targets.get(rarity), min=0,
                                      format="%d",
                                      on_change=lambda e, a=archetype, r=rarity: set_target(a, r, e.value)) \
                                .props("dense").classes("w-24")
        rows()
    with m.footer:
        c.button("Add archetype", kind="secondary", icon="add", on_click=add)
        ui.space()
        c.button("Done", kind="primary", on_click=m.close)
    m.open()
    return m
