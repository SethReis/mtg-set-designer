"""Render the frame background of each card face, using the stylesheet's own scripts
(`card style > card color > image` and `mask`), for eyeballing.

Usage: python tools/render_frames.py OUT_DIR [project folder]
Without a project folder, uses the test fixture set (tests/fixtures/oracle_project.py).
Writes <uid>.png (frame) and <uid>-masked.png (frame with its mask applied) per face.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from setdesigner.model import load_project  # noqa: E402
from setdesigner.mse.environment import ScriptEnvironment  # noqa: E402
from setdesigner.mse.script import images as I  # noqa: E402


def render_frames(env: ScriptEnvironment, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for card in env.set.cards:
        opts = env.image_options(card.style, 375, 523)
        frame = I.as_image(env.style_value(card, "card color", "image")).generate_conform(opts)
        name = card.uid.replace("/", "-")
        frame.to_pil().save(out / f"{name}.png")
        mask_value = env.style_value(card, "card color", "mask")
        mask = I.as_image(mask_value).generate_conform(opts)
        I.multiply_alpha(frame, mask.rgb[..., 0].astype("int32")).to_pil().save(out / f"{name}-masked.png")
        written.append(out / f"{name}.png")
    return written


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if len(sys.argv) > 2:
        project = load_project(Path(sys.argv[2]))
    else:
        from fixtures.oracle_project import oracle_project
        project = oracle_project()
    for path in render_frames(ScriptEnvironment(project), Path(sys.argv[1])):
        print(path)


if __name__ == "__main__":
    main()
