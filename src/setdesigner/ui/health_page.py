"""Health, a workspace modal laid out as a dashboard: warnings from the set-health checks
beside curves, roles per color, mechanics and archetypes, and complexity (see app/health/)."""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app.health import stats
from ..app.health.checks import CHECKS, enabled, run_checks
from ..app.health.roles import ROLES
from ..app.overview import COLOR_LABELS, MANA_VALUES
from ..model import Card
from . import components as c
from .widgets import RARITY_LETTERS, number_label

RARITY_CHOICES = {"": "All rarities", "common": "Common", "uncommon": "Uncommon", "rare": "Rare",
                  "mythic": "Mythic", "special": "Special"}
RARITY_LETTERS_BY_VALUE = {r.value: letter for r, letter in RARITY_LETTERS.items()}
CHART_TEXT = "#8b93a1"                   # chart labels: readable on both themes' surfaces
NAME = "minmax(120px, 1.4fr)"            # a table's name column
NUMBER = "minmax(48px, 1fr)"             # and its number columns


def rarity_counts(by_rarity: dict[str, int]) -> str:
    """Counts per rarity, as "C 2 · U 1"."""
    return " · ".join(f"{RARITY_LETTERS_BY_VALUE[r]} {n}" for r, n in by_rarity.items()) or "—"


def color_cell(key: str) -> Callable[[], None]:
    def build() -> None:
        with ui.row().classes("items-center gap-2 no-wrap"):
            c.pips(key)
            ui.label(COLOR_LABELS[key])
    return build


