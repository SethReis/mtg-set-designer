"""The shared building blocks of every screen (docs/design/components.md). They style
themselves only through the theme's tokens (ui/theme/), so screens built from them
follow the design language and both themes.

    button("Create 5 cards", kind="primary", on_click=create)
    with modal("md", "Set settings", parent=dialogs) as m:
        ...                                  # m.body, m.actions (header), m.footer
    choice = await confirm(dialogs, "Delete Hunt?", "Its 3 cards keep their text.")
"""
from __future__ import annotations

import asyncio
import html
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from nicegui import background_tasks, ui

from ..model import Rarity

LEAVE = 0.3                              # seconds: a closing modal's leave animation
BUTTON_PROPS = {
    "primary": "unelevated no-caps color=primary text-color=on-accent",
    "secondary": "outline no-caps",
    "ghost": "flat no-caps",
    "danger": "flat no-caps color=negative",
    "icon": "flat round dense",
}
# token values for things CSS variables can't reach (chart canvases): tokens.css --mana-*
MANA_COLORS = {"W": "#efe6c4", "U": "#4b8fd6", "B": "#8a7f93", "R": "#df5b3b", "G": "#3f9a5d",
               "M": "#d4af37", "C": "#a8aeb6", "L": "#a5835b"}


def button(label: str = "", *, kind: str = "secondary", icon: str | None = None,
           on_click: Callable | None = None, tooltip: str | None = None) -> ui.button:
    """A button in one of the design's kinds: primary (one per view), secondary, ghost,
    danger, or icon (a round icon-only button; give it a tooltip)."""
    b = ui.button(label, icon=icon, on_click=on_click).props(BUTTON_PROPS[kind])
    if kind == "secondary":
        b.classes("ds-secondary")
    if tooltip:
        b.tooltip(tooltip)
    return b


def segmented(options: dict | list, value, on_change: Callable | None = None) -> ui.toggle:
    """A segmented control (one of a few options, all visible)."""
    return ui.toggle(options, value=value, on_change=on_change) \
        .props("no-caps unelevated dense toggle-color=seg-on toggle-text-color=seg-on")


# ---------------------------------------------------------------------- text and data

SYMBOL = re.compile(r"\{([^}]+)\}")
MANA_GLYPHS = {"T": "tap", "Q": "untap", "∞": "infinity", "½": "1-2"}


def mana_glyph(symbol: str) -> str | None:
    """The Mana font class for a symbol's text inside braces ("W", "2", "W/U", "T"), or
    None when it isn't a mana symbol."""
    s = symbol.upper()
    if s in MANA_GLYPHS:
        return MANA_GLYPHS[s]
    if re.fullmatch(r"\d{1,2}|[WUBRGCXYZSE]", s):
        return s.lower()
    if re.fullmatch(r"([WUBRG2C])/([WUBRGP])", s):              # hybrid, Phyrexian, {2/W}
        return s.replace("/", "").lower()
    return None


def mana_html(text: str) -> str:
    """HTML for text with {symbols} drawn as mana symbols (the rest escaped)."""
    out, last = [], 0
    for m in SYMBOL.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        glyph = mana_glyph(m.group(1))
        out.append(f'<i class="ms ms-{glyph} ms-cost" title="{html.escape(m.group(0))}"></i>' if glyph
                   else html.escape(m.group(0)))
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def mana_cost(text: str) -> ui.html:
    """A mana cost (or any text with {symbols}) with real mana symbols."""
    return ui.html(mana_html(text), sanitize=False, tag="span").classes("whitespace-nowrap")


def pips(colors: str) -> ui.element:
    """8px color dots for color data ("WU", "M", "L"): quieter than mana symbols."""
    with ui.element("span").classes("inline-flex items-center gap-[3px]") as row:
        for color in colors:
            ui.element("span").classes(f"ds-pip {color}")
    return row


def rarity_letter(rarity: Rarity) -> ui.label:
    return ui.label(rarity.value[0].upper()).classes(f"ds-rarity {rarity.value}").tooltip(rarity.value.title())


def badge(text: str, kind: str = "neutral") -> ui.label:
    """A pill for a state: warning, success, info, danger, neutral."""
    return ui.label(text).classes(f"ds-badge {kind}")


def status(text: str, kind: str = "success") -> ui.label:
    """The quiet "dot + text" status (saving, drawing, errors)."""
    colors = {"success": "--success", "muted": "--text-faint", "info": "--info", "danger": "--danger",
              "warning": "--warning"}
    return ui.label(text).classes("ds-status").style(f"--dot: var({colors[kind]})")


def label(text: str) -> ui.label:
    """A field or group label (above its control)."""
    return ui.label(text).classes("ds-label")


def hint(text: str) -> ui.label:
    return ui.label(text).classes("ds-hint")


# ---------------------------------------------------------------------- containers

@contextmanager
def section(title: str | None = None, *, actions: Callable[[], None] | None = None) -> Iterator[ui.element]:
    """A panel with an optional title row (actions on its right)."""
    with ui.element("div").classes("ds-section w-full") as panel:
        if title or actions:
            with ui.row().classes("w-full items-center gap-2 no-wrap mb-3"):
                if title:
                    ui.label(title).classes("ds-section-title")
                ui.space()
                if actions:
                    actions()
        yield panel


