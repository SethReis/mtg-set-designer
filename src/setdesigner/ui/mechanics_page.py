"""The Mechanics page: define the set's mechanics and see where each is used.

Left: the mechanics. Right: the selected one's definition (saved when you leave a field:
mechanics are set-wide, so each save restarts the renderer) and the cards that use it.
Renaming offers to update the cards that mention the old name and its word forms.
"""
from __future__ import annotations

import html

from nicegui import ui

from ..app.ability_words import build_line, definition_change_plan, template_uses
from ..app.health.roles import ROLES
from ..app.mechanics import PARAMETER_TYPES, find_uses, reminder_preview, rename_plan, suggest_forms, usage
from ..app.overview import COLOR_LABELS
from ..model import AbilityTemplate, Mechanic, MechanicKind, ReminderPolicy
from ..mse.mechanics import words_pattern
from .widgets import COLOR_PIPS, RARITY_LETTERS, number_label

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


def register(state) -> None:

    @ui.page("/set/mechanics")
    def mechanics_page() -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        project = session.project
        view = {"id": project.mechanics[0].id if project.mechanics else None}

        def selected() -> Mechanic | None:
            return next((m for m in project.mechanics if m.id == view["id"]), None)

        def select(mechanic: Mechanic | None) -> None:
            view["id"] = mechanic.id if mechanic else None
            mechanic_list.refresh()
            detail.refresh()

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

            with ui.column().classes("w-full gap-2 pr-4").style("max-width:900px"):
                with ui.element("div").classes("w-full") \
                        .style("display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px"):
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
                    ui.label(hint).classes("text-xs text-gray-500 -mt-2")
                    with ui.row().classes("w-full items-end gap-2 no-wrap"):
                        forms = ui.input_chips("Word forms that also count", value=list(mechanic.forms),
                                               new_value_mode="add-unique",
                                               on_change=lambda e: save(forms=list(e.value or []))) \
                            .classes("grow")

                        def add_common() -> None:
                            forms.value = list(dict.fromkeys([*forms.value, *suggest_forms(mechanic.name)]))
                        ui.button("Add common forms", on_click=add_common).props("flat dense no-caps")
                intent = ui.textarea("Design intent", value=mechanic.design_intent).props("autogrow") \
                    .classes("w-full")
                intent.on("blur", lambda: save(design_intent=intent.value))
                if not ability_word:
                    with ui.row().classes("items-center gap-2"):
                        ui.label("On a card:").classes("text-sm text-gray-500")
                        parts["preview"] = ui.label(reminder_preview(mechanic)).classes("text-sm italic")
                ui.button("Delete mechanic", icon="delete", on_click=lambda: delete(mechanic)) \
                    .props("flat dense no-caps color=negative").classes("self-start")

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

            ui.label("Shared phrases").classes("text-sm font-semibold mt-2")
            ui.label("Write a phrase once; use it in variants as {=name}.").classes("text-xs text-gray-500")
            for key, wording in mechanic.phrases.items():
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    n = ui.input("Name", value=key).props("dense").classes("w-40")
                    w = ui.input("Wording", value=wording).props("dense").classes("grow")
                    n.on("blur", changed)
                    w.on("blur", changed)
                    ui.button(icon="close", on_click=lambda k=key: remove_phrase(k)) \
                        .props("flat round dense size=sm").tooltip("Remove phrase")
                    phrase_rows.append((n, w))
            ui.button("Phrase", icon="add", on_click=add_phrase).props("flat dense no-caps")

            ui.label("Variants").classes("text-sm font-semibold mt-2")
            ui.label("The text after the dash. {effect}, {cost}, {trigger} or any {name} are filled per "
                     "card; {=name} inserts a shared phrase.").classes("text-xs text-gray-500")
            for i, template in enumerate(mechanic.templates):
                with ui.column().classes("w-full gap-0 border rounded p-2"):
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        l = ui.input("Label", value=template.label).props("dense").classes("w-40")
                        t = ui.textarea("Template", value=template.text).props("dense autogrow") \
                            .classes("grow")
                        l.on("blur", changed)
                        t.on("blur", changed)
                        ui.button(icon="close", on_click=lambda i=i: remove_variant(i)) \
                            .props("flat round dense size=sm").tooltip("Remove variant")
                        variant_rows.append((l, t))
                    example = build_line(mechanic, template.text)
                    ui.html(f"<i>{html.escape(mechanic.name)}</i>{html.escape(example[len(mechanic.name):])}") \
                        .classes("text-sm text-gray-700 mt-1")
            ui.button("Variant", icon="add", on_click=add_variant).props("flat dense no-caps")

        async def confirm_changes(title: str, changes, notes=()) -> bool | None:
            """Show card text changes. True: update the cards; False: keep their text;
            None: cancel."""
            with view["dialogs"], ui.dialog() as dialog, ui.card().classes("w-[640px] max-w-[95vw]"):
                ui.label(title).classes("text-lg font-semibold")
                ui.label(f"{len(changes)} card face{'s' * (len(changes) != 1)} affected. "
                         "Update their rules text?").classes("text-sm")
                for note in notes:
                    ui.label(note).classes("text-sm text-amber-800")
                for change in changes[:5]:
                    with ui.column().classes("gap-0 w-full border rounded p-2"):
                        ui.label(change.card.faces[change.face].name).classes("text-xs text-gray-500")
                        ui.label(change.before).classes("text-sm line-through text-gray-500 whitespace-pre-line")
                        ui.label(change.after).classes("text-sm whitespace-pre-line")
                if len(changes) > 5:
                    ui.label(f"… and {len(changes) - 5} more").classes("text-xs text-gray-500")
                with ui.row():
                    ui.button(f"Update {len(changes)} card{'s' * (len(changes) != 1)}",
                              on_click=lambda: dialog.submit(True)).props("color=primary")
                    ui.button("Keep card text", on_click=lambda: dialog.submit(False)).props("flat")
                    ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            return await dialog

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
            with view["dialogs"], ui.dialog() as dialog, ui.card():
                ui.label(f"Delete “{mechanic.name}”? Cards keep their text; it's just no longer "
                         "a mechanic of the set (no reminder text).")
                with ui.row():
                    ui.button("Delete", on_click=lambda: dialog.submit(True)).props("color=negative")
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            if await dialog:
                session.delete_mechanic(mechanic)
                select(project.mechanics[0] if project.mechanics else None)

        # ---------------------------------------------------------------- uses
        @ui.refreshable
        def uses_section(mechanic: Mechanic) -> None:
            stats = usage(project, mechanic)
            with ui.column().classes("w-full gap-2 pr-4").style("max-width:900px"):
                ui.label(f"Used on {stats.cards} card{'s' * (stats.cards != 1)}") \
                    .classes("text-base font-semibold")
                if stats.cards:
                    with ui.row().classes("items-center gap-4"):
                        with ui.row().classes("items-center gap-2"):
                            for key, n in stats.by_color.items():
                                with ui.row().classes("items-center gap-1 no-wrap").tooltip(COLOR_LABELS[key]):
                                    color = COLOR_PIPS.get(key, "#bbb")
                                    ui.element("span").style(f"width:10px;height:10px;border-radius:50%;"
                                                             f"background:{color};border:1px solid #888")
                                    ui.label(f"{COLOR_LABELS[key] if key in 'MCL' else ''} {n}".strip())
                        ui.label(" · ".join(f"{RARITY_NAMES[r]} {n}" for r, n in stats.by_rarity.items())) \
                            .classes("text-sm text-gray-600")
                if mechanic.kind == MechanicKind.ABILITY_WORD:
                    ability_word_lines(mechanic)
                    return
                for use in find_uses(project, mechanic):
                    card = use.card
                    with ui.row().classes("w-full items-start no-wrap gap-3 px-2 py-1 rounded cursor-pointer "
                                          "hover:bg-gray-100") \
                            .on("click", lambda c=card: ui.navigate.to(f"/set/card/{c.id}")):
                        ui.label(number_label(card)).classes("text-xs text-gray-500 w-8 shrink-0 mt-0.5")
                        ui.label(card.faces[use.face].name).classes("w-48 shrink-0 font-medium truncate")
                        ui.label(RARITY_LETTERS[card.rarity]).classes("text-xs text-gray-500 w-4 shrink-0 mt-0.5")
                        with ui.column().classes("gap-0 grow"):
                            for sentence in use.sentences:
                                ui.html(highlight(sentence, mechanic)).classes("text-sm")

        def ability_word_lines(mechanic: Mechanic) -> None:
            """Each card line of an ability word: its variant and values, or a badge."""
            for use in template_uses(project, mechanic):
                card = use.card
                with ui.row().classes("w-full items-start no-wrap gap-3 px-2 py-1 rounded cursor-pointer "
                                      "hover:bg-gray-100") \
                        .on("click", lambda c=card: ui.navigate.to(f"/set/card/{c.id}")):
                    ui.label(number_label(card)).classes("text-xs text-gray-500 w-8 shrink-0 mt-0.5")
                    ui.label(card.faces[use.face].name).classes("w-48 shrink-0 font-medium truncate")
                    ui.label(RARITY_LETTERS[card.rarity]).classes("text-xs text-gray-500 w-4 shrink-0 mt-0.5")
                    with ui.column().classes("gap-0 grow"):
                        with ui.row().classes("items-center gap-2"):
                            if use.match is None:
                                ui.badge("Doesn't follow any variant", color="amber-2", text_color="amber-10")
                            else:
                                ui.label(use.match.label or f"Variant {use.match.variant + 1}") \
                                    .classes("text-xs font-semibold text-gray-600")
                                ui.label(" · ".join(f"{k}: {v}" for k, v in use.match.values.items())) \
                                    .classes("text-xs text-gray-600")
                            if use.unfinished:
                                ui.badge("Unfinished", color="amber-2", text_color="amber-10")
                        ui.label(use.line).classes("text-sm")

        # ---------------------------------------------------------------- header
        # dialogs live here: the part of the page that opened one may be rebuilt meanwhile
        view["dialogs"] = ui.element("div")
        with ui.header().classes("items-center bg-slate-800 py-2"):
            ui.button(icon="arrow_back", on_click=lambda: (session.flush(), ui.navigate.to("/set"))) \
                .props("flat round color=white").tooltip("Back to the set overview").mark("back")
            ui.label("Mechanics").classes("text-lg font-semibold")
            ui.label(project.info.name).classes("text-sm opacity-70")

        ui.query(".q-page").classes("column")
        ui.query(".nicegui-content").classes("grow h-0 min-h-0")
        with ui.row().classes("w-full h-full no-wrap gap-6 items-start"):
            # ------------------------------------------------------------ the list
            with ui.column().classes("w-72 shrink-0 h-full gap-2"):
                ui.button("New mechanic", icon="add", on_click=new).props("flat no-caps")

                @ui.refreshable
                def mechanic_list() -> None:
                    with ui.scroll_area().classes("w-full grow border rounded"):
                        if not project.mechanics:
                            ui.label("No mechanics yet.").classes("text-gray-500 m-2")
                        for mechanic in project.mechanics:
                            active = mechanic.id == view["id"]
                            n = usage(project, mechanic).cards
                            with ui.row().classes("w-full items-center no-wrap gap-2 px-2 py-1 rounded "
                                                  "cursor-pointer " + ("bg-blue-100" if active
                                                                       else "hover:bg-gray-100")) \
                                    .on("click", lambda m=mechanic: select(m)):
                                ui.label(mechanic.name or "(no name)").classes("grow truncate font-medium")
                                ui.label(f"{n} card{'s' * (n != 1)}").classes("text-xs text-gray-500")
                mechanic_list()

            # ------------------------------------------------------------ the detail
            with ui.scroll_area().classes("grow h-full"):
                @ui.refreshable
                def detail() -> None:
                    mechanic = selected()
                    if mechanic is None:
                        ui.label("Add a mechanic with “New mechanic”.").classes("text-gray-500 m-4")
                        return
                    definition(mechanic)
                    ui.separator().classes("my-3")
                    uses_section(mechanic)
                detail()
