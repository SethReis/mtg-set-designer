"""Cycles, a workspace modal: define a cycle (colors, shared template, per-member tweaks), generate
its placeholder cards, and keep them in step with the template.

Left: the cycles. Right: the selected one. Fields save when you leave them. Once cards
exist they are the truth: the table shows them, and template changes are offered to the
members that still follow the template (see app/cycles.py).
"""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app.cycles import (ALL_COMBINATIONS, GROUP_NAMES, GROUPINGS, member_fields, render, status,
                          template_change_plan)
from ..model import Card, Cycle, CycleTemplate, Rarity
from . import components as ds
from .mechanics_page import changes_list
from .widgets import number_label, responsive_grid

FIELD_LABELS = {"name": "Name", "mana_cost": "Mana cost", "type_line": "Type line",
                "rules_text": "Rules text", "flavor_text": "Flavor text", "power": "Power",
                "toughness": "Toughness", "rarity": "Rarity", "frame": "Frame"}
TABLE_FIELDS = ("name", "mana_cost", "type_line", "rules_text")
TOKEN_HELP = ("Tokens: {c} mana symbols ({c1} {c2} … one each) · {color} / {Color} color names · "
              "{basic} basic land types ({basic1} …) · {group} Azorius, Esper… · {n} member number. "
              "Uppercase {W} {2} {T} stay symbols.")


def combo_label(colors: str) -> str:
    return f"{colors or 'C'} · {GROUP_NAMES.get(colors, colors)}"


