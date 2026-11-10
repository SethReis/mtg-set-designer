"""Balance (rail: Balance, /set?open=balance): how strong each card is for its cost and
each archetype for its deck, worked out by app.balance (docs/balance.md).

Three tabs: Cards (every card's worth against its cost, with a breakdown and the set's
closest cards), Archetypes (ranked by strength, with their key roles) and Norms (the values
scores use, overridable per set).
"""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..app import balance as bal
from ..app.health.roles import ROLES
from ..app.overview import color_key
from ..model import Card, Rarity
from . import components as c
from .widgets import card_name

VERDICTS = {"above": ("Above curve", "warning"), "on": ("On curve", "success"), "below": ("Below curve", "info")}


def signed(x: float) -> str:
    return f"{x:+.2g}" if abs(x) < 10 else f"{x:+.0f}"


def verdict_text(s: bal.Score) -> str:
    if s.verdict == "on":
        return "On curve"
    return f"{signed(s.delta)} {'above' if s.verdict == 'above' else 'below'}"


def balance_panel(state, m: c.Modal, *, select_id: str | None = None,
                  open_card: Callable[[Card], None], on_select: Callable[[str | None], None],
                  on_change: Callable[[], None]) -> None:
    session = state.session
    project = session.project
    view = {"tab": "cards", "id": select_id, "verdict": "", "rarity": "", "archetype": "", "open": None}

    def changed() -> None:
        body.refresh()
        on_change()

    def select(card_id: str | None) -> None:
        view["id"] = card_id
        body.refresh()
        on_select(card_id)

    # ---------------------------------------------------------------- cards
    def cards_tab() -> None:
        scored = bal.scores(project)
        offset = bal.set_offset(scored)
        cards = [x for x in project.cards if x.id in scored
                 and (not view["verdict"] or scored[x.id].verdict == view["verdict"])
                 and (not view["rarity"] or x.rarity.value == view["rarity"])
                 and (not view["archetype"] or view["archetype"] in x.archetypes)]
        cards.sort(key=lambda x: -abs(scored[x.id].delta))
        with ui.element("div").classes("ds-notebook-bar"):
            with ui.row().classes("items-center gap-2"):
                def pick(key, options, label):
                    ui.select({"": f"Any {label.lower()}", **options}, value=view[key], label=label,
                              on_change=lambda e, k=key: (view.update({k: e.value}), body.refresh())) \
                        .props("dense outlined").classes("w-40")
                pick("verdict", {k: v[0] for k, v in VERDICTS.items()}, "Verdict")
                pick("rarity", {r.value: r.value.title() for r in Rarity}, "Rarity")
                pick("archetype", {a.id: a.name for a in project.archetypes}, "Archetype")
                ui.element("div").classes("grow")
                ui.label(f"{len(cards)} of {len(scored)} cards · your set runs {signed(offset)} vs. the norms") \
                    .classes("muted text-sm")
        with ui.element("div").classes("ds-notebook-main"):
            with ui.element("div").classes("ds-notebook-board"):
                if not cards:
                    c.hint("No cards to score here." if scored else "Cards with a cost show here once you make some.")
                rows = []
                for card in cards:
                    s = scored[card.id]
                    def name_cell(x=card) -> None:
                        ui.label(card_name(x)).classes("ds-link truncate").on("click", lambda x=x: select(x.id)) \
                            .mark(f"balance-card-{x.id}")
                    def verdict_cell(s=s) -> None:
                        c.badge(verdict_text(s), VERDICTS[s.verdict][1])
                    rows.append([name_cell, card.rarity.value.title(), str(s.actual), f"{s.effective:g}",
                                 signed(s.delta), signed(s.delta - offset), verdict_cell,
                                 str(len(s.unscored)) if s.unscored else ""])
                c.data_table([c.Column("Card", "minmax(160px, 2fr)"), c.Column("Rarity"),
                              c.Column("Cost", "60px", "right"), c.Column("Worth", "70px", "right"),
                              c.Column("Gap", "60px", "right"), c.Column("Vs. set", "70px", "right"),
                              c.Column("Verdict", "minmax(120px, 1fr)"), c.Column("Unscored", "90px", "right")], rows)
            with ui.element("div").classes("ds-notebook-detail"):
                card_detail(scored)

    def card_detail(scored) -> None:
        card = next((x for x in project.cards if x.id == view["id"]), None)
        s = scored.get(view["id"] or "")
        if card is None or s is None:
            c.hint("Click a card to see how its worth adds up.").classes("p-4")
            return
        with ui.column().classes("w-full gap-3 p-4").mark("balance-detail"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.label(card_name(card)).classes("ds-section-title grow truncate")
                c.button(icon="edit", kind="icon", tooltip="Open in the editor", on_click=lambda: open_card(card))
                c.button(icon="close", kind="icon", tooltip="Close", on_click=lambda: select(None))
            with ui.row().classes("items-center gap-2"):
                c.mana_cost(card.faces[0].mana_cost or "—")
                c.badge(verdict_text(s), VERDICTS[s.verdict][1])
                ui.label(f"worth {s.effective:g} · costs {s.actual} · {card.rarity.value} "
                         f"tolerance ±{s.tolerance:g}").classes("muted text-sm")
            ui.label("How it adds up").classes("ds-label")
            with ui.column().classes("w-full gap-1").mark("balance-parts"):
                for label, value in s.parts:
                    with ui.row().classes("w-full no-wrap gap-2"):
                        ui.label(label).classes("grow")
                        ui.label(signed(value)).classes("num")
            if s.unscored:
                ui.label("Not scored").classes("ds-label")
                c.hint("The scorer doesn't understand these lines; the worth above leaves them out. "
                       "Add an adjustment if they matter.")
                for line in s.unscored:
                    ui.label(line).classes("muted text-sm")
            ui.label("Adjustment").classes("ds-label")
            with ui.row().classes("w-full no-wrap gap-2 items-start"):
                ui.number(value=card.balance_adjust or None, step=0.25, placeholder="0") \
                    .props("dense outlined suffix=mana").classes("w-32").mark("balance-adjust") \
                    .on("blur", lambda e, x=card: (session.update(x, "balance_adjust", e.sender.value), changed()))
                ui.input(value=card.balance_note, placeholder="Why (the scorer misses its drawback)") \
                    .props("dense outlined").classes("grow") \
                    .on("blur", lambda e, x=card: (session.update(x, "balance_note", e.sender.value), changed()))
            near = bal.similar(card, project, scored)
            if near:
                ui.label("Closest in your set").classes("ds-label")
                for other in near:
                    o = scored[other.id]
                    with ui.row().classes("w-full items-center no-wrap gap-2"):
                        ui.label(card_name(other)).classes("ds-link grow truncate") \
                            .on("click", lambda x=other: select(x.id))
                        ui.label(f"{o.actual} → {o.effective:g}").classes("num muted text-sm")
                        c.badge(verdict_text(o), VERDICTS[o.verdict][1])

    # ---------------------------------------------------------------- archetypes
    def archetypes_tab() -> None:
        ranked = bal.archetype_strength(project)
        with ui.element("div").classes("ds-balance-scroll"):
            if not ranked:
                c.hint("Add archetypes (rail: Archetypes) and tag cards with them to compare them here.")
                return
            c.hint("Strength mixes playables against target (40%), card power against the other "
                   "archetypes (30%) and key roles covered (30%).")
            for i, a in enumerate(ranked, 1):
                is_open = view["open"] == a.archetype.id
                with ui.element("div").classes("ds-balance-arch").mark(f"arch-{a.archetype.id}"):
                    head = ui.row().classes("w-full items-center no-wrap gap-3 cursor-pointer")
                    head.on("click", lambda aid=a.archetype.id: (
                        view.update(open=None if view["open"] == aid else aid), body.refresh()))
                    with head:
                        ui.label(f"{i}").classes("faint num w-5")
                        c.pips(a.archetype.colors)
                        ui.label(a.archetype.name).classes("font-medium grow truncate")
                        ui.label(f"{len(a.cards)}/{a.target} cards" if a.archetype.targets else f"{len(a.cards)} cards").classes("num muted text-sm")
                        ui.label("—" if a.average_delta is None else f"avg {signed(a.average_delta)}") \
                            .classes("num muted text-sm w-20")
                        for rid, n in a.role_counts.items():
                            c.badge(f"{bal.ROLE_LABELS.get(rid, rid)} {n}", "success" if n else "danger")
                        with ui.element("div").classes("ds-meter w-24").tooltip(
                                f"Playables {a.playables:.0%} · power {a.power:.0%} · roles {a.roles:.0%}"):
                            ui.element("div").classes("fill").style(f"width:{a.strength}%")
                        ui.label(str(a.strength)).classes("num font-medium w-8 text-right")
                        ui.icon("expand_less" if is_open else "expand_more").classes("faint")
                    if is_open:
                        archetype_detail(a)

    def archetype_detail(a: bal.ArchetypeStrength) -> None:
        with ui.column().classes("w-full gap-2 pt-3 pl-8"):
            curve = a.curve()
            if curve:
                ui.label("Curve").classes("ds-label")
                top = max(curve.values())
                with ui.row().classes("items-end gap-2 no-wrap"):
                    for mv, n in curve.items():
                        with ui.column().classes("items-center gap-1"):
                            ui.label(str(n)).classes("num text-xs faint")
                            ui.element("div").classes("ds-bar").style(f"height:{8 + 40 * n // top}px")
                            ui.label("7+" if mv == 7 else str(mv)).classes("num text-xs")
            options = {"two_drop": "Two-drops", **{rid: r.label for rid, r in ROLES.items()}}
            ui.select(options, multiple=True, value=bal.key_roles(a.archetype), label="Key roles",
                      on_change=lambda e, x=a.archetype: (session.update_archetype(x, key_roles=list(e.value or [])),
                                                          changed())) \
                .props("dense outlined use-chips").classes("w-full max-w-[560px]").mark("key-roles")

    # ---------------------------------------------------------------- norms
    def norms_tab() -> None:
        values = bal.norms(project)
        overrides = project.info.balance

        def set_norm(key: str, value) -> None:
            value = None if value in (None, "") else float(value)
            if value is not None and value == bal.NORMS[key][2]:
                value = None
            if overrides.get(key) != value:
                session.set_balance_norm(key, value)
                changed()

        with ui.element("div").classes("ds-balance-scroll"):
            c.hint("What scores count, in mana. Change any value for this set; Reset puts the default back.")
            for group in bal.GROUPS:
                ui.label(group).classes("ds-section-title mt-4")
                with ui.element("div").classes("ds-norms"):
                    for key, (g, label, default) in bal.NORMS.items():
                        if g != group:
                            continue
                        ui.label(label)
                        ui.number(value=values[key], step=0.05, format="%g") \
                            .props("dense outlined").classes("w-24").mark(f"norm-{key}") \
                            .on("blur", lambda e, k=key: set_norm(k, e.sender.value))
                        if key in overrides:
                            c.button("Reset", kind="ghost", on_click=lambda k=key: set_norm(k, None)) \
                                .props("dense").tooltip(f"Default {default:g}")
                        else:
                            ui.label("")

    @ui.refreshable
    def body() -> None:
        with ui.element("div").classes("ds-notebook w-full"):
            with ui.row().classes("ds-notebook-bar items-center gap-2 w-full"):
                c.segmented({"cards": "Cards", "archetypes": "Archetypes", "norms": "Norms"}, view["tab"],
                            lambda e: (view.update(tab=e.value), body.refresh())).mark("balance-tabs")
            if view["tab"] == "cards":
                cards_tab()
            elif view["tab"] == "archetypes":
                archetypes_tab()
            else:
                norms_tab()

    body()
