"""Whole cards compared with real MSE's renders (tools/oracle_cases/renders*.txt).

Outside text boxes (frames, art, boxes, overlays) the pixels must match. Inside text
boxes glyphs are drawn like MSE draws them (4x and averaged down, Windows line metrics)
but rasterized by FreeType instead of Windows GDI, so pixels differ a little: we check
the mean difference and that the same rows carry ink (first and last line within a pixel).
The rarity symbol box is excluded: it is our own SVG/PNG symbol by design.
`python tools/compare_renders.py OUT` shows ours | MSE | difference side by side.
"""
import pytest

from render_compare import PACKAGES, compare_case, render_cases

CASES = render_cases()
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")

MAX_OUTSIDE_TEXT = 0.25         # mean channel difference (0-255) outside text boxes
MAX_INSIDE_TEXT = 6.0           # the same inside them (measured 0.3-4.4)
MAX_INK_OFFSET = 1              # pixels, first/last inked row of each text box
KNOWN_DIFFERENCES = {
    # MSE paints see-through areas as a checkerboard (here: no art, seen through the
    # planeswalker frame's translucent text box); ours leaves them transparent
    "ajani-goldmane": "MSE draws transparency as a checkerboard",
}


@pytest.mark.parametrize("case", CASES, ids=[f"{c['file']}: {c['expr']}" for c in CASES])
def test_card_matches_mse(case) -> None:
    result = compare_case(case)
    if result.uid in KNOWN_DIFFERENCES and result.outside_text > MAX_OUTSIDE_TEXT:
        pytest.xfail(KNOWN_DIFFERENCES[result.uid])
    assert result.outside_text <= MAX_OUTSIDE_TEXT, f"{result.uid}: {result.outside_text:.2f}"
    assert result.inside_text <= MAX_INSIDE_TEXT, f"{result.uid}: text {result.inside_text:.2f}"
    for region in result.text_regions:
        ours, theirs = region["ours"], region["theirs"]
        assert (ours is None) == (theirs is None), f"{result.uid}: text {region['text']!r} missing"
        if ours is not None:
            offset = max(abs(ours[0] - theirs[0]), abs(ours[1] - theirs[1]))
            assert offset <= MAX_INK_OFFSET, f"{result.uid}: {region['text']!r} ink rows {ours} vs {theirs}"
