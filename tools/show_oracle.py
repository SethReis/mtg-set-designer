"""Print recorded MSE oracle results compactly.

Usage: python tools/show_oracle.py [name] [substring]
  name       oracle file (core, builtins, ...); default: all
  substring  only show cases whose expression contains it
"""
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "script" / "oracle"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "*"
    needle = sys.argv[2] if len(sys.argv) > 2 else ""
    for path in sorted(RESULTS_DIR.glob(f"{name}.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            if needle in case["expr"]:
                output = case["output"].replace("\n", " | ")
                print(f"{case['expr'][:72]:<72} {case['status'][:3]}  {output[:110]}")


if __name__ == "__main__":
    main()
