"""The app shell of an open set (docs/design/layout.md): the left rail, the top bar, and
the region under it that a view fills.

    shell = set_shell(state, open_view=open_view, new_card=new_card)
    with shell.main:
        ...                                   # the workspace: toolbar and cards
    shell.set_health(len(warnings))           # the rail's warnings badge
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nicegui import ui

from . import components as c
from . import theme
from .widgets import served_url

# (view, label, icon, tooltip); "cards" is the workspace, the rest open over it
NAV = [("cards", "Cards", "view_module", "The set's cards"),
       ("notebook", "Notebook", "lightbulb", "Ideas before they're cards"),
       ("skeleton", "Skeleton", "grid_view", "The slots the set plans to fill"),
       ("mechanics", "Mechanics", "auto_fix_high", "Keywords and ability words"),
       ("cycles", "Cycles", "donut_large", "Cards made as a cycle"),
       ("archetypes", "Archetypes", "hub", "Draft archetypes and their targets"),
       ("health", "Health", "monitor_heart", "Curves, roles per color, mechanics, complexity"),
       ("balance", "Balance", "balance", "How strong each card and archetype is for its cost")]
FOOT = [("print", "Print", "print", "Print the set as paper proxies"),
        ("settings", "Set", "tune", "The set's name, frame, symbol and rarity targets"),
        ("sets", "Sets", "arrow_back", "Back to sets")]


@dataclass
class Shell:
    main: ui.element                       # under the top bar: the view fills it
    dialogs: ui.element                    # holds the modals (outlives refreshes)
    search: ui.input
    status: ui.label
    health: ui.button
    health_badge: ui.label
    dark: ui.dark_mode
    refresh_title: Callable[[], None]     # after the set's name, code or symbol change
    banner: ui.element = None              # full-width notices under the top bar (renderer_notice)
    renderer_chip: ui.button = None        # "Stand-in renderer" once its notice is put away
    notebook_badge: ui.label = None        # the Notebook rail item's Inbox count
    busy: Callable[[], bool] = lambda: False   # a modal is open: the shell's keys rest

    def set_inbox(self, ideas: int) -> None:
        """The Notebook rail item's count of ideas in the Inbox (hidden at 0)."""
        if self.notebook_badge is not None:
            self.notebook_badge.text = str(ideas)
            self.notebook_badge.set_visibility(ideas > 0)

    def set_health(self, warnings: int) -> None:
        self.health_badge.text = str(warnings)
        self.health_badge.set_visibility(warnings > 0)
        self.health.tooltip(f"{warnings} warning{'s' * (warnings != 1)}" if warnings else "Healthy")

    def set_status(self, text: str, kind: str = "success") -> None:
        colors = {"success": "--success", "muted": "--text-faint", "info": "--info", "danger": "--danger",
                  "warning": "--warning"}
        self.status.text = text
        self.status.style(f"--dot: var({colors[kind]})")


