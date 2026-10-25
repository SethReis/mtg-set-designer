"""Shared helpers for comparing our renders with real MSE's (recorded by
tools/mse_oracle.py into tests/script/oracle/renders*.json + images/)."""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

ORACLE = Path(__file__).resolve().parents[1] / "script" / "oracle"
PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"


def render_cases() -> list[dict]:
    cases = []
    for name in ("renders", "renders_keywords"):
        path = ORACLE / f"{name}.json"
        if path.is_file():
            cases += [{**c, "file": name} for c in json.loads(path.read_text(encoding="utf-8"))
                      if "image" in c]
    return cases


@lru_cache(maxsize=None)
def environment(project: str):
    from setdesigner.mse.environment import ScriptEnvironment
    fixture = getattr(importlib.import_module(f"fixtures.{project}"), project)
    return ScriptEnvironment(fixture(), PACKAGES)


def flatten(img: Image.Image) -> np.ndarray:
    """RGB on white (transparent card corners compare as background), as int array."""
    out = Image.new("RGBA", img.size, (255, 255, 255, 255))
    out.alpha_composite(img.convert("RGBA"))
    return np.asarray(out.convert("RGB"), int)


@dataclass
class Comparison:
    uid: str
    outside_text: float                 # mean channel diff outside text and symbol boxes
    text_regions: list[dict]            # per text layer: box, mean diff, ink row spans


def ink_rows(region: np.ndarray) -> tuple[int, int] | None:
    """First and last row with clear ink (far from the region's typical color)."""
    background = np.median(region.reshape(-1, 3), axis=0)
    ink = np.abs(region - background).sum(axis=2) > 150
    rows = np.where(ink.mean(axis=1) > 0.01)[0]
    return (int(rows[0]), int(rows[-1])) if rows.size else None


def compare_case(case: dict) -> Comparison:
    from setdesigner.render.draw import draw
    from setdesigner.render.layout import TextLayer
    from setdesigner.render.mse_layout import MSELayoutBuilder
    env = environment(case["project"])
    card = env.set.cards[int(case["expr"].split(".")[-1])]
    builder = MSELayoutBuilder(env, card)
    layout = builder.build()
    ours = flatten(draw(layout))
    theirs = flatten(Image.open(ORACLE / case["image"]))
    diff = np.abs(ours - theirs).mean(axis=2)
    h, w = diff.shape
    excluded = np.zeros((h, w), bool)
    regions = []
    for layer in layout.layers:
        if isinstance(layer, TextLayer):
            b = layer.box
            y0, y1 = max(0, int(b.top)), min(h, int(b.bottom) + 1)
            x0, x1 = max(0, int(b.left)), min(w, int(b.right) + 1)
            excluded[y0:y1, x0:x1] = True
            regions.append({"text": layer.text[:40], "box": (x0, y0, x1, y1),
                            "mean": float(diff[y0:y1, x0:x1].mean()),
                            "ours": ink_rows(ours[y0:y1, x0:x1]),
                            "theirs": ink_rows(theirs[y0:y1, x0:x1])})
    rarity = builder.entry("rarity")
    box = builder.box(rarity) if rarity else None
    if box is not None:                     # our own set symbol, by design
        excluded[max(0, int(box.top)):int(box.bottom) + 1, max(0, int(box.left)):int(box.right) + 1] = True
    return Comparison(card.uid, float(diff[~excluded].mean()), regions)
