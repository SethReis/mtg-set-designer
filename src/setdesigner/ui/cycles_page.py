"""The Cycles page: define a cycle (colors, shared template, per-member tweaks), generate
its placeholder cards, and keep them in step with the template.

Left: the cycles. Right: the selected one. Fields save when you leave them. Once cards
exist they are the truth: the table shows them, and template changes are offered to the
members that still follow the template (see app/cycles.py).
"""
from __future__ import annotations

from nicegui import ui

from ..app.cycles import (ALL_COMBINATIONS, GROUP_NAMES, GROUPINGS, member_fields, render, status,
                          template_change_plan)
from ..model import Cycle, CycleTemplate, Rarity
from .widgets import COLOR_PIPS, number_label

FIELD_LABELS = {"name": "Name", "mana_cost": "Mana cost", "type_line": "Type line",
                "rules_text": "Rules text", "flavor_text": "Flavor text", "power": "Power",
                "toughness": "Toughness", "rarity": "Rarity", "frame": "Frame"}
TABLE_FIELDS = ("name", "mana_cost", "type_line", "rules_text")
TOKEN_HELP = ("Tokens: {c} mana symbols ({c1} {c2} … one each) · {color} / {Color} color names · "
              "{basic} basic land types ({basic1} …) · {group} Azorius, Esper… · {n} member number. "
              "Uppercase {W} {2} {T} stay symbols.")


def combo_label(colors: str) -> str:
    return f"{colors or 'C'} · {GROUP_NAMES.get(colors, colors)}"


def pips(colors: str) -> None:
    with ui.row().classes("items-center gap-0.5 no-wrap"):
        for c in colors or "":
            ui.element("span").style(f"width:10px;height:10px;border-radius:50%;flex:none;"
                                     f"background:{COLOR_PIPS[c]};border:1px solid #888")
        if not colors:
            ui.element("span").style("width:10px;height:10px;border-radius:50%;background:#ccc;"
                                     "border:1px solid #888")


