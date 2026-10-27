"""The set overview (home of an open set): every card, grouped in rows or in a matrix."""
from __future__ import annotations

import hashlib

from nicegui import app, ui

from ..app import overview as ov
from ..model import Card, Rarity, Status
from .widgets import CARD_RATIO, COLOR_PIPS, compact_tile

THUMB_POLL = 0.5                         # seconds between checks for newly rendered pictures
COLOR_CHOICES = {k: v for k, v in ov.COLOR_LABELS.items()}
_served: dict[str, str] = {}             # thumbnail folder -> URL it is served at


def thumbnail_url(folder, path) -> str:
    """Pictures are served straight from the cache folder."""
    key = str(folder)
    if key not in _served:
        folder.mkdir(parents=True, exist_ok=True)
        url = f"/thumbs/{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"
        app.add_static_files(url, folder)
        _served[key] = url
    return f"{_served[key]}/{path.name}"


def register(state) -> None:

    @ui.page("/set")
    def overview_page() -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        view, settings = state.overview, state.settings
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

        with ui.row().classes("w-full items-center gap-3 flex-wrap"):

            @ui.refreshable
            def factor_selects() -> None:
                # rebuilt with the content, so they show changes made elsewhere (a matrix cell
                # click switches to rows) without firing their own change handlers
                ui.toggle({"rows": "Rows", "matrix": "Matrix"}, value=view.mode,
                          on_change=lambda e: set_view(mode=e.value, cell=None)).props("dense no-caps")
                if view.mode == "rows":
                    ui.select(factor_names, value=view.group_by, label="Group by",
                              on_change=lambda e: set_view(group_by=e.value, cell=None)).classes("w-36")
                else:
                    ui.select(factor_names, value=view.rows, label="Rows",
                              on_change=lambda e: set_view(rows=e.value)).classes("w-32")
                    ui.select(factor_names, value=view.columns, label="Columns",
                              on_change=lambda e: set_view(columns=e.value)).classes("w-32")
            factor_selects()
            ui.select({k: label for k, (label, _) in ov.SORTS.items()}, value=view.sort, label="Sort",
                      on_change=lambda e: set_view(sort=e.value)).classes("w-40")
            ui.separator().props("vertical")
            ui.toggle({"images": "Images", "compact": "Compact"}, value=settings.tiles,
                      on_change=lambda e: set_setting(tiles=e.value)).props("dense no-caps")
            with ui.row().classes("items-center gap-1"):
                ui.icon("photo_size_select_small").classes("text-gray-500")
                ui.slider(min=100, max=300, step=20, value=settings.tile_width) \
                    .on("change", lambda e: set_setting(tile_width=int(e.args))).classes("w-28") \
                    .props("dense")

        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            ui.input(placeholder="Search name, type, rules", value=view.filters.text) \
                .props("dense outlined clearable").classes("w-64") \
                .on_value_change(lambda e: set_filter(text=e.value or ""))
            ui.select({s.value: s.value.title() for s in Status}, multiple=True, label="Status",
                      value=sorted(view.filters.statuses),
                      on_change=lambda e: set_filter(statuses=set(e.value or []))) \
                .props("dense use-chips clearable").classes("min-w-[140px]")
            ui.select({r.value: r.value.title() for r in Rarity}, multiple=True, label="Rarity",
                      value=sorted(view.filters.rarities),
                      on_change=lambda e: set_filter(rarities=set(e.value or []))) \
                .props("dense use-chips clearable").classes("min-w-[140px]")
            ui.select(COLOR_CHOICES, multiple=True, label="Color", value=sorted(view.filters.colors),
                      on_change=lambda e: set_filter(colors=set(e.value or []))) \
                .props("dense use-chips clearable").classes("min-w-[140px]")

        # ------------------------------------------------------------ tiles
        def picture(card: Card, width: int) -> None:
            path = worker.get(card) if settings.tiles == "images" else None
            if path is not None:
                ui.element("img").props(f'src="{thumbnail_url(worker.cache.folder, path)}" '
                                        f'loading=lazy draggable=false') \
                    .style(f"width:{width}px;height:{round(width * CARD_RATIO)}px;display:block")
            else:
                compact_tile(card, width)

        def tile(card: Card, width: int) -> None:
            box = ui.element("div").classes("cursor-pointer hover:shadow-lg transition-shadow rounded") \
                .on("click", lambda c=card: open_card(c)).tooltip(card.faces[0].name) \
                .mark(f"tile-{card.id}")
            box.card, box.width = card, width
            tiles.setdefault(card.id, []).append(box)
            with box:
                picture(card, width)

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
            for g in ov.group(cards, factor, session.project):
                if view.cell is not None:                    # just the cell's group
                    rows, r, cols, c = view.cell
                    if g.key != r:
                        continue
                    wanted = target(ov.FACTORS[rows], r, ov.FACTORS[cols], c)
                else:
                    wanted = target(factor, g.key)
                key = f"{factor.name}:{g.key}"
                with ui.expansion(heading(g.label, len(g.cards), wanted), value=key not in view.collapsed) \
                        .classes("w-full").props("dense header-class=text-base font-semibold") as section:
                    section.on_value_change(lambda e, k=key: view.collapsed.discard(k) if e.value
                                            else view.collapsed.add(k))
                    if not g.cards:
                        ui.label("No cards").classes("text-sm text-gray-400 ml-2")
                    with ui.row().classes("gap-3 flex-wrap"):
                        for card in g.cards:
                            tile(card, width)

        def matrix_view(cards: list[Card]) -> None:
            rows, cols = ov.FACTORS[view.rows], ov.FACTORS[view.columns]
            m = ov.matrix(cards, rows, cols, session.project)
            width = max(56, settings.tile_width // 2)

            def open_cell(r: str, c: str) -> None:
                set_view(mode="rows", group_by=view.rows, cell=(view.rows, r, view.columns, c))

            with ui.element("table").classes("border-collapse"):
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
                            with ui.row().classes("items-center gap-1 no-wrap"):
                                if pip:
                                    ui.element("span").style(f"width:10px;height:10px;border-radius:50%;"
                                                             f"background:{pip};border:1px solid #888")
                                ui.label(heading(row_label, n, target(rows, r))) \
                                    .classes("whitespace-nowrap")
                        for c, _ in m.columns:
                            in_cell = m.cell(r, c)
                            wanted = target(rows, r, cols, c)
                            short = wanted is not None and len(in_cell) < wanted
                            with ui.element("td").classes("align-top border p-1"):
                                ui.button(f"{len(in_cell)}" + (f" / {wanted}" if wanted is not None else ""),
                                          on_click=lambda r=r, c=c: open_cell(r, c)) \
                                    .props("flat dense no-caps size=sm"
                                           + (" text-color=orange-9" if short else " text-color=grey-7")) \
                                    .tooltip("Show just these cards")
                                with ui.row().classes("gap-1 flex-wrap").style(f"max-width:{4 * (width + 4)}px"):
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
            update_tiles()
            waiting = settings.tiles == "images" and any(worker.get(b[0].card) is None
                                                         for b in tiles.values() if b)
            status.text = (f"Pictures: {worker.error}" if worker.error
                           else "Drawing card pictures…" if waiting else "")

        ui.timer(THUMB_POLL, tick)

        def archetype_dialog() -> None:
            from .archetypes import archetype_manager
            archetype_manager(session, on_close=content.refresh)
