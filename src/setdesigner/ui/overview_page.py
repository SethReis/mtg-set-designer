"""The card workspace (home of an open set, docs/design/layout.md): every card, grouped in
rows or in a matrix, inside the app shell. Everything else opens over it.

    /set                          the workspace
    /set?card=<id>                ... with a card open in the editor
    /set?card=<id>&part=text      ... and one of its parts open for editing (name, cost, ...)
    /set?open=mechanics&id=<id>   ... with a rail item open (skeleton, mechanics, cycles, health,
                                  archetypes, settings, print)
"""
from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from ..app import overview as ov
from ..app.health.checks import run_checks
from ..model import Card, Rarity, Status
from . import components as c
from .cycles_page import cycles_panel
from .editor_page import editor_panel
from .health_page import health_panel
from . import renderer_notice
from .mechanics_page import mechanics_panel
from .shell import set_shell
from .uploads import add_art_script, set_paste_target
from .widgets import CARD_RATIO, STACK_CSS, compact_tile, served_url, skeleton_tile

THUMB_POLL = 0.5                         # seconds between checks for newly rendered pictures
COLOR_CHOICES = {k: v for k, v in ov.COLOR_LABELS.items()}
# the views that open over the workspace: workspace-size modals and the two dialogs
WORKSPACE_VIEWS = {"notebook": "Notebook", "skeleton": "Skeleton", "mechanics": "Mechanics", "cycles": "Cycles", "health": "Set health", "balance": "Balance"}
VIEWS = {*WORKSPACE_VIEWS, "archetypes", "settings", "print"}


def thumbnail_url(folder, path) -> str:
    """Pictures are served straight from the cache folder."""
    return served_url(folder, path)