def cycles_panel(state, m: ds.Modal, *, select_id: str | None = None,
                 open_card: Callable[[Card], None], on_select: Callable[[str | None], None]) -> None:
    """Build the Cycles workspace into the modal `m`: the list and the selected cycle.
    `on_select` runs with the shown cycle's id."""
    session = state.session
    project = session.project
    first = project.cycles[0].id if project.cycles else None
    view = {"id": select_id if any(x.id == select_id for x in project.cycles) else first,
            "dialogs": m.body}

    def selected() -> Cycle | None:
        return next((c for c in project.cycles if c.id == view["id"]), None)

    def select(c: Cycle | None) -> None:
        view["id"] = c.id if c else None
        cycle_list.refresh()
        detail.refresh()
        on_select(view["id"])

    def new() -> None:
        select(session.new_cycle())

    # ---------------------------------------------------------------- definition
    def definition(c: Cycle) -> None:
        def save(**values) -> None:
            if any(getattr(c, k) != v for k, v in values.items()):
                session.update_cycle(c, **values)
                cycle_list.refresh()

        with ui.column().classes("w-full gap-2"):
            with responsive_grid(220):
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
            members_table(c)
            ds.button("Delete cycle", kind="danger", icon="delete", on_click=lambda: delete(c)) \
                .props("dense").classes("self-start mt-2")

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

        ui.label("Shared template").classes("ds-form-h")
        ds.hint(TOKEN_HELP)
        with responsive_grid(200):
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
        """True: update the cards; False: keep their text; None: cancel."""
        def details() -> None:
            if plan.kept:
                ds.status(f"{len(plan.kept)} card(s) have fields you edited; those fields stay.",
                          "warning").classes("whitespace-normal")
            changes_list([(f"{x.card.faces[0].name} · {FIELD_LABELS[name]}", before, after)
                          for x in plan.changes for name, (before, after) in x.fields.items()])
        n = len(plan.changes)
        choice = await ds.confirm(view["dialogs"], f"Change “{c.name}”",
                                  f"{n} card{'s' * (n != 1)} still follow the template. Update them?",
                                  confirm_label=f"Update {n} card{'s' * (n != 1)}", kind="primary",
                                  extra="Keep card text", details=details)
        return {"confirm": True, "extra": False}.get(choice)

    # ---------------------------------------------------------------- members
    def members_table(c: Cycle) -> None:
        states = status(c, project)
        missing = [st for st in states if st.card is None]
        made = states_made(states)
        with ui.row().classes("w-full items-center mt-4"):
            ui.label(f"Members · {len(states) - len(missing)} of {len(states)} made") \
                .classes("ds-section-title")
            ui.space()
            if missing:
                ds.button(f"Create {len(missing)} card{'s' * (len(missing) != 1)}", kind="primary",
                          icon="add", on_click=lambda: generate(c))
        ds.hint("Before a card exists you can give a member its own text (it overrides the template "
                "for that member). Afterwards, edit the card itself.")

        def colors_cell(st) -> None:
            with ui.column().classes("gap-1"):
                ds.pips(st.member.colors or "C")
                ui.label(GROUP_NAMES.get(st.member.colors, "") if st.member.colors else f"#{st.n}") \
                    .classes("text-xs muted")

        def field_cell(st, key: str):
            index, member = st.n - 1, st.member
            if st.card is not None:
                face = st.card.faces[0]
                text = face.rules_text.split("\n")[0] if key == "rules_text" else getattr(face, key)
                return lambda: ui.label(text or "—").classes("warning-text" if key in st.edited else "")

            def editable() -> None:
                fields = member_fields(c, member, st.n)
                own = key in member.overrides
                box = (ui.textarea if key == "rules_text" else ui.input)(value=fields[key]) \
                    .props("dense autogrow" if key == "rules_text" else "dense") \
                    .classes("w-full" + (" ds-overridden" if own else ""))
                box.on("blur", lambda e=None: override(c, index, member, key, box.value))
            return editable

        def state_cell(st):
            def build() -> None:
                with ui.column().classes("gap-1 items-start"):
                    if st.card is None:
                        if made:
                            ds.badge("Missing" if st.member.card_id is None else "Not made", "warning")
                        else:
                            ds.badge("Not made", "neutral")
                        if st.member.overrides:
                            ds.button("Use template", kind="ghost",
                                      on_click=lambda i=st.n - 1: reset(c, i)).props("dense size=sm")
                    else:
                        ds.button(f"{number_label(st.card)} · open", kind="ghost",
                                  on_click=lambda cd=st.card: open_card(cd)).props("dense size=sm")
                        if st.edited:
                            ds.badge("Edited: " + ", ".join(FIELD_LABELS[f].lower() for f in st.edited),
                                     "warning").classes("whitespace-normal h-auto")
            return build

        ds.data_table(MEMBER_COLUMNS, [[lambda st=st: colors_cell(st),
                                        *[field_cell(st, key) for key in TABLE_FIELDS],
                                        state_cell(st)] for st in states])

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
        if await ds.confirm(view["dialogs"], f"Delete the cycle “{c.name}”?",
                            "Its cards stay in the set; they're just no longer linked to it.") == "confirm":
            session.delete_cycle(c)
            select(project.cycles[0] if project.cycles else None)

    # ---------------------------------------------------------------- layout
    with ui.element("div").classes("ds-split"):
        with ui.element("div").classes("ds-split-list"):
            with ui.element("div").classes("p-3"):
                ds.button("New cycle", kind="secondary", icon="add", on_click=new).classes("w-full")

            @ui.refreshable
            def cycle_list() -> None:
                with ui.element("div").classes("ds-editor-scroll"):
                    if not project.cycles:
                        ds.hint("No cycles yet.").classes("px-3")
                    for c in project.cycles:
                        made = sum(1 for st in status(c, project) if st.card is not None)
                        with ds.list_row(selected=c.id == view["id"], on_click=lambda cy=c: select(cy)) \
                                as row:
                            row.classes("h-auto py-1")
                            with ui.column().classes("grow gap-0 min-w-0"):
                                ui.label(c.name or "(no name)").classes("truncate font-medium")
                                ui.label(GROUPINGS[c.grouping][0]).classes("text-xs faint truncate")
                            ui.label(f"{made}/{len(c.members)}").classes("text-xs faint num")
            cycle_list()

        with ui.element("div").classes("ds-split-detail"):
            @ui.refreshable
            def detail() -> None:
                c = selected()
                if c is None:
                    ds.empty_state("donut_large", "Nothing selected",
                                   "A cycle makes one card per color (or group) from a shared template.")
                    return
                definition(c)
            detail()


MEMBER_COLUMNS = [ds.Column("Colors", "minmax(70px, auto)"), ds.Column("Name", "minmax(140px, 1.2fr)"),
                  ds.Column("Cost", "minmax(80px, 0.6fr)"), ds.Column("Type", "minmax(120px, 1fr)"),
                  ds.Column("Rules text", "minmax(200px, 2fr)"), ds.Column("", "minmax(120px, auto)")]
