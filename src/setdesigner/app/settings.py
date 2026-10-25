"""Per-user app settings: recently opened sets and the window size.
Stored as JSON in %APPDATA%/setdesigner/settings.json (or ~/.setdesigner elsewhere)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_RECENT = 8


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    folder = Path(base) / "setdesigner" if base else Path.home() / ".setdesigner"
    return folder / "settings.json"


@dataclass
class Settings:
    recent: list[str] = field(default_factory=list)     # set folders, most recent first
    window: tuple[int, int] = (1400, 900)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(recent=[str(p) for p in data.get("recent", [])][:MAX_RECENT],
                       window=tuple(data.get("window", (1400, 900))))
        except (OSError, ValueError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def remember(self, folder: Path, path: Path | None = None) -> None:
        key = str(Path(folder).resolve())
        self.recent = [key] + [p for p in self.recent if p != key][:MAX_RECENT - 1]
        self.save(path)

    def existing_recent(self) -> list[Path]:
        return [Path(p) for p in self.recent if (Path(p) / "set.json").is_file()]
