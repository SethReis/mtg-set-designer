"""Mechanics, a workspace modal: define the set's mechanics and see where each is used.

Left: the mechanics. Right: the selected one's definition (saved when you leave a field:
mechanics are set-wide, so each save restarts the renderer) and the cards that use it.
Renaming offers to update the cards that mention the old name and its word forms.
"""
from __future__ import annotations

import html

from typing import Callable

from nicegui import ui

from ..app.ability_words import build_line, definition_change_plan, template_uses
from ..app.health.roles import ROLES
from ..app.mechanics import PARAMETER_TYPES, find_uses, reminder_preview, rename_plan, suggest_forms, usage
from ..app.overview import COLOR_LABELS
from ..model import AbilityTemplate, Card, Mechanic, MechanicKind, ReminderPolicy
from ..mse.mechanics import words_pattern
from . import components as c
from .widgets import number_label, responsive_grid

KIND_LABELS = {MechanicKind.KEYWORD.value: "Keyword (Flying, Cycling {2})",
               MechanicKind.ABILITY_WORD.value: "Ability word (Landfall — …)",
               MechanicKind.KEYWORD_ACTION.value: "Keyword action (Scry 2, Surveil 1)"}
POLICY_LABELS = {ReminderPolicy.ALWAYS.value: "Always",
                 ReminderPolicy.COMMONS_ONLY.value: "On commons only",
                 ReminderPolicy.FIRST_PER_COLOR.value: "First card of each color",
                 ReminderPolicy.NEVER.value: "Never"}
RARITY_NAMES = {"common": "C", "uncommon": "U", "rare": "R", "mythic": "M", "special": "S"}


def highlight(sentence: str, mechanic: Mechanic) -> str:
    """The sentence as HTML with the mechanic's words marked."""
    return words_pattern(mechanic).sub(lambda m: f"<mark>{m.group(0)}</mark>", html.escape(sentence))


