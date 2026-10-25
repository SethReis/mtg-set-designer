"""Compare our generated images with real MSE's (tools/oracle_cases/images.txt ->
tests/script/oracle/images.json + images/*.png, recorded by tools/mse_oracle.py)."""
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from setdesigner.mse.script import images as I

HERE = Path(__file__).parent
PACKAGES = HERE.parents[1] / "resources" / "mse_packages"
CASES = [c for c in json.loads((HERE / "oracle" / "images.json").read_text(encoding="utf-8"))
         if "image" in c]
SIZE = re.compile(r"^\[(\d+)x(\d+)\]\s*")

# Point-wise operations must match exactly. Where MSE resamples, blurs or rounds with
# its own algorithms, allow small differences: (max channel difference, mean difference).
EXACT = (0, 0.0)
RESAMPLED = (16, 0.8)
TOLERANCE_BY_FUNCTION = {
    "resize_image": RESAMPLED, "nine_slice_image": RESAMPLED, "[": RESAMPLED,
    "drop_shadow": (16, 0.2),               # also add_drop_shadow
    "linear_blend": (1, 0.1), "insert_image": (1, 0.05), "set_mask": (1, 0.05),
    "card_background": (1, 0.05),           # real M15 frame scripts (blends inside)
}


def tolerance(expr: str) -> tuple[int, float]:
    for name, tol in TOLERANCE_BY_FUNCTION.items():
        if name in expr:
            return tol
    return EXACT


def ours(case) -> I.Raster:
    from test_oracle import environment         # same environment as the cards cases
    from setdesigner.mse.script import run
    env = environment(case["project"])
    m = SIZE.match(case["expr"])
    width, height = (int(m[1]), int(m[2])) if m else (0, 0)
    ctx = env.context(env.default_style)
    marker = ctx.open_scope()
    try:
        value = run(case["expr"][m.end():] if m else case["expr"], ctx=ctx)
    finally:
        ctx.close_scope(marker)
    opts = I.ImageOptions(width=width, height=height, root=PACKAGES,
                          package=PACKAGES / f"{env.default_style}.mse-style")
    return I.as_image(value).generate_conform(opts)


def theirs(case) -> I.Raster:
    with Image.open(HERE / "oracle" / case["image"]) as img:
        return I.Raster.from_pil(img)


def differences(a: I.Raster, b: I.Raster) -> tuple[int, float]:
    """Max and mean channel difference. Colour only counts where a pixel is clearly
    visible (alpha >= 64 in either image): the colour of an almost transparent pixel
    hardly shows, and resamplers treat it very differently."""
    alpha_a, alpha_b = a.alpha_or_opaque().astype(int), b.alpha_or_opaque().astype(int)
    visible = (alpha_a >= 64) | (alpha_b >= 64)
    rgb = np.abs(a.rgb.astype(int) - b.rgb.astype(int))[visible]
    al = np.abs(alpha_a - alpha_b)
    diffs = np.concatenate([rgb.ravel(), al.ravel()])
    return int(diffs.max(initial=0)), float(diffs.mean()) if diffs.size else 0.0


@pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")
@pytest.mark.parametrize("case", CASES, ids=[c["image"] for c in CASES])
def test_image_matches_mse(case) -> None:
    mine, real = ours(case), theirs(case)
    assert mine.size == real.size
    max_diff, mean_diff = differences(mine, real)
    max_ok, mean_ok = tolerance(case["expr"])
    assert max_diff <= max_ok and mean_diff <= mean_ok, \
        f"max diff {max_diff}, mean {mean_diff:.2f} for {case['expr']}"
