"""Whole cards compared with real MSE's renders (tools/oracle_cases/renders*.txt).

Outside text boxes (frames, art, boxes, overlays) must match closely. Inside text
boxes, fonts are rasterized differently (FreeType vs Windows GDI), so we check the
layout instead: the same rows carry ink (first and last line within a few pixels).
The rarity symbol box is excluded: it is our own SVG/PNG symbol by design.
`python tools/compare_renders.py OUT` shows ours | MSE | difference side by side.
"""
import pytest

from render_compare import PACKAGES, compare_case, render_cases

CASES = render_cases()
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")

MAX_OUTSIDE_TEXT = 2.5          # mean channel difference (0-255) outside text boxes
MAX_INK_OFFSET = 4              # pixels, first/last inked row of each text box


@pytest.mark.parametrize("case", CASES, ids=[f"{c['file']}: {c['expr']}" for c in CASES])
def test_card_matches_mse(case) -> None:
    result = compare_case(case)
    assert result.outside_text <= MAX_OUTSIDE_TEXT, f"{result.uid}: {result.outside_text:.2f}"
    for region in result.text_regions:
        ours, theirs = region["ours"], region["theirs"]
        assert (ours is None) == (theirs is None), f"{result.uid}: text {region['text']!r} missing"
        if ours is not None:
            offset = max(abs(ours[0] - theirs[0]), abs(ours[1] - theirs[1]))
            assert offset <= MAX_INK_OFFSET, f"{result.uid}: {region['text']!r} ink rows {ours} vs {theirs}"