def mechanics_panel(state, m: c.Modal, *, select_id: str | None = None,
                    open_card: Callable[[Card], None], on_select: Callable[[str | None], None]) -> None:
    """Build the Mechanics workspace into the modal `m`: the list, the selected mechanic's
    definition and the cards that use it. `on_select` runs with the shown mechanic's id."""
    session = state.session
    project = session.project
    first = project.mechanics[0].id if project.mechanics else None
    view = {"id": select_id if any(x.id == select_id for x in project.mechanics) else first,
            "dialogs": m.body}

    def selected() -> Mechanic | None:
        return next((x for x in project.mechanics if x.id == view["id"]), None)

    def select(mechanic: Mechanic | None) -> None:
        view["id"] = mechanic.id if mechanic else None
        mechanic_list.refresh()
        detail.refresh()
        on_select(view["id"])

    def new() -> None:
        select(session.new_mechanic())

    # ---------------------------------------------------------------- definition
    def definition(mechanic: Mechanic) -> None:
        ability_word = mechanic.kind == MechanicKind.ABILITY_WORD
        parts = {"preview": None}

        def save(**values) -> None:
            if any(getattr(mechanic, k) != v for k, v in values.items()):
                session.update_mechanic(mechanic, **values)
                if parts["preview"] is not None:
                    parts["preview"].text = reminder_preview(mechanic)
                mechanic_list.refresh()
                if "kind" in values:                    # different fields for ability words
                    detail.refresh()
                elif "forms" in values:                 # which cards count may change
                    uses_section.refresh()

        with ui.column().classes("w-full gap-2"):
            with responsive_grid(220):
                name = ui.input("Name", value=mechanic.name)
                name.on("blur", lambda: rename(mechanic, name))
                ui.select(KIND_LABELS, value=mechanic.kind.value, label="Kind",
                          on_change=lambda e: save(kind=e.value))
                if not ability_word:
                    ui.select(PARAMETER_TYPES, value=mechanic.parameter or "", label="Parameter",
                              on_change=lambda e: save(parameter=e.value or None))
                    ui.select(POLICY_LABELS, value=mechanic.reminder_policy.value,
                              label="Show reminder text",
                              on_change=lambda e: save(reminder_policy=e.value))
                ui.select({rid: role.label for rid, role in ROLES.items()}, multiple=True,
                          value=list(mechanic.roles), label="Roles",
                          on_change=lambda e: save(roles=[r for r in ROLES if r in (e.value or [])])) \
                    .props("use-chips dense").mark("mechanic-roles") \
                    .tooltip("Cards with this mechanic count toward these on the Health page")
            if ability_word:
                throughline(mechanic)
            else:
                reminder = ui.textarea("Reminder text", value=mechanic.reminder_text).props("autogrow") \
                    .classes("w-full")
                reminder.on("blur", lambda: save(reminder_text=reminder.value))
                hint = "Use {" + (mechanic.parameter or "param") + "} where the parameter's value goes." \
                    if mechanic.parameter else "Shown in parentheses after the mechanic on cards."
                c.hint(hint).classes("-mt-2")
                with ui.row().classes("w-full items-end gap-2 no-wrap"):
                    forms = ui.input_chips("Word forms that also count", value=list(mechanic.forms),
                                           new_value_mode="add-unique",
                                           on_change=lambda e: save(forms=list(e.value or []))) \
                        .classes("grow")

                    def add_common() -> None:
                        forms.value = list(dict.fromkeys([*forms.value, *suggest_forms(mechanic.name)]))
                    c.button("Add common forms", kind="ghost", on_click=add_common).props("dense")
            intent = ui.textarea("Design intent", value=mechanic.design_intent).props("autogrow") \
                .classes("w-full")
            intent.on("blur", lambda: save(design_intent=intent.value))
            if not ability_word:
                with ui.row().classes("items-center gap-2"):
                    ui.label("On a card:").classes("muted")
                    parts["preview"] = ui.label(reminder_preview(mechanic)).classes("italic")
            c.button("Delete mechanic", kind="danger", icon="delete", on_click=lambda: delete(mechanic)) \
                .props("dense").classes("self-start")

    # ---------------------------------------------------------------- ability words
    def throughline(mechanic: Mechanic) -> None:
        """Shared phrases and template variants (see app/ability_words.py)."""
        phrase_rows, variant_rows = [], []

        def collect() -> tuple[dict[str, str], list[AbilityTemplate]]:
            phrases = {n.value.strip(): w.value for n, w in phrase_rows if n.value.strip()}
            templates = [AbilityTemplate(label=l.value.strip(), text=t.value) for l, t in variant_rows]
            return phrases, templates

        async def changed() -> None:
            phrases, templates = collect()
            if phrases == mechanic.phrases and templates == mechanic.templates:
                return
            await apply_definition(mechanic, phrases=phrases, templates=templates)

        def add_phrase() -> None:
            phrases, templates = collect()
            n = 1
            while f"phrase{n}" in phrases:
                n += 1
            phrases[f"phrase{n}"] = ""
            session.update_mechanic(mechanic, phrases=phrases, templates=templates)
            detail.refresh()

        def add_variant() -> None:
            phrases, templates = collect()
            templates.append(AbilityTemplate(label=f"Variant {len(templates) + 1}", text="{effect}"))
            session.update_mechanic(mechanic, phrases=phrases, templates=templates)
            detail.refresh()

        async def remove_phrase(key: str) -> None:
            phrases, templates = collect()
            phrases.pop(key, None)
            await apply_definition(mechanic, phrases=phrases, templates=templates)

        def remove_variant(index: int) -> None:
            phrases, templates = collect()
            del templates[index]
            session.update_mechanic(mechanic, phrases=phrases, templates=templates)
            detail.refresh()

        ui.label("Shared phrases").classes("ds-form-h")
        c.hint("Write a phrase once; use it in variants as {=name}.")
        for key, wording in mechanic.phrases.items():
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                n = ui.input("Name", value=key).props("dense").classes("w-40")
                w = ui.input("Wording", value=wording).props("dense").classes("grow")
                n.on("blur", changed)
                w.on("blur", changed)
                c.button(icon="close", kind="icon", on_click=lambda k=key: remove_phrase(k),
                         tooltip="Remove phrase").props("size=sm")
                phrase_rows.append((n, w))
        c.button("Phrase", kind="ghost", icon="add", on_click=add_phrase).props("dense").classes("self-start")

        ui.label("Variants").classes("ds-form-h")
        c.hint("The text after the dash. {effect}, {cost}, {trigger} or any {name} are filled per "
               "card; {=name} inserts a shared phrase.")
        for i, template in enumerate(mechanic.templates):
            with ui.element("div").classes("ds-section w-full p-3"):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    l = ui.input("Label", value=template.label).props("dense").classes("w-40")
                    t = ui.textarea("Template", value=template.text).props("dense autogrow") \
                        .classes("grow")
                    l.on("blur", changed)
                    t.on("blur", changed)
                    c.button(icon="close", kind="icon", on_click=lambda i=i: remove_variant(i),
                             tooltip="Remove variant").props("size=sm")
                    variant_rows.append((l, t))
                example = build_line(mechanic, template.text)
                ui.html(f"<i>{html.escape(mechanic.name)}</i>{html.escape(example[len(mechanic.name):])}") \
                    .classes("muted mt-1")
        c.button("Variant", kind="ghost", icon="add", on_click=add_variant).props("dense").classes("self-start")

    async def confirm_changes(title: str, changes, notes=()) -> bool | None:
        """Show card text changes. True: update the cards; False: keep their text;
        None: cancel."""
        def details() -> None:
            for note in notes:
                c.status(note, "warning").classes("whitespace-normal")
            changes_list([(x.card.faces[x.face].name, x.before, x.after) for x in changes])
        n = len(changes)
        choice = await c.confirm(view["dialogs"], title,
                                 f"{n} card face{'s' * (n != 1)} affected. Update their rules text?",
                                 confirm_label=f"Update {n} card{'s' * (n != 1)}", kind="primary",
                                 extra="Keep card text", details=details)
        return {"confirm": True, "extra": False}.get(choice)

    async def apply_definition(mechanic: Mechanic, **values) -> None:
        """Save changed phrases / variants, offering to update the cards that follow them."""
        plan = definition_change_plan(project, mechanic, **values)
        update = False
        if plan.changes:
            notes = [f"{label}: " + ", ".join("{" + s + "}" for s in lost)
                     + " no longer in the template; that part of those cards is dropped."
                     for label, lost in plan.dropped.items()]
            if plan.unmatched:
                notes.append(f"{len(plan.unmatched)} line(s) don't follow any variant and stay as they are.")
            update = await confirm_changes(f"Change “{mechanic.name}”", plan.changes, notes)
            if update is None:
                detail.refresh()                        # put the fields back
                return
        done = session.update_mechanic(mechanic, update_cards=bool(update), **values)
        if done:
            ui.notify(f"Updated {len(done)} card face{'s' * (len(done) != 1)}", type="positive")
        detail.refresh()

    async def rename(mechanic: Mechanic, field) -> None:
        new_name = (field.value or "").strip()
        if not new_name or new_name == mechanic.name:
            field.value = mechanic.name
            return
        changes = rename_plan(project, mechanic, new_name)
        update = False
        if changes:
            update = await confirm_changes(f"Rename “{mechanic.name}” to “{new_name}”", changes)
            if update is None:
                field.value = mechanic.name
                return
        done = session.rename_mechanic(mechanic, new_name, update_cards=update)
        if done:
            ui.notify(f"Updated {len(done)} card face{'s' * (len(done) != 1)}", type="positive")
        mechanic_list.refresh()
        detail.refresh()

    async def delete(mechanic: Mechanic) -> None:
        if await c.confirm(view["dialogs"], f"Delete “{mechanic.name}”?",
                           "Cards keep their text; it's just no longer a mechanic of the set "
                           "(no reminder text).") == "confirm":
            session.delete_mechanic(mechanic)
            select(project.mechanics[0] if project.mechanics else None)

    # ---------------------------------------------------------------- uses
    @ui.refreshable
    def uses_section(mechanic: Mechanic) -> None:
        stats = usage(project, mechanic)
        with ui.column().classes("w-full gap-3"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label(f"Used on {stats.cards} card{'s' * (stats.cards != 1)}").classes("ds-section-title")
                if stats.cards:
                    for key, n in stats.by_color.items():
                        with ui.row().classes("items-center gap-1 no-wrap").tooltip(COLOR_LABELS[key]):
                            c.pips(key)
                            ui.label(f"{COLOR_LABELS[key] if key in 'MCL' else ''} {n}".strip()).classes("num")
                    ui.label(" · ".join(f"{RARITY_NAMES[r]} {n}" for r, n in stats.by_rarity.items())) \
                        .classes("muted num")
            if mechanic.kind == MechanicKind.ABILITY_WORD:
                ability_word_lines(mechanic)
                return

            def sentences(use) -> None:
                with ui.column().classes("gap-0"):
                    for sentence in use.sentences:
                        ui.html(highlight(sentence, mechanic), sanitize=False)
            uses = find_uses(project, mechanic)
            if uses:
                c.data_table(USE_COLUMNS, [use_row(use.card, use.face, lambda u=use: sentences(u))
                                           for use in uses])

    def use_row(card: Card, face: int, text: Callable[[], None]) -> list:
        """A row of a "used on" table: number, card (opens it), rarity, its text."""
        return [number_label(card),
                lambda: c.button(card.faces[face].name, kind="ghost", on_click=lambda: open_card(card))
                .props("dense").classes("truncate max-w-full"),
                lambda: c.rarity_letter(card.rarity),
                text]

    def ability_word_lines(mechanic: Mechanic) -> None:
        """Each card line of an ability word: its variant and values, or a badge."""
        def line(use) -> None:
            with ui.column().classes("gap-1"):
                with ui.row().classes("items-center gap-2"):
                    if use.match is None:
                        c.badge("Doesn't follow any variant", "warning")
                    else:
                        ui.label(use.match.label or f"Variant {use.match.variant + 1}") \
                            .classes("text-xs font-semibold muted")
                        ui.label(" · ".join(f"{k}: {v}" for k, v in use.match.values.items())) \
                            .classes("text-xs muted")
                    if use.unfinished:
                        c.badge("Unfinished", "warning")
                ui.label(use.line)
        uses = template_uses(project, mechanic)
        if uses:
            c.data_table(USE_COLUMNS, [use_row(use.card, use.face, lambda u=use: line(u)) for use in uses])

    # ---------------------------------------------------------------- layout
    with ui.element("div").classes("ds-split"):
        with ui.element("div").classes("ds-split-list"):
            with ui.element("div").classes("p-3"):
                c.button("New mechanic", kind="secondary", icon="add", on_click=new).classes("w-full")

            @ui.refreshable
            def mechanic_list() -> None:
                with ui.element("div").classes("ds-editor-scroll"):
                    if not project.mechanics:
                        c.hint("No mechanics yet.").classes("px-3")
                    for mechanic in project.mechanics:
                        n = usage(project, mechanic).cards
                        with c.list_row(selected=mechanic.id == view["id"],
                                        on_click=lambda x=mechanic: select(x)):
                            ui.label(mechanic.name or "(no name)").classes("grow truncate font-medium")
                            ui.label(f"{n} card{'s' * (n != 1)}").classes("faint num text-xs")
            mechanic_list()

        with ui.element("div").classes("ds-split-detail"):
            @ui.refreshable
            def detail() -> None:
                mechanic = selected()
                if mechanic is None:
                    c.empty_state("auto_fix_high", "Nothing selected",
                                  "Keywords, ability words and keyword actions of the set.")
                    return
                definition(mechanic)
                ui.element("div").classes("ds-divider")
                uses_section(mechanic)
            detail()


USE_COLUMNS = [c.Column("No.", "minmax(44px, auto)"), c.Column("Card", "minmax(140px, 1fr)"),
               c.Column("", "28px"), c.Column("Text", "minmax(240px, 3fr)")]


def changes_list(changes: list[tuple[str, str, str]]) -> None:
    """Card text before / after, for a confirmation (the first 5)."""
    for name, before, after in changes[:5]:
        with ui.element("div").classes("ds-section w-full p-3 mt-2"):
            ui.label(name).classes("ds-label")
            ui.label(before).classes("faint line-through whitespace-pre-line")
            ui.label(after).classes("whitespace-pre-line")
    if len(changes) > 5:
        c.hint(f"… and {len(changes) - 5} more").classes("mt-2")
