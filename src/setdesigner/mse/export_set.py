"""Write a project as a Magic Set Editor set file (.mse-set).

Used to check our field computations against real MSE (tools/mse_oracle.py), and
later for "open this set in MSE". A .mse-set is a zip holding a `set` file in
MSE's indented key: value format.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from ..model import SetProject
from .frames import GAME, stylesheet_name, stylesheet_package
from .mapping import set_values
from .mechanics import mechanic_keyword, project_to_mse

MSE_VERSION = "2.6.0"


def _key(name: str) -> str:
    return name.replace(" ", "_")


def _entry(key: str, value: str, indent: int) -> list[str]:
    tabs = "\t" * indent
    if "\n" not in value:
        return [f"{tabs}{_key(key)}: {value}"]
    return [f"{tabs}{_key(key)}:"] + [f"{tabs}\t{line}" for line in value.split("\n")]


BLANK_SYMBOL = "blank.mse-symbol"            # an empty MSE symbol, stored inside the set file
BLANK_SYMBOL_TEXT = f"mse_version: {MSE_VERSION}\n"


def set_file_text(project: SetProject, only_uids: set[str] | None = None,
                  extra_set_values: dict[str, str] | None = None,
                  extra_card_values: dict[str, dict[str, str]] | None = None) -> str:
    """The `set` file. `only_uids` keeps just those MSE cards (reminder policies and
    other set-wide choices are still worked out on the whole project); the extra
    values are added to / override the set's and individual cards' field values."""
    info = project.info
    default_style = stylesheet_package(info.default_frame)
    lines = [f"mse_version: {MSE_VERSION}", f"game: {GAME}",
             f"stylesheet: {stylesheet_name(default_style)}", "set_info:"]
    for key, value in {**set_values(info), **(extra_set_values or {})}.items():
        lines += _entry(key, value, 1)
    for mechanic in project.mechanics:          # the set's own keywords
        lines.append("keyword:")
        for key, value in mechanic_keyword(mechanic).items():
            lines += _entry(key, value, 1)
    for card in project_to_mse(project):
        if only_uids is not None and card.uid not in only_uids:
            continue
        card.values = {**card.values, **(extra_card_values or {}).get(card.uid, {})}
        lines.append("card:")
        if card.stylesheet != default_style:
            lines += _entry("stylesheet", stylesheet_name(card.stylesheet), 1)
        lines += _entry("uid", card.uid, 1)
        if card.notes:
            lines += _entry("notes", card.notes, 1)
        for i, (uid, relation) in enumerate(card.links, 1):
            lines += _entry(f"linked card {i}", uid, 1)
            lines += _entry(f"linked relation {i}", relation, 1)
        for key, value in card.values.items():
            lines += _entry(key, value, 1)
    return "\n".join(lines) + "\n"


def write_mse_set(project: SetProject, path: Path, blank_symbol: bool = False, **options) -> Path:
    """Write a .mse-set. `blank_symbol` gives MSE an empty set symbol, so it draws no
    rarity symbol (we draw our own over its render). Other options: see set_file_text."""
    path = Path(path)
    if blank_symbol:
        options["extra_set_values"] = {"symbol": BLANK_SYMBOL, **options.get("extra_set_values", {})}
    elif project.info.symbol_path:              # MSE can't read our SVG/PNG symbols
        options["extra_set_values"] = {"symbol": "", **options.get("extra_set_values", {})}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("set", set_file_text(project, **options))
        if blank_symbol:
            z.writestr(BLANK_SYMBOL, BLANK_SYMBOL_TEXT)
    return path