def set_shell(state, *, active: str = "cards", open_view: Callable[[str], None],
              new_card: Callable[[], None], new_idea: Callable[[], None] | None = None, on_search: Callable[[str], None] | None = None,
              search_text: str = "") -> Shell:
    """Build the shell for the open set. `open_view(view)` runs for a rail item ("mechanics",
    "settings", "sets", ...); `on_search` gets the top bar's search text."""
    session, settings = state.session, state.settings
    dark = theme.mode(settings.theme)

    # the page's own content area becomes the shell: no padding, the window's height
    ui.query(".nicegui-content").classes("p-0 gap-0 h-screen")
    app = ui.element("div").classes("ds-app" + (" rail-open" if settings.rail_open else ""))

    def rail_icon() -> str:
        return "keyboard_double_arrow_left" if settings.rail_open else "keyboard_double_arrow_right"

    def toggle_rail() -> None:
        settings.rail_open = not settings.rail_open
        app.classes(add="rail-open") if settings.rail_open else app.classes(remove="rail-open")
        collapse.props(f"icon={rail_icon()}")
        settings.save(state.settings_path)

    def nav(view: str, label: str, icon: str, tooltip: str) -> ui.button:
        b = ui.button(label, icon=icon, on_click=lambda v=view: open_view(v)) \
            .props("flat no-caps align=left").classes("ds-nav" + (" active" if view == active else "")) \
            .mark(f"nav-{view}")
        b.tooltip(f"{label} · {tooltip}")
        return b

    with app:
        # ------------------------------------------------------------ rail
        with ui.element("nav").classes("ds-rail"):
            with ui.row().classes("ds-brand no-wrap"):
                ui.icon("style")
                ui.label("Set Designer")
            for item in NAV:
                b = nav(*item)
                if item[0] == "notebook":
                    with b:
                        notebook_badge = ui.label().classes("ds-badge info ds-nav-badge")
                if item[0] == "health":
                    health = b.mark("health")
                    with b:
                        health_badge = ui.label().classes("ds-badge warning ds-nav-badge")
            ui.element("div").classes("grow")
            for item in FOOT:
                nav(*item)
            ui.element("hr").classes("ds-rule")
            collapse = ui.button("Collapse", on_click=toggle_rail) \
                .props(f"flat no-caps align=left icon={rail_icon()}") \
                .classes("ds-nav").mark("rail-toggle").tooltip("Toggle the sidebar · Ctrl+B")

        # ------------------------------------------------------------ top bar and view
        with ui.element("div").classes("ds-main"):
            with ui.element("header").classes("ds-topbar"):
                @ui.refreshable
                def title() -> None:
                    info = session.project.info
                    with ui.row().classes("ds-setname no-wrap items-center"):
                        symbol = session.project.resolve(info.symbol_path)
                        if symbol is not None and symbol.is_file() and symbol.suffix.lower() != ".svg":
                            ui.element("img").props(f'src="{served_url(session.folder, symbol)}" alt=""')
                        else:
                            ui.icon("style").classes("text-[22px]").style("color: var(--accent)")
                        ui.label(info.name).classes("display")
                        ui.label(info.code).classes("faint")
                title()
                search = ui.input(placeholder="Search name, type, rules", value=search_text) \
                    .props("dense outlined clearable debounce=250").classes("ds-search")
                with search.add_slot("prepend"):
                    ui.icon("search").classes("text-[18px]")
                if on_search:
                    search.on_value_change(lambda e: on_search(e.value or ""))
                ui.element("div").classes("grow")
                renderer_chip = c.button("Stand-in renderer", kind="ghost", icon="warning",
                                         tooltip="Cards aren't drawn by Magic Set Editor right now")                     .props("dense").classes("ds-renderer-chip").mark("renderer-chip")
                renderer_chip.set_visibility(False)
                status = c.status("All changes saved")
                if new_idea:
                    c.button(icon="lightbulb", kind="icon", on_click=new_idea,
                             tooltip="Catch an idea · Ctrl+Shift+N").mark("catch-idea")
                c.button("New card", kind="primary", icon="add", on_click=new_card,
                         tooltip="New card · Ctrl+N").props("no-wrap")
                with c.button(icon="more_horiz", kind="icon", tooltip="More").mark("more"):
                    with ui.menu().props("anchor='bottom right' self='top right'"):
                        ui.label("Theme").classes("ds-label px-4 pt-2")
                        for value, label in theme.THEMES.items():
                            ui.menu_item(label, on_click=lambda v=value: set_theme(v)) \
                                .classes("text-accent" if value == settings.theme else "") \
                                .mark(f"theme-{value}")
            banner = ui.element("div").classes("ds-banner")
            main = ui.element("div").classes("ds-view")
        dialogs = ui.element("div")

    def set_theme(value: str) -> None:
        settings.theme = value
        settings.save(state.settings_path)
        dark.value = theme.dark_value(value)

    def keys(e) -> None:
        if not e.action.keydown or not e.modifiers.ctrl or shell.busy():
            return
        key = e.key.name.lower() if e.key.name else ""
        if key == "b":
            toggle_rail()
        elif key == "k":
            search.run_method("focus")
        elif key == "n" and e.modifiers.shift:
            if new_idea:
                new_idea()
        elif key == "n":
            new_card()

    ui.keyboard(on_key=keys, ignore=["input", "select", "button", "textarea"])
    shell = Shell(main, dialogs, search, status, health, health_badge, dark, title.refresh, banner,
                  renderer_chip, notebook_badge)
    shell.set_health(0)
    shell.set_inbox(sum(1 for i in session.project.notebook if i.lane == "inbox"))
    return shell
