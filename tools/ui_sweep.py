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
    # states reached by clicking (overlap_check.js: dev_click, by visible text)
    "start-new": "/?dev_click=New set",
    "overview-matrix": "/set?dev_click=Matrix",
    "overview-stacks": "/set?dev_click=Stacks",
    "overview-text": "/set?dev_click=Text",
    "overview-filters": "/set?dev_click=Filters",
    "skeleton-table": "/set?open=skeleton&dev_click=Table",
    "skeleton-archetype": "/set?open=skeleton&dev_click=By archetype",
    "skeleton-counts": "/set?open=skeleton&dev_click=Edit counts…",
    "mechanics-item": "/set?open=mechanics&dev_click=Flurry",
    "cycles-item": "/set?open=cycles&dev_click=Allied duals",
    "health-tune": "/set?open=health&dev_click=Tune checks",
}


def url(base: str, folder: Path, theme: str, path: str, card: str, dfc: str) -> str:
    if not path or path.startswith("/?"):
        return f"{base}/?theme_={theme}" + ("&" + quote(path[2:], safe="=&") if path else "")
    target = path.format(card=card, dfc=dfc)
    return f"{base}/?open_set={quote(str(folder))}&theme_={theme}&then={quote(target, safe='')}"


class Edge:
    """A headless Edge driven over the DevTools protocol, in real time (so the app's
    connection stays up through clicks and loading)."""

    def __init__(self, width: int, height: int):
        import json
        import socket
        import urllib.request
        from websockets.sync.client import connect
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.profile = Path(tempfile.mkdtemp(prefix="sweep-edge-"))
        self.proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                      f"--remote-debugging-port={port}", f"--user-data-dir={self.profile}",
                                      f"--window-size={width},{height}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = next(p for p in pages if p["type"] == "page")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("Edge did not start")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.ws = connect(page["webSocketDebuggerUrl"], max_size=None)
        self.next_id = 0
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                  deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        import json
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.next_id:
                return message.get("result", {})

    def evaluate(self, expression: str):
        return self.call("Runtime.evaluate", expression=expression, returnByValue=True)["result"].get("value")

    def open(self, address: str, timeout: float = 60) -> str | None:
        """Load the page and wait for overlap_check.js's report (its JSON, or None)."""
        self.call("Page.navigate", url=address)
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.5)
            found = self.evaluate("document.getElementById('overlap-report')?.textContent ?? null")
            if found is not None:
                return found
        return None

    def screenshot(self, target: Path) -> None:
        import base64
        target.write_bytes(base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"]))

    def close(self) -> None:
        try:
            self.ws.close()
        finally:
            self.proc.kill()
            self.proc.wait()
            shutil.rmtree(self.profile, ignore_errors=True)


def shoot(address: str, target: Path, width: int, height: int) -> bool:
    edge = Edge(width, height)
    try:
        if edge.open(address) is None:
            return False
        edge.screenshot(target)
        return True
    finally:
        edge.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("set_folder", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--base", default="http://localhost:8765")
    parser.add_argument("--widths", default="900,1100,1400,1920")
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
