"""The Skeleton, a workspace modal: the set's planned slots (app/skeleton.py), as a board of
columns (colors, archetype color sets, colorless, land) by rarity, or as a table.

Empty slots show what they ask for; clicking a slot opens its popover (ui/slot_popover.py)
to describe it, create a card from it or assign one. Cards can be dragged onto slots, from
another slot (a move or swap) or from the "Outside the skeleton" strip. "Edit counts…"
generates the skeleton from a preset, or adjusts it in place later.
"""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app import skeleton as sk
from ..app.health.roles import ROLES
from ..model import Card
from ..model.skeleton import ANY
from . import components as c
from .slot_popover import slot_menu
from .widgets import card_name, number_label, served_url

RARITY_NAMES = {"common": "Common", "uncommon": "Uncommon", "rare": "Rare", "mythic": "Mythic", ANY: "Slots"}
DROP_JS = "(e) => { e.preventDefault(); emit(e.dataTransfer.getData('text/plain')); }"


def skeleton_panel(state, m: c.Modal, *, open_card: Callable[[Card], None],
                   on_change: Callable[[], None]) -> None:
    """Build the Skeleton view into the modal `m`. `on_change` runs after slots change (the
    workspace behind refreshes its targets and empty tiles)."""
    session = state.session
    project = session.project
    view = {"mode": "board", "group": "color", "empty_only": False, "column": "", "rarity": ""}

    def changed() -> None:
        body.refresh()
        summary.refresh()
        on_change()

    def card_by_id() -> dict[str, Card]:
        return {x.id: x for x in project.cards}

    # ---------------------------------------------------------------- drag and drop
    def drag_source(element: ui.element, card: Card) -> None:
        element.props('draggable="true"')
        element.on("dragstart", js_handler=f"(e) => e.dataTransfer.setData('text/plain', 'card:{card.id}')")

    def drop_target(element: ui.element, slot) -> None:
        element.on("dragover", js_handler="(e) => e.preventDefault()")
        element.on("drop", lambda e, s=slot: dropped(s, e.args), js_handler=DROP_JS)

    def dropped(slot, data) -> None:
        if not isinstance(data, str) or not data.startswith("card:"):
            return
        card = card_by_id().get(data[5:])
        if card is not None:
            session.assign(slot, card)
            changed()

    # ---------------------------------------------------------------- pieces
    def chip(slot, cards: dict[str, Card]) -> None:
        card = cards.get(slot.card_id) if slot.card_id else None
        element = ui.element("div").classes("ds-slot-chip " + ("filled" if card else "empty")) \
            .mark(f"slot-{slot.id}")
        with element:
            ui.label(slot.id).classes("id")
            if card is not None:
                path = session.thumbnails.get(card)
                if path is not None:
                    ui.element("img").props(f'src="{served_url(session.thumbnails.cache.folder, path)}" alt=""')
                ui.label(card_name(card)).classes("name")
            else:
                ui.label(sk.describe(slot, project) or "—").classes("desc")
            menu = slot_menu(session, slot, open_card=open_card, on_change=changed)
        element.on("click", menu.open)
        if card is not None:
            drag_source(element, card)
        drop_target(element, slot)

    def add_button(column: str, rarity: str) -> None:
        def add() -> None:
            session.add_slot(column, rarity)
            changed()
        c.button(icon="add", kind="icon", on_click=add, tooltip="Add a slot") \
            .props("size=xs").classes("ds-slot-add").mark(f"add-{column}-{rarity}")

    def board() -> None:
        skeleton = project.skeleton
        cards = card_by_id()
        columns = skeleton.columns
        grid = ui.element("div").classes("ds-skeleton-board") \
            .style(f"grid-template-columns: 96px repeat({len(columns)}, minmax(132px, 1fr))")
        with grid:
            ui.element("div")
            for column in columns:
                cell_slots = [s for s in skeleton.slots if s.column == column]
                full = sum(1 for s in cell_slots if s.card_id)
                with ui.element("div").classes("ds-board-head"):
                    ui.label(sk.column_label(column)).classes("name")
                    ui.label(f"{full} / {len(cell_slots)}").classes("num faint")
            if view["group"] == "archetype":
                rows = [(a.id, a.name) for a in project.archetypes] + [(None, "No archetype")]
                for archetype, name in rows:
                    in_row = [s for s in skeleton.slots if s.archetype == archetype]
                    if not in_row and archetype is not None:
                        continue
                    full = sum(1 for s in in_row if s.card_id)
                    with ui.element("div").classes("ds-board-band"):
                        ui.label(name)
                        ui.label(f"{full} / {len(in_row)}").classes("num faint")
                    for column in columns:
                        with ui.element("div").classes("ds-board-cell"):
                            for slot in [s for s in in_row if s.column == column]:
                                chip(slot, cards)
            else:
                rarities = sk.rarities_of(skeleton.preset)
                for rarity in rarities:
                    in_band = [s for s in skeleton.slots if (s.rarity.value if s.rarity else ANY) == rarity]
                    full = sum(1 for s in in_band if s.card_id)
                    with ui.element("div").classes("ds-board-band"):
                        ui.label(RARITY_NAMES[rarity])
                        ui.label(f"{full} / {len(in_band)}").classes("num faint")
                    for column in columns:
                        with ui.element("div").classes("ds-board-cell"):
                            for slot in sk.cell(skeleton, column, rarity):
                                chip(slot, cards)
                            add_button(column, rarity)

    def table() -> None:
        skeleton = project.skeleton
        cards = card_by_id()
        with ui.row().classes("w-full items-center gap-3 mb-2"):
            ui.switch("Empty only", value=view["empty_only"],
                      on_change=lambda e: (view.update(empty_only=e.value), body.refresh()))
            ui.select({"": "All columns", **{x: sk.column_label(x) for x in skeleton.columns}}, value=view["column"],
                      label="Column", on_change=lambda e: (view.update(column=e.value), body.refresh())) \
                .props("dense").classes("w-40")
            rarities = sk.rarities_of(skeleton.preset)
            if rarities != [ANY]:
                ui.select({"": "All rarities", **{r: RARITY_NAMES[r] for r in rarities}}, value=view["rarity"],
                          label="Rarity", on_change=lambda e: (view.update(rarity=e.value), body.refresh())) \
                    .props("dense").classes("w-40")
        slots = [s for s in skeleton.slots
                 if (not view["empty_only"] or not s.card_id)
                 and (not view["column"] or s.column == view["column"])
                 and (not view["rarity"] or (s.rarity and s.rarity.value == view["rarity"]))]
        roles = {"": "—", **{rid: r.label for rid, r in ROLES.items()}}
        archetypes = {"": "—", **{a.id: a.name for a in project.archetypes}}
        with ui.element("div").classes("ds-slot-table"):
            for heading in ("Slot", "Type", "MV", "Role", "Archetype", "Note", "Card"):
                ui.label(heading).classes("head")
            for slot in slots:
                ui.label(slot.id).classes("num")
                ui.input(value=slot.types, on_change=lambda e, s=slot: session.update_slot(s, types=e.value)) \
                    .props("dense borderless").mark(f"table-type-{slot.id}")
                ui.number(value=slot.mana_value, min=0, format="%d",
                          on_change=lambda e, s=slot: session.update_slot(s, mana_value=e.value)) \
                    .props("dense borderless")
                ui.select(roles, value=slot.role or "",
                          on_change=lambda e, s=slot: session.update_slot(s, role=e.value)).props("dense borderless")
                ui.select(archetypes, value=slot.archetype or "",
                          on_change=lambda e, s=slot: session.update_slot(s, archetype=e.value)) \
                    .props("dense borderless")
                ui.input(value=slot.note, on_change=lambda e, s=slot: session.update_slot(s, note=e.value)) \
                    .props("dense borderless").mark(f"table-note-{slot.id}")
                card = cards.get(slot.card_id) if slot.card_id else None
                with ui.element("div").classes("ds-slot-table-card").mark(f"table-card-{slot.id}") as holder:
                    ui.label(card_name(card) if card else "—").classes("truncate" + ("" if card else " faint"))
                    menu = slot_menu(session, slot, open_card=open_card, on_change=changed)
                holder.on("click", menu.open)

    def outside_strip() -> None:
        loose = sk.outside(project.skeleton, project.cards)
        with ui.element("div").classes("ds-outside"):
            ui.label(f"Outside the skeleton · {len(loose)}").classes("ds-label")
            if not loose:
                c.hint("Every card is in a slot.")
            with ui.element("div").classes("ds-outside-cards"):
                for card in loose:
                    element = ui.element("div").classes("ds-slot-chip filled loose").mark(f"loose-{card.id}")
                    with element:
                        ui.label(number_label(card)).classes("id")
                        ui.label(card_name(card)).classes("name")
                    element.on("dblclick", lambda x=card: open_card(x))
                    element.tooltip("Drag onto a slot · double-click to open")
                    drag_source(element, card)

    # ---------------------------------------------------------------- header
    @ui.refreshable
    def summary() -> None:
        skeleton = project.skeleton
        if skeleton is not None:
            full = sum(1 for s in skeleton.slots if s.card_id)
            ui.label(f"{full} of {len(skeleton.slots)} slots filled").classes("muted").mark("skeleton-summary")

    with m.actions:
        summary()
        ui.element("div").classes("ds-sep")
        c.segmented({"board": "Board", "table": "Table"}, view["mode"],
                    lambda e: (view.update(mode=e.value), body.refresh())).mark("skeleton-mode")
        c.segmented({"color": "By color", "archetype": "By archetype"}, view["group"],
                    lambda e: (view.update(group=e.value), body.refresh())).mark("skeleton-group")
        c.button("Edit counts…", kind="secondary", icon="tune", on_click=lambda: counts_dialog(adjusting=True)) \
            .props("dense").mark("skeleton-counts")
        with c.button(icon="more_horiz", kind="icon", tooltip="More"):
            with ui.menu().props("anchor='bottom right' self='top right'"):
                ui.menu_item("Delete the skeleton…", on_click=lambda: delete_skeleton()).classes("text-negative")

    async def delete_skeleton() -> None:
        if await c.confirm(m.body, "Delete the skeleton?",
                           "Its slots and notes go; the cards stay in the set.") == "confirm":
            session.delete_skeleton()
            changed()

    # ---------------------------------------------------------------- generating and adjusting
    def counts_dialog(adjusting: bool = False) -> None:
        skeleton = project.skeleton
        adjusting = adjusting and skeleton is not None
        state_ = {"preset": skeleton.preset if adjusting else "play_booster"}
        state_["columns"] = list(skeleton.columns) if adjusting else sk.default_columns(project)
        state_["counts"] = ({col: dict(r) for col, r in skeleton.counts.items()} if adjusting
                            else sk.default_counts(state_["preset"], state_["columns"]))

        def set_preset(value: str) -> None:
            state_["preset"] = value
            state_["counts"] = sk.default_counts(value, state_["columns"])
            grid_.refresh()

        def set_count(column: str, rarity: str, value) -> None:
            state_["counts"].setdefault(column, {})[rarity] = max(0, int(value or 0))
            totals_.refresh()

        def add_column(text: str) -> None:
            column = sk.canonical(text) if any(ch in "WUBRGwubrg" for ch in text) else text.strip().upper()
            if len(column) < 2 or column in state_["columns"]:
                ui.notify("Type a color set that isn't a column yet, e.g. RW or WUB", type="warning")
                return
            state_["columns"] = sorted([*state_["columns"], column], key=sk.column_order)
            state_["counts"][column] = {r: 0 for r in sk.rarities_of(state_["preset"])}
            grid_.refresh()

        def remove_column(column: str) -> None:
            state_["columns"].remove(column)
            state_["counts"].pop(column, None)
            grid_.refresh()

        async def apply() -> None:
            columns, counts = state_["columns"], state_["counts"]
            if not adjusting:
                left = session.create_skeleton(state_["preset"], columns, counts)
                dialog.close()
                changed()
                ui.notify(f"Skeleton made: {len(project.skeleton.slots)} slots"
                          + (f", {len(left)} cards outside it" if left else ""), type="positive")
                return
            blocked = session.adjust_skeleton(columns, counts)
            if blocked:
                names = ", ".join(s.id for s in blocked[:6]) + ("…" if len(blocked) > 6 else "")
                answer = await c.confirm(m.body, f"Remove {len(blocked)} filled slot{'s' * (len(blocked) != 1)}?",
                                         f"{names} hold cards. The cards stay in the set, outside the skeleton.",
                                         confirm_label="Remove them")
                if answer == "confirm":
                    session.adjust_skeleton(columns, counts, remove_filled=True)
            dialog.close()
            changed()

        with c.modal("lg", "Edit the skeleton's counts" if adjusting else "Generate a skeleton",
                     parent=m.body, footer=True, persistent=False) as dialog_modal:
            dialog = dialog_modal.dialog
            with ui.row().classes("w-full items-end gap-3"):
                ui.select({k: p.label for k, p in sk.PRESETS.items()}, value=state_["preset"], label="Preset",
                          on_change=lambda e: set_preset(e.value)).classes("w-56").props("dense") \
                    .mark("skeleton-preset").set_enabled(not adjusting)
                c.hint(sk.PRESETS[state_["preset"]].description if not adjusting else
                       "Adding keeps every slot; removing takes empty slots first and asks before filled ones.")
            c.hint("Multicolor columns follow your archetypes' colors. Add one for a color set no archetype covers.")

            @ui.refreshable
            def grid_() -> None:
                rarities = sk.rarities_of(state_["preset"])
                with ui.element("div").classes("ds-counts-table") \
                        .style(f"grid-template-columns: 96px repeat({len(state_['columns'])}, minmax(56px, 1fr)) 64px"):
                    ui.element("div")
                    for column in state_["columns"]:
                        with ui.row().classes("items-center no-wrap gap-0 head"):
                            ui.label(column).tooltip(sk.column_label(column))
                            if sk.is_multicolor(column):
                                c.button(icon="close", kind="icon", on_click=lambda col=column: remove_column(col),
                                         tooltip="Remove this column").props("size=xs")
                    ui.label("Total").classes("head")
                    for rarity in rarities:
                        ui.label(RARITY_NAMES[rarity]).classes("muted")
                        for column in state_["columns"]:
                            ui.number(value=state_["counts"].get(column, {}).get(rarity, 0), min=0, format="%d",
                                      on_change=lambda e, col=column, r=rarity: set_count(col, r, e.value)) \
                                .props("dense borderless").mark(f"count-{column}-{rarity}")
                        totals_(rarity)

            @ui.refreshable
            def totals_(rarity: str | None = None) -> None:
                if rarity is None:
                    return
                ui.label(str(sk.totals(state_["counts"]).get(rarity, 0))).classes("num")
            grid_()
            with ui.row().classes("items-center gap-2 mt-2"):
                new_column = ui.input(placeholder="RW, WUB…").props("dense outlined").classes("w-32")
                c.button("Add column", kind="ghost", icon="add",
                         on_click=lambda: (add_column(new_column.value or ""), new_column.set_value(""))) \
                    .props("dense").mark("add-column")
        with dialog_modal.footer:
            ui.space()
            c.button("Cancel", kind="ghost", on_click=dialog.close)
            c.button("Apply" if adjusting else "Generate", kind="primary", on_click=apply).mark("skeleton-apply")
        dialog_modal.open()

    # ---------------------------------------------------------------- body
    @ui.refreshable
    def body() -> None:
        if project.skeleton is None:
            c.empty_state("grid_view", "Plan the set's slots",
                          "Generate a grid from a preset (Play Booster, Classic draft or Cube), then describe "
                          "each slot and fill it with a card.",
                          action="Generate skeleton…", on_action=lambda: counts_dialog())
            return
        with ui.element("div").classes("ds-skeleton"):
            with ui.element("div").classes("ds-skeleton-main"):
                board() if view["mode"] == "board" else table()
            outside_strip()

    with ui.element("div").classes("ds-skeleton-host"):
        body()
