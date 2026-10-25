"""Evaluate expressions with real Magic Set Editor to pin down script semantics.

Usage: python tools/mse_oracle.py [name ...] [--mse path/to/magicseteditor.com]

For each tools/oracle_cases/<name>.txt (all of them by default), runs the cases
through `magicseteditor.com --cli --quiet --raw` (no set loaded, so only built-in
functions are available) and writes tests/script/oracle/<name>.json: a list of
{expr, status, output}, where status is "ok", "warning" or "error" and output is
MSE's printed result (its `toCode` form) or error message. The JSON is committed
so the tests don't need MSE installed.

A case file with a `#! project: <name>` line is run with a set loaded: the fixture
project tests/fixtures/<name>.py is exported to a .mse-set and `:load`ed first,
so cases can read `set.cards.0.card_color` and so on.

A case file with a `#! images` line is in image mode: each expression is written
to a PNG by MSE's write_image_file (`[WxH] expr` asks for that size); the PNGs go
to tests/script/oracle/images/ and the JSON records their file names.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES_DIR = REPO / "tools" / "oracle_cases"
RESULTS_DIR = REPO / "tests" / "script" / "oracle"
DEFAULT_MSE = REPO / "Full-Magic-Pack-main" / "magicseteditor.com"
STATUS = {"0": "ok", "1": "warning", "2": "error"}


IMAGE_SIZE = re.compile(r"^\[(\d+)x(\d+)\]\s*")


def read_cases(path: Path) -> tuple[str | None, bool, list[str]]:
    """The cases of a file, the fixture project named by a `#! project: name` line,
    and whether the file is in image mode (`#! images`)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    project = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("#! project:")), None)
    images = any(l.strip() == "#! images" for l in lines)
    return project, images, [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def image_command(expr: str, file: str) -> str:
    """`[WxH] expr` -> write_image_file(file: ..., input: (expr), width: W, height: H)."""
    m = IMAGE_SIZE.match(expr)
    size = f", width: {m[1]}, height: {m[2]}" if m else ""
    body = expr[m.end():] if m else expr
    return f'write_image_file(file: "{file}", input: ({body}){size})'


def export_fixture(name: str, folder: Path) -> Path:
    """Write the fixture project tests/fixtures/<name>.py:<name>() as a .mse-set."""
    sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]
    import importlib
    from setdesigner.mse.export_set import write_mse_set
    project = getattr(importlib.import_module(f"fixtures.{name}"), name)()
    return write_mse_set(project, folder / f"{name}.mse-set")


def run_mse(exe: Path, cases: list[str], setup: list[str] = ()) -> list[dict]:
    """Run setup commands (:load, :cd), then the cases; one result per case."""
    commands = list(setup) + cases + [":quit"]
    stdin = "\n".join(commands) + "\n"
    proc = subprocess.run([str(exe), "--cli", "--quiet", "--raw"], input=stdin.encode("utf-8"),
                          capture_output=True, timeout=300)
    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()

    # Raw mode: per command, a status line, a count k, then k lines.
    records, i = [], 0
    while i + 1 < len(lines):
        status, count = lines[i].strip(), int(lines[i + 1])
        records.append((STATUS.get(status, status), lines[i + 2:i + 2 + count]))
        i += 2 + count
    if len(records) != len(commands):
        raise SystemExit(f"expected {len(commands)} records, got {len(records)}:\n" + "\n".join(lines))
    for command in setup:
        status, out = records.pop(0)
        if status != "ok":
            raise SystemExit(f"MSE failed on {command}:\n" + "\n".join(out))

    return [{"expr": expr, "status": status, "output": "\n".join(out)}
            for expr, (status, out) in zip(cases, records)]


def run_file(exe: Path, name: str) -> list[dict]:
    project, images, cases = read_cases(CASES_DIR / f"{name}.txt")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        setup = [f":load {export_fixture(project, tmp)}"] if project else []
        if not images:
            results = run_mse(exe, cases, setup)
        else:
            files = [f"{name}-{i:03d}.png" for i in range(len(cases))]
            out_dir = tmp / "images"
            out_dir.mkdir()
            results = run_mse(exe, [image_command(c, f) for c, f in zip(cases, files)],
                              setup + [f":cd {out_dir}"])
            image_dir = RESULTS_DIR / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            for old in image_dir.glob(f"{name}-*.png"):
                old.unlink()
            for result, case, file in zip(results, cases, files):
                result["expr"] = case
                if result["status"] == "ok" and (out_dir / file).is_file():
                    shutil.copyfile(out_dir / file, image_dir / file)
                    result["image"] = f"images/{file}"
    if project:
        results = [{**r, "project": project} for r in results]
    return results


def main() -> None:
    args = sys.argv[1:]
    exe = DEFAULT_MSE
    if "--mse" in args:
        exe = Path(args[args.index("--mse") + 1])
        del args[args.index("--mse"):args.index("--mse") + 2]
    names = args or sorted(p.stem for p in CASES_DIR.glob("*.txt"))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        results = run_file(exe, name)
        out = RESULTS_DIR / f"{name}.json"
        out.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        width = max(len(r["expr"]) for r in results)
        print(f"==== {name}")
        for r in results:
            print(f"{r['expr']:<{width}}  {r['status']:<7} {r['output']}")
        print(f"Wrote {len(results)} results to {out.relative_to(REPO)}\n")


if __name__ == "__main__":
    main()
