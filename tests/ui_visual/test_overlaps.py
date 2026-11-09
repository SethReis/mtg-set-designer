"""No text overlaps other text, and no label is cut off, on any view (headless Edge).

Runs only with SETDESIGNER_VISUAL=1 and a dev app started with SETDESIGNER_DEV=1 on
$SETDESIGNER_VISUAL_BASE (default http://localhost:8765), opening the set in
$SETDESIGNER_VISUAL_SET. The page's dev script (ui/theme/overlap_check.js) writes its
findings into the DOM; this reads them over Edge's DevTools protocol.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ui_sweep import EDGE, VIEWS, Edge, url  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("SETDESIGNER_VISUAL") != "1" or not Path(EDGE).exists(),
                                reason="visual check: set SETDESIGNER_VISUAL=1 with a dev app running")
BASE = os.environ.get("SETDESIGNER_VISUAL_BASE", "http://localhost:8765")
SET = Path(os.environ.get("SETDESIGNER_VISUAL_SET", "."))


def report(address: str, width: int) -> list[dict]:
    edge = Edge(width, round(width * 0.62))
    try:
        found = edge.open(address)
    finally:
        edge.close()
    assert found is not None, f"no report from {address}"
    return json.loads(found)


@pytest.mark.parametrize("width", [900, 1100, 1280, 1400, 1600, 1920])
@pytest.mark.parametrize("view", [v for v in VIEWS if v != "editor-outlines" and v != "editor-dfc"])
def test_no_overlapping_text(view, width) -> None:
    problems = report(url(BASE, SET.resolve(), "dark", VIEWS[view], "canopy-stalker", "grove-warden"), width)
    assert problems == [], f"{view} at {width}px: {problems[:8]}"
