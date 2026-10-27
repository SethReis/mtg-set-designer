"""The archetype manager: a dialog to define the set's archetypes (saved as you type)."""
from __future__ import annotations

from nicegui import ui

from ..model import Archetype, Rarity
from .widgets import COLOR_PIPS

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def archetype_manager(session, on_close=None) -> None:
    """Open the dialog. `on_close` runs after it closes (e.g. to refresh the overview)."""

    def toggle_color(archetype: Archetype, color: str) -> None:
        colors = set(archetype.colors) ^ {color}
        session.update_archetype(archetype, colors="".join(c for c in "WUBRG" if c in colors))
        rows.refresh()

    def set_target(archetype: Archetype, rarity: Rarity, value) -> None:
        targets = {r.value: n for r, n in archetype.targets.items()}
        targets[rarity.value] = int(value or 0)
        session.update_archetype(archetype, targets=targets)

    def add() -> None:
        session.new_archetype(f"Archetype {len(session.project.archetypes) + 1}")
        rows.refresh()

    async def delete(archetype: Archetype) -> None:
        tagged = sum(archetype.id in c.archetypes for c in session.project.cards)
        with ui.dialog() as confirm, ui.card():
            ui.label(f"Delete “{archetype.name}”?"
                     + (f" It is removed from {tagged} card{'s' * (tagged != 1)}." if tagged else ""))
            with ui.row():
                ui.button("Delete", on_click=lambda: confirm.submit(True)).props("color=negative")
                ui.button("Cancel", on_click=lambda: confirm.submit(False)).props("flat")
        if await confirm:
            session.delete_archetype(archetype)
            rows.refresh()

    with ui.dialog() as dialog, ui.card().classes("w-[900px] max-w-[95vw]"):
        ui.label("Archetypes").classes("text-xl font-semibold")
        ui.label("Draft archetypes or any groups you plan around. Tag cards with them in the "
                 "card editor; targets are how many cards you want of each rarity.") \
            .classes("text-sm text-gray-500")

        @ui.refreshable
        def rows() -> None:
            if not session.project.archetypes:
                ui.label("No archetypes yet.").classes("text-gray-500 my-2")
            for archetype in session.project.archetypes:
                tagged = sum(archetype.id in c.archetypes for c in session.project.cards)
                with ui.card().props("flat bordered").classes("w-full"):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.input("Name", value=archetype.name,
                                 on_change=lambda e, a=archetype: session.update_archetype(a, name=e.value)) \
                            .classes("w-48")
                        for color, name in COLOR_NAMES.items():
                            on = color in archetype.colors
                            ui.button(color, on_click=lambda a=archetype, c=color: toggle_color(a, c)) \
                                .props("dense round flat size=sm text-color=black").tooltip(name) \
                                .style(f"background:{COLOR_PIPS[color] if on else '#eee'};"
                                       f"opacity:{1 if on else 0.5};"
                                       + ("color:white !important" if on and color in "UBRG" else ""))
                        ui.label(f"{tagged} card{'s' * (tagged != 1)}").classes("text-sm text-gray-500 grow")
                        ui.button(icon="delete", on_click=lambda a=archetype: delete(a)) \
                            .props("flat round dense").tooltip("Delete archetype")
                    ui.input("Description", value=archetype.description,
                             on_change=lambda e, a=archetype: session.update_archetype(a, description=e.value)) \
                        .classes("w-full")
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Targets").classes("text-sm text-gray-500")
                        for rarity in Rarity:
                            ui.number(rarity.value.title(), value=archetype.targets.get(rarity), min=0,
                                      format="%d",
                                      on_change=lambda e, a=archetype, r=rarity: set_target(a, r, e.value)) \
                                .props("dense").classes("w-24")
        rows()
        with ui.row().classes("w-full"):
            ui.button("Add archetype", icon="add", on_click=add).props("flat no-caps")
            ui.space()
            ui.button("Done", on_click=dialog.close).props("color=primary")

    dialog.on("hide", lambda: on_close and on_close())
    dialog.open()
