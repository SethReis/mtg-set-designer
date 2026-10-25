import sys, zipfile
from pathlib import Path

root = Path(sys.argv[1]).expanduser()
data = root / "data"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".mse-symbol",
             ".ttf", ".otf", ".xcf", ".psd", ".dic", ".onetoc2"}

KEEP_STYLES = {"magic-m15-altered", "magic-old", "magic-new", "magic-veryold", "magic-old-abu"}

def wanted(pkg: Path) -> bool:
    n = pkg.name.lower()
    if n.endswith((".mse-game", ".mse-include", ".mse-symbol-font")):
        return True
    return n.endswith(".mse-style") and n[:-len(".mse-style")] in KEEP_STYLES

lines = ["TOP-LEVEL NAMES IN data/", *sorted(p.name for p in data.iterdir()), ""]
packages = [p for p in sorted(data.iterdir()) if p.is_dir() and wanted(p)]

with zipfile.ZipFile("mse_sample.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for pkg in packages:
        files = [f for f in pkg.rglob("*") if f.is_file()]
        lines.append(f"{pkg.name}: {len(files)} files")
        for f in files:
            rel = f.relative_to(pkg)
            lines.append(f"    {rel.as_posix()}")
            if f.suffix.lower() not in IMAGE_EXT:
                z.write(f, f"{pkg.name}/{rel}")
    z.writestr("listing.txt", "\n".join(lines))

print(f"Wrote mse_sample.zip with {len(packages)} packages")