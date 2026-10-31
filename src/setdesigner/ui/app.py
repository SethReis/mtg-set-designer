"""The desktop app: page routes and startup. All behaviour lives in setdesigner.app;
these UI modules only arrange widgets and call into it.

    python -m setdesigner             # its own window
    python -m setdesigner --browser   # a browser tab instead (development)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import app, ui

from ..app.overview import Filters
from ..app.session import SetSession
from ..app.settings import Settings

REPO = Path(__file__).resolve().parents[3]
FRAME_LABELS = {"m15": "Modern (M15)", "ub": "Universes Beyond (M15)", "8th": "8th Edition (2003)",
                "old": "Classic (1997)", "4th": "4th Edition", "abu": "Alpha / Beta"}


@dataclass
class OverviewView:
    """How the overview is set up; kept while a set is open (back from the editor)."""
    mode: str = "rows"                      # "rows" or "matrix"
    group_by: str = "color"                 # rows mode
    rows: str = "color"                     # matrix mode
    columns: str = "rarity"
    sort: str = "number"
    filters: Filters = field(default_factory=Filters)
    cell: tuple[str, str, str, str] | None = None   # a matrix cell shown on its own
    collapsed: set[str] = field(default_factory=set)


@dataclass
class AppState:
    """What is open in the (single-user) app."""
    sets_root: Path = REPO / "sets"
    settings_path: Path | None = None
    renderer_factory: object = None             # tests pass the built-in renderer
    session: SetSession | None = None
    settings: Settings = field(default_factory=Settings)
    overview: OverviewView = field(default_factory=OverviewView)

    def open_session(self, session: SetSession) -> None:
        if self.session is not None:
            self.session.close()
        self.session = session
        self.overview = OverviewView()
        self.settings.remember(session.folder, self.settings_path)

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None


STATE = AppState()


def build(sets_root: Path | None = None, settings_path: Path | None = None,
          renderer_factory=None) -> AppState:
    """Register the pages. Returns the shared state (tests inspect it)."""
    from . import (cycles_page, editor_page, health_page, mechanics_page, overview_page, start_page,
                   uploads)
    STATE.sets_root = Path(sets_root) if sets_root else REPO / "sets"
    STATE.settings_path = settings_path
    STATE.renderer_factory = renderer_factory
    STATE.settings = Settings.load(settings_path)
    STATE.session = None
    start_page.register(STATE)
    overview_page.register(STATE)
    uploads.register(STATE)
    mechanics_page.register(STATE)
    cycles_page.register(STATE)
    health_page.register(STATE)
    editor_page.register(STATE)
    app.on_shutdown(STATE.close)
    return STATE


def main(argv: list[str] | None = None) -> None:
    """Start the app. $SETDESIGNER_SETS_DIR and $SETDESIGNER_SETTINGS override where new
    sets go and where settings are kept (e.g. for a portable copy or for testing)."""
    import os
    argv = sys.argv[1:] if argv is None else argv
    browser = "--browser" in argv
    settings = os.environ.get("SETDESIGNER_SETTINGS")
    state = build(sets_root=os.environ.get("SETDESIGNER_SETS_DIR") or None,
                  settings_path=Path(settings) if settings else None)
    if not browser:
        from .native_window import window_started      # spelling suggestions (see there)
        app.native.start_args["func"] = window_started
    ui.run(title="Set Designer", native=not browser, show=browser,
           window_size=None if browser else tuple(state.settings.window),
           reload=False, port=8765 if browser else None, favicon="🃏")
