"""Small pieces shared by the overview and the editor."""
from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from ..app.overview import color_key
from ..model import Card, Rarity
from .components import mana_cost

RARITY_LETTERS = {Rarity.COMMON: "C", Rarity.UNCOMMON: "U", Rarity.RARE: "R",
                  Rarity.MYTHIC: "M", Rarity.SPECIAL: "S"}
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


def card_name(card: Card) -> str:
    """The card's name as cards print it: "Front // Back" for two-faced cards."""
    return " // ".join(face.name or "(no name)" for face in card.faces)


def number_label(card: Card) -> str:
    n = card.collector_number
    return n.zfill(3) if n.isdigit() else n or "—"



TILE_BORDERS = {k: f"var(--mana-{k.lower()})" for k in "WUBRGMCL"}     # tokens.css


def skeleton_tile() -> None:
    """A card-shaped placeholder with a soft shimmer, while the card's picture is drawn."""
    ui.element("div").classes("ds-loading-tile")


def compact_tile(card: Card, width: int, face_index: int = 0) -> None:
    """A card (or one of its faces) as text in a card-shaped box: name, cost, type, start
    of the rules, P/T. It fills its container's width; `width` (the card size) picks the
    text size."""
    face = card.faces[face_index]
    small = width < 140
    stats = (f"{face.power}/{face.toughness}" if face.power or face.toughness
             else face.loyalty or "")
    with ui.element("div").classes("ds-text-tile").style(
            f"--tile-border:{TILE_BORDERS[color_key(card)]};font-size:{10 if small else 12}px"):
        with ui.element("div").classes("head"):
            ui.label(face.name or "(no name)").classes("name")
            if not small and face.mana_cost:
                mana_cost(face.mana_cost).classes("shrink-0")
        if len(card.faces) > 1 and face_index == 0:   # the back's name, as "// Back"
            ui.label(f"// {card.faces[1].name or '(no name)'}").classes("back")
        if not small:
            ui.label(face.type_line).classes("type")
        ui.label(face.rules_text).classes("rules").style(f"-webkit-line-clamp:{3 if small else 8}")
        with ui.element("div").classes("foot"):
            ui.element("span").classes(f"ds-status-dot {card.status.value}") \
                .tooltip(card.status.value.title())
            ui.label(f"{RARITY_LETTERS[card.rarity]} {number_label(card)}")
            if stats:
                ui.label(stats).classes("stats")
