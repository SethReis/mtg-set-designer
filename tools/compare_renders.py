"""Render fixture cards and put them next to real MSE's renders: ours | MSE | difference.

Usage: python tools/compare_renders.py OUT_DIR [renders|renders_keywords]
Writes OUT_DIR/<case>.png (side by side) and OUT_DIR/sheet.png (all, small), and
prints per-card mean differences (whole card, and outside text boxes).
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]
ORACLE = REPO / "tests" / "script" / "oracle"

from setdesigner.mse.environment import ScriptEnvironment  # noqa: E402
from setdesigner.render.draw import draw  # noqa: E402
from setdesigner.render.layout import TextLayer  # noqa: E402
from setdesigner.render.mse_layout import mse_layout  # noqa: E402


def flatten(img: Image.Image) -> Image.Image:
    """On white, so transparent corners compare as background."""
    out = Image.new("RGBA", img.size, (255, 255, 255, 255))
    out.alpha_composite(img.convert("RGBA"))
    return out.convert("RGB")


def text_mask(layout, size) -> np.ndarray:
    mask = np.zeros((size[1], size[0]), bool)
    for layer in layout.layers:
        if isinstance(layer, TextLayer):
            b = layer.box
            mask[max(0, int(b.top)):int(b.bottom) + 1, max(0, int(b.left)):int(b.right) + 1] = True
    return mask


def compare(name: str, out: Path) -> list[tuple]:
    cases = json.loads((ORACLE / f"{name}.json").read_text(encoding="utf-8"))
    project_name = cases[0]["project"]
    project = getattr(importlib.import_module(f"fixtures.{project_name}"), project_name)()
    env = ScriptEnvironment(project)
    rows = []
    for case in cases:
        index = int(case["expr"].split(".")[-1])
        card = env.set.cards[index]
        t = time.time()
        layout = mse_layout(env, card)
        ours = draw(layout)
        elapsed = time.time() - t
        theirs = Image.open(ORACLE / case["image"])
        a, b = np.asarray(flatten(ours), int), np.asarray(flatten(theirs), int)
        diff = np.abs(a - b).mean(axis=2)
        outside = ~text_mask(layout, ours.size)
        rows.append((card.uid, diff.mean(), diff[outside].mean(), elapsed, layout.warnings))
        diff_img = Image.fromarray(np.clip(diff * 3, 0, 255).astype(np.uint8), "L").convert("RGB")
        side = Image.new("RGB", (ours.width * 3 + 20, ours.height), "white")
        for n, im in enumerate((flatten(ours), flatten(theirs), diff_img)):
            side.paste(im, (n * (ours.width + 10), 0))
        side.save(out / f"{name}-{index}.png")
    return rows


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or ["renders", "renders_keywords"]
    for name in names:
        for uid, whole, outside, elapsed, warnings in compare(name, out):
            print(f"{name:17} {uid:22} mean diff {whole:5.2f}  outside text {outside:5.2f}  "
                  f"{elapsed * 1000:5.0f} ms  warnings {len(warnings)}")
            for w in warnings[:3]:
                print("      ", w[:150])


if __name__ == "__main__":
    main()
