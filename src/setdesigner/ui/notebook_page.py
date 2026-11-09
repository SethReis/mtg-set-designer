"""The design notebook (rail: Notebook, /set?open=notebook): ideas on a board of lanes
(Inbox, Promising, Used, Parked), filtered by kind, tag, color and text. Clicking an idea
opens it on the right, where it can become a card, fill a skeleton slot or start a
mechanic (docs/notebook.md)."""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app.overview import COLOR_LABELS
from ..model import Card, Idea
from ..model.notebook import KINDS, LANES
from . import components as c
from .notebook_capture import capture_idea
from .widgets import responsive_grid

KIND_ICONS = {"card": "style", "mechanic": "auto_fix_high", "thought": "chat_bubble_outline",
              "problem": "report_problem"}
DROP_JS = "(e) => { e.preventDefault(); emit(e.dataTransfer.getData('text/plain')); }"


def idea_matches(idea: Idea, text: str) -> bool:
    """Every word of `text` is in the idea's title, notes, tags or sketch."""
    s = idea.sketch
    haystack = " ".join([idea.title, idea.body, *idea.tags, s.name, s.type_line, s.rules_text]).lower()
    return all(word in haystack for word in text.lower().split())


def notebook_panel(state, m: c.Modal, *, select_id: str | None = None,
                   open_card: Callable[[Card], None], open_mechanic: Callable[[str], None],
                   on_select: Callable[[str | None], None], on_change: Callable[[], None]) -> None:
    """Build the Notebook view into the modal `m`. `on_select` runs with the shown idea's
    id; `on_change` after ideas change (the rail's Inbox count)."""
    session = state.session
    project = session.project
    view = {"id": select_id if session.idea(select_id or "") else None,
            "kind": "", "tag": "", "color": "", "text": ""}

    def changed() -> None:
        board.refresh()
        on_change()

    def select(idea: Idea | None) -> None:
        view["id"] = idea.id if idea else None
        board.refresh()
        detail.refresh()
        on_select(view["id"])

    def shown() -> list[Idea]:
        out = []
        for idea in project.notebook:
            if view["kind"] and idea.kind != view["kind"]:
                continue
            if view["tag"] and view["tag"] not in idea.tags:
                continue
            if view["color"] and view["color"] not in idea.colors:
                continue
            if view["text"] and not idea_matches(idea, view["text"]):
                continue
            out.append(idea)
        return out

    def new() -> None:
        capture_idea(state, parent=m.body, on_saved=lambda idea: (changed(), select(idea)))

    # ---------------------------------------------------------------- drag and drop
    def dropped(lane: str, before: Idea | None, data) -> None:
        if not isinstance(data, str) or not data.startswith("idea:"):
            return
        idea = session.idea(data[5:])
        if idea is None or idea is before:
            return
        index = None
        if before is not None:
            in_lane = [i for i in project.notebook if i.lane == lane and i is not idea]
            index = in_lane.index(before)
        session.move_idea(idea, lane, index)
        changed()

    def drop_target(element: ui.element, lane: str, before: Idea | None = None) -> None:
        element.on("dragover", js_handler="(e) => e.preventDefault()")
        element.on("drop", lambda e, ln=lane, b=before: dropped(ln, b, e.args), js_handler=DROP_JS)

    # ---------------------------------------------------------------- board
    def tile(idea: Idea) -> None:
        element = ui.element("div").classes("ds-idea" + (" selected" if idea.id == view["id"] else "")) \
            .props('draggable="true"').mark(f"idea-{idea.id}")
        element.on("dragstart", js_handler=f"(e) => {{ e.stopPropagation(); "
                                           f"e.dataTransfer.setData('text/plain', 'idea:{idea.id}'); }}")
        element.on("click", lambda i=idea: select(i))
        drop_target(element, idea.lane, idea)
        with element:
            with ui.row().classes("items-center gap-2 no-wrap w-full"):
                ui.icon(KIND_ICONS[idea.kind]).classes("kind").tooltip(KINDS[idea.kind])
                ui.label(idea.title or idea.body[:60] or "(empty)").classes("title grow")
                if idea.colors:
                    c.pips(idea.colors)
            if idea.body and idea.title:
                ui.label(idea.body).classes("body")
            if idea.tags or idea.links or idea.author:
                with ui.row().classes("items-center gap-1 w-full"):
                    for tag in idea.tags:
                        ui.label(tag).classes("ds-tag")
                    for link in idea.links:
                        ui.label({"card": "→ card", "slot": "→ slot", "mechanic": "→ mechanic"}[link.kind]) \
                            .classes("ds-tag link")
                    ui.element("div").classes("grow")
                    if idea.author:
                        ui.label(idea.author).classes("faint text-xs")

    @ui.refreshable
    def board() -> None:
        ideas = shown()
        with ui.element("div").classes("ds-idea-board"):
            for lane, label in LANES.items():
                in_lane = [i for i in ideas if i.lane == lane]
                column = ui.element("div").classes("ds-idea-lane").mark(f"lane-{lane}")
                drop_target(column, lane)
                with column:
                    with ui.row().classes("ds-idea-lane-head items-baseline gap-2 no-wrap"):
                        ui.label(label).classes("name")
                        ui.label(str(len(in_lane))).classes("faint num")
                    for idea in in_lane:
                        tile(idea)
                    if not in_lane:
                        c.hint("Drop ideas here" if project.notebook else
                               ("Catch your first idea with New idea or Ctrl+Shift+N" if lane == "inbox" else ""))

    # ---------------------------------------------------------------- detail
    def go(link) -> None:
        if link.kind == "card" or link.kind == "slot":
            card = next((x for x in project.cards if x.id == link.id), None) if link.kind == "card" else \
                next((x for x in project.cards if project.skeleton and
                      (s := project.skeleton.slot_of(x.id)) and s.id == link.id), None)
            if card is not None:
                open_card(card)
        elif link.kind == "mechanic":
            open_mechanic(link.id)

    def link_label(link) -> str:
        if link.kind == "card":
            card = next((x for x in project.cards if x.id == link.id), None)
            return f"Card · {card.faces[0].name}" if card else "Card"
        if link.kind == "slot":
            return f"Slot · {link.id}"
        mechanic = next((x for x in project.mechanics if x.id == link.id), None)
        return f"Mechanic · {mechanic.name}" if mechanic else "Mechanic"

    def promote_card(idea: Idea, slot=None) -> None:
        card = session.promote_to_card(idea, slot)
        changed()
        open_card(card)

    def promote_mechanic(idea: Idea) -> None:
        mechanic = session.promote_to_mechanic(idea)
        changed()
        open_mechanic(mechanic.id)

    def slot_picker(idea: Idea) -> None:
        slots = session.slots_for_idea(idea)
        with c.modal("md", "Fill a slot", parent=m.body, persistent=False) as pick:
            c.hint("Empty slots, best fit first. The new card takes the slot's rarity.")
            with ui.column().classes("w-full gap-1 mt-2"):
                for slot in slots:
                    from ..app import skeleton as sk
                    with c.list_row(on_click=lambda s=slot: (pick.dialog.close(), promote_card(idea, s))):
                        ui.label(slot.id).classes("num font-medium w-20")
                        ui.label(sk.describe(slot, project) or "—").classes("grow truncate muted")
        pick.open()

    async def delete(idea: Idea) -> None:
        if await c.confirm(m.body, "Delete this idea?", idea.title or "") == "confirm":
            session.delete_idea(idea)
            select(None)
            changed()

    @ui.refreshable
    def detail() -> None:
        idea = session.idea(view["id"] or "")
        if idea is None:
            c.hint("Click an idea to see and edit it.").classes("p-4")
            return

        def save(**values) -> None:
            if any(getattr(idea, k) != v for k, v in values.items()):
                session.update_idea(idea, **values)
                board.refresh()

        def save_sketch(field: str, value: str) -> None:
            if getattr(idea.sketch, field) != value:
                session.update_idea(idea, sketch={**idea.sketch.model_dump(), field: value})
                board.refresh()

        with ui.column().classes("w-full gap-3 p-4"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.select(KINDS, value=idea.kind, label="Kind",
                          on_change=lambda e: (save(kind=e.value), detail.refresh())).classes("grow")
                c.button(icon="close", kind="icon", tooltip="Close", on_click=lambda: select(None))
            title = ui.input("Title", value=idea.title).classes("w-full").mark("idea-title")
            title.on("blur", lambda: save(title=title.value or ""))
            body = ui.textarea("Notes", value=idea.body).props("autogrow").classes("w-full")
            body.on("blur", lambda: save(body=body.value or ""))
            ui.input_chips("Tags", value=list(idea.tags), new_value_mode="add-unique",
                           on_change=lambda e: save(tags=list(e.value or []))).classes("w-full")
            with responsive_grid(140):
                ui.select({k: COLOR_LABELS[k] for k in "WUBRG"}, multiple=True, label="Colors",
                          value=list(idea.colors),
                          on_change=lambda e: save(colors="".join(k for k in "WUBRG" if k in (e.value or []))))\
                    .props("use-chips dense")
                ui.select({a.id: a.name for a in project.archetypes}, multiple=True, label="Archetypes",
                          value=[a for a in idea.archetypes if any(x.id == a for x in project.archetypes)],
                          on_change=lambda e: save(archetypes=list(e.value or []))).props("use-chips dense")
            if idea.kind == "card":
                ui.label("Rough card").classes("ds-form-h")
                with responsive_grid(140):
                    for field, label in (("name", "Name"), ("mana_cost", "Mana cost"),
                                         ("type_line", "Type line")):
                        box = ui.input(label, value=getattr(idea.sketch, field))
                        box.on("blur", lambda f=field, b=box: save_sketch(f, b.value or ""))
                rules = ui.textarea("Rules text", value=idea.sketch.rules_text).props("autogrow").classes("w-full")
                rules.on("blur", lambda: save_sketch("rules_text", rules.value or ""))
                with ui.row().classes("gap-3 no-wrap"):
                    for field, label in (("power", "Power"), ("toughness", "Toughness")):
                        box = ui.input(label, value=getattr(idea.sketch, field)).classes("w-24")
                        box.on("blur", lambda f=field, b=box: save_sketch(f, b.value or ""))
            if idea.links:
                ui.label("Became").classes("ds-form-h")
                with ui.row().classes("gap-2"):
                    for link in idea.links:
                        c.button(link_label(link), kind="secondary", on_click=lambda ln=link: go(ln)) \
                            .props("dense")
            with ui.row().classes("w-full items-center gap-2"):
                with c.button("Make it…", kind="primary", icon="arrow_forward").mark("promote"):
                    with ui.menu() as menu:
                        ui.menu_item("New card", on_click=lambda: promote_card(idea)).mark("promote-card")
                        item = ui.menu_item("Fill a skeleton slot…", on_click=lambda: slot_picker(idea)) \
                            .mark("promote-slot")
                        if project.skeleton is None:
                            item.props("disable")
                        ui.menu_item("New mechanic", on_click=lambda: promote_mechanic(idea)).mark("promote-mechanic")
                ui.element("div").classes("grow")
                if idea.author:
                    ui.label(f"by {idea.author}").classes("faint text-xs")
                c.button("Delete", kind="danger", icon="delete", on_click=lambda: delete(idea)).props("dense")

    # ---------------------------------------------------------------- layout
    def set_filter(**values) -> None:
        view.update(values)
        board.refresh()

    with ui.element("div").classes("ds-notebook"):
        with ui.row().classes("ds-notebook-bar items-end gap-3 w-full"):
            c.button("New idea", kind="primary", icon="lightbulb", on_click=new,
                     tooltip="New idea · Ctrl+Shift+N").mark("new-idea")
            ui.select({"": "All kinds", **KINDS}, value="", label="Kind",
                      on_change=lambda e: set_filter(kind=e.value or "")).classes("w-40")
            tags = sorted({t for i in project.notebook for t in i.tags})
            ui.select({"": "All tags", **{t: t for t in tags}}, value="", label="Tag",
                      on_change=lambda e: set_filter(tag=e.value or "")).classes("w-36")
            ui.select({"": "All colors", **{k: COLOR_LABELS[k] for k in "WUBRG"}}, value="", label="Color",
                      on_change=lambda e: set_filter(color=e.value or "")).classes("w-36")
            ui.input("Search", on_change=lambda e: set_filter(text=e.value or "")) \
                .props("clearable debounce=200").classes("w-48")
        with ui.element("div").classes("ds-notebook-main"):
            with ui.element("div").classes("ds-notebook-board"):
                board()
            with ui.element("div").classes("ds-notebook-detail"):
                detail()