def health_panel(state, m: c.Modal, *, open_card: Callable[[Card], None],
                 open_cycle: Callable[[str], None], on_change: Callable[[], None]) -> None:
    """Build the Health dashboard into the modal `m`. `on_change` runs when the checks are
    tuned (the rail's warnings badge)."""
    session = state.session
    project = session.project
    view = {"curve_rarity": "", "role_rarity": "common"}
    by_id = {x.id: x for x in project.cards}

    def card_chips(card_ids) -> None:
        with ui.row().classes("gap-1 flex-wrap"):
            for cid in card_ids:
                card = by_id.get(cid)
                if card is not None:
                    ui.chip(f"{number_label(card)} {card.faces[0].name}", on_click=lambda x=card: open_card(x)) \
                        .props("dense clickable outline").classes("text-xs")

    def show_cards(title: str, cards: list[Card]) -> None:
        with c.modal("sm", title, parent=m.body, persistent=False) as shown:
            if cards:
                card_chips([x.id for x in cards])
            else:
                c.hint("No cards.")
        shown.open()

    def card_link(card: Card) -> Callable[[], None]:
        return lambda: c.button(card.faces[0].name, kind="ghost", on_click=lambda: open_card(card)) \
            .props("dense").classes("truncate max-w-full")

    def number(n: int, wanted: int | None = None) -> Callable[[], None]:
        text = f"{n} / {wanted}" if wanted else str(n)
        short = wanted is not None and n < wanted
        return lambda: ui.label(text).classes("num" + (" warning-text font-semibold" if short else ""))

    # ---------------------------------------------------------------- warnings
    @ui.refreshable
    def warnings_section() -> None:
        found = run_checks(project)
        checks = sum(enabled(project, x) for x in CHECKS.values())

        def actions() -> None:
            c.button("Tune checks", kind="ghost", icon="tune", on_click=tune).props("dense")
        with c.section("Warnings" if found else "No warnings", actions=actions):
            c.hint(f"{len(found)} warning{'s' * (len(found) != 1)} from {checks} checks")
            for check in CHECKS.values():
                mine = [w for w in found if w.check_id == check.id]
                if not mine:
                    continue
                ui.label(check.label).classes("ds-form-h")
                for w in mine:
                    icon = "warning" if w.severity == "warning" else "info"
                    color = "warning" if w.severity == "warning" else "info"
                    if w.card_ids:                  # opens to the cards
                        with ui.expansion().props("dense header-class='px-1 py-1 min-h-0'") \
                                .classes("w-full") as expansion:
                            with expansion.add_slot("header"), ui.row().classes("items-center gap-2 grow no-wrap"):
                                ui.icon(icon, color=color).classes("text-[18px]")
                                ui.label(w.message).classes("grow")
                                c.badge(f"{len(w.card_ids)} card{'s' * (len(w.card_ids) != 1)}")
                            with ui.element("div").classes("pl-8 pb-2"):
                                card_chips(w.card_ids)
                    else:
                        with ui.row().classes("items-center gap-2 px-1 py-1 no-wrap"):
                            ui.icon(icon, color=color).classes("text-[18px]")
                            ui.label(w.message)

    def tune() -> None:
        rows = []
        with c.modal("md", "Tune checks", parent=m.body, footer=True, persistent=False) as tuning:
            c.hint("Saved with the set. Leave a number empty for the default.")
            for check in CHECKS.values():
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    on = ui.checkbox(check.label, value=enabled(project, check)).classes("grow")
                    field = None
                    if check.default is not None:
                        setting = project.info.health.get(check.id)
                        field = ui.number(value=setting.threshold if setting else None,
                                          placeholder=f"{check.default:g}", min=0) \
                            .props("dense outlined").classes("w-20").mark(f"threshold-{check.id}")
                    # the unit beside the field, in a fixed column so the fields line up
                    ui.label(check.unit if field else "").classes("muted text-sm w-40 shrink-0")
                    rows.append((check, on, field))

        def save() -> None:
            for check, on, field in rows:
                value = float(field.value) if field is not None and field.value not in (None, "") else None
                setting = project.info.health.get(check.id)
                if setting is None and on.value and value is None:
                    continue
                session.set_health_check(check.id, bool(on.value), value)
            tuning.close()
            warnings_section.refresh()
            on_change()
        with tuning.footer:
            c.button("Cancel", kind="ghost", on_click=tuning.close)
            c.button("Save", kind="primary", on_click=save)
        tuning.open()

    # ---------------------------------------------------------------- curves and counts
    @ui.refreshable
    def curve_chart() -> None:
        data = stats.curve(project, view["curve_rarity"] or None)
        series = []
        for color, by_mv in data.items():
            if any(sum(v) for v in by_mv.values()):
                series.append({"name": COLOR_LABELS[color], "type": "bar", "stack": "all",
                               "itemStyle": {"color": c.MANA_COLORS[color]},
                               "data": [sum(by_mv[mv]) for mv in MANA_VALUES]})
        axis = {"axisLine": {"lineStyle": {"color": CHART_TEXT}}, "axisLabel": {"color": CHART_TEXT},
                "splitLine": {"lineStyle": {"color": "rgba(139,147,161,.18)"}}}
        ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"top": 0, "textStyle": {"color": CHART_TEXT}},
                   "textStyle": {"fontFamily": "Inter, sans-serif"},
                   "grid": {"left": 30, "right": 10, "top": 34, "bottom": 30},
                   "xAxis": {"type": "category", "data": MANA_VALUES, "name": "Mana value",
                             "nameTextStyle": {"color": CHART_TEXT}, **axis},
                   "yAxis": {"type": "value", "minInterval": 1, **axis},
                   "series": series}).classes("w-full h-64")

    def counts_table() -> None:
        counts = stats.color_rarity_counts(project)
        rarities = stats.RARITIES
        wanted = {k.value: v for k, v in project.info.rarity_slots.items()}
        columns = [c.Column("Color", NAME), *[c.Column(r.title(), NUMBER, "right") for r in rarities],
                   c.Column("Total", NUMBER, "right")]
        rows = [[color_cell(color), *[str(row[r]) for r in rarities], str(sum(row.values()))]
                for color, row in counts.items() if sum(row.values())]
        rows.append([lambda: ui.label("All").classes("font-semibold"),
                     *[number(sum(row[r] for row in counts.values()), wanted.get(r)) for r in rarities],
                     number(len(project.cards))])
        c.data_table(columns, rows)

    def creature_tables() -> None:
        with ui.element("div").classes("ds-dash-pair"):
            with ui.column().classes("gap-2 min-w-0"):
                ui.label("Creatures among commons").classes("ds-form-h")
                c.data_table([c.Column("Color", NAME), c.Column("Creatures", "minmax(110px, 1fr)", "right")],
                             [[color_cell(color), f"{n} / {total}  ({100 * n / total:.0f}%)"]
                              for color, (n, total) in stats.creature_ratio(project, "common").items() if total])
            with ui.column().classes("gap-2 min-w-0"):
                ui.label("Average common creature").classes("ds-form-h")
                c.data_table([c.Column("Mana value", NUMBER),
                              c.Column("Power / tough.", "minmax(90px, 1fr)", "right"),
                              c.Column("Cards", NUMBER, "right")],
                             [[mv, f"{power:.1f} / {tough:.1f}", str(n)]
                              for mv, (power, tough, n) in stats.creature_size(project).items()])

    # ---------------------------------------------------------------- roles
    @ui.refreshable
    def roles_table() -> None:
        table = stats.role_table(project, view["role_rarity"] or None)
        role_ids = list(ROLES)

        def cell(color: str, rid: str, cards: list[Card]) -> Callable[[], None]:
            def build() -> None:
                weak = color in "WUBRG" and rid == "removal" and not cards
                b = c.button(str(len(cards)) if cards else "–", kind="ghost",
                             on_click=lambda: show_cards(f"{COLOR_LABELS[color]} · {ROLES[rid].label}", cards)) \
                    .props("dense").classes("num")
                if weak:
                    b.classes("warning-text").tooltip("No removal at this rarity")
            return build
        rows = [[color_cell(color), *[cell(color, rid, row[rid]) for rid in role_ids]]
                for color, row in table.items() if color in "WUBRG" or any(row.values())]
        with ui.element("div").classes("w-full overflow-x-auto"):
            c.data_table([c.Column("Color", NAME), *[c.Column(ROLES[rid].label, "minmax(112px, 1fr)", "right")
                                                     for rid in role_ids]], rows)

    # ---------------------------------------------------------------- mechanics & archetypes
    def mechanics_tables() -> None:
        spreads = stats.mechanic_spread(project)
        if spreads:
            ui.label("Mechanics").classes("ds-form-h")
            cols = ["W", "U", "B", "R", "G", "M", "C", "L"]
            with ui.element("div").classes("w-full overflow-x-auto"):
                c.data_table([c.Column("Mechanic", NAME),
                              *[c.Column(x, "minmax(30px, .5fr)", "right") for x in cols],
                              c.Column("By rarity", "minmax(120px, 1.4fr)"), c.Column("Cards", NUMBER, "right")],
                             [[s.mechanic.name, *[str(s.by_color.get(x, "")) or "·" for x in cols],
                               rarity_counts(s.by_rarity), str(s.cards)] for s in spreads])
        coverage = stats.archetype_coverage(project)
        if coverage:
            ui.label("Archetypes").classes("ds-form-h")
            c.data_table([c.Column("Archetype", NAME),
                          *[c.Column(r.title(), NUMBER, "right") for r in stats.RARITIES]],
                         [[cov.archetype.name,
                           *[number(cov.counts[r], cov.targets.get(r)) if cov.targets.get(r) or cov.counts[r]
                             else "·" for r in stats.RARITIES]] for cov in coverage])
        cycles = stats.cycle_completeness(project)
        if cycles:
            ui.label("Cycles").classes("ds-form-h")

            def link(st) -> Callable[[], None]:
                return lambda: c.button(st.cycle.name, kind="ghost", on_click=lambda: open_cycle(st.cycle.id)) \
                    .props("dense").classes("truncate max-w-full")

            def notes(st) -> str:
                parts = (["missing " + ", ".join(st.missing)] if st.missing else []) \
                    + ([f"{st.edited} edited by hand"] if st.edited else [])
                return " · ".join(parts) or "complete"
            c.data_table([c.Column("Cycle", NAME), c.Column("Made", NUMBER, "right"),
                          c.Column("Notes", "minmax(160px, 2fr)")],
                         [[link(st), f"{st.made} / {st.total}", notes(st)] for st in cycles])
        issues = stats.ability_word_issues(project)
        if issues:
            ui.label("Ability-word lines that follow no variant").classes("ds-form-h")
            card_chips(list(dict.fromkeys(u.card.id for u in issues)))
        if not (spreads or coverage or cycles or issues):
            c.hint("No mechanics, archetypes or cycles yet.")

    # ---------------------------------------------------------------- complexity
    def complexity_tables() -> None:
        with ui.element("div").classes("ds-dash-pair"):
            with ui.column().classes("gap-2 min-w-0"):
                ui.label("Average per card").classes("ds-form-h")
                c.data_table([c.Column("Rarity", NAME), c.Column("Words", NUMBER, "right"),
                              c.Column("Abilities", NUMBER, "right"), c.Column("Cards", NUMBER, "right")],
                             [[r.title(), f"{words:.1f}", f"{abilities:.1f}", str(n)]
                              for r, (words, abilities, n) in stats.complexity_by_rarity(project).items()])
            with ui.column().classes("gap-2 min-w-0"):
                ui.label("Wordiest commons").classes("ds-form-h")
                commons = sorted((stats.complexity(x) for x in stats.cards_at(project, "common")),
                                 key=lambda cx: -cx.words)[:8]
                c.data_table([c.Column("Card", "minmax(140px, 2fr)"), c.Column("Words", NUMBER, "right"),
                              c.Column("Abilities", NUMBER, "right")],
                             [[card_link(cx.card), str(cx.words), str(cx.abilities)] for cx in commons])

    # ---------------------------------------------------------------- layout
    m.subtitle.text = f"{len(project.cards)} cards"
    m.subtitle.set_visibility(True)
    with ui.element("div").classes("ds-dash"):
        with ui.element("div").classes("ds-dash-side"):
            warnings_section()
        with ui.element("div").classes("ds-dash-main"):
            def rarity_select(key: str, refresh) -> None:
                ui.select(RARITY_CHOICES, value=view[key], label="Rarity",
                          on_change=lambda e: (view.update({key: e.value}), refresh.refresh())) \
                    .props("dense outlined options-dense").classes("w-44")
            with c.section("Mana curve", actions=lambda: rarity_select("curve_rarity", curve_chart)):
                curve_chart()
            with c.section("Cards per color and rarity"):
                counts_table()
                creature_tables()
            with c.section("Roles per color", actions=lambda: rarity_select("role_rarity", roles_table)):
                c.hint("Detected from rules text and the roles given to mechanics; correct a card's roles in "
                       "the editor. Click a number to see the cards.").classes("mb-2 block")
                roles_table()
            with c.section("Mechanics, archetypes and cycles"):
                mechanics_tables()
            with c.section("Complexity"):
                complexity_tables()
