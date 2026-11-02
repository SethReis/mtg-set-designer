"""The card workspace (home of an open set, docs/design/layout.md): every card, grouped in
rows or in a matrix, inside the app shell. Everything else opens over it.

    /set                          the workspace
    /set?card=<id>                ... with a card open in the editor
    /set?open=mechanics&id=<id>   ... with a rail item open (mechanics, cycles, health,
                                  archetypes, settings)
"""
from __future__ import annotations

from nicegui import ui

from ..app import overview as ov
from ..app.health.checks import run_checks
from ..model import Card, Rarity, Status
from . import components as c
from .shell import set_shell
from .uploads import add_art_script, set_paste_target
from .widgets import CARD_RATIO, STACK_CSS, compact_tile, served_url

THUMB_POLL = 0.5                         # seconds between checks for newly rendered pictures
COLOR_CHOICES = {k: v for k, v in ov.COLOR_LABELS.items()}
# rail items that are still pages of their own (they become modals over the workspace)
PAGES = {"mechanics": "/set/mechanics", "cycles": "/set/cycles", "health": "/set/health"}
PAGE_IDS = {"mechanics": "mechanic", "cycles": "cycle"}     # their query parameter for ?id=


def thumbnail_url(folder, path) -> str:
    """Pictures are served straight from the cache folder."""
    return served_url(folder, path)