def register(state) -> None:

    # the routes from before the views became modals
    @ui.page("/set/card/{card_id}")
    def old_card(card_id: str) -> RedirectResponse:
        return RedirectResponse(f"/set?card={card_id}")

    @ui.page("/set/mechanics")
    def old_mechanics() -> RedirectResponse:
        return RedirectResponse("/set?open=mechanics")

    @ui.page("/set/cycles")
    def old_cycles(cycle: str = "") -> RedirectResponse:
        return RedirectResponse("/set?open=cycles" + (f"&id={cycle}" if cycle else ""))

    @ui.page("/set/health")
    def old_health() -> RedirectResponse:
        return RedirectResponse("/set?open=health")

    @ui.page("/set")
    def overview_page(open: str = "", id: str = "", card: str = "", part: str = "",   # noqa: A002
                      part_outlines: str = "") -> None:
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

        def open_card(card: Card, back: tuple[str, str | None] | None = None) -> None:
            show("card", card.id, back)

        def new_card() -> None:
            open_card(session.new_card())

        def open_view(name: str) -> None:
            if name == "cards":
                close_view()
            elif name == "sets":
                close_view()
                session.flush()
                state.close()
                ui.navigate.to("/")
            else:
                show(name)

        def inbox_changed() -> None:
            shell.set_inbox(sum(1 for i in session.project.notebook if i.lane == "inbox"))

        def new_idea(prefill: dict | None = None) -> None:
            from .notebook_capture import capture_idea
            capture_idea(state, parent=shell.dialogs, prefill=prefill, on_saved=lambda idea: inbox_changed())

        def set_filter(**values) -> None:
            for key, value in values.items():
                setattr(view.filters, key, value)
            content.refresh()

        shell = set_shell(state, open_view=open_view, new_card=new_card, new_idea=new_idea,
                          on_search=lambda text: set_filter(text=text), search_text=view.filters.text)
        # the view open over the workspace: its modal, (name, item), and the one to return to
        active = {"modal": None, "view": None, "back": None}
        shell.busy = lambda: active["modal"] is not None

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
                .props(f'dense outlined options-dense prefix="{prefix}"').props(remove="stack-label")                 .classes("ds-select")

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
                slots_switch = ui.switch("Slots", value=settings.show_slots,
                                         on_change=lambda e: set_setting(show_slots=e.value))                     .props("dense").mark("show-slots")                     .tooltip("The skeleton's empty slots, as tiles in their groups")
                ui.element("div").classes("grow")
                count = ui.label().classes("muted num ds-wide-only")
                with c.button("Filters", kind="secondary", icon="filter_list") \
                        .props("dense").classes("px-2 ds-collapse") as filters_button:
                    filters_badge = ui.label().classes("ds-badge info ml-1")
                    with ui.menu().props("anchor='bottom right' self='top right'"), \
                            ui.column().classes("p-4 gap-3 w-[300px]"):
                        ui.label("Status").classes("ds-label -mb-3")
                        ui.select({s.value: s.value.title() for s in Status}, multiple=True, label="Status",
                                  value=sorted(view.filters.statuses),
                                  on_change=lambda e: set_filter(statuses=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full ds-unlabeled")
                        ui.label("Rarity").classes("ds-label -mb-3")
                        ui.select({r.value: r.value.title() for r in Rarity}, multiple=True, label="Rarity",
                                  value=sorted(view.filters.rarities),
                                  on_change=lambda e: set_filter(rarities=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full ds-unlabeled")
                        ui.label("Color").classes("ds-label -mb-3")
                        ui.select(COLOR_CHOICES, multiple=True, label="Color", value=sorted(view.filters.colors),
                                  on_change=lambda e: set_filter(colors=set(e.value or []))) \
                            .props("dense outlined use-chips clearable").classes("w-full ds-unlabeled")
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
                    ui.chip(f"{label}: {chosen}", removable=True, color=None,
                            on_value_change=lambda e, k=key: set_filter(**{k: set()}))
                if active:
                    c.button("Clear all", kind="ghost",
                             on_click=lambda: set_filter(statuses=set(), rarities=set(), colors=set())) \
                        .props("dense")

        # ------------------------------------------------------------ tiles
        def picture(card: Card, width: int) -> None:
            path = worker.get(card) if settings.tiles == "images" else None
            if path is None:
                if settings.tiles == "images" and not worker.error:
                    skeleton_tile()                  # its picture is on its way
                else:
                    compact_tile(card, width)
                return
            ui.element("img").classes("face-front").props(
                f'src="{thumbnail_url(worker.cache.folder, path)}" loading=lazy draggable=false alt=""')
            back = worker.get(card, face=1) if len(card.faces) > 1 else None
            if back is not None:                     # two-faced: the badge shows the back
                ui.element("img").classes("face-back").props(
                    f'src="{thumbnail_url(worker.cache.folder, back)}" loading=lazy draggable=false alt=""')
                with ui.element("div").classes("ds-dfc-badge").mark(f"dfc-{card.id}")                         .tooltip("Two-faced: hover to see the back, click to flip") as badge:
                    ui.icon("flip")
                badge.on("click", js_handler="(e) => { e.stopPropagation();"
                         " e.currentTarget.closest('.ds-tile').classList.toggle('show-back'); }")

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
            box.shown = worker.get(card) if settings.tiles == "images" else None
            tiles.setdefault(card.id, []).append(box)
            with box:
                picture(card, width)

        def empty_slots(factor_name: str, key: str, column_factor: str | None = None,
                        column_key: str | None = None) -> list:
            """The skeleton's empty slots that belong in a group (or matrix cell), when shown.
            Grouping by color, rarity or archetype only: other factors don't apply to slots."""
            skeleton = session.project.skeleton
            if skeleton is None or not settings.show_slots or view.filters.active:
                return []

            def keys(slot, name: str) -> list[str] | None:
                if name == "color":
                    return [ov.slot_color_key(slot.column)]
                if name == "rarity":
                    return [slot.rarity.value] if slot.rarity else []
                if name == "archetype":
                    return [slot.archetype or ov.NO_ARCHETYPE]
                return None
            out = []
            for slot in skeleton.slots:
                if slot.card_id is not None:
                    continue
                first = keys(slot, factor_name)
                if first is None or key not in first:
                    continue
                if column_factor is not None:
                    second = keys(slot, column_factor)
                    if second is None or column_key not in second:
                        continue
                out.append(slot)
            return out

        def slot_tile(slot, width: int, fixed: bool = False) -> None:
            """An empty skeleton slot: dashed, saying what it asks for; click to fill it."""
            from ..app import skeleton as sk
            from .slot_popover import slot_menu
            box = ui.element("div").classes("ds-tile ds-slot-tile").mark(f"slot-tile-{slot.id}")
            if fixed:
                box.style(f"width:{width}px")
            with box:
                ui.label(slot.id).classes("id")
                ui.label(sk.describe(slot, session.project) or "Empty slot").classes("desc")
                menu = slot_menu(session, slot, open_card=lambda card: open_card(card), on_change=content.refresh)
            box.on("click", menu.open)

        def slots_summary(slots: list, width: int) -> None:
            """Stacks layout: a group's empty slots as one dashed tile, opening the Skeleton."""
            with ui.element("div").classes("ds-tile ds-slot-tile").style(f"width:{width}px")                     .mark(f"slots-summary-{slots[0].column}") as box:
                ui.label(str(len(slots))).classes("count")
                ui.label(f"empty slot{'s' * (len(slots) != 1)}").classes("desc")
            box.on("click", lambda: show("skeleton"))
            box.tooltip("Open the Skeleton to fill them")

        def stack(cards: list[Card], width: int) -> None:
            with ui.element("div").classes("card-stack").mark("stack") \
                    .style(f"--card-h:{round(width * CARD_RATIO)}px"):
                for card in cards:
                    tile(card, width, fixed=True, stacked=True)

        def update_tiles() -> None:
            """Show pictures rendered meanwhile: in place of text tiles, or of stand-in
            pictures once Magic Set Editor has redrawn them."""
            if worker.version == seen["version"]:
                return
            seen["version"] = worker.version
            for boxes in tiles.values():
                for box in boxes:
                    path = worker.get(box.card)
                    if path is not None and path != box.shown:
                        box.clear()
                        box.shown = path
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
            slots_switch.set_visibility(session.project.skeleton is not None)
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
                    ui.chip(f"{labels.get(r, r)} · {labels2.get(c_, c_)}", removable=True, color=None,
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
                    slots = [] if view.cell is not None else empty_slots(factor.name, g.key)
                    if not g.cards and not slots:
                        ui.label("No cards").classes("faint ml-7")
                    # tiles fill the row: each at least the card size, all growing alike
                    with ui.element("div").classes("ds-tiles").style(f"--tile:{width}px"):
                        for card in g.cards:
                            tile(card, width)
                        for slot in slots:
                            slot_tile(slot, width)

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
                        slots = [] if view.cell is not None else empty_slots(factor.name, g.key)
                        if not g.cards and not slots:
                            ui.label("No cards").classes("faint ml-6")
                        with ui.row().classes("gap-3 no-wrap items-start"):
                            for cards_in_stack in ov.stacks(g.cards):
                                stack(cards_in_stack, width)
                            if slots:                       # one tile for the group's gaps
                                slots_summary(slots, width)

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
                                    c.button(f"{len(in_cell)}" + (f" / {wanted}" if wanted is not None else ""),
                                             kind="ghost", on_click=lambda r=r, col=col: open_cell(r, col),
                                             tooltip="Show just these cards") \
                                        .props("dense size=sm").classes("num" + (" warning-text" if short else ""))
                                    if settings.layout == "stacks":
                                        if in_cell:
                                            stack(in_cell, width)
                                    else:
                                        with ui.row().classes("gap-2 flex-wrap"):
                                            for card in in_cell:
                                                tile(card, width, fixed=True)
                                            for slot in empty_slots(rows.name, r, cols.name, col):
                                                slot_tile(slot, width, fixed=True)

        with workspace:
            content()

        # ------------------------------------------------------------ timers
        def tick() -> None:
            session.flush_due()
            renderer_health = renderer_notice.health(session)
            if renderer_health.version != renderer_seen["version"]:
                renderer_seen["version"] = renderer_health.version
                shell.renderer_chip.set_visibility(renderer_health.problem and renderer_health.dismissed)
                if renderer_health.phase == "fixed":
                    content.refresh()                    # stand-in pictures get redrawn by MSE
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

        renderer_seen = {"version": -1}
        with shell.banner:
            renderer_notice.notice(session)
        shell.renderer_chip.on_click(lambda: renderer_notice.health(session).update(dismissed=False))
        ui.timer(0, lambda: renderer_notice.check(session), once=True)
        # a head start for the editor: set-wide values and MSE's start (background priority)
        ui.timer(0, session.warm_up, once=True)
        ui.timer(THUMB_POLL, tick)

        # ------------------------------------------------------------ views over the workspace
        # One at a time (docs/design/navigation.md): opening a card from Mechanics replaces
        # that modal, and closing the editor returns to it.
        def remember() -> None:
            """Keep the open view in the URL, so a reload or a link reopens it."""
            name, item = active["view"] or (None, None)
            query = (f"card={item}" if name == "card" else
                     f"open={name}" + (f"&id={item}" if item else "") if name else "")
            ui.navigate.history.replace(f"/set?{query}" if query else "/set")

        def shown(item: str | None) -> None:
            """The open view shows another item (card, mechanic, cycle)."""
            if active["view"] is not None:
                active["view"] = (active["view"][0], item)
                remember()

        def close_view() -> None:
            if active["modal"] is not None:
                active["modal"].close()

        def show(name: str, item: str | None = None, back: tuple[str, str | None] | None = None) -> None:
            """Open a view over the workspace, in place of the one that is open."""
            previous = active["modal"]
            active.update(modal=None, view=(name, item), back=back)
            if previous is not None:
                previous.close()                     # closed() sees it's no longer the active one

            def here() -> tuple[str, str | None] | None:
                return active["view"]                # where a card is opened from: back to it
            if name == "archetypes":
                from .archetypes import archetype_manager
                m = archetype_manager(session, parent=shell.dialogs, on_close=lambda: closed(m))
            elif name == "settings":
                from .app import FRAME_LABELS
                from .set_settings import set_settings
                m = set_settings(session, FRAME_LABELS, parent=shell.dialogs, on_close=lambda: closed(m))
            elif name == "print":
                from .print_dialog import print_dialog
                m = print_dialog(state, cards=list(session.project.cards),
                                 filtered=workspace_order() if view.filters.active else None,
                                 parent=shell.dialogs, on_close=lambda: closed(m))
            else:
                with c.modal("workspace", WORKSPACE_VIEWS.get(name, ""), parent=shell.dialogs,
                             on_close=lambda: closed(m)) as m:
                    if name == "card":
                        editor_panel(state, m, item, order=workspace_order,
                                     open_cycle=lambda cid: show("cycles", cid, back=here()),
                                     on_card=lambda card: shown(card.id if card else None),
                                     open_part_name=part if item == card else None,   # ?part=
                                     outlines=bool(part_outlines),                    # dev: all hotspots
                                     open_balance=lambda cid: show("balance", cid, back=here()))
                    elif name == "mechanics":
                        mechanics_panel(state, m, select_id=item, on_select=shown,
                                        open_card=lambda card: open_card(card, back=here()))
                    elif name == "cycles":
                        cycles_panel(state, m, select_id=item, on_select=shown,
                                     open_card=lambda card: open_card(card, back=here()))
                    elif name == "notebook":
                        from .notebook_page import notebook_panel
                        notebook_panel(state, m, select_id=item, on_select=shown,
                                       open_card=lambda card: open_card(card, back=here()),
                                       open_mechanic=lambda mid: show("mechanics", mid, back=here()),
                                       on_change=inbox_changed)
                    elif name == "skeleton":
                        from .skeleton_page import skeleton_panel
                        skeleton_panel(state, m, open_card=lambda card: open_card(card, back=here()),
                                       on_change=content.refresh)
                    elif name == "balance":
                        from .balance_page import balance_panel
                        balance_panel(state, m, select_id=item, on_select=shown,
                                      open_card=lambda card: open_card(card, back=here()),
                                      on_change=content.refresh)
                    elif name == "health":
                        health_panel(state, m, open_card=lambda card: open_card(card, back=here()),
                                     open_cycle=lambda cid: show("cycles", cid, back=here()),
                                     on_change=content.refresh)
                m.open()
            active["modal"] = m
            remember()

        def closed(m: c.Modal) -> None:
            if active["modal"] is not m:             # replaced by another view
                return
            session.flush()
            set_paste_target(None)
            back = active["back"]
            active.update(modal=None, view=None, back=None)
            shell.refresh_title()                    # Set settings may have changed it
            content.refresh()                        # edits show on the tiles
            if back is not None:
                show(*back)
            else:
                remember()

        def workspace_order() -> list[Card]:
            """The cards in the workspace's order (the editor's previous / next)."""
            return ov.sort(ov.apply(view.filters, session.project.cards), view.sort)

        # a linked view opens once the page is up: building one can take a while (Set
        # settings draws its symbol previews), longer than the page may take to connect
        if card and any(x.id == card for x in session.project.cards):
            ui.timer(0, lambda: show("card", card), once=True)
        elif open in VIEWS:
            ui.timer(0, lambda: show(open, id or None), once=True)
