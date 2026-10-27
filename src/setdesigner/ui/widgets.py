"""Small pieces shared by the overview and the editor."""
from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from ..app.overview import color_key
from ..model import Card, Rarity, Status

COLOR_PIPS = {"W": "#f3eccb", "U": "#3b82c4", "B": "#3a3434", "R": "#d9472b", "G": "#2f8f4e"}
# tile borders by overview color group (M multicolor, C colorless, L land)
COLOR_BORDERS = {"W": "#d8cc9a", "U": "#3b82c4", "B": "#3a3434", "R": "#d9472b", "G": "#2f8f4e",
                 "M": "#c9a227", "C": "#9aa3ab", "L": "#8b6b4a"}
RARITY_LETTERS = {Rarity.COMMON: "C", Rarity.UNCOMMON: "U", Rarity.RARE: "R",
                  Rarity.MYTHIC: "M", Rarity.SPECIAL: "S"}
STATUS_DOTS = {Status.IDEA: "#cbd5e1", Status.DRAFT: "#facc15", Status.PLAYTESTED: "#60a5fa",
               Status.FINAL: "#22c55e"}
CARD_RATIO = 523 / 375                   # height / width of an M15 card
PEEK = 0.12                              # share of a stacked card left showing: its name bar

# Stacks: each card after the first is pulled up over the one before it, so only name bars
# show. Hovering a card pushes the next one (and so everything below) down to reveal it.
# A stack sets --card-h (tile height); PEEK is the part of each card that stays visible.
STACK_CSS = f"""
.card-stack {{ display: flex; flex-direction: column; width: max-content; }}
.card-stack > .stack-card {{ border-radius: 6px; box-shadow: 0 -1px 4px rgba(0, 0, 0, .35); }}
.card-stack > .stack-card + .stack-card {{
    margin-top: calc(var(--card-h) * {PEEK - 1:.3f});
    transition: margin-top .15s ease;
}}
.card-stack > .stack-card:hover + .stack-card {{ margin-top: 0; }}
"""


_served: dict[str, str] = {}             # local folder -> URL it is served at


def served_url(folder: Path, path: Path) -> str:
    """A URL for a file in a local folder (card pictures, a set's assets). Each folder is
    served once; a `?v=` stamp makes the browser reload a file that was replaced."""
    import hashlib
    key = str(Path(folder).resolve())
    if key not in _served:
        Path(folder).mkdir(parents=True, exist_ok=True)
        url = f"/files/{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"
        app.add_static_files(url, folder)
        _served[key] = url
    relative = Path(path).resolve().relative_to(key).as_posix()
    stamp = Path(path).stat().st_mtime_ns if Path(path).is_file() else 0
    return f"{_served[key]}/{relative}?v={stamp}"


def responsive_grid(min_px: int, gap: int = 12, columns: str | None = None) -> ui.element:
    """A full-width grid whose children stretch to fill the row and wrap onto more rows
    as the window narrows (each at least `min_px` wide). `columns` replaces the default
    `repeat(auto-fit, minmax(min_px, 1fr))` template."""
    template = columns or f"repeat(auto-fit, minmax({min_px}px, 1fr))"
    return ui.element("div").classes("w-full items-center") \
        .style(f"display:grid;grid-template-columns:{template};gap:{gap}px")


def grid_cells() -> ui.element:
    """A wrapper whose children act as cells of the surrounding grid (display: contents),
    e.g. for a refreshable group of controls."""
    return ui.element("div").style("display:contents")


def number_label(card: Card) -> str:
    n = card.collector_number
    return n.zfill(3) if n.isdigit() else n or "—"


def color_pips(card: Card) -> None:
    for color in card.color_identity:
        ui.element("span").style(f"width:9px;height:9px;border-radius:50%;flex:none;"
                                 f"background:{COLOR_PIPS[color]};border:1px solid #888")


def compact_tile(card: Card, width: int) -> None:
    """A card as text in a card-shaped box: name, cost, type, start of the rules, P/T."""
    face = card.faces[0]
    small = width < 140
    stats = (f"{face.power}/{face.toughness}" if face.power or face.toughness
             else face.loyalty or "")
    with ui.column().classes("gap-0 bg-white rounded overflow-hidden").style(
            f"width:{width}px;height:{round(width * CARD_RATIO)}px;"
            f"border:3px solid {COLOR_BORDERS[color_key(card)]};"
            f"font-size:{10 if small else 12}px;line-height:1.25"):
        with ui.row().classes("w-full no-wrap items-center gap-1 px-1 py-0.5 bg-gray-100"):
            ui.label(face.name or "(no name)").classes("font-semibold truncate grow")
            if not small:
                ui.label(face.mana_cost.replace("}{", "").strip("{}")).classes("text-gray-600 shrink-0")
        if not small:
            ui.label(face.type_line).classes("w-full px-1 truncate text-gray-600 italic")
        ui.label(face.rules_text).classes("w-full px-1 grow overflow-hidden whitespace-pre-line") \
            .style("display:-webkit-box;-webkit-box-orient:vertical;"
                   f"-webkit-line-clamp:{3 if small else 8}")
        with ui.row().classes("w-full no-wrap items-center gap-1 px-1 py-0.5 text-gray-500"):
            ui.element("span").style(f"width:8px;height:8px;border-radius:50%;flex:none;"
                                     f"background:{STATUS_DOTS[card.status]}") \
                .tooltip(card.status.value.title())
            ui.label(f"{RARITY_LETTERS[card.rarity]} {number_label(card)}").classes("grow")
            if stats:
                ui.label(stats).classes("font-semibold text-gray-800")
