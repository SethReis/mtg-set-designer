"""Copy the MSE packages we use from an MSE install into resources/.

Usage:
    python tools/sync_packages.py "Full-Magic-Pack-main"          # whitelist only
    python tools/sync_packages.py "Full-Magic-Pack-main" --all    # every package

Packages land as siblings in resources/mse_packages/ (the reader's `root`).
The install's "Magic - Fonts" folder is copied to resources/fonts/.
Safe to re-run: existing copies are replaced.
"""

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGES_DIR = REPO / "resources" / "mse_packages"
FONTS_DIR = REPO / "resources" / "fonts"

KEEP_STYLES = {"magic-m15-altered", "magic-old", "magic-new", "magic-veryold", "magic-old-abu",
               "magic-m15-planeswalker", "magic-new-planeswalker", "magic-old-planeswalker"}
KEEP_SUFFIXES = (".mse-game", ".mse-include", ".mse-symbol-font")


def wanted(pkg: Path, everything: bool) -> bool:
    name = pkg.name.lower()
    if everything:
        return name.startswith("magic") or name.endswith(KEEP_SUFFIXES)
    if name.endswith(KEEP_SUFFIXES):
        return True
    return name.endswith(".mse-style") and name.removesuffix(".mse-style") in KEEP_STYLES


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("install", type=Path, help="MSE install folder (contains data/)")
    parser.add_argument("--all", action="store_true", help="copy every magic package, not just the whitelist")
    args = parser.parse_args()

    data = args.install / "data"
    if not data.is_dir():
        raise SystemExit(f"No data/ folder in {args.install}")

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    packages = [p for p in sorted(data.iterdir()) if p.is_dir() and wanted(p, args.all)]
    for pkg in packages:
        copy_tree(pkg, PACKAGES_DIR / pkg.name)
    print(f"Copied {len(packages)} packages to {PACKAGES_DIR}")

    missing = [s for s in KEEP_STYLES if not (PACKAGES_DIR / f"{s}.mse-style").is_dir()]
    if missing:
        print(f"WARNING: whitelisted styles not found: {', '.join(sorted(missing))}")

    fonts = args.install / "Magic - Fonts"
    if fonts.is_dir():
        copy_tree(fonts, FONTS_DIR)
        count = sum(1 for f in FONTS_DIR.rglob("*") if f.is_file())
        print(f"Copied {count} font files to {FONTS_DIR}")
    else:
        print(f"WARNING: no 'Magic - Fonts' folder in {args.install}; fonts not copied")


if __name__ == "__main__":
    main()
