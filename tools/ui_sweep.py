"""Screenshot every view of the app, for a visual review (overlaps, misalignment).

    python tools/ui_sweep.py <set folder> <out folder> [--base http://localhost:8765]
                             [--widths 1100,1400,1920] [--themes dark,light] [--only editor]

Needs a running app started with SETDESIGNER_DEV=1 (the start page then opens a set and a
view straight from the URL) and Microsoft Edge. Each shot uses a fresh headless browser
profile; files are named <view>-<theme>-<width>.png.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# view name -> path inside the set (after the start page opened it); "" = the start page
VIEWS = {
    "start": "",
    "overview": "/set",
    "editor": "/set?card={card}",
    "editor-name": "/set?card={card}&part=name",
    "editor-type": "/set?card={card}&part=type",
    "editor-text": "/set?card={card}&part=text",
    "editor-pt": "/set?card={card}&part=pt",
    "editor-art": "/set?card={card}&part=art",
    "editor-outlines": "/set?card={card}&part_outlines=1",
    "editor-dfc": "/set?card={dfc}&part_outlines=1",
    "skeleton": "/set?open=skeleton",
    "mechanics": "/set?open=mechanics",
    "cycles": "/set?open=cycles",
    "health": "/set?open=health",
    "archetypes": "/set?open=archetypes",
    "settings": "/set?open=settings",
    "print": "/set?open=print",
}


def url(base: str, folder: Path, theme: str, path: str, card: str, dfc: str) -> str:
    if not path:
        return f"{base}/?theme_={theme}"
    target = path.format(card=card, dfc=dfc)
    return f"{base}/?open_set={quote(str(folder))}&theme_={theme}&then={quote(target, safe='')}"


def shoot(address: str, target: Path, width: int, height: int) -> bool:
    profile = Path(tempfile.mkdtemp(prefix="sweep-edge-"))
    target.unlink(missing_ok=True)
    try:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        f"--window-size={width},{height}", "--virtual-time-budget=15000",
                        f"--screenshot={target}", address], timeout=90, capture_output=True)
        for _ in range(40):
            if target.exists() and target.stat().st_size:
                return True
            time.sleep(0.25)
        return False
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("set_folder", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--base", default="http://localhost:8765")
    parser.add_argument("--widths", default="1100,1400,1920")
    parser.add_argument("--themes", default="dark,light")
    parser.add_argument("--only", default="", help="views whose name starts with this")
    parser.add_argument("--card", default="canopy-stalker")
    parser.add_argument("--dfc", default="grove-warden")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for theme in args.themes.split(","):
        for width in [int(w) for w in args.widths.split(",")]:
            height = round(width * 0.62)
            for name, path in VIEWS.items():
                if args.only and not name.startswith(args.only):
                    continue
                target = args.out / f"{name}-{theme}-{width}.png"
                ok = shoot(url(args.base, args.set_folder.resolve(), theme, path, args.card, args.dfc),
                           target, width, height)
                print(f"{'ok ' if ok else 'FAIL'} {target.name}")


if __name__ == "__main__":
    main()