def empty_state(icon: str, title: str, hint_text: str = "", *, action: str | None = None,
                on_action: Callable | None = None) -> ui.element:
    """What a region shows when it has nothing yet."""
    with ui.element("div").classes("ds-empty w-full") as box:
        ui.icon(icon)
        ui.label(title).classes("ds-empty-title")
        if hint_text:
            ui.label(hint_text).classes("text-sm")
        if action:
            button(action, kind="primary", on_click=on_action).classes("mt-2")
    return box


@contextmanager
def list_row(*, selected: bool = False, on_click: Callable | None = None) -> Iterator[ui.element]:
    """A 34px row of a list (selection shown with the accent bar)."""
    row = ui.element("div").classes("ds-list-row" + (" selected" if selected else ""))
    if on_click:
        row.on("click", on_click)
    with row:
        yield row


@dataclass
class Column:
    label: str
    track: str = "minmax(80px, 1fr)"      # its grid track
    align: str = "left"                    # "left" or "right" (numbers)


def data_table(columns: list[Column], rows: list[list]) -> ui.element:
    """A table on a CSS grid: sticky header, fluid tracks. A cell is text or a function
    that builds its content."""
    template = " ".join(c.track for c in columns)
    with ui.element("div").classes("ds-table").style(f"grid-template-columns:{template}") as table:
        for c in columns:
            ui.label(c.label).classes("ds-th" + (" right" if c.align == "right" else ""))
        for row in rows:
            for c, cell in zip(columns, row):
                with ui.element("div").classes("ds-td" + (" right" if c.align == "right" else "")):
                    if callable(cell):
                        cell()
                    elif cell is not None:
                        ui.label(str(cell)).classes("truncate")
    return table


# ---------------------------------------------------------------------- modals

@dataclass
class Modal:
    dialog: ui.dialog
    card: ui.card
    title: ui.label
    subtitle: ui.label
    actions: ui.element                    # the header's right side, before the close button
    body: ui.element
    footer: ui.element | None

    def open(self) -> None:
        self.dialog.open()

    def close(self) -> None:
        self.dialog.close()


@contextmanager
def modal(size: str, title: str, *, parent: ui.element, subtitle: str | None = None,
          footer: bool = False, on_close: Callable | None = None, persistent: bool | None = None,
          ) -> Iterator[Modal]:
    """A dialog over the blurred page: sm (confirmations), md, lg, or workspace (94vw ×
    92vh). Content built inside the `with` goes into the body. `parent` is a container that
    outlives refreshes (a page's dialog holder). Workspace modals ignore clicks outside."""
    persistent = size == "workspace" if persistent is None else persistent
    with parent, ui.dialog() as dialog, ui.card().classes(f"ds-modal ds-modal-{size}") as card:
        if persistent:                     # a stray click outside mustn't close it; Esc does
            dialog.props("no-backdrop-dismiss")
        with ui.element("div").classes("ds-modal-head"):
            title_label = ui.label(title).classes("ds-modal-title truncate")
            subtitle_label = ui.label(subtitle or "").classes("muted truncate")
            subtitle_label.set_visibility(bool(subtitle))
            ui.space()
            actions = ui.row().classes("items-center gap-1 no-wrap")
            button(icon="close", kind="icon", on_click=dialog.close, tooltip="Close · Esc").mark("modal-close")
        body = ui.element("div").classes("ds-modal-body")
        foot = ui.element("div").classes("ds-modal-foot") if footer else None
    # a modal is built for one showing: closed, it goes (after Quasar's leave animation)
    dialog.on_value_change(lambda e: None if e.value else background_tasks.create(_retire(dialog)))
    if on_close:
        dialog.on_value_change(lambda e: None if e.value else on_close())
    m = Modal(dialog, card, title_label, subtitle_label, actions, body, foot)
    with body:
        yield m


async def _retire(dialog: ui.dialog) -> None:
    await asyncio.sleep(LEAVE)
    if not dialog.is_deleted:
        dialog.delete()


async def confirm(parent: ui.element, title: str, message: str = "", *, confirm_label: str = "Delete",
                  kind: str = "danger", extra: str | None = None, details: Callable[[], None] | None = None,
                  ) -> str | None:
    """Ask before something destructive or wide. Returns "confirm", "extra" (the optional
    middle button, e.g. "Keep card text"), or None for Cancel / Esc."""
    with modal("sm" if details is None else "md", title, parent=parent, footer=True, persistent=False) as m:
        if message:
            ui.label(message).classes("text-sm")
        if details:
            details()
    with m.footer:
        button("Cancel", kind="ghost", on_click=lambda: m.dialog.submit(None))
        if extra:
            button(extra, kind="secondary", on_click=lambda: m.dialog.submit("extra"))
        ui.button(confirm_label, on_click=lambda: m.dialog.submit("confirm")) \
            .props("unelevated no-caps " + ("color=negative" if kind == "danger" else BUTTON_PROPS["primary"]))
    return await m.dialog
