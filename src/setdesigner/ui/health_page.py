"""The Health page: warnings from the set-health checks, then curves, roles per color,
mechanics and archetypes, and complexity (see app/health/)."""
from __future__ import annotations

from nicegui import ui

from ..app.health import stats
from ..app.health.checks import CHECKS, enabled, run_checks, threshold
from ..app.health.roles import ROLES
from ..app.overview import COLOR_LABELS, MANA_VALUES
from ..model import Card
from .widgets import COLOR_BORDERS, RARITY_LETTERS, number_label

RARITY_CHOICES = {"": "All rarities", "common": "Common", "uncommon": "Uncommon", "rare": "Rare",
                  "mythic": "Mythic", "special": "Special"}
GRID = "display:grid;gap:4px 12px;align-items:center"


def grid(columns: str) -> ui.element:
    return ui.element("div").style(f"{GRID};grid-template-columns:{columns}")


def color_cell(key: str) -> None:
    with ui.row().classes("items-center gap-1 no-wrap"):
        ui.element("span").style(f"width:10px;height:10px;border-radius:50%;flex:none;"
                                 f"background:{COLOR_BORDERS[key]};border:1px solid #888")
        ui.label(COLOR_LABELS[key]).classes("text-sm")


def section(title: str):
    card = ui.card().classes("w-full").props("flat bordered")
    with card:
        ui.label(title).classes("text-lg font-semibold")
    return card