def register(state) -> None:

    @ui.page("/set")
    def overview_page(open: str = "", id: str = "", card: str = "") -> None:   # noqa: A002 (query names)
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        if card and any(x.id == card for x in session.project.cards):
            ui.navigate.to(f"/set/card/{card}")
            return
        if open in PAGES:
            key = PAGE_IDS.get(open)
            ui.navigate.to(PAGES[open] + (f"?{key}={id}" if key and id else ""))
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

        def open_view(name: str) -> None:
            if name == "cards":
                return
            if name == "sets":
                session.flush()
                state.close()
                ui.navigate.to("/")
            elif name in PAGES:
                session.flush()
                ui.navigate.to(PAGES[name])
            elif name == "archetypes":
                archetype_dialog()
            elif name == "settings":
                settings_dialog()

        def set_filter(**values) -> None:
            for key, value in values.items():
                setattr(view.filters, key, value)
            content.refresh()

        shell = set_shell(state, open_view=open_view, new_card=new_card,
                          on_search=lambda text: set_filter(text=text), search_text=view.filters.text)

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

        def select(options: dict, value, label: str, prefix: str, on_change) -> ui.select:
            """A compact toolbar select: its label shows as a prefix ("Group  Color")."""
            return ui.select(options, value=value, label=label, on_change=on_change) \
                .props(f'dense outlined options-dense prefix="{prefix}"').classes("ds-select")

        with shell.main:
            with ui.element("div").classes("ds-toolbar"):
                @ui.refreshable
                def factor_selects() -> None:
                    # rebuilt with the content, so they show changes made elsewhere (a matrix
                    # cell click switches to rows) without firing their own change handlers
                    c.segmented({"rows": "Rows", "matrix": "Matrix"}, view.mode,
                                lambda e: set_view(mode=e.value, cell=None))
                    if view.mode == "rows":
                        select(factor_names, view.group_by, "Group by", "Group",
                               lambda e: set_view(group_by=e.value, cell=None))
                    else:
                        select(factor_names, view.rows, "Rows", "Rows", lambda e: set_view(rows=e.value))
                        select(factor_names, view.columns, "Columns", "Columns",
                               lambda e: set_view(columns=e.value))
                factor_selects()
                select({k: label for k, (label, _) in ov.SORTS.items()}, view.sort, "Sort", "Sort",
                       lambda e: set_view(sort=e.value))
                ui.element("div").classes("ds-sep")
                c.segmented({"grid": "Grid", "stacks": "Stacks"}, settings.layout,
                            lambda e: set_setting(layout=e.value)) \
                    .tooltip("Stacks overlap the cards: hover one to see it")
                c.segmented({"images": "Images", "text": "Text"}, settings.tiles,
                            lambda e: set_setting(tiles=e.value))
                ui.element("div").classes("grow")
                count = ui.label().classes("muted num")
                with c.button("Filters", kind="secondary", icon="filter_list") \
                        .props("dense").classes("px-2") as filters_button:
                    filters_badge = ui.label().classes("ds-badge info ml-1")
                    with ui.menu().props("anchor='bottom right' self='top right'"), \
                            ui.column().classes("p-4 gap-3 w-[300px]"):
                        ui.select({s.value: s.value.title() for s in Status}, multiple=True, label="Status",
                                  value=sorted(view.filters.statuses),
                                  on_change=lambda e: set_filter(statuses=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full")
                        ui.select({r.value: r.value.title() for r in Rarity}, multiple=True, label="Rarity",
                                  value=sorted(view.filters.rarities),
                                  on_change=lambda e: set_filter(rarities=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full")
                        ui.select(COLOR_CHOICES, multiple=True, label="Color", value=sorted(view.filters.colors),
                                  on_change=lambda e: set_filter(colors=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full")
                filters_button.tooltip("Status, rarity, color")
                with ui.element("div").classes("ds-size").tooltip("Card size"):
                    ui.icon("photo_size_select_small").classes("text-[16px]")
                    ui.slider(min=100, max=300, step=20, value=settings.tile_width) \
                        .on("change", lambda e: set_setting(tile_width=int(e.args))).props("dense") \
                        .classes("grow")

            filter_chips = ui.element("div").classes("ds-filters")
            workspace = ui.element("div").classes("ds-workspace")

        def show_filters() -> None:
            """The active filters as removable chips under the toolbar (and the badge count)."""
            f = view.filters
            groups = [("Status", "statuses", {s.value: s.value.title() for s in Status}),
                      ("Rarity", "rarities", {r.value: r.value.title() for r in Rarity}),
                      ("Color", "colors", COLOR_CHOICES)]
            active = [(label, key, names) for label, key, names in groups if getattr(f, key)]
            filters_badge.text = str(len(active))
            filters_badge.set_visibility(bool(active))
            filter_chips.clear()
            filter_chips.set_visibility(bool(active))
            with filter_chips:
                for label, key, names in active:
                    chosen = ", ".join(names.get(v, v) for v in sorted(getattr(f, key)))
                    ui.chip(f"{label}: {chosen}", removable=True,
                            on_value_change=lambda e, k=key: set_filter(**{k: set()}))
                if active:
                    c.button("Clear all", kind="ghost",
                             on_click=lambda: set_filter(statuses=set(), rarities=set(), colors=set())) \
                        .props("dense")

        # ------------------------------------------------------------ tiles
        def picture(card: Card, width: int) -> None:
            path = worker.get(card) if settings.tiles == "images" else None
            if path is not None:
                ui.element("img").props(f'src="{thumbnail_url(worker.cache.folder, path)}" '
                                        f'loading=lazy draggable=false alt=""')
            else:
                compact_tile(card, width)

        def tile(card: Card, width: int, fixed: bool = False, stacked: bool = False) -> None:
            """A card's tile. It fills its grid cell, or is `width` wide when `fixed` (stacks,
            matrix cells)."""
            box = ui.element("div").classes("ds-tile") \
                .on("click", lambda c=card: open_card(c)).mark(f"tile-{card.id}") \
                .props(f'data-art-card="{card.id}"')            # drop an image: the card's art
            if fixed:
                box.style(f"width:{width}px")
            if stacked:
                box.classes("stack-card")                # see STACK_CSS
            else:
                box.tooltip(card.faces[0].name)
            box.card, box.width = card, width
            tiles.setdefault(card.id, []).append(box)
            with box:
                picture(card, width)

        def stack(cards: list[Card], width: int) -> None:
            with ui.element("div").classes("card-stack").mark("stack") \
                    .style(f"--card-h:{round(width * CARD_RATIO)}px"):
                for card in cards:
                    tile(card, width, fixed=True, stacked=True)

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
            rows, r, cols, c_ = view.cell
            p = session.project
            return [x for x in cards if r in ov.keys(x, ov.FACTORS[rows], p)
                    and c_ in ov.keys(x, ov.FACTORS[cols], p)]

        # ------------------------------------------------------------ content
        @ui.refreshable
        def content() -> None:
            factor_selects.refresh()
            show_filters()
            tiles.clear()
            seen["version"] = -1
            project = session.project
            cards = ov.sort(ov.apply(view.filters, project.cards), view.sort)
            if view.mode == "rows":
                cards = cell_cards(cards)
            count.text = f"{len(cards)} of {len(project.cards)} cards" \
                if len(cards) != len(project.cards) else f"{len(cards)} card{'s' * (len(cards) != 1)}"
            shell.set_health(len(run_checks(project)))
            if settings.tiles == "images":
                worker.request(cards)
            if not project.cards:
                c.empty_state("style", "No cards yet", "Start the set with its first card.",
                              action="Create the first card", on_action=new_card)
                return
            if view.mode == "rows":
                rows_view(cards)
            else:
                matrix_view(cards)

        def group_header(title: str, open_: bool, short: bool, pip: str | None, toggle) -> None:
            with ui.element("div").classes("ds-group-h").on("click", toggle):
                ui.icon("expand_more" if open_ else "chevron_right")
                if pip:
                    c.pips(pip)
                ui.label(title).classes("ds-group-title")
                if short:
                    ui.icon("error_outline").classes("short").tooltip("Fewer cards than the target")
                ui.element("div").classes("ds-rule")

        def toggle_group(key: str) -> None:
            view.collapsed.symmetric_difference_update({key})
            content.refresh()

        def rows_view(cards: list[Card]) -> None:
            if view.cell is not None:
                rows, r, cols, c_ = view.cell
                labels = dict(ov.FACTORS[rows].options(session.project))
                labels2 = dict(ov.FACTORS[cols].options(session.project))
                with ui.row().classes("items-center gap-2 mt-2"):
                    ui.chip(f"{labels.get(r, r)} · {labels2.get(c_, c_)}", removable=True,
                            on_value_change=lambda e: set_view(cell=None))
                    ui.label("(one matrix cell)").classes("faint")
            factor = ov.FACTORS[view.group_by]
            width = settings.tile_width
            groups = []                                      # (group, its target, collapse key)
            for g in ov.group(cards, factor, session.project):
                if view.cell is not None:                    # just the cell's group
                    rows, r, cols, c_ = view.cell
                    if g.key != r:
                        continue
                    wanted = target(ov.FACTORS[rows], r, ov.FACTORS[cols], c_)
                else:
                    wanted = target(factor, g.key)
                groups.append((g, wanted, f"{factor.name}:{g.key}"))
            if settings.layout == "stacks":
                stacked_groups(groups, width, factor)
                return
            for g, wanted, key in groups:
                open_ = key not in view.collapsed
                with ui.element("div").classes("ds-group"):
                    group_header(heading(g.label, len(g.cards), wanted), open_,
                                 wanted is not None and len(g.cards) < wanted,
                                 g.key if factor.name == "color" else None,
                                 lambda k=key: toggle_group(k))
                    if not open_:
                        continue
                    if not g.cards:
                        ui.label("No cards").classes("faint ml-7")
                    # tiles fill the row: each at least the card size, all growing alike
                    with ui.element("div").classes("ds-tiles").style(f"--tile:{width}px"):
                        for card in g.cards:
                            tile(card, width)

        def stacked_groups(groups, width: int, factor) -> None:
            """Stacks layout: each group is a column of stacks, the columns flowing across."""
            with ui.row().classes("w-full gap-x-8 gap-y-4 items-start"):
                for g, wanted, key in groups:
                    open_ = key not in view.collapsed
                    with ui.column().classes("gap-2"):
                        group_header(heading(g.label, len(g.cards), wanted), open_,
                                     wanted is not None and len(g.cards) < wanted,
                                     g.key if factor.name == "color" else None,
                                     lambda k=key: toggle_group(k))
                        if not open_:
                            continue
                        if not g.cards:
                            ui.label("No cards").classes("faint ml-6")
                        with ui.row().classes("gap-3 no-wrap items-start"):
                            for cards_in_stack in ov.stacks(g.cards):
                                stack(cards_in_stack, width)

        def matrix_view(cards: list[Card]) -> None:
            rows, cols = ov.FACTORS[view.rows], ov.FACTORS[view.columns]
            m = ov.matrix(cards, rows, cols, session.project)
            width = settings.tile_width
            row_header = 170

            def open_cell(r: str, c_: str) -> None:
                set_view(mode="rows", group_by=view.rows, cell=(view.rows, r, view.columns, c_))

            # full width; the browser gives busy columns more room than empty ones. Every
            # column fits at least one tile: below that the table scrolls sideways instead
            # of squashing
            min_width = row_header + len(m.columns) * (width + 24)
            with ui.element("table").classes("ds-matrix mt-2").style(f"min-width:{min_width}px"):
                with ui.element("colgroup"):
                    ui.element("col").style(f"width:{row_header}px")
                    for _ in m.columns:
                        ui.element("col")
                with ui.element("thead"), ui.element("tr"):
                    ui.element("th")
                    for col, label in m.columns:
                        with ui.element("th"):
                            n = sum(len(m.cell(r, col)) for r, _ in m.rows)
                            ui.label(heading(label, n, target(cols, col)))
                with ui.element("tbody"):
                    for r, row_label in m.rows:
                        with ui.element("tr"):
                            with ui.element("th"):
                                n = sum(len(m.cell(r, col)) for col, _ in m.columns)
                                with ui.row().classes("items-center gap-2 no-wrap"):
                                    if rows.name == "color":
                                        c.pips(r)
                                    ui.label(heading(row_label, n, target(rows, r)))
                            for col, _ in m.columns:
                                in_cell = m.cell(r, col)
                                wanted = target(rows, r, cols, col)
                                short = wanted is not None and len(in_cell) < wanted
                                with ui.element("td").style(f"min-width:{width + 24}px"):
                                    ui.button(f"{len(in_cell)}" + (f" / {wanted}" if wanted is not None else ""),
                                              on_click=lambda r=r, col=col: open_cell(r, col)) \
                                        .props("flat dense no-caps size=sm") \
                                        .classes("num" + (" text-warning" if short else "")) \
                                        .tooltip("Show just these cards")
                                    if settings.layout == "stacks":
                                        if in_cell:
                                            stack(in_cell, width)
                                    else:
                                        with ui.row().classes("gap-2 flex-wrap"):
                                            for card in in_cell:
                                                tile(card, width, fixed=True)

        with workspace:
            content()

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
            if worker.error:
                shell.set_status(f"Pictures: {worker.error}", "danger")
            elif session.unsaved:
                shell.set_status("Saving…", "muted")
            elif waiting:
                shell.set_status("Drawing card pictures…", "info")
            else:
                shell.set_status("All changes saved")

        ui.timer(THUMB_POLL, tick)

        def remember(name: str | None) -> None:
            """Keep the open modal in the URL, so a reload reopens it."""
            ui.navigate.history.replace(f"/set?open={name}" if name else "/set")

        def archetype_dialog() -> None:
            from .archetypes import archetype_manager
            remember("archetypes")
            archetype_manager(session, on_close=lambda: (remember(None), content.refresh()))

        def settings_dialog() -> None:
            from .app import FRAME_LABELS
            from .set_settings import set_settings
            remember("settings")
            # the top bar, targets and every card picture may change: rebuild the page
            set_settings(session, FRAME_LABELS, on_close=lambda: ui.navigate.to("/set"))

        if open == "archetypes":
            archetype_dialog()
        elif open == "settings":
            settings_dialog()
