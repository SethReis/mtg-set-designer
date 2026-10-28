"""The set overview (home of an open set): every card, grouped in rows or in a matrix."""
from __future__ import annotations

from nicegui import ui

from ..app import overview as ov
from ..model import Card, Rarity, Status
from .uploads import add_art_script, set_paste_target
from .widgets import (CARD_RATIO, COLOR_PIPS, STACK_CSS, compact_tile, grid_cells, responsive_grid,
                      served_url)

THUMB_POLL = 0.5                         # seconds between checks for newly rendered pictures
COLOR_CHOICES = {k: v for k, v in ov.COLOR_LABELS.items()}


def thumbnail_url(folder, path) -> str:
    """Pictures are served straight from the cache folder."""
    return served_url(folder, path)


def register(state) -> None:

    @ui.page("/set")
    def overview_page() -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        view, settings = state.overview, state.settings
        ui.add_css(STACK_CSS)
        add_art_script()                         # drop an image on a card: its art
        set_paste_target(None)                   # no single card to paste into here
        art_seen = {"version": session.art_version}
        worker = session.thumbnails
        tiles: dict[str, list] = {}              # card id -> its placeholder containers
        seen = {"version": -1}

        def open_card(card: Card) -> None:
            ui.navigate.to(f"/set/card/{card.id}")

        def new_card() -> None:
            open_card(session.new_card())

        # ------------------------------------------------------------ header
        with ui.header().classes("items-center bg-slate-800 py-2"):
            ui.button(icon="arrow_back", on_click=lambda: (state.close(), ui.navigate.to("/"))) \
                .props("flat round color=white").tooltip("Back to sets")
            ui.label(session.project.info.name).classes("text-lg font-semibold")
            ui.label(session.project.info.code).classes("text-sm opacity-70")
            count = ui.label().classes("text-sm opacity-70 ml-2")
            ui.space()
            status = ui.label().classes("text-sm opacity-70")
            ui.button("Set", icon="settings", on_click=lambda: settings_dialog()) \
                .props("flat no-caps color=white").tooltip("Name, frame, symbol, rarity targets")
            ui.button("Mechanics", icon="auto_fix_high", on_click=lambda: ui.navigate.to("/set/mechanics")) \
                .props("flat no-caps color=white")
            ui.button("Archetypes", icon="hub", on_click=lambda: archetype_dialog()) \
                .props("flat no-caps color=white")
            ui.button("New card", icon="add", on_click=new_card).props("flat no-caps color=white")

        # ------------------------------------------------------------ toolbar
        factor_names = {name: f.label for name, f in ov.FACTORS.items()}

        def set_view(**values) -> None:
            for key, value in values.items():
                setattr(view, key, value)
            content.refresh()

        def set_setting(**values) -> None:
            for key, value in values.items():
                setattr(settings, key, value)
            settings.save(state.settings_path)
            content.refresh()

        def set_filter(**values) -> None:
            for key, value in values.items():
                setattr(view.filters, key, value)
            content.refresh()

        # one grid for every control: they stretch across the window and wrap onto more
        # rows as it narrows
        with responsive_grid(140).classes("pb-1"):
            with grid_cells():
                @ui.refreshable
                def factor_selects() -> None:
                    # rebuilt with the content, so they show changes made elsewhere (a matrix
                    # cell click switches to rows) without firing their own change handlers
                    ui.toggle({"rows": "Rows", "matrix": "Matrix"}, value=view.mode,
                              on_change=lambda e: set_view(mode=e.value, cell=None)) \
                        .props("no-caps spread").classes("w-full")
                    if view.mode == "rows":
                        ui.select(factor_names, value=view.group_by, label="Group by",
                                  on_change=lambda e: set_view(group_by=e.value, cell=None)) \
                            .classes("w-full")
                    else:
                        ui.select(factor_names, value=view.rows, label="Rows",
                                  on_change=lambda e: set_view(rows=e.value)).classes("w-full")
                        ui.select(factor_names, value=view.columns, label="Columns",
                                  on_change=lambda e: set_view(columns=e.value)).classes("w-full")
                factor_selects()
            ui.select({k: label for k, (label, _) in ov.SORTS.items()}, value=view.sort, label="Sort",
                      on_change=lambda e: set_view(sort=e.value)).classes("w-full")
            ui.toggle({"grid": "Grid", "stacks": "Stacks"}, value=settings.layout,
                      on_change=lambda e: set_setting(layout=e.value)) \
                .props("no-caps spread").classes("w-full").tooltip("Stacks overlap the cards: hover one to see it")
            ui.toggle({"images": "Images", "text": "Text"}, value=settings.tiles,
                      on_change=lambda e: set_setting(tiles=e.value)) \
                .props("no-caps spread").classes("w-full")
            with ui.column().classes("w-full gap-0"):
                ui.label("Card size").classes("text-xs text-gray-500")
                ui.slider(min=100, max=300, step=20, value=settings.tile_width) \
                    .on("change", lambda e: set_setting(tile_width=int(e.args))).classes("w-full") \
                    .props("dense")
            ui.input(placeholder="Search name, type, rules", value=view.filters.text) \
                .props("dense outlined clearable").classes("w-full").style("grid-column:span 2") \
                .on_value_change(lambda e: set_filter(text=e.value or ""))
            ui.select({s.value: s.value.title() for s in Status}, multiple=True, label="Status",
                      value=sorted(view.filters.statuses),
                      on_change=lambda e: set_filter(statuses=set(e.value or []))) \
                .props("dense use-chips clearable").classes("w-full")
            ui.select({r.value: r.value.title() for r in Rarity}, multiple=True, label="Rarity",
                      value=sorted(view.filters.rarities),
                      on_change=lambda e: set_filter(rarities=set(e.value or []))) \
                .props("dense use-chips clearable").classes("w-full")
            ui.select(COLOR_CHOICES, multiple=True, label="Color", value=sorted(view.filters.colors),
                      on_change=lambda e: set_filter(colors=set(e.value or []))) \
                .props("dense use-chips clearable").classes("w-full")

        # ------------------------------------------------------------ tiles
        def picture(card: Card, width: int) -> None:
            path = worker.get(card) if settings.tiles == "images" else None
            if path is not None:
                ui.element("img").props(f'src="{thumbnail_url(worker.cache.folder, path)}" '
                                        f'loading=lazy draggable=false') \
                    .style(f"width:{width}px;height:{round(width * CARD_RATIO)}px;display:block")
            else:
                compact_tile(card, width)

        def tile(card: Card, width: int, stacked: bool = False) -> None:
            box = ui.element("div").classes("cursor-pointer") \
                .on("click", lambda c=card: open_card(c)).mark(f"tile-{card.id}") \
                .props(f'data-art-card="{card.id}"')            # drop an image: the card's art
            if stacked:
                box.classes("stack-card")                # see STACK_CSS
            else:
                box.classes("hover:shadow-lg transition-shadow rounded").tooltip(card.faces[0].name)
            box.card, box.width = card, width
            tiles.setdefault(card.id, []).append(box)
            with box:
                picture(card, width)

        def stack(cards: list[Card], width: int) -> None:
            with ui.element("div").classes("card-stack").mark("stack") \
                    .style(f"--card-h:{round(width * CARD_RATIO)}px"):
                for card in cards:
                    tile(card, width, stacked=True)

        def update_tiles() -> None:
            """Swap text tiles for pictures that have been rendered meanwhile."""
            if worker.version == seen["version"]:
                return
            seen["version"] = worker.version
            for boxes in tiles.values():
                for box in boxes:
                    has_picture = any(c.tag == "img" for c in box.default_slot.children)
                    if not has_picture and worker.get(box.card) is not None:
                        box.clear()
                        with box:
                            picture(box.card, box.width)

        def target(*args) -> int | None:
            """A group's or cell's target, but not while filtering (the counts are partial)."""
            return None if view.filters.active else ov.target(session.project, *args)

        def heading(label: str, n: int, wanted: int | None) -> str:
            return f"{label} · {n}" + (f" / {wanted}" if wanted is not None else "")

        def cell_cards(cards: list[Card]) -> list[Card]:
            if view.cell is None:
                return cards
            rows, r, cols, c = view.cell
            p = session.project
            return [x for x in cards if r in ov.keys(x, ov.FACTORS[rows], p)
                    and c in ov.keys(x, ov.FACTORS[cols], p)]

        # ------------------------------------------------------------ content
        @ui.refreshable
        def content() -> None:
            factor_selects.refresh()
            tiles.clear()
            seen["version"] = -1
            project = session.project
            cards = ov.sort(ov.apply(view.filters, project.cards), view.sort)
            if view.mode == "rows":
                cards = cell_cards(cards)
            count.text = f"{len(cards)} of {len(project.cards)} cards" \
                if len(cards) != len(project.cards) else f"{len(project.cards)} cards"
            if settings.tiles == "images":
                worker.request(cards)
            if not project.cards:
                ui.label("No cards yet. Add one with “New card”.").classes("text-gray-500 m-4")
                return
            if view.mode == "rows":
                rows_view(cards)
            else:
                matrix_view(cards)

        def rows_view(cards: list[Card]) -> None:
            if view.cell is not None:
                rows, r, cols, c = view.cell
                labels = dict(ov.FACTORS[rows].options(session.project))
                labels2 = dict(ov.FACTORS[cols].options(session.project))
                with ui.row().classes("items-center gap-2"):
                    ui.chip(f"{labels.get(r, r)} · {labels2.get(c, c)}", removable=True,
                            on_value_change=lambda e: set_view(cell=None)).props("color=blue-1")
                    ui.label("(one matrix cell)").classes("text-sm text-gray-500")
            factor = ov.FACTORS[view.group_by]
            width = settings.tile_width
            groups = []                                      # (group, its target, collapse key)
            for g in ov.group(cards, factor, session.project):
                if view.cell is not None:                    # just the cell's group
                    rows, r, cols, c = view.cell
                    if g.key != r:
                        continue
                    wanted = target(ov.FACTORS[rows], r, ov.FACTORS[cols], c)
                else:
                    wanted = target(factor, g.key)
                groups.append((g, wanted, f"{factor.name}:{g.key}"))
            if settings.layout == "stacks":
                stacked_groups(groups, width)
                return
            for g, wanted, key in groups:
                with ui.expansion(heading(g.label, len(g.cards), wanted), value=key not in view.collapsed) \
                        .classes("w-full").props("dense header-class=text-base font-semibold") as section:
                    section.on_value_change(lambda e, k=key: view.collapsed.discard(k) if e.value
                                            else view.collapsed.add(k))
                    if not g.cards:
                        ui.label("No cards").classes("text-sm text-gray-400 ml-2")
                    # the same columns in every section, spread across the window
                    with ui.element("div").classes("w-full pr-2").style(
                            f"display:grid;grid-template-columns:repeat(auto-fill,{width}px);"
                            "justify-content:space-between;gap:12px"):
                        for card in g.cards:
                            tile(card, width)

        def stacked_groups(groups, width: int) -> None:
            """Stacks layout: each group is a column of stacks, the columns flowing across."""
            def toggle(key: str) -> None:
                view.collapsed.symmetric_difference_update({key})
                content.refresh()

            with ui.row().classes("w-full gap-x-8 gap-y-4 items-start"):
                for g, wanted, key in groups:
                    open_ = key not in view.collapsed
                    with ui.column().classes("gap-2"):
                        with ui.row().classes("items-center gap-1 cursor-pointer no-wrap") \
                                .on("click", lambda k=key: toggle(k)):
                            ui.icon("expand_more" if open_ else "chevron_right").classes("text-gray-500")
                            ui.label(heading(g.label, len(g.cards), wanted)) \
                                .classes("text-base font-semibold whitespace-nowrap")
                        if not open_:
                            continue
                        if not g.cards:
                            ui.label("No cards").classes("text-sm text-gray-400 ml-6")
                        with ui.row().classes("gap-3 no-wrap items-start"):
                            for cards_in_stack in ov.stacks(g.cards):
                                stack(cards_in_stack, width)

        def matrix_view(cards: list[Card]) -> None:
            rows, cols = ov.FACTORS[view.rows], ov.FACTORS[view.columns]
            m = ov.matrix(cards, rows, cols, session.project)
            width = settings.tile_width
            row_header = 170

            def open_cell(r: str, c: str) -> None:
                set_view(mode="rows", group_by=view.rows, cell=(view.rows, r, view.columns, c))

            # full width; the browser gives busy columns more room than empty ones. Every
            # column fits at least one tile: below that the table scrolls sideways instead
            # of squashing
            min_width = row_header + len(m.columns) * (width + 24)
            with ui.element("table").classes("border-collapse w-full") \
                    .style(f"min-width:{min_width}px"):
                with ui.element("colgroup"):
                    ui.element("col").style(f"width:{row_header}px")
                    for _ in m.columns:
                        ui.element("col")
                with ui.element("tr"):
                    ui.element("th").classes("sticky top-0 left-0 z-20 bg-gray-100")
                    for c, label in m.columns:
                        with ui.element("th").classes("sticky top-0 z-10 bg-gray-100 px-2 py-1 "
                                                      "text-left font-semibold border"):
                            n = sum(len(m.cell(r, c)) for r, _ in m.rows)
                            ui.label(heading(label, n, target(cols, c)))
                for r, row_label in m.rows:
                    with ui.element("tr"):
                        with ui.element("th").classes("sticky left-0 z-10 bg-gray-100 px-2 py-1 "
                                                      "text-left align-top font-semibold border"):
                            n = sum(len(m.cell(r, c)) for c, _ in m.columns)
                            pip = COLOR_PIPS.get(r) if rows.name == "color" else None
                            with ui.row().classes("items-center gap-1"):
                                if pip:
                                    ui.element("span").style(f"width:10px;height:10px;border-radius:50%;"
                                                             f"background:{pip};border:1px solid #888")
                                ui.label(heading(row_label, n, target(rows, r)))
                        for c, _ in m.columns:
                            in_cell = m.cell(r, c)
                            wanted = target(rows, r, cols, c)
                            short = wanted is not None and len(in_cell) < wanted
                            with ui.element("td").classes("align-top border p-1") \
                                    .style(f"min-width:{width + 24}px"):
                                ui.button(f"{len(in_cell)}" + (f" / {wanted}" if wanted is not None else ""),
                                          on_click=lambda r=r, c=c: open_cell(r, c)) \
                                    .props("flat dense no-caps size=sm"
                                           + (" text-color=orange-9" if short else " text-color=grey-7")) \
                                    .tooltip("Show just these cards")
                                if settings.layout == "stacks":
                                    if in_cell:
                                        stack(in_cell, width)
                                else:
                                    with ui.row().classes("gap-2 flex-wrap"):
                                        for card in in_cell:
                                            tile(card, width)

        with ui.scroll_area().classes("w-full grow"):
            content()

        # page fills the window under the header; the cards scroll
        ui.query(".q-page").classes("column")
        ui.query(".nicegui-content").classes("grow h-0 min-h-0")

        # ------------------------------------------------------------ timers
        def tick() -> None:
            session.flush_due()
            if session.art_notice is not None:           # from a dropped file
                kind, message = session.art_notice
                session.art_notice = None
                ui.notify(message, type=kind)
            if session.art_version != art_seen["version"]:
                art_seen["version"] = session.art_version
                content.refresh()                        # redraws pictures of changed cards
            update_tiles()
            waiting = settings.tiles == "images" and any(worker.get(b[0].card) is None
                                                         for b in tiles.values() if b)
            status.text = (f"Pictures: {worker.error}" if worker.error
                           else "Drawing card pictures…" if waiting else "")

        ui.timer(THUMB_POLL, tick)

        def archetype_dialog() -> None:
            from .archetypes import archetype_manager
            archetype_manager(session, on_close=content.refresh)

        def settings_dialog() -> None:
            from .app import FRAME_LABELS
            from .set_settings import set_settings
            # the header, targets and every card picture may change: rebuild the page
            set_settings(session, FRAME_LABELS, on_close=lambda: ui.navigate.to("/set"))
