"""The card editor: a workspace modal over the set (card list | form | live preview).

    with modal("workspace", card.faces[0].name, parent=shell.dialogs) as m:
        editor_panel(state, m, card.id, order=..., open_cycle=..., on_card=...)
"""
from __future__ import annotations

import time
from typing import Callable

from nicegui import run, ui

from ..app import ability_words, text_input
from ..app.health.roles import ROLES, detected_roles, mechanic_roles
from ..model import Card, MechanicKind, Rarity, Status
from ..mse.mapping import split_type_line
from . import components as c
from .art_editor import art_editor
from .mechanics_page import POLICY_LABELS
from .uploads import set_paste_target
from .widgets import number_label, responsive_grid

PALETTE = ["W", "U", "B", "R", "G", "C", "X", "T", "Q", "1", "2", "3", "4", "5"]
PREVIEW_DELAY = 0.3                      # seconds after the last keystroke


def editor_panel(state, m: c.Modal, card_id: str, *, order: Callable[[], list[Card]],
                 open_cycle: Callable[[str], None], on_card: Callable[[Card | None], None]) -> None:
    """Build the editor into the modal `m`, showing `card_id`. `order()` is the workspace's
    card order (previous / next); `on_card` runs when another card is shown."""
    from .app import FRAME_LABELS
    session = state.session
    cards = session.cards()
    view = {
        "card": next((x for x in cards if x.id == card_id), cards[0] if cards else None),
        "query": "",
        "caret": {},                  # field -> caret position
        "focus": "rules_text",        # field the symbol palette inserts into
        "preview_due": 0.0,
        "generation": 0,
        "inputs": {},                 # field -> element (cost, rules)
        "art": None,                  # the Art section's refreshable
        "mechanics": None,            # the "Mechanics" row's refreshable
        "roles": None,                # the "Roles" row's refreshable
        "art_version": session.art_version,
        "list_open": True,                # the card list column
    }

    # ------------------------------------------------------------ actions
    def select(card: Card | None) -> None:
        session.flush()
        view["card"] = card
        card_list.refresh()
        card_form.refresh()
        art_target(card)
        retitle()
        schedule_preview(now=True)
        on_card(card)

    def retitle() -> None:
        card = view["card"]
        m.title.text = (card.faces[0].name or "(no name)") if card else "No cards"
        m.subtitle.text = f"{number_label(card)} · {card.rarity.value.title()}" if card else ""
        m.subtitle.set_visibility(card is not None)

    def step(by: int) -> None:
        """The previous / next card in the workspace's order."""
        card = view["card"]
        cards = order() or session.cards()
        if card is None or not cards:
            return
        ids = [x.id for x in cards]
        i = ids.index(card.id) + by if card.id in ids else 0
        select(cards[i % len(cards)])

    def art_target(card: Card | None) -> None:
        """Pasted images and images dropped on the preview go to this card."""
        set_paste_target(card.id if card else None)
        if card is not None:
            preview_box.props(f'data-art-card="{card.id}"')
        else:
            preview_box.props(remove="data-art-card")

    def new_card() -> None:
        select(session.new_card())

    def duplicate(card: Card) -> None:
        select(session.duplicate(card))

    async def delete(card: Card) -> None:
        if await c.confirm(m.body, f"Delete “{card.faces[0].name}”?",
                           "Its file is removed from the set folder.") == "confirm":
            session.delete(card)
            remaining = session.cards()
            select(remaining[0] if remaining else None)

    def toggle_list() -> None:
        view["list_open"] = not view["list_open"]
        grid.classes(remove="list-closed") if view["list_open"] else grid.classes(add="list-closed")

    def changed(field: str, value) -> None:
        card = view["card"]
        if card is None:
            return
        used = list(card.mechanics)
        session.update(card, field, value)
        if field in ("name", "collector_number", "rarity", "mana_cost"):
            card_list.refresh()
            retitle()
        ability_word = any(x.kind == MechanicKind.ABILITY_WORD and x.id in card.mechanics
                           for x in session.project.mechanics)
        if view["mechanics"] is not None and (card.mechanics != used
                                              or (field == "rules_text" and ability_word)):
            view["mechanics"].refresh()     # a mechanic appeared or went, or a variant check
        if field in ("rules_text", "name", "types") and view["roles"] is not None:
            view["roles"].refresh()         # detection reads the text and the types
        schedule_preview()

    def mechanics_row(card: Card):
        """One chip per mechanic on the card, each with its reminder-text choice."""
        @ui.refreshable
        def row() -> None:
            used = [x for x in session.project.mechanics if x.id in card.mechanics]
            if not used:
                return
            with ui.row().classes("w-full items-center gap-3"):
                c.label("Mechanics").classes("mb-0")
                for mechanic in used:
                    if mechanic.kind == MechanicKind.ABILITY_WORD:     # no reminder text
                        lines = [line for face in card.faces for line in face.rules_text.split("\n")
                                 if ability_words.starts_line(mechanic, line)]
                        off = [line for line in lines if ability_words.parse_line(mechanic, line) is None]
                        if off and mechanic.templates:
                            c.badge(f"{mechanic.name}: doesn't follow any variant", "warning")
                        else:
                            ui.label(mechanic.name).classes("italic")
                        continue
                    current = card.reminders.get(mechanic.id)
                    options = {"policy": f"{mechanic.name}: reminder as policy "
                                         f"({POLICY_LABELS[mechanic.reminder_policy.value].lower()})",
                               "show": f"{mechanic.name}: show reminder",
                               "hide": f"{mechanic.name}: hide reminder"}
                    value = "policy" if current is None else "show" if current else "hide"

                    def choose(e, mech=mechanic) -> None:
                        session.set_reminder(card, mech, None if e.value == "policy" else e.value == "show")
                        schedule_preview(now=True)
                    ui.select(options, value=value, on_change=choose) \
                        .props("dense options-dense outlined").classes("min-w-[260px]")
        row()
        return row

    def roles_row(card: Card):
        """The card's set-health roles (app/health/roles.py): detected ones, ones added
        by hand (marked), detected ones removed by hand (struck through, click to restore)."""
        @ui.refreshable
        def row() -> None:
            detected = detected_roles(card, session.project)
            from_mechanics = mechanic_roles(card, session.project)
            overrides = card.role_overrides

            def set_role(rid: str, value) -> None:
                session.set_role(card, rid, value)
                row.refresh()
            with ui.row().classes("w-full items-center gap-1").mark("roles"):
                c.label("Roles").classes("mb-0 mr-2") \
                    .tooltip("What the card does in the set, for Health")
                for rid, role in ROLES.items():
                    found, override = rid in detected, overrides.get(rid)
                    if found and override is False:
                        ui.chip(role.label, icon="undo", on_click=lambda r=rid: set_role(r, None)) \
                            .props("dense outline clickable").classes("text-xs line-through opacity-60") \
                            .tooltip("Removed by hand; click to restore")
                    elif found or override:
                        mechanics = from_mechanics.get(rid)
                        icon = "auto_fix_high" if mechanics else None if found else "person"
                        tip = (f"From {', '.join(mechanics)}" if mechanics
                               else "Detected from the rules text" if found else "Added by hand")
                        ui.chip(role.label, removable=True, icon=icon,
                                on_value_change=lambda e, r=rid, f=found: set_role(r, False if f else None)) \
                            .props("dense").classes("text-xs").tooltip(tip)
                missing = [rid for rid in ROLES if rid not in detected and not overrides.get(rid)]
                if missing:
                    with c.button(icon="add", kind="icon", tooltip="Add a role").props("size=sm"):
                        with ui.menu():
                            for rid in missing:
                                ui.menu_item(ROLES[rid].label, on_click=lambda r=rid: set_role(r, True))
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
                    c.button(option.label, kind="secondary", on_click=lambda o=option: accept(field, o)) \
                        .props("dense size=sm")
                c.hint("Tab to accept the first").classes("self-center")

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

    def symbol_palette(field: str, costs_only: bool = False) -> None:
        """Buttons inserting symbols (and CARDNAME / mechanics for rules text)."""
        with ui.row().classes("ds-palette gap-0.5 items-center"):
            for symbol in PALETTE if not costs_only else [s for s in PALETTE if s not in "TQ"]:
                with c.button(kind="ghost", on_click=lambda s=symbol: insert(field, f"{{{s}}}"),
                              tooltip=f"{{{symbol}}}").props("dense").classes("ds-symbol"):
                    c.mana_cost(f"{{{symbol}}}")
            if not costs_only:
                ui.element("div").classes("ds-sep")
                c.button("CARDNAME", kind="ghost", on_click=lambda: insert(field, "CARDNAME"),
                         tooltip="This card's name").props("dense size=sm")
                for mechanic in session.project.mechanics:
                    variants = text_input.ability_word_inserts(mechanic)
                    if len(variants) > 1:                  # ability word: pick a variant
                        with c.button(mechanic.name, kind="ghost").props("dense size=sm"):
                            with ui.menu():
                                for label, text, start, length in variants:
                                    ui.menu_item(label, on_click=lambda t=text, a=start, n=length:
                                                 insert(field, t, a, n))
                    elif variants:
                        _, text, start, length = variants[0]
                        c.button(mechanic.name, kind="ghost", on_click=lambda t=text, a=start, n=length:
                                 insert(field, t, a, n)).props("dense size=sm")
                    else:
                        snippet, _ = text_input.mechanic_insert(mechanic)
                        c.button(mechanic.name, kind="ghost", on_click=lambda s=snippet: insert(field, s)) \
                            .props("dense size=sm")

    def form_section(title: str) -> None:
        ui.label(title).classes("ds-form-h")

    # ------------------------------------------------------------ header
    with m.actions:
        status = c.status("All changes saved")
        ui.element("div").classes("ds-sep")
        c.button(icon="chevron_left", kind="icon", on_click=lambda: step(-1),
                 tooltip="Previous card · Ctrl+[").mark("prev-card")
        c.button(icon="chevron_right", kind="icon", on_click=lambda: step(1),
                 tooltip="Next card · Ctrl+]").mark("next-card")
        c.button(icon="view_list", kind="icon", on_click=toggle_list, tooltip="Card list")
        c.button(icon="add", kind="icon", on_click=new_card, tooltip="New card · Ctrl+N")
        with c.button(icon="more_horiz", kind="icon", tooltip="More"):
            with ui.menu().props("anchor='bottom right' self='top right'"):
                ui.menu_item("Duplicate · Ctrl+D", on_click=lambda: view["card"] and duplicate(view["card"]))
                ui.menu_item("Delete…", on_click=lambda: view["card"] and delete(view["card"])) \
                    .classes("text-negative")

    # ------------------------------------------------------------ layout
    # three columns filling the modal, each scrolling on its own
    grid = ui.element("div").classes("ds-editor" + ("" if view["list_open"] else " list-closed"))
    with grid:
        # ---- card list
        with ui.element("div").classes("ds-editor-list"):
            search = ui.input(placeholder="Search cards").props("dense outlined clearable") \
                .classes("w-full px-3 pt-3 pb-2")
            search.on_value_change(lambda e: (view.update(query=e.value or ""), card_list.refresh()))

            @ui.refreshable
            def card_list() -> None:
                with ui.element("div").classes("ds-editor-scroll"):
                    for card in session.search(view["query"]):
                        active = view["card"] is not None and card.id == view["card"].id
                        with c.list_row(selected=active, on_click=lambda x=card: select(x)):
                            ui.label(number_label(card)).classes("faint num text-xs w-8")
                            c.pips(card.color_identity)
                            ui.label(card.faces[0].name or "(no name)").classes("grow truncate")
                            c.rarity_letter(card.rarity)
            card_list()

        # ---- form
        with ui.element("div").classes("ds-editor-form"):
            @ui.refreshable
            def card_form() -> None:
                card = view["card"]
                if card is None:
                    c.empty_state("style", "No cards yet", action="New card", on_action=new_card)
                    return
                face = card.faces[0]
                if len(card.faces) > 1:
                    c.hint(f"This is a {card.layout.value} card; editing its other face comes in a "
                           "later version. Showing the front face.")
                form_section("Identity")
                # field rows are grids: they use the column's width and wrap when narrow
                with responsive_grid(160, columns="minmax(0, 2fr) minmax(140px, 1fr)"):
                    ui.input("Name", value=face.name,
                             on_change=lambda e: changed("name", e.value)).classes("w-full")
                    with ui.column().classes("w-full gap-0"):
                        text_field("mana_cost", "Mana cost", face.mana_cost, "w-full")
                symbol_palette("mana_cost", costs_only=True)
                # two fields so nobody has to type the "—" (added when both are filled)
                types, subtypes = split_type_line(face.type_line)
                with responsive_grid(200, gap=16):
                    ui.input("Types", value=types, placeholder="Legendary Creature",
                             on_change=lambda e: changed("types", e.value)).classes("w-full")
                    ui.input("Subtypes", value=subtypes, placeholder="Elf Druid",
                             on_change=lambda e: changed("subtypes", e.value)).classes("w-full")

                form_section("Text")
                symbol_palette("rules_text")
                text_field("rules_text", "Rules text", face.rules_text, "w-full", textarea=True)
                view["mechanics"] = mechanics_row(card)
                view["roles"] = roles_row(card)
                ui.textarea("Flavor text", value=face.flavor_text,
                            on_change=lambda e: changed("flavor_text", e.value)) \
                    .props("autogrow").classes("w-full")

                form_section("Art")
                view["art"] = art_editor(session, card, schedule_preview)

                form_section("Stats and set data")
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
                cycle = next((x for x in session.project.cycles if x.id == card.cycle), None)
                if cycle is not None:
                    c.button(f"Cycle: {cycle.name}", kind="ghost", icon="donut_large",
                             on_click=lambda: open_cycle(cycle.id)).props("dense").classes("self-start")
                form_section("Notes")
                ui.textarea("Notes", value=card.notes,
                            on_change=lambda e: changed("notes", e.value)) \
                    .props("autogrow").classes("w-full")
            card_form()

        # ---- preview
        with ui.element("div").classes("ds-editor-preview"):
            preview_box = ui.element("div").classes("ds-preview-box")
            with preview_box:
                preview = ui.image().props("fit=contain no-spinner no-transition").classes("ds-preview")
            preview_note = c.hint("Starting the renderer…")

    # ------------------------------------------------------ timers
    async def tick() -> None:
        if session.unsaved:
            status.text = "Saving…"
            status.style("--dot: var(--text-faint)")
        else:
            status.text = "All changes saved"
            status.style("--dot: var(--success)")
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
    retitle()
    schedule_preview(now=True)

    # ------------------------------------------------------ keyboard
    def on_key(e) -> None:
        if not e.action.keydown or not e.modifiers.ctrl or not m.dialog.value:
            return
        key = e.key.name.lower() if hasattr(e.key, "name") else str(e.key).lower()
        if key == "n":
            new_card()
        elif key == "d" and view["card"] is not None:
            duplicate(view["card"])
        elif key == "f":
            search.run_method("focus")
        elif key in ("[", "bracketleft"):
            step(-1)
        elif key in ("]", "bracketright"):
            step(1)

    ui.keyboard(on_key=on_key, ignore=[])
