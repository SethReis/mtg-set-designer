"""The app as NiceGUI's simulated user runs it in tests: sets and settings live in the
folder given by $SETDESIGNER_TEST_DIR, and cards use the built-in renderer (no MSE)."""
import os
from pathlib import Path

from nicegui import ui

from setdesigner.render import CardRenderer
from setdesigner.ui.app import build

base = Path(os.environ["SETDESIGNER_TEST_DIR"])
build(sets_root=base / "sets", settings_path=base / "settings.json",
      renderer_factory=lambda project: CardRenderer(project, use_mse=False))
ui.run()
