"""Render every card face of a project to PNG files.

Usage: python tools/render_cards.py OUT_DIR [project folder] [--builtin]
Without a project folder, renders the test fixture set (tests/fixtures/oracle_project.py).
Uses real MSE (with our set symbol on top); --builtin uses our own renderer instead.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from setdesigner.model import load_project  # noqa: E402
from setdesigner.render import CardRenderer  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    out = Path(args[0])
    if len(args) > 1:
        project = load_project(Path(args[1]))
    else:
        from fixtures.oracle_project import oracle_project
        project = oracle_project()
    t = time.time()
    with CardRenderer(project, use_mse="--builtin" not in sys.argv) as renderer:
        files = renderer.render_set(out)
        backend = "MSE" if renderer.mse is not None and not renderer.warnings else "built-in"
        for warning in renderer.warnings:
            print("warning:", warning)
    for path in files:
        print(path)
    print(f"{len(files)} faces with the {backend} renderer in {time.time() - t:.1f} s")


if __name__ == "__main__":
    main()