def register(state) -> None:

    @ui.page("/set/health")
    def health_page() -> None:
        session = state.session
        if session is None:
            ui.navigate.to("/")
            return
        project = session.project
        view = {"curve_rarity": "", "role_rarity": "common"}
        dialogs = ui.element("div")                 # dialogs live here (see cycles_page)

        def open_card(card_id: str) -> None:
            ui.navigate.to(f"/set/card/{card_id}")

        def card_chips(card_ids) -> None:
            cards = {c.id: c for c in project.cards}
            with ui.row().classes("gap-1 flex-wrap"):
                for cid in card_ids:
                    card = cards.get(cid)
                    if card is not None:
                        ui.chip(f"{number_label(card)} {card.faces[0].name}", on_click=lambda c=cid: open_card(c)) \
                            .props("dense clickable outline").classes("text-xs")

        def show_cards(title: str, cards: list[Card]) -> None:
            with dialogs, ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[95vw]"):
                ui.label(title).classes("text-lg font-semibold")
                if cards:
                    card_chips([c.id for c in cards])
                else:
                    ui.label("No cards.").classes("text-gray-500")
                ui.button("Close", on_click=dialog.close).props("flat")
            dialog.open()

        # ---------------------------------------------------------------- warnings
        @ui.refreshable
        def warnings_section() -> None:
            found = run_checks(project)
            with section("Warnings" if found else "No warnings"):
                with ui.row().classes("w-full items-center"):
                    ui.label(f"{len(found)} warning{'s' * (len(found) != 1)} from "
                             f"{sum(enabled(project, c) for c in CHECKS.values())} checks").classes("text-sm text-gray-500")
                    ui.space()
                    ui.button("Tune checks", icon="tune", on_click=tune).props("flat dense no-caps")
                for check in CHECKS.values():
                    mine = [w for w in found if w.check_id == check.id]
                    if not mine:
                        continue
                    ui.label(check.label).classes("text-sm font-semibold mt-2")
                    for w in mine:
                        icon = "warning" if w.severity == "warning" else "info"
                        color = "amber-8" if w.severity == "warning" else "blue-grey-5"
                        if w.card_ids:                  # opens to the cards
                            with ui.expansion().props("dense header-class='pl-4 py-1 min-h-0'") \
                                    .classes("w-full") as expansion:
                                with expansion.add_slot("header"), ui.row().classes("items-center gap-2 grow"):
                                    ui.icon(icon, color=color)
                                    ui.label(w.message).classes("text-sm")
                                    ui.label(f"{len(w.card_ids)} card{'s' * (len(w.card_ids) != 1)}") \
                                        .classes("text-xs text-gray-500")
                                with ui.element("div").classes("pl-11 pb-2"):
                                    card_chips(w.card_ids)
                        else:
                            with ui.row().classes("items-center gap-2 pl-4 py-1"):
                                ui.icon(icon, color=color)
                                ui.label(w.message).classes("text-sm")

        def tune() -> None:
            rows = []
            with dialogs, ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-[95vw]"):
                ui.label("Tune checks").classes("text-lg font-semibold")
                ui.label("Saved with the set. Leave a number empty for the default.").classes("text-xs text-gray-500")
                for check in CHECKS.values():
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        on = ui.checkbox(check.label, value=enabled(project, check)).classes("grow")
                        number = None
                        if check.default is not None:
                            setting = project.info.health.get(check.id)
                            number = ui.number(check.unit, value=setting.threshold if setting else None,
                                               placeholder=f"{check.default:g}", min=0) \
                                .props("dense").classes("w-36").mark(f"threshold-{check.id}")
                        rows.append((check, on, number))

                def save() -> None:
                    for check, on, number in rows:
                        value = float(number.value) if number is not None and number.value not in (None, "") else None
                        setting = project.info.health.get(check.id)
                        if setting is None and on.value and value is None:
                            continue
                        session.set_health_check(check.id, bool(on.value), value)
                    dialog.close()
                    warnings_section.refresh()
                with ui.row():
                    ui.button("Save", on_click=save).props("color=primary")
                    ui.button("Cancel", on_click=dialog.close).props("flat")
            dialog.open()

        # ---------------------------------------------------------------- curves and counts
        @ui.refreshable
        def curve_chart() -> None:
            data = stats.curve(project, view["curve_rarity"] or None)
            series = []
            for color, by_mv in data.items():
                if any(sum(v) for v in by_mv.values()):
                    series.append({"name": COLOR_LABELS[color], "type": "bar", "stack": "all",
                                   "itemStyle": {"color": COLOR_BORDERS[color]},
                                   "data": [sum(by_mv[mv]) for mv in MANA_VALUES]})
            ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0},
                       "grid": {"left": 30, "right": 10, "top": 30, "bottom": 25},
                       "xAxis": {"type": "category", "data": MANA_VALUES, "name": "Mana value"},
                       "yAxis": {"type": "value", "minInterval": 1},
                       "series": series}).classes("w-full h-64")

        def counts_tables() -> None:
            counts = stats.color_rarity_counts(project)
            rarities = stats.RARITIES
            with grid("140px " + " ".join(["70px"] * len(rarities)) + " 70px"):
                ui.label("")
                for r in rarities:
                    ui.label(r.title()).classes("text-xs font-semibold text-gray-600")
                ui.label("Total").classes("text-xs font-semibold text-gray-600")
                for color, row in counts.items():
                    if not sum(row.values()):
                        continue
                    color_cell(color)
                    for r in rarities:
                        ui.label(str(row[r])).classes("text-sm")
                    ui.label(str(sum(row.values()))).classes("text-sm font-semibold")
                ui.label("All").classes("text-sm font-semibold")
                for r in rarities:
                    n = sum(row[r] for row in counts.values())
                    wanted = {k.value: v for k, v in project.info.rarity_slots.items()}.get(r)
                    text = f"{n} / {wanted}" if wanted else str(n)
                    short = wanted is not None and n < wanted
                    ui.label(text).classes("text-sm font-semibold" + (" text-amber-800" if short else ""))
                ui.label(str(len(project.cards))).classes("text-sm font-semibold")

        def creature_tables() -> None:
            with ui.row().classes("w-full gap-12 items-start"):
                with ui.column().classes("gap-1"):
                    ui.label("Creatures among commons").classes("text-sm font-semibold")
                    with grid("140px 110px"):
                        for color, (creatures, total) in stats.creature_ratio(project, "common").items():
                            if total:
                                color_cell(color)
                                ui.label(f"{creatures} / {total}  ({100 * creatures / total:.0f}%)").classes("text-sm")
                with ui.column().classes("gap-1"):
                    ui.label("Average common creature by mana value").classes("text-sm font-semibold")
                    with grid("80px 110px 60px"):
                        for header in ("Mana value", "Power/Tough.", "Cards"):
                            ui.label(header).classes("text-xs text-gray-500")
                        for mv, (power, tough, n) in stats.creature_size(project).items():
                            ui.label(mv).classes("text-sm")
                            ui.label(f"{power:.1f} / {tough:.1f}").classes("text-sm")
                            ui.label(str(n)).classes("text-sm")

        # ---------------------------------------------------------------- roles
        @ui.refreshable
        def roles_table() -> None:
            table = stats.role_table(project, view["role_rarity"] or None)
            role_ids = list(ROLES)
            with ui.element("div").classes("w-full overflow-x-auto"):
                with grid("140px " + " ".join(["minmax(70px,1fr)"] * len(role_ids))):
                    ui.label("")
                    for rid in role_ids:
                        ui.label(ROLES[rid].label).classes("text-xs font-semibold text-gray-600")
                    for color, row in table.items():
                        if color in ("M", "C", "L") and not any(row.values()):
                            continue
                        color_cell(color)
                        for rid in role_ids:
                            cards = row[rid]
                            weak = color in "WUBRG" and rid == "removal" and not cards
                            btn = ui.button(str(len(cards)) if cards else "–",
                                            on_click=lambda c=cards, col=color, r=rid:
                                            show_cards(f"{COLOR_LABELS[col]} · {ROLES[r].label}", c)) \
                                .props("flat dense no-caps").classes("text-sm")
                            if weak:
                                btn.classes("bg-amber-100")

        # ---------------------------------------------------------------- mechanics & archetypes
        def mechanics_tables() -> None:
            spreads = stats.mechanic_spread(project)
            if spreads:
                ui.label("Mechanics").classes("text-sm font-semibold")
                cols = ["W", "U", "B", "R", "G", "M", "C", "L"]
                with grid("160px " + " ".join(["36px"] * len(cols)) + " 160px 60px"):
                    ui.label("")
                    for c in cols:
                        ui.label(c).classes("text-xs font-semibold text-gray-600")
                    ui.label("By rarity").classes("text-xs font-semibold text-gray-600")
                    ui.label("Cards").classes("text-xs font-semibold text-gray-600")
                    for s in spreads:
                        ui.label(s.mechanic.name).classes("text-sm")
                        for c in cols:
                            ui.label(str(s.by_color.get(c, "")) or "·").classes("text-sm text-center")
                        ui.label(" · ".join(f"{RARITY_LETTERS_BY_VALUE[r]} {n}" for r, n in s.by_rarity.items())
                                 or "—").classes("text-sm")
                        ui.label(str(s.cards)).classes("text-sm font-semibold")
            coverage = stats.archetype_coverage(project)
            if coverage:
                ui.label("Archetypes").classes("text-sm font-semibold mt-4")
                with grid("160px " + " ".join(["80px"] * len(stats.RARITIES))):
                    ui.label("")
                    for r in stats.RARITIES:
                        ui.label(r.title()).classes("text-xs font-semibold text-gray-600")
                    for cov in coverage:
                        ui.label(cov.archetype.name).classes("text-sm")
                        for r in stats.RARITIES:
                            n, wanted = cov.counts[r], cov.targets.get(r)
                            text = f"{n} / {wanted}" if wanted else (str(n) if n else "·")
                            ui.label(text).classes("text-sm" + (" text-amber-800" if wanted and n < wanted else ""))
            cycles = stats.cycle_completeness(project)
            if cycles:
                ui.label("Cycles").classes("text-sm font-semibold mt-4")
                with grid("200px 90px 1fr"):
                    for st in cycles:
                        ui.link(st.cycle.name, f"/set/cycles?cycle={st.cycle.id}").classes("text-sm")
                        ui.label(f"{st.made} / {st.total} made").classes("text-sm")
                        notes = []
                        if st.missing:
                            notes.append("missing " + ", ".join(st.missing))
                        if st.edited:
                            notes.append(f"{st.edited} edited by hand")
                        ui.label(" · ".join(notes) or "complete").classes("text-sm text-gray-600")
            issues = stats.ability_word_issues(project)
            if issues:
                ui.label("Ability-word lines that follow no variant").classes("text-sm font-semibold mt-4")
                card_chips(list(dict.fromkeys(u.card.id for u in issues)))

        # ---------------------------------------------------------------- complexity
        def complexity_tables() -> None:
            with ui.row().classes("w-full gap-12 items-start"):
                with ui.column().classes("gap-1"):
                    ui.label("Average per card").classes("text-sm font-semibold")
                    with grid("90px 70px 80px 50px"):
                        for header in ("Rarity", "Words", "Abilities", "Cards"):
                            ui.label(header).classes("text-xs text-gray-500")
                        for r, (words, abilities, n) in stats.complexity_by_rarity(project).items():
                            ui.label(r.title()).classes("text-sm")
                            ui.label(f"{words:.1f}").classes("text-sm")
                            ui.label(f"{abilities:.1f}").classes("text-sm")
                            ui.label(str(n)).classes("text-sm")
                with ui.column().classes("gap-1 grow"):
                    ui.label("Wordiest commons").classes("text-sm font-semibold")
                    commons = sorted((stats.complexity(c) for c in stats.cards_at(project, "common")),
                                     key=lambda cx: -cx.words)[:8]
                    with grid("1fr 60px 70px"):
                        for header in ("Card", "Words", "Abilities"):
                            ui.label(header).classes("text-xs text-gray-500")
                        for cx in commons:
                            ui.link(cx.card.faces[0].name, f"/set/card/{cx.card.id}").classes("text-sm")
                            ui.label(str(cx.words)).classes("text-sm")
                            ui.label(str(cx.abilities)).classes("text-sm")

        # ---------------------------------------------------------------- page
        with ui.header().classes("items-center bg-slate-800 py-2"):
            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/set")) \
                .props("flat round color=white").tooltip("Back to the set overview").mark("back")
            ui.label("Set health").classes("text-lg font-semibold")
            ui.label(f"{project.info.name} · {len(project.cards)} cards").classes("text-sm opacity-70")

        with ui.column().classes("w-full gap-4").style("max-width:1200px"):
            warnings_section()
            with section("Mana curve"):
                ui.select(RARITY_CHOICES, value=view["curve_rarity"], label="Rarity",
                          on_change=lambda e: (view.update(curve_rarity=e.value), curve_chart.refresh())) \
                    .classes("w-48")
                curve_chart()
            with section("Cards per color and rarity"):
                counts_tables()
                creature_tables()
            with section("Roles per color"):
                ui.label("Detected from rules text; correct a card's roles in the editor. "
                         "Click a number to see the cards.").classes("text-xs text-gray-500")
                ui.select(RARITY_CHOICES, value=view["role_rarity"], label="Rarity",
                          on_change=lambda e: (view.update(role_rarity=e.value), roles_table.refresh())) \
                    .classes("w-48")
                roles_table()
            with section("Mechanics, archetypes and cycles"):
                mechanics_tables()
            with section("Complexity"):
                complexity_tables()


RARITY_LETTERS_BY_VALUE = {r.value: letter for r, letter in RARITY_LETTERS.items()}
