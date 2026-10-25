"""Run the reader over every package's main file and print a summary.
Usage: python tools/check_reader.py <folder containing the *.mse-style etc. packages>
"""
import sys, time
from collections import Counter
from pathlib import Path
from setdesigner.mse.reader import read_file, MSEReadError

MAIN_FILE = {".mse-style": "style", ".mse-game": "game",
             ".mse-symbol-font": "symbol-font"}

root = Path(sys.argv[1]).expanduser()
ok = failed = 0
problems = []
t0 = time.time()
for pkg in sorted(p for p in root.iterdir() if p.is_dir()):
    main = MAIN_FILE.get(pkg.suffix)
    if not main or not (pkg / main).is_file():
        continue
    try:
        nodes, st = read_file(pkg / main, root)
        ok += 1
        if st.unresolved or st.space_indented_lines:
            problems.append((pkg.name, st.unresolved, st.space_indented_lines))
    except MSEReadError as e:
        failed += 1
        problems.append((pkg.name, [f"ERROR {e}"], 0))
print(f"{ok} files read, {failed} failed, {time.time()-t0:.1f}s\n")
for name, unresolved, spaces in problems:
    print(f"  {name}: unresolved={unresolved} space-indented={spaces}")

print("\nTop-level keys in magic-m15-altered style:")
nodes, st = read_file(root / "magic-m15-altered.mse-style" / "style", root)
for k, c in Counter(n.key for n in nodes).most_common(12):
    print(f"  {c:4d}  {k}")
print(f"  includes resolved: {st.includes_resolved}")