def register(state) -> None:

    @ui.page("/set/cycles")
    def cycles_page(cycle: str = "") -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        project = session.project
        first = project.cycles[0].id if project.cycles else None
        view = {"id": cycle if any(c.id == cycle for c in project.cycles) else first}

        def selected() -> Cycle | None:
            return next((c for c in project.cycles if c.id == view["id"]), None)

        def select(c: Cycle | None) -> None:
            view["id"] = c.id if c else None
            cycle_list.refresh()
            detail.refresh()

        def new() -> None:
            select(session.new_cycle())

        # ---------------------------------------------------------------- definition
        def definition(c: Cycle) -> None:
            def save(**values) -> None:
                if any(getattr(c, k) != v for k, v in values.items()):
                    session.update_cycle(c, **values)
                    cycle_list.refresh()

            with ui.column().classes("w-full gap-2 pr-4").style("max-width:1000px"):
                with ui.element("div").classes("w-full") \
                        .style("display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px"):
                    name = ui.input("Cycle name", value=c.name)
                    name.on("blur", lambda: save(name=name.value.strip() or c.name))
                    ui.select({k: label for k, (label, _) in GROUPINGS.items()}, value=c.grouping,
                              label="Colors", on_change=lambda e: regroup(c, e.value))
                    if c.grouping == "numbered":
                        count = ui.number("How many cards", value=len(c.members), min=1, max=30, format="%d")
                        count.on("blur", lambda: regroup(c, "numbered", count=int(count.value or 1)))
                if c.grouping == "custom":
                    ui.select({k: combo_label(k) for k in ALL_COMBINATIONS}, multiple=True,
                              value=[m.colors for m in c.members], label="Color combinations",
                              on_change=lambda e: regroup(c, "custom", custom=list(e.value or []))) \
                        .props("use-chips").classes("w-full")
                notes = ui.textarea("Notes", value=c.notes).props("autogrow").classes("w-full")
                notes.on("blur", lambda: save(notes=notes.value))
                template_editor(c)
                ui.separator().classes("my-2")
                members_table(c)
                ui.button("Delete cycle", icon="delete", on_click=lambda: delete(c)) \
                    .props("flat dense no-caps color=negative").classes("self-start mt-2")

        def regroup(c: Cycle, grouping: str, custom: list[str] | None = None, count: int = 5) -> None:
            if grouping == "custom" and custom is None:
                custom = [m.colors for m in c.members]
            session.set_cycle_grouping(c, grouping, custom, count)
            cycle_list.refresh()
            detail.refresh()

        # ---------------------------------------------------------------- template
        def template_editor(c: Cycle) -> None:
            fields = {}

            def current() -> CycleTemplate:
                values = {k: (f.value or "") for k, f in fields.items()}
                return CycleTemplate(**values, tag_archetypes=bool(tag.value))

            ui.label("Shared template").classes("text-sm font-semibold mt-2")
            ui.label(TOKEN_HELP).classes("text-xs text-gray-500")
            with ui.element("div").classes("w-full") \
                    .style("display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px"):
                for key in ("name", "mana_cost", "type_line"):
                    fields[key] = ui.input(FIELD_LABELS[key], value=getattr(c.template, key))
                fields["rarity"] = ui.select({r.value: r.value.title() for r in Rarity},
                                             value=c.template.rarity or "common", label="Rarity")
                from .app import FRAME_LABELS
                fields["frame"] = ui.select({"": "Set default", **FRAME_LABELS}, value=c.template.frame,
                                            label="Frame")
                fields["power"] = ui.input("Power", value=c.template.power)
                fields["toughness"] = ui.input("Toughness", value=c.template.toughness)
            fields["rules_text"] = ui.textarea("Rules text", value=c.template.rules_text) \
                .props("autogrow").classes("w-full")
            fields["flavor_text"] = ui.textarea("Flavor text", value=c.template.flavor_text) \
                .props("autogrow").classes("w-full")
            tag = ui.checkbox("Tag each card with the archetype of its colors (signposts)",
                              value=c.template.tag_archetypes)
            for key, f in fields.items():
                if key in ("rarity", "frame"):
                    f.on_value_change(lambda _: apply_template(c, current()))
                else:
                    f.on("blur", lambda: apply_template(c, current()))
            tag.on_value_change(lambda _: apply_template(c, current()))

        async def apply_template(c: Cycle, new: CycleTemplate) -> None:
            if new == c.template:
                return
            plan = template_change_plan(c, project, new)
            update = False
            if plan.changes:
                update = await confirm(c, plan)
                if update is None:
                    detail.refresh()                        # put the fields back
                    return
            done = session.update_cycle(c, update_cards=bool(update), template=new)
            if done:
                ui.notify(f"Updated {len(done)} card{'s' * (len(done) != 1)}", type="positive")
            detail.refresh()

        async def confirm(c: Cycle, plan) -> bool | None:
            with view["dialogs"], ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-[95vw]"):
                ui.label(f"Change “{c.name}”").classes("text-lg font-semibold")
                n = len(plan.changes)
                ui.label(f"{n} card{'s' * (n != 1)} still follow the template. Update them?") \
                    .classes("text-sm")
                if plan.kept:
                    ui.label(f"{len(plan.kept)} card(s) have fields you edited; those fields stay.") \
                        .classes("text-sm text-amber-800")
                for change in plan.changes[:5]:
                    with ui.column().classes("gap-0 w-full border rounded p-2"):
                        ui.label(change.card.faces[0].name).classes("text-xs text-gray-500")
                        for name, (before, after) in change.fields.items():
                            ui.label(f"{FIELD_LABELS[name]}:").classes("text-xs text-gray-500")
                            ui.label(before).classes("text-sm line-through text-gray-500 whitespace-pre-line")
                            ui.label(after).classes("text-sm whitespace-pre-line")
                if n > 5:
                    ui.label(f"… and {n - 5} more").classes("text-xs text-gray-500")
                with ui.row():
                    ui.button(f"Update {n} card{'s' * (n != 1)}", on_click=lambda: dialog.submit(True)) \
                        .props("color=primary")
                    ui.button("Keep card text", on_click=lambda: dialog.submit(False)).props("flat")
                    ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            return await dialog

        # ---------------------------------------------------------------- members
        def members_table(c: Cycle) -> None:
            states = status(c, project)
            missing = [st for st in states if st.card is None]
            with ui.row().classes("w-full items-center"):
                ui.label(f"Members · {len(states) - len(missing)} of {len(states)} made") \
                    .classes("text-base font-semibold")
                ui.space()
                if missing:
                    ui.button(f"Create {len(missing)} card{'s' * (len(missing) != 1)}", icon="add",
                              on_click=lambda: generate(c)).props("color=primary no-caps")
            ui.label("Before a card exists you can give a member its own text (it overrides the template "
                     "for that member). Afterwards, edit the card itself.").classes("text-xs text-gray-500")
            with ui.element("div").classes("w-full") \
                    .style("display:grid;grid-template-columns:70px 1.2fr 0.6fr 1fr 2fr 130px;gap:6px;"
                           "align-items:start"):
                for header in ("Colors", "Name", "Cost", "Type", "Rules text", ""):
                    ui.label(header).classes("text-xs text-gray-500 font-semibold")
                for st in states:
                    member, index = st.member, st.n - 1
                    with ui.column().classes("gap-0 pt-2"):
                        pips(member.colors)
                        ui.label(GROUP_NAMES.get(member.colors, "") if member.colors else f"#{st.n}") \
                            .classes("text-xs text-gray-500")
                    if st.card is None:
                        fields = member_fields(c, member, st.n)
                        for key in TABLE_FIELDS:
                            own = key in member.overrides
                            box = (ui.textarea if key == "rules_text" else ui.input)(value=fields[key]) \
                                .props("dense autogrow" if key == "rules_text" else "dense") \
                                .classes("w-full" + (" bg-amber-50" if own else ""))
                            box.on("blur", lambda e=None, k=key, b=box, i=index, m=member:
                                   override(c, i, m, k, b.value))
                        with ui.column().classes("gap-1 pt-1"):
                            ui.badge("Missing" if member.card_id is None and states_made(states) else "Not made",
                                     color="amber-2" if states_made(states) else "grey-3",
                                     text_color="amber-10" if states_made(states) else "grey-8")
                            if member.overrides:
                                ui.button("Use template", on_click=lambda i=index: reset(c, i)) \
                                    .props("flat dense no-caps size=sm")
                    else:
                        card = st.card
                        face = card.faces[0]
                        for key in TABLE_FIELDS:
                            text = face.rules_text.split("\n")[0] if key == "rules_text" else getattr(face, key)
                            ui.label(text or "—").classes("text-sm pt-2" + (" text-amber-800" if key in st.edited
                                                                              else ""))
                        with ui.column().classes("gap-1 pt-1"):
                            ui.button(f"{number_label(card)} · open", on_click=lambda cd=card:
                                      ui.navigate.to(f"/set/card/{cd.id}")).props("flat dense no-caps size=sm")
                            if st.edited:
                                ui.badge("Edited: " + ", ".join(FIELD_LABELS[f].lower() for f in st.edited),
                                         color="amber-2", text_color="amber-10").classes("whitespace-normal")

        def states_made(states) -> bool:
            return any(st.card is not None for st in states)

        def override(c: Cycle, index: int, member, key: str, value: str) -> None:
            template_value = render(getattr(c.template, key), member.colors, index + 1)
            current = member.overrides.get(key)
            new = None if value == template_value else value
            if new != current:
                session.set_member_override(c, index, key, new)
                detail.refresh()

        def reset(c: Cycle, index: int) -> None:
            for key in list(c.members[index].overrides):
                session.set_member_override(c, index, key, None)
            detail.refresh()

        def generate(c: Cycle) -> None:
            made = session.generate_cycle(c)
            ui.notify(f"Created {len(made)} card{'s' * (len(made) != 1)}", type="positive")
            cycle_list.refresh()
            detail.refresh()

        async def delete(c: Cycle) -> None:
            with view["dialogs"], ui.dialog() as dialog, ui.card():
                ui.label(f"Delete the cycle “{c.name}”? Its cards stay in the set; they're just no "
                         "longer linked to it.")
                with ui.row():
                    ui.button("Delete", on_click=lambda: dialog.submit(True)).props("color=negative")
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            if await dialog:
                session.delete_cycle(c)
                select(project.cycles[0] if project.cycles else None)

        # ---------------------------------------------------------------- page
        # dialogs live here: the part of the page that opened one may be rebuilt meanwhile
        view["dialogs"] = ui.element("div")
        with ui.header().classes("items-center bg-slate-800 py-2"):
            ui.button(icon="arrow_back", on_click=lambda: (session.flush(), ui.navigate.to("/set"))) \
                .props("flat round color=white").tooltip("Back to the set overview").mark("back")
            ui.label("Cycles").classes("text-lg font-semibold")
            ui.label(project.info.name).classes("text-sm opacity-70")

        ui.query(".q-page").classes("column")
        ui.query(".nicegui-content").classes("grow h-0 min-h-0")
        with ui.row().classes("w-full h-full no-wrap gap-6 items-start"):
            with ui.column().classes("w-72 shrink-0 h-full gap-2"):
                ui.button("New cycle", icon="add", on_click=new).props("flat no-caps")

                @ui.refreshable
                def cycle_list() -> None:
                    with ui.scroll_area().classes("w-full grow border rounded"):
                        if not project.cycles:
                            ui.label("No cycles yet.").classes("text-gray-500 m-2")
                        for c in project.cycles:
                            made = sum(1 for st in status(c, project) if st.card is not None)
                            active = c.id == view["id"]
                            with ui.row().classes("w-full items-center no-wrap gap-2 px-2 py-1 rounded "
                                                  "cursor-pointer " + ("bg-blue-100" if active
                                                                       else "hover:bg-gray-100")) \
                                    .on("click", lambda cy=c: select(cy)):
                                with ui.column().classes("grow gap-0"):
                                    ui.label(c.name or "(no name)").classes("truncate font-medium")
                                    ui.label(GROUPINGS[c.grouping][0]).classes("text-xs text-gray-500")
                                ui.label(f"{made}/{len(c.members)}").classes("text-xs text-gray-500")
                cycle_list()

            with ui.scroll_area().classes("grow h-full"):
                @ui.refreshable
                def detail() -> None:
                    c = selected()
                    if c is None:
                        ui.label("Add a cycle with “New cycle”.").classes("text-gray-500 m-4")
                        return
                    definition(c)
                detail()
