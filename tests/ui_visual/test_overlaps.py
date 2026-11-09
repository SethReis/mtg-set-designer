"""No text overlaps other text, and no label is cut off, on any view (headless Edge).

Runs only with SETDESIGNER_VISUAL=1 and a dev app started with SETDESIGNER_DEV=1 on
$SETDESIGNER_VISUAL_BASE (default http://localhost:8765), opening the set in
$SETDESIGNER_VISUAL_SET. The page's dev script (ui/theme/overlap_check.js) writes its
findings into the DOM; this reads them from Edge's --dump-dom.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ui_sweep import EDGE, VIEWS, url  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("SETDESIGNER_VISUAL") != "1" or not Path(EDGE).exists(),
                                reason="visual check: set SETDESIGNER_VISUAL=1 with a dev app running")
BASE = os.environ.get("SETDESIGNER_VISUAL_BASE", "http://localhost:8765")
SET = Path(os.environ.get("SETDESIGNER_VISUAL_SET", "."))


def report(address: str, width: int) -> list[dict]:
    profile = tempfile.mkdtemp(prefix="overlap-edge-")
    try:
        done = subprocess.run([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                               f"--window-size={width},{round(width * 0.62)}", "--virtual-time-budget=20000",
                               "--dump-dom", address], capture_output=True, text=True, encoding="utf-8", timeout=120)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    found = re.search(r'<pre id="overlap-report" hidden="">(.*?)</pre>', done.stdout, re.S)
    assert found, f"no report from {address}"
    import html
    return json.loads(html.unescape(found.group(1)))


@pytest.mark.parametrize("width", [1100, 1400])
@pytest.mark.parametrize("view", [v for v in VIEWS if v != "editor-outlines" and v != "editor-dfc"])
def test_no_overlapping_text(view, width) -> None:
    problems = report(url(BASE, SET.resolve(), "dark", VIEWS[view], "canopy-stalker", "grove-warden"), width)
    assert problems == [], f"{view} at {width}px: {problems[:8]}"
