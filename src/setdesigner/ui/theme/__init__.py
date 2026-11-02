"""The app's theme (docs/design/): token and Quasar stylesheets, bundled fonts, and the
dark/light mode from Settings.theme.

    theme.apply()                      # once, when the pages are registered
    theme.mode(settings.theme)         # on each page: dark, light or follow the system
"""
from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

FOLDER = Path(__file__).parent
URL = "/theme"
STYLESHEETS = ["tokens.css", "base.css", "fonts/mana.css"]
THEMES = {"dark": "Dark", "light": "Light", "system": "Match the system"}


def apply() -> None:
    """Serve the theme folder and add its stylesheets to every page (once per app start)."""
    app.add_static_files(URL, FOLDER)
    links = "".join(f'<link rel="stylesheet" href="{URL}/{name}?v={(FOLDER / name).stat().st_mtime_ns}">'
                    for name in STYLESHEETS)          # ?v=: no stale copy after an update
    ui.add_head_html(links, shared=True)


def dark_value(theme: str) -> bool | None:
    """Quasar's dark setting for a Settings.theme: True, False, or None (the system's)."""
    return {"dark": True, "light": False}.get(theme)


def mode(theme: str) -> ui.dark_mode:
    """Set this page's light or dark mode ("system" follows the operating system)."""
    return ui.dark_mode(dark_value(theme))
