"""Parse every script snippet used by the game and our target styles; report failures.

Usage: python tools/check_script_parse.py [packages_root] [--show N]
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from setdesigner.mse.script.corpus import STYLES, parse_snippet, target_snippets  # noqa: E402
from setdesigner.mse.script.tokens import ScriptSyntaxError  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = int(sys.argv[sys.argv.index("--show") + 1]) if "--show" in sys.argv else 3
    root = Path(args[0]) if args else REPO / "resources" / "mse_packages"

    t0 = time.time()
    snippets = target_snippets(root)
    failures = defaultdict(list)
    for snip in snippets:
        try:
            parse_snippet(snip)
        except ScriptSyntaxError as e:
            # group by message without the line number
            failures[str(e).split(": ", 1)[-1]].append((snip, e))
    total = sum(len(v) for v in failures.values())
    print(f"{len(snippets)} snippets from magic.mse-game + {len(STYLES)} styles, "
          f"{total} failed, {time.time() - t0:.1f}s")
    for message, items in sorted(failures.items(), key=lambda kv: -len(kv[1])):
        print(f"\n[{len(items)}x] {message}")
        for snip, e in items[:show]:
            line = snip.text.splitlines()[e.line - 1] if 0 < e.line <= len(snip.text.splitlines()) else ""
            print(f"    {snip.source} :: {snip.path} :: line {e.line}: {line.strip()[:120]}")


if __name__ == "__main__":
    main()
