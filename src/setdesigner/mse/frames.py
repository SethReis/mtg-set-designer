"""Our frame names -> MSE stylesheet packages (all in resources/mse_packages)."""
from __future__ import annotations

FRAMES: dict[str, str] = {
    "m15": "magic-m15-altered",     # M15 Main (modern frame, DFC support via magic-modules)
    "ub": "magic-m15-altered",      # Universes Beyond: M15 Main with its "frames" styling option
    "8th": "magic-new",             # 8th Edition frame (2003)
    "old": "magic-old",             # "Old Main": before 8th Edition (1997 style)
    "4th": "magic-veryold",         # 4th Edition style
    "abu": "magic-old-abu",         # Alpha/Beta/Unlimited style
}
# Planeswalkers need their own stylesheet (loyalty box, one cost per ability). The
# pre-8th frames never had planeswalkers; they use the closest one, "old".
PLANESWALKER_FRAMES: dict[str, str] = {
    "m15": "magic-m15-planeswalker",
    "ub": "magic-m15-planeswalker",                 # no Universes Beyond planeswalker frame
    "8th": "magic-new-planeswalker",
    "old": "magic-old-planeswalker",
    "4th": "magic-old-planeswalker",
    "abu": "magic-old-planeswalker",
}
# Frames that are a stylesheet plus styling options (MSE's per-card "styling data")
FRAME_STYLING: dict[str, dict[str, str]] = {
    "ub": {"frames": "universes beyond"},
}
GAME = "magic"


def frame_styling(frame: str, planeswalker: bool = False) -> dict[str, str]:
    """The styling options a frame sets on a card (none for planeswalkers: their
    stylesheets don't have these options)."""
    return {} if planeswalker else dict(FRAME_STYLING.get(frame, {}))


def stylesheet_package(frame: str, planeswalker: bool = False) -> str:
    """The stylesheet package for a frame name; package names are accepted as is.
    `planeswalker` picks the frame's planeswalker version (not for package names)."""
    if planeswalker and frame in PLANESWALKER_FRAMES:
        return PLANESWALKER_FRAMES[frame]
    if frame in FRAMES:
        return FRAMES[frame]
    if frame.endswith(".mse-style"):
        return frame[:-len(".mse-style")]
    if frame.startswith(f"{GAME}-"):
        return frame
    raise KeyError(f"unknown frame {frame!r}; known: {', '.join(FRAMES)}")


def stylesheet_name(package: str) -> str:
    """How a set file names a stylesheet: the package without the game prefix
    ("magic-m15-altered" -> "m15-altered")."""
    return package[len(GAME) + 1:] if package.startswith(f"{GAME}-") else package
