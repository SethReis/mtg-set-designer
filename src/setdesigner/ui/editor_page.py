"""The card editor: card list | form | live preview. Opened from the overview."""
from __future__ import annotations

import time

from nicegui import run, ui

from ..app import ability_words, text_input
from ..model import Card, MechanicKind, Rarity, Status
from ..mse.mapping import split_type_line
from .art_editor import art_editor
from .mechanics_page import POLICY_LABELS
from .uploads import add_art_script, set_paste_target
from .widgets import RARITY_LETTERS, color_pips, number_label, responsive_grid

PALETTE = ["W", "U", "B", "R", "G", "C", "X", "T", "Q", "1", "2", "3", "4", "5"]
SYMBOL_STYLE = {"W": "background:#f3eccb;color:#222", "U": "background:#a9d0f0;color:#123",
                "B": "background:#b8b0aa;color:#111", "R": "background:#f2a68f;color:#311",
                "G": "background:#9fd3a8;color:#132"}
PREVIEW_DELAY = 0.3                      # seconds after the last keystroke


def register(state) -> None:
    from .app import FRAME_LABELS

    @ui.page("/set/card/{card_id}")
    async def editor_page(card_id: str) -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return

        cards = session.cards()
        view = {
            "card": next((c for c in cards if c.id == card_id), cards[0] if cards else None),
            "query": "",
            "caret": {},                  # field -> caret position
            "focus": "rules_text",        # field the symbol palette inserts into
            "preview_due": 0.0,
            "generation": 0,
            "inputs": {},                 # field -> element (cost, rules)
            "art": None,                  # the Art section's refreshable
            "mechanics": None,            # the "Mechanics" row's refreshable
            "art_version": session.art_version,
        }
        add_art_script()                  # drop / paste images as card art (see uploads.py)

        # ------------------------------------------------------------ header
        with ui.header().classes("items-center bg-slate-800 py-2"):
            ui.button(icon="arrow_back", on_click=lambda: (session.flush(), ui.navigate.to("/set"))) \
                .props("flat round color=white").tooltip("Back to the set overview").mark("back")
            ui.label(f"{session.project.info.name}").classes("text-lg font-semibold")
            ui.label(session.project.info.code).classes("text-sm opacity-70")
            ui.space()
            saved = ui.label("All changes saved").classes("text-sm opacity-70")

        # ------------------------------------------------------------ actions
        def select(card: Card | None) -> None:
            session.flush()
            view["card"] = card
            card_list.refresh()
            card_form.refresh()
            art_target(card)
            schedule_preview(now=True)

        def art_target(card: Card | None) -> None:
            """Pasted images and images dropped on the preview go to this card."""
            set_paste_target(card.id if card else None)
            if card is not None:
                preview.props(f'data-art-card="{card.id}"')
            else:
                preview.props(remove="data-art-card")

        def new_card() -> None:
            select(session.new_card())

        def duplicate(card: Card) -> None:
            select(session.duplicate(card))

        async def delete(card: Card) -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label(f"Delete “{card.faces[0].name}”? Its file is removed from the set folder.")
                with ui.row():
                    ui.button("Delete", on_click=lambda: dialog.submit(True)).props("color=negative")
                    ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            if await dialog:
                session.delete(card)
                remaining = session.cards()
                select(remaining[0] if remaining else None)

        def changed(field: str, value) -> None:
            card = view["card"]
            if card is None:
                return
            used = list(card.mechanics)
            session.update(card, field, value)
            if field in ("name", "collector_number", "rarity", "mana_cost"):
                card_list.refresh()
            ability_word = any(m.kind == MechanicKind.ABILITY_WORD and m.id in card.mechanics
                               for m in session.project.mechanics)
            if view["mechanics"] is not None and (card.mechanics != used
                                                  or (field == "rules_text" and ability_word)):
                view["mechanics"].refresh()     # a mechanic appeared or went, or a variant check
            schedule_preview()

        def mechanics_row(card: Card):
            """One chip per mechanic on the card, each with its reminder-text choice."""
            @ui.refreshable
            def row() -> None:
                used = [m for m in session.project.mechanics if m.id in card.mechanics]
                if not used:
                    return
                with ui.row().classes("w-full items-center gap-3"):
                    ui.label("Mechanics").classes("text-xs text-gray-500")
                    for mechanic in used:
                        if mechanic.kind == MechanicKind.ABILITY_WORD:     # no reminder text
                            lines = [line for face in card.faces for line in face.rules_text.split("\n")
                                     if ability_words.starts_line(mechanic, line)]
                            off = [line for line in lines if ability_words.parse_line(mechanic, line) is None]
                            if off and mechanic.templates:
                                ui.badge(f"{mechanic.name}: doesn't follow any variant",
                                         color="amber-2", text_color="amber-10")
                            else:
                                ui.label(mechanic.name).classes("text-sm italic")
                            continue
                        current = card.reminders.get(mechanic.id)
                        options = {"policy": f"{mechanic.name}: reminder as policy "
                                             f"({POLICY_LABELS[mechanic.reminder_policy.value].lower()})",
                                   "show": f"{mechanic.name}: show reminder",
                                   "hide": f"{mechanic.name}: hide reminder"}
                        value = "policy" if current is None else "show" if current else "hide"

                        def choose(e, m=mechanic) -> None:
                            session.set_reminder(card, m, None if e.value == "policy" else e.value == "show")
                            schedule_preview(now=True)
                        ui.select(options, value=value, on_change=choose) \
                            .props("dense options-dense outlined").classes("min-w-[260px]")
            row()
            return row

        def schedule_preview(now: bool = False) -> None:
            view["preview_due"] = time.monotonic() + (0 if now else PREVIEW_DELAY)

        # ------------------------------------------------------ text helpers
        def text_field(field: str, label: str, value: str, classes: str, textarea: bool = False):
            """An input with caret tracking and suggestions (mana symbols, mechanics)."""
            make = ui.textarea if textarea else ui.input
            element = make(label, value=value).classes(classes)
            if textarea:
                element.props("autogrow")
            view["inputs"][field] = element

            @ui.refreshable
            def suggestion_row() -> None:
                caret = view["caret"].get(field, len(element.value or ""))
                options = text_input.suggestions(element.value or "", caret, session.project.mechanics)
                element.props(f"data-suggest={1 if options else 0}")   # lets Tab accept (see below)
                if not options:
                    return
                with ui.row().classes("gap-1 -mt-1 mb-1"):
                    for option in options[:12]:
                        ui.button(option.label, on_click=lambda o=option: accept(field, o)) \
                            .props("dense no-caps outline size=sm")
                    ui.label("Tab to accept the first").classes("text-xs text-gray-400 self-center")

            def on_change(e) -> None:
                changed(field, e.value)
                suggestion_row.refresh()

            def on_caret(e) -> None:
                view["caret"][field] = int(e.args) if e.args is not None else len(element.value or "")
                view["focus"] = field
                suggestion_row.refresh()

            async def on_tab(_e) -> None:
                caret = view["caret"].get(field, len(element.value or ""))
                options = text_input.suggestions(element.value or "", caret, session.project.mechanics)
                if options:
                    accept(field, options[0])

            element.on_value_change(on_change)
            # the caret comes with every key and click (QInput doesn't pass on native `input`
            # events); whichever of the text and the caret updates arrives last refreshes the
            # suggestions with both up to date. Tab's keyup is skipped: it would report the
            # caret from before the suggestion it accepted
            element.on("keyup", on_caret,
                       js_handler="(e) => { if (e.key !== 'Tab') emit(e.target.selectionStart); }")
            element.on("click", on_caret, js_handler="(e) => emit(e.target.selectionStart)")
            # Tab accepts the first suggestion, but only while suggestions are shown
            element.on("keydown", on_tab, js_handler=(
                "(e) => { const s = e.target.closest('[data-suggest]');"
                " if (e.key === 'Tab' && s && s.dataset.suggest === '1') { e.preventDefault(); emit(); } }"))
            suggestion_row()
            return element

        def set_text(field: str, text: str, caret: int, select: int = 0) -> None:
            """New text, the caret at `caret`; `select` characters after it selected (so a
            placeholder like "[effect]" is typed over)."""
            element = view["inputs"][field]
            view["caret"][field] = caret               # first: on_change refreshes the suggestions
            element.value = text                       # triggers on_change -> save + preview
            tag = "textarea" if isinstance(element, ui.textarea) else "input"
            ui.run_javascript(f"setTimeout(() => {{ const t = document.querySelector('#c{element.id} {tag}');"
                              f" if (t) {{ t.focus(); t.setSelectionRange({caret}, {caret + select}); }} }}, 30);")

        def accept(field: str, option) -> None:
            element = view["inputs"][field]
            caret = view["caret"].get(field, len(element.value or ""))
            text, new_caret = text_input.apply(element.value or "", caret, option)
            set_text(field, text, new_caret, option.select)

        def insert(field: str, snippet: str, select_start: int | None = None, select: int = 0) -> None:
            """Insert at the caret; optionally select `select` characters from `select_start`
            within the snippet."""
            element = view["inputs"].get(field)
            if element is None:
                return
            caret = view["caret"].get(field, len(element.value or ""))
            text, new_caret = text_input.insert(element.value or "", caret, snippet)
            if select_start is not None:
                new_caret = new_caret - len(snippet) + select_start
            set_text(field, text, new_caret, select)

        def symbol_palette(field: str, _element, costs_only: bool = False) -> None:
            """Buttons inserting symbols (and CARDNAME / mechanics for rules text)."""
            with ui.row().classes("gap-1 items-center"):
                for symbol in PALETTE if not costs_only else [s for s in PALETTE if s not in "TQ"]:
                    # flat: Quasar's colored buttons force their own background
                    ui.button(f"{{{symbol}}}", on_click=lambda s=symbol: insert(field, f"{{{s}}}")) \
                        .props("dense no-caps flat size=sm text-color=black") \
                        .style(SYMBOL_STYLE.get(symbol, "background:#e2e2e2"))
                if not costs_only:
                    ui.button("CARDNAME", on_click=lambda: insert(field, "CARDNAME")) \
                        .props("dense no-caps flat size=sm").tooltip("This card's name")
                    for mechanic in session.project.mechanics:
                        variants = text_input.ability_word_inserts(mechanic)
                        if len(variants) > 1:                  # ability word: pick a variant
                            with ui.button(mechanic.name).props("dense no-caps flat size=sm"):
                                with ui.menu():
                                    for label, text, start, length in variants:
                                        ui.menu_item(label, on_click=lambda t=text, a=start, n=length:
                                                     insert(field, t, a, n))
                        elif variants:
                            _, text, start, length = variants[0]
                            ui.button(mechanic.name, on_click=lambda t=text, a=start, n=length:
                                      insert(field, t, a, n)).props("dense no-caps flat size=sm")
                        else:
                            snippet, _ = text_input.mechanic_insert(mechanic)
                            ui.button(mechanic.name, on_click=lambda s=snippet: insert(field, s)) \
                                .props("dense no-caps flat size=sm")

        # ------------------------------------------------------------ layout
        # The columns fill exactly the space under the header (each scrolls on its own),
        # so the page itself never needs a scrollbar: the page is a flex column whose
        # content takes the remaining height.
        ui.query(".q-page").classes("column")
        ui.query(".nicegui-content").classes("grow h-0 min-h-0")
        with ui.row().classes("w-full h-full no-wrap gap-4 items-start"):

            # ---- card list
            with ui.column().classes("w-64 shrink-0 h-full gap-2"):
                search = ui.input(placeholder="Search cards").props("dense outlined clearable") \
                    .classes("w-full")
                search.on_value_change(lambda e: (view.update(query=e.value or ""), card_list.refresh()))
                ui.button("New card", icon="add", on_click=new_card).props("flat no-caps") \
                    .tooltip("Ctrl+N")

                @ui.refreshable
                def card_list() -> None:
                    with ui.scroll_area().classes("w-full grow border rounded"):
                        for card in session.search(view["query"]):
                            active = view["card"] is not None and card.id == view["card"].id
                            row = ui.row().classes(
                                "w-full items-center no-wrap gap-2 px-2 py-1 cursor-pointer rounded "
                                + ("bg-blue-100" if active else "hover:bg-gray-100"))
                            with row:
                                ui.label(number_label(card)).classes("text-xs text-gray-500 w-8")
                                color_pips(card)
                                ui.label(card.faces[0].name or "(no name)").classes("grow truncate")
                                ui.label(RARITY_LETTERS[card.rarity]).classes("text-xs text-gray-500")
                                with ui.button(icon="more_vert").props("flat round dense size=sm") \
                                        .on("click.stop", lambda: None):
                                    with ui.menu():
                                        ui.menu_item("Duplicate", on_click=lambda c=card: duplicate(c))
                                        ui.menu_item("Delete", on_click=lambda c=card: delete(c))
                            row.on("click", lambda c=card: select(c))
                card_list()

            # ---- form
            with ui.scroll_area().classes("grow h-full min-w-[320px]"):
                @ui.refreshable
                def card_form() -> None:
                    card = view["card"]
                    if card is None:
                        ui.label("No cards yet. Add one with “New card”.").classes("text-gray-500 m-4")
                        return
                    face = card.faces[0]
                    with ui.column().classes("w-full gap-1 pr-4"):
                        if len(card.faces) > 1:
                            ui.label(f"This is a {card.layout.value} card; editing its other face "
                                     "comes in a later version. Showing the front face.") \
                                .classes("text-sm text-amber-700")
                        # field rows are grids: they use the column's width and wrap when narrow
                        with responsive_grid(160, columns="minmax(0, 2fr) minmax(140px, 1fr)"):
                            ui.input("Name", value=face.name,
                                     on_change=lambda e: changed("name", e.value)).classes("w-full")
                            with ui.column().classes("w-full gap-0"):
                                cost = text_field("mana_cost", "Mana cost", face.mana_cost, "w-full")
                        symbol_palette("mana_cost", cost, costs_only=True)
                        # two fields so nobody has to type the "—" (added when both are filled)
                        types, subtypes = split_type_line(face.type_line)
                        with responsive_grid(200, gap=16):
                            ui.input("Types", value=types, placeholder="Legendary Creature",
                                     on_change=lambda e: changed("types", e.value)).classes("w-full")
                            ui.input("Subtypes", value=subtypes, placeholder="Elf Druid",
                                     on_change=lambda e: changed("subtypes", e.value)).classes("w-full")
                        symbol_palette("rules_text", None)
                        text_field("rules_text", "Rules text", face.rules_text, "w-full", textarea=True)
                        view["mechanics"] = mechanics_row(card)
                        view["art"] = art_editor(session, card, schedule_preview)
                        ui.textarea("Flavor text", value=face.flavor_text,
                                    on_change=lambda e: changed("flavor_text", e.value)) \
                            .props("autogrow").classes("w-full")
                        with responsive_grid(110):
                            ui.input("Power", value=face.power or "",
                                     on_change=lambda e: changed("power", e.value)).classes("w-full")
                            ui.input("Toughness", value=face.toughness or "",
                                     on_change=lambda e: changed("toughness", e.value)).classes("w-full")
                            ui.input("Loyalty", value=face.loyalty or "",
                                     on_change=lambda e: changed("loyalty", e.value)).classes("w-full")
                            ui.select({r.value: r.value.title() for r in Rarity}, value=card.rarity.value,
                                      label="Rarity", on_change=lambda e: changed("rarity", e.value)) \
                                .classes("w-full")
                            ui.input("Number", value=card.collector_number,
                                     on_change=lambda e: changed("collector_number", e.value)).classes("w-full")
                        with responsive_grid(180):
                            ui.select({"": "Set default", **FRAME_LABELS}, value=card.frame or "",
                                      label="Frame", on_change=lambda e: changed("frame", e.value)) \
                                .classes("w-full")
                            ui.input("Artist", value=face.artist,
                                     on_change=lambda e: changed("artist", e.value)).classes("w-full")
                            ui.select({s.value: s.value.title() for s in Status}, value=card.status.value,
                                      label="Status", on_change=lambda e: changed("status", e.value)) \
                                .classes("w-full")
                        if session.project.archetypes:
                            known = {a.id: a.name for a in session.project.archetypes}
                            ui.select(known, multiple=True, label="Archetypes",
                                      value=[a for a in card.archetypes if a in known],
                                      on_change=lambda e: changed("archetypes", e.value or [])) \
                                .props("use-chips").classes("w-full")
                        ui.textarea("Notes", value=card.notes,
                                    on_change=lambda e: changed("notes", e.value)) \
                            .props("autogrow").classes("w-full")
                card_form()

            # ---- preview
            with ui.column().classes("w-[380px] shrink-0 h-full items-center gap-1"):
                preview = ui.image().classes("w-[375px]").style("min-height:523px")
                preview_note = ui.label("Starting the renderer…").classes("text-xs text-gray-500")


        # ------------------------------------------------------ timers
        async def tick() -> None:
            saved.text = "Saving…" if session.unsaved else "All changes saved"
            session.flush_due()
            if session.art_notice is not None:           # from a dropped or pasted file
                kind, message = session.art_notice
                session.art_notice = None
                ui.notify(message, type=kind)
            if session.art_version != view["art_version"]:
                view["art_version"] = session.art_version
                if view["art"] is not None:
                    view["art"].refresh()
                schedule_preview(now=True)
            due = view["preview_due"]
            if due and time.monotonic() >= due and view["card"] is not None:
                view["preview_due"] = 0.0
                view["generation"] += 1
                generation, card = view["generation"], view["card"]
                try:
                    image = await run.io_bound(session.render, card)
                except Exception as e:                   # never break the editor over a preview
                    preview_note.text = f"Preview failed: {e}"
                    return
                if generation == view["generation"]:      # skip stale results
                    preview.set_source(image)
                    note = session.renderer_note
                    preview_note.text = f"Drawn by the {note}" if note else ""
            elif view["card"] is None:
                preview.set_source("")
                preview_note.text = ""

        ui.timer(0.1, tick)
        art_target(view["card"])
        schedule_preview(now=True)

        # ------------------------------------------------------ keyboard
        def on_key(e) -> None:
            if not e.action.keydown or not e.modifiers.ctrl:
                return
            key = e.key.name.lower() if hasattr(e.key, "name") else str(e.key).lower()
            if key == "n":
                new_card()
            elif key == "d" and view["card"] is not None:
                duplicate(view["card"])
            elif key == "f":
                search.run_method("focus")

        ui.keyboard(on_key=on_key, ignore=[])
