"""The card editor: a workspace modal over the set (card list | the card | side panel).

The rendered card is the editor: each part the frame draws (name, cost, type line, text
box, P/T, art, ...) is a hotspot, placed from the frame's layout (CardRenderer.field_boxes);
clicking it opens a small popover editing just that part. The side panel holds what isn't
printed on the card (rarity, number, status, frame, archetypes, notes) and lists the parts,
which also reaches parts this frame doesn't draw. Tab walks from part to part.

    with modal("workspace", card.faces[0].name, parent=shell.dialogs) as m:
        editor_panel(state, m, card.id, order=..., open_cycle=..., on_card=...)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from nicegui import run, ui

from ..app import ability_words, text_input
from ..app.health.roles import ROLES, detected_roles, mechanic_roles
from ..app import balance as bal
from ..model import Card, Layout, MechanicKind, Rarity, Status, validate_card
from ..model.card import COLOR_NAMES, COLORS
from ..model.layouts import TRANSFORM_SYMBOL_LABELS
from ..mse import game_keywords as gk
from ..mse.mapping import split_type_line
from . import components as c
from . import renderer_notice
from .art_editor import art_editor
from .mechanics_page import POLICY_LABELS
from .uploads import set_paste_target
from .widgets import card_name, number_label, responsive_grid, served_url

SYMBOLS = ["W", "U", "B", "R", "G", "C", "X", "T", "Q", "S", "0", "1", "2", "3", "4", "5", "6",
           "7", "8", "9", "W/U", "U/B", "B/R", "R/G", "G/W", "W/B", "U/R", "B/G", "R/W", "G/U"]
COST_SYMBOLS = [x for x in SYMBOLS if x not in ("T", "Q")]
PART_LABELS = {"name": "Name", "cost": "Mana cost", "type": "Type line", "text": "Rules & flavor",
               "pt": "Power / toughness", "loyalty": "Loyalty", "art": "Art", "indicator": "Color indicator",
               "artist": "Artist"}
PREVIEW_DELAY = 0.3                      # seconds after the last keystroke
COLOR_WORDS = {letter: name.title() for name, letter in COLOR_NAMES.items()}
LAYOUT_LABELS = {Layout.NORMAL.value: "Single", Layout.TRANSFORM.value: "Transform",
                 Layout.MDFC.value: "Modal DFC"}
BACK_FIELDS = ("name", "mana_cost", "type_line", "rules_text", "flavor_text", "power", "toughness",
               "loyalty", "art_path")   # a back face with any of these has content to lose


def editor_panel(state, m: c.Modal, card_id: str, *, order: Callable[[], list[Card]],
                 open_cycle: Callable[[str], None], on_card: Callable[[Card | None], None],
                 open_part_name: str | None = None, outlines: bool = False,
                 open_balance: Callable[[str], None] | None = None) -> None:
    """Build the editor into the modal `m`, showing `card_id`. `order()` is the workspace's
    card order (previous / next); `on_card` runs when another card is shown;
    `open_part_name` opens that part's editor once the card is shown ("name", "text", ...)."""
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
        "face": 0,                        # the face shown in the form and the preview
        "faces_row": None,                # the layout and Front / Back row's refreshable
        "boxes": {},                      # part -> (left, top, width, height), fractions of the card
        "boxes_pending": False,           # new boxes came while a part was open
        "hotspot_menus": {},              # part -> its popover on the card
        "row_menus": {},                  # part -> its popover in the side panel (not on the card)
        "open_part": None,                # the part being edited, if any
        "open_first": open_part_name,     # a part to open once the card is shown (?part=)
    }

    # ------------------------------------------------------------ actions
    def select(card: Card | None) -> None:
        session.flush()
        view["card"] = card
        view["face"] = 0
        close_parts()
        card_list.refresh()
        refresh_card_view()
        art_target(card)
        retitle()
        show_provisional()
        schedule_preview(now=True)
        on_card(card)

    def retitle() -> None:
        card = view["card"]
        m.title.text = card_name(card) if card else "No cards"
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
        """Pasted images and images dropped on the preview go to this card (the face shown)."""
        set_paste_target(card.id if card else None, view["face"])
        if card is not None:
            preview_box.props(f'data-art-card="{card.id}" data-art-face="{view["face"]}"')
        else:
            preview_box.props(remove="data-art-card data-art-face")

    def show_face(face: int) -> None:
        """Show the front (0) or the back (1) in the form and the preview."""
        card = view["card"]
        if card is None or not 0 <= face < len(card.faces) or face == view["face"]:
            return
        session.flush()
        close_parts()
        view["face"] = face
        refresh_card_view()
        art_target(card)
        show_provisional()
        schedule_preview(now=True)

    def show_provisional() -> None:
        """Until the face is drawn: its overview picture if there is one (sharp render
        follows), else a shimmering card, with the progress line along the bottom."""
        card = view["card"]
        if card is None:
            return
        path = session.thumbnails.get(card, view["face"])
        preview.set_source(served_url(session.thumbnails.cache.folder, path) if path else "")
        preview_box.classes(add="pending")
        preview_box.classes(remove="empty") if path else preview_box.classes(add="empty")

    def refresh_card_view() -> None:
        """Another card or face: the layout row, the hotspots (until new boxes come) and
        the side panel."""
        faces_row.refresh()
        hotspots.refresh()
        side_panel.refresh()

    def toggle_indicator(color: str) -> None:
        card = view["card"]
        if card is None:
            return
        current = set(card.faces[view["face"]].color_indicator)
        current ^= {color}
        changed("color_indicator", "".join(x for x in COLORS if x in current))
        indicator_toggles.refresh()

    def flip() -> None:
        card = view["card"]
        if card is not None and len(card.faces) > 1:
            show_face(1 - view["face"])

    async def change_layout(value: str) -> None:
        """Single / Transform / Modal DFC, asking first when the back would lose content."""
        card = view["card"]
        layout = Layout(value)
        if card is None or layout == card.layout:
            return
        back = card.faces[1] if len(card.faces) > 1 else None
        if back is not None and layout == Layout.NORMAL and any(getattr(back, f) for f in BACK_FIELDS):
            question = (f"Remove the back face “{back.name or '(no name)'}”?",
                        "Its name, text and art go; the front stays as it is.", "Remove back face")
        elif back is not None and layout == Layout.TRANSFORM and back.mana_cost:
            question = ("Remove the back face's mana cost?",
                        f"Transform backs have no mana cost, so {back.mana_cost} is removed.", "Remove cost")
        else:
            question = None
        if question and await c.confirm(m.body, question[0], question[1], confirm_label=question[2]) != "confirm":
            faces_row.refresh()                       # put the switch back
            return
        new_back = len(card.faces) == 1 and layout != Layout.NORMAL
        session.set_layout(card, layout)
        view["face"] = 1 if new_back else min(view["face"], len(card.faces) - 1)
        close_parts()
        card_list.refresh()
        refresh_card_view()
        retitle()
        art_target(card)
        schedule_preview(now=True)

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
        keywords = [k.name for k in gk.used(card, session.project)] if field == "rules_text" else []
        session.update(card, field, value, face=view["face"])
        if field in ("mana_cost", "rules_text", "power", "toughness", "rarity", "types", "subtypes", "type_line"):
            balance_badge.refresh()
        if field in ("name", "collector_number", "rarity", "mana_cost", "color_indicator"):
            card_list.refresh()
            retitle()
            if field == "name" and view["faces_row"] is not None:
                view["faces_row"].refresh()       # the Front / Back switch shows the names
        ability_word = any(x.kind == MechanicKind.ABILITY_WORD and x.id in card.mechanics
                           for x in session.project.mechanics)
        if view["mechanics"] is not None and (card.mechanics != used
                                              or (field == "rules_text" and ability_word)
                                              or (field == "rules_text" and keywords
                                                  != [k.name for k in gk.used(card, session.project)])):
            view["mechanics"].refresh()     # a mechanic appeared or went, or a variant check
        if field in ("rules_text", "name", "types") and view["roles"] is not None:
            view["roles"].refresh()         # detection reads the text and the types
        schedule_preview()

    def mechanics_row(card: Card):
        """One chip per mechanic on the card, each with its reminder-text choice; then
        Magic's own keywords on it (Flying, Cycling...), with the same choice."""
        @ui.refreshable
        def row() -> None:
            used = [x for x in session.project.mechanics if x.id in card.mechanics]
            keywords = [k for k in gk.used(card, session.project) if k.reminder]
            if not used and not keywords:
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
                for kw in keywords:
                    current = card.reminders.get(kw.card_key)
                    policy = POLICY_LABELS[gk.policy(session.project, kw).value].lower()
                    options = {"policy": f"{kw.name}: reminder as set ({policy})",
                               "show": f"{kw.name}: show reminder", "hide": f"{kw.name}: hide reminder"}
                    value = "policy" if current is None else "show" if current else "hide"

                    def choose_kw(e, name=kw.name) -> None:
                        session.set_keyword_reminder(card, name, None if e.value == "policy" else e.value == "show")
                        schedule_preview(now=True)
                    ui.select(options, value=value, on_change=choose_kw) \
                        .props("dense options-dense outlined").classes("min-w-[260px]") \
                        .mark(f"keyword-reminder-{kw.key}").tooltip(kw.preview())
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
                        ui.chip(role.label, icon="undo", color=None, on_click=lambda r=rid: set_role(r, None)) \
                            .props("dense outline clickable").classes("text-xs line-through opacity-60") \
                            .tooltip("Removed by hand; click to restore")
                    elif found or override:
                        mechanics = from_mechanics.get(rid)
                        icon = "auto_fix_high" if mechanics else None if found else "person"
                        tip = (f"From {', '.join(mechanics)}" if mechanics
                               else "Detected from the rules text" if found else "Added by hand")
                        ui.chip(role.label, removable=True, icon=icon, color=None,
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
        # in rules text, "Raid - " becomes "Raid — " as you type (text_input.long_dashes,
        # which saving applies too), the caret kept where it was
        dashes = "" if field != "rules_text" else (
            r"const t = e.target, re = /^([A-Z][A-Za-z']*(?: [A-Za-z']+){0,3}) ?(?:--|-|–)(?= |$)/gm;"
            r" const v = t.value.replace(re, (m, a) => a + ' —');"
            r" if (v !== t.value) { const p = t.selectionStart - (t.value.length - v.length);"
            r" t.value = v; t.dispatchEvent(new Event('input'));"
            r" for (const ms of [0, 60, 200]) setTimeout(() => t.setSelectionRange(p, p), ms); }")
        element.on("keyup", on_caret,
                   js_handler="(e) => { " + dashes + " if (e.key !== 'Tab') emit(e.target.selectionStart); }")
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

    def symbol_menu(field: str, costs_only: bool = False) -> None:
        """The symbol picker, on demand: a button opening a grid of symbols."""
        with c.button(icon="add_circle_outline", kind="icon", tooltip="Insert a symbol").props("size=sm") \
                .mark(f"symbols-{field}"):
            with ui.menu():
                with ui.element("div").classes("ds-symbol-grid"):
                    for symbol in COST_SYMBOLS if costs_only else SYMBOLS:
                        with ui.button(on_click=lambda s=symbol: insert(field, f"{{{s}}}")) \
                                .props("flat dense").classes("ds-symbol").tooltip(f"{{{symbol}}}"):
                            c.mana_cost(f"{{{symbol}}}")

    def text_extras(field: str) -> None:
        """CARDNAME and the set's mechanics (with ability-word variants), for rules text."""
        c.button("CARDNAME", kind="ghost", on_click=lambda: insert(field, "CARDNAME"),
                 tooltip="This card's name").props("dense size=sm")
        if session.project.mechanics:
            with c.button("Mechanic", kind="ghost", icon="expand_more").props("dense size=sm"):
                with ui.menu():
                    for mechanic in session.project.mechanics:
                        variants = text_input.ability_word_inserts(mechanic)
                        if variants:
                            for label, text, start, length in variants:
                                ui.menu_item(f"{mechanic.name} · {label}" if len(variants) > 1 else mechanic.name,
                                             on_click=lambda t=text, a=start, n=length: insert(field, t, a, n))
                        else:
                            snippet, _ = text_input.mechanic_insert(mechanic)
                            ui.menu_item(mechanic.name, on_click=lambda x=snippet: insert(field, x))

    # ------------------------------------------------------------ parts of the card
    def current_face():
        card = view["card"]
        return card.faces[min(view["face"], len(card.faces) - 1)]

    def parts_for(card: Card) -> list[str]:
        """The parts the side panel lists (and Tab walks), for the face shown."""
        face = current_face()
        back = view["face"] == 1
        parts = ["name"]
        if not (back and card.layout == Layout.TRANSFORM):
            parts.append("cost")
        parts += ["type", "text", "pt"]
        if face.loyalty or "planeswalker" in face.type_line.lower():
            parts.append("loyalty")
        parts.append("art")
        if back or face.color_indicator:
            parts.append("indicator")
        return parts + ["artist"]

    def summary(part: str) -> str:
        """One muted line: the part's current value."""
        face = current_face()
        values = {"name": face.name, "cost": face.mana_cost, "type": face.type_line,
                  "text": face.rules_text.replace("\n", " · "),
                  "pt": f"{face.power}/{face.toughness}" if face.power or face.toughness else "",
                  "loyalty": face.loyalty or "", "art": Path(face.art_path).name if face.art_path else "",
                  "indicator": face.color_indicator, "artist": face.artist}
        return values.get(part) or "—"

    def open_part(part: str) -> None:
        """Open a part's editor: on the card if it shows there, else beside its panel row."""
        menu = view["hotspot_menus"].get(part) or view["row_menus"].get(part)
        if menu is not None and not menu.is_deleted:
            menu.open()

    def close_parts() -> None:
        for menu in [*view["hotspot_menus"].values(), *view["row_menus"].values()]:
            if not menu.is_deleted and menu.value:
                menu.close()

    def goto(part: str, step_by: int) -> None:
        """Tab / Shift+Tab out of a part's editor: the next or previous part."""
        card = view["card"]
        if card is None:
            return
        parts = parts_for(card)
        here = parts.index(part) if part in parts else 0
        close_parts()
        target = parts[(here + step_by) % len(parts)]
        ui.timer(0.15, lambda: open_part(target), once=True)     # after the closing one

    def part_menu(part: str) -> ui.menu:
        """A popover holding the part's editor, built when it opens (so it starts with the
        current values and its first field focused) and cleared when it closes."""
        menu = ui.menu().props("anchor='bottom left' self='top left' :offset='[0, 6]'") \
            .classes("ds-part-menu" + (" wide" if part in ("text", "art") else ""))

        def toggled(e) -> None:
            if e.value:
                view["open_part"] = part
                menu.clear()
                with menu:
                    part_editor(part, menu)
            else:
                if view["open_part"] == part:
                    view["open_part"] = None
                menu.clear()
                side_panel.refresh()                 # its one-line summaries
                if view["boxes_pending"]:
                    view["boxes_pending"] = False
                    hotspots.refresh()
        menu.on_value_change(toggled)
        return menu

    def part_editor(part: str, menu: ui.menu) -> None:
        card, face = view["card"], current_face()
        editor = ui.element("div").classes(f"ds-part-editor {part}").mark(f"editor-{part}")
        # Tab out of the last field (or Shift+Tab out of the first) goes to the next part;
        # a Tab that accepted a suggestion was handled already (defaultPrevented)
        editor.on("keydown", lambda e: goto(part, int(e.args)), js_handler=(
            "(e) => { if (e.key !== 'Tab' || e.defaultPrevented) return;"
            " const f = [...e.currentTarget.querySelectorAll('input, textarea')];"
            " if (!f.length) return;"
            " if (!e.shiftKey && e.target === f[f.length - 1]) { e.preventDefault(); emit(1); }"
            " else if (e.shiftKey && e.target === f[0]) { e.preventDefault(); emit(-1); } }"))
        with editor:
            with ui.row().classes("w-full items-center no-wrap gap-1"):
                ui.label(PART_LABELS[part]).classes("ds-part-title grow")
                if part == "cost":
                    symbol_menu("mana_cost", costs_only=True)
                elif part == "text":
                    symbol_menu("rules_text")
                    text_extras("rules_text")
            if part == "name":
                field = ui.input(value=face.name, on_change=lambda e: changed("name", e.value)) \
                    .props("autofocus dense outlined").classes("w-full").mark("face-name")
                field.on("keydown.enter", menu.close)
            elif part == "cost":
                field = text_field("mana_cost", "", face.mana_cost, "w-full")
                field.props("autofocus dense outlined placeholder={2}{W}")
                field.on("keydown.enter", menu.close)
            elif part == "type":
                types, subtypes = split_type_line(face.type_line)
                with ui.row().classes("w-full no-wrap gap-2"):
                    ui.input("Types", value=types, placeholder="Legendary Creature",
                             on_change=lambda e: changed("types", e.value)) \
                        .props("autofocus dense outlined").classes("grow")
                    ui.input("Subtypes", value=subtypes, placeholder="Elf Druid",
                             on_change=lambda e: changed("subtypes", e.value)) \
                        .props("dense outlined").classes("grow")
            elif part == "text":
                field = text_field("rules_text", "Rules text", face.rules_text, "w-full", textarea=True)
                field.props("autofocus outlined")
                view["mechanics"] = mechanics_row(card)
                ui.textarea("Flavor text", value=face.flavor_text,
                            on_change=lambda e: changed("flavor_text", e.value)) \
                    .props("autogrow outlined").classes("w-full")
            elif part == "pt":
                with ui.row().classes("w-full no-wrap gap-2 items-center"):
                    ui.input("Power", value=face.power or "", on_change=lambda e: changed("power", e.value)) \
                        .props("autofocus dense outlined").classes("w-24")
                    ui.label("/").classes("muted")
                    toughness = ui.input("Toughness", value=face.toughness or "",
                                         on_change=lambda e: changed("toughness", e.value)) \
                        .props("dense outlined").classes("w-24")
                    toughness.on("keydown.enter", menu.close)
            elif part == "loyalty":
                field = ui.input(value=face.loyalty or "", on_change=lambda e: changed("loyalty", e.value)) \
                    .props("autofocus dense outlined").classes("w-24")
                field.on("keydown.enter", menu.close)
                c.hint("Abilities go in the rules text, one per line: +1: Draw a card.")
            elif part == "art":
                view["art"] = art_editor(session, card, schedule_preview, face=view["face"])
            elif part == "indicator":
                indicator_toggles()
            elif part == "artist":
                field = ui.input(value=face.artist, placeholder=session.project.info.artist or "",
                                 on_change=lambda e: changed("artist", e.value)) \
                    .props("autofocus dense outlined").classes("w-full")
                field.on("keydown.enter", menu.close)

    @ui.refreshable
    def indicator_toggles() -> None:
        face = current_face()
        with ui.row().classes("items-center gap-1"):
            for color in COLORS:
                with ui.button(on_click=lambda col=color: toggle_indicator(col)).props("flat round dense") \
                        .classes("ds-color-toggle" + (" on" if color in face.color_indicator else "")) \
                        .tooltip(COLOR_WORDS[color]).mark(f"indicator-{color}"):
                    c.mana_cost(f"{{{color}}}")

    def spin_off(card: Card) -> None:
        """A notebook idea that starts from this card (linked to it, in the Inbox)."""
        from .notebook_capture import capture_idea
        capture_idea(state, parent=m.body, prefill={"title": f"Variant of {card.faces[0].name}",
                                                   "links": [{"kind": "card", "id": card.id}]})

    @ui.refreshable
    def balance_badge() -> None:
        """How the card scores for its cost (app.balance); click: the breakdown in Balance."""
        card = view["card"]
        s = bal.score(card, session.project) if card is not None else None
        if s is None:
            return
        from .balance_page import VERDICTS, verdict_text
        b = c.badge(f"Balance: {verdict_text(s)}", VERDICTS[s.verdict][1]).mark("balance-badge")             .tooltip(f"Worth {s.effective:g} mana, costs {s.actual}"
                     + (f"; {len(s.unscored)} line(s) not scored" if s.unscored else ""))
        if open_balance is not None:
            b.classes("cursor-pointer").on("click", lambda: open_balance(card.id))

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
                if open_balance is not None:
                    ui.menu_item("Balance…", on_click=lambda: view["card"] and open_balance(view["card"].id))                         .mark("open-balance")
                ui.menu_item("Spin off an idea…", on_click=lambda: view["card"] and spin_off(view["card"]))                     .mark("spin-off-idea")
                ui.menu_item("Delete…", on_click=lambda: view["card"] and delete(view["card"])) \
                    .classes("text-negative")

    # ------------------------------------------------------------ layout
    # three columns filling the modal: the card list | the card | the side panel
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
                            ui.label(card_name(card)).classes("grow truncate")
                            c.rarity_letter(card.rarity)
            card_list()

        # ---- the card: click a part to edit it
        with ui.element("div").classes("ds-editor-stage"):
            @ui.refreshable
            def faces_row() -> None:
                """The card's layout, and which face is shown."""
                card = view["card"]
                if view.get("flip") is not None:
                    view["flip"].set_visibility(card is not None and len(card.faces) > 1)
                if card is None:
                    return
                with ui.row().classes("ds-faces-row items-center justify-center gap-3"):
                    c.segmented(LAYOUT_LABELS, card.layout.value,
                                lambda e: change_layout(e.value)).mark("card-layout")
                    if len(card.faces) > 1:
                        names = {i: f"{label} · {card.faces[i].name or '(no name)'}"
                                 for i, label in enumerate(("Front", "Back"))}
                        c.segmented(names, view["face"], lambda e: show_face(int(e.value))) \
                            .classes("ds-face-switch").mark("card-face")
            view["faces_row"] = faces_row
            faces_row()

            with ui.element("div").classes("ds-card-area"):
                preview_box = ui.element("div").classes("ds-card-box" + (" show-outlines" if outlines else ""))
                with preview_box:
                    preview = ui.image().props("fit=fill no-spinner").classes("ds-preview")   # fill: hotspots are fractions of the card
                    ui.element("div").classes("ds-card-progress")

                    @ui.refreshable
                    def hotspots() -> None:
                        """Clickable parts over the picture, where the frame draws them."""
                        view["hotspot_menus"] = {}
                        card = view["card"]
                        if card is None:
                            return
                        # the art first: on some frames it spans the text, which must stay on top
                        for part, (left, top, width, height) in sorted(view["boxes"].items(),
                                                                       key=lambda item: item[0] != "art"):
                            spot = ui.element("div").classes("ds-hotspot").mark(f"part-{part}").props(
                                f'data-label="{PART_LABELS[part]}"').style(
                                f"left:{left * 100:.2f}%;top:{top * 100:.2f}%;"
                                f"width:{width * 100:.2f}%;height:{height * 100:.2f}%")
                            spot.on("click", lambda p=part: open_part(p))
                            with spot:
                                view["hotspot_menus"][part] = part_menu(part)
                    hotspots()
                    flip_button = c.button(icon="flip", kind="icon", on_click=flip,
                                           tooltip="Show the other face · Ctrl+.") \
                        .classes("ds-flip").mark("flip-face")
                    view["flip"] = flip_button
                    flip_button.set_visibility(view["card"] is not None and len(view["card"].faces) > 1)
            preview_note = c.hint("").classes("text-center")
            renderer_notice.notice(session, compact=True)

        # ---- side panel: what isn't printed on the card, and a list of what is
        with ui.element("div").classes("ds-editor-side"):
            @ui.refreshable
            def side_panel() -> None:
                view["row_menus"] = {}
                card = view["card"]
                if card is None:
                    c.empty_state("style", "No cards yet", action="New card", on_action=new_card)
                    return
                for problem in validate_card(card):
                    c.status(problem[0].upper() + problem[1:], "warning")
                balance_badge()
                face_label = "" if len(card.faces) == 1 else (" · front" if view["face"] == 0 else " · back")
                ui.label(f"On this card{face_label}").classes("ds-form-h")
                c.hint("Click a part of the card, or a line here, to edit it. Tab moves on.")
                with ui.element("div").classes("ds-part-list"):
                    for part in parts_for(card):
                        row = ui.element("div").classes("ds-part-row").mark(f"row-{part}")
                        with row:
                            ui.label(PART_LABELS[part]).classes("label")
                            ui.label(summary(part)).classes("value")
                            row.on("click", lambda p=part: open_part(p))
                            if part not in view["boxes"]:     # not drawn on this frame: edit it here
                                view["row_menus"][part] = part_menu(part)

                ui.label("Card" if len(card.faces) == 1 else "Card (both faces)").classes("ds-form-h")
                with responsive_grid(120, gap=10):
                    ui.select({r.value: r.value.title() for r in Rarity}, value=card.rarity.value,
                              label="Rarity", on_change=lambda e: changed("rarity", e.value)).classes("w-full")
                    ui.input("Number", value=card.collector_number,
                             on_change=lambda e: changed("collector_number", e.value)).classes("w-full")
                    ui.select({s.value: s.value.title() for s in Status}, value=card.status.value,
                              label="Status", on_change=lambda e: changed("status", e.value)).classes("w-full")
                    ui.number("Print copies", value=card.print_copies, min=0, format="%d",
                              on_change=lambda e: changed("print_copies", e.value)).classes("w-full") \
                        .tooltip("Copies in a print by rarity; empty follows the card's rarity")
                ui.select({"": "Set default", **FRAME_LABELS}, value=card.frame or "",
                          label="Frame", on_change=lambda e: changed("frame", e.value)).classes("w-full")
                if card.layout == Layout.TRANSFORM:
                    ui.select(TRANSFORM_SYMBOL_LABELS, value=card.transform_symbol, label="Transform symbol",
                              on_change=lambda e: changed("transform_symbol", e.value or "")) \
                        .classes("w-full").mark("transform-symbol") \
                        .tooltip("The front's symbol; the back gets its pair")
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
                view["roles"] = roles_row(card)
                for idea in session.ideas_for("card", card.id):
                    with ui.row().classes("items-center gap-2 no-wrap w-full"):
                        ui.icon("lightbulb").classes("text-[16px] faint")
                        ui.label(f"From idea: {idea.title or idea.body[:60]}").classes("text-sm muted truncate")                             .tooltip(idea.body or idea.title).mark("from-idea")
                with ui.expansion("Notes", value=bool(card.notes)).classes("w-full ds-notes"):
                    ui.textarea(value=card.notes, placeholder="Design notes, playtest feedback…",
                                on_change=lambda e: changed("notes", e.value)) \
                        .props("autogrow outlined").classes("w-full")
            side_panel()
    renderer_seen = {"version": renderer_notice.health(session).version}

    # ------------------------------------------------------ timers
    async def tick() -> None:
        if session.unsaved:
            status.text = "Saving…"
            status.style("--dot: var(--text-faint)")
        else:
            status.text = "All changes saved"
            status.style("--dot: var(--success)")
        session.flush_due()
        renderer_health = renderer_notice.health(session)
        if renderer_health.version != renderer_seen["version"]:
            renderer_seen["version"] = renderer_health.version
            if renderer_health.phase == "fixed":     # Magic Set Editor works again: redraw
                schedule_preview(now=True)
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
            preview_box.classes(add="pending")
            generation, card, face = view["generation"], view["card"], view["face"]
            face = min(face, len(card.faces) - 1)
            try:
                # where the parts are first: it comes from the layout, so the card can be
                # edited before (and while) its picture is drawn
                boxes = await run.io_bound(session.field_boxes, card, face)
                if boxes is None or preview.is_deleted or generation != view["generation"]:
                    return                           # None: cancelled (the page or app is closing)
                if boxes != view["boxes"]:
                    view["boxes"] = boxes
                    if view["open_part"] is None:
                        await hotspots.refresh()         # now, so a part can open on the new ones
                        await side_panel.refresh()
                    else:
                        view["boxes_pending"] = True     # don't close the part being edited
                if view["open_first"]:
                    open_part(view["open_first"])
                    view["open_first"] = None
                image = await run.io_bound(session.render, card, face)
                if image is None:
                    return                           # cancelled
            except Exception as e:                   # never break the editor over a preview
                if not preview_note.is_deleted:
                    preview_note.text = f"Preview failed: {e}"
                return
            if preview.is_deleted:                    # the editor closed while the render waited
                return
            if generation == view["generation"]:      # skip stale results
                preview.set_source(image)
                preview_box.classes(remove="pending empty")
                stand_in = session.renderer_note and not renderer_notice.health(session).problem
                preview_note.text = "Drawn by the stand-in renderer" if stand_in else ""   # else: the notice
        elif view["card"] is None:
            preview.set_source("")
            preview_note.text = ""

    ui.timer(0.1, tick)
    art_target(view["card"])
    retitle()
    show_provisional()
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
        elif key in (".", "period"):
            flip()

    ui.keyboard(on_key=on_key, ignore=[])

    def on_enter(e) -> None:
        """Enter, outside any field, starts editing the card at its name."""
        if (e.action.keydown and not e.modifiers.ctrl and m.dialog.value and view["card"] is not None
                and view["open_part"] is None and (e.key.name if hasattr(e.key, "name") else "") == "Enter"):
            open_part("name")

    ui.keyboard(on_key=on_enter)                  # ignores keys typed into fields
