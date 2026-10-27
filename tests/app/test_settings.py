"""App settings: loading, defaults, and old values."""
import json

from setdesigner.app.settings import Settings


def test_defaults_and_old_compact_value(tmp_path) -> None:
    path = tmp_path / "settings.json"
    assert (Settings.load(path).layout, Settings.load(path).tiles) == ("grid", "images")
    path.write_text(json.dumps({"tiles": "compact", "tile_width": 140}), encoding="utf-8")
    loaded = Settings.load(path)
    assert (loaded.layout, loaded.tiles, loaded.tile_width) == ("grid", "text", 140)


def test_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    Settings(layout="stacks", tiles="text", tile_width=220).save(path)
    loaded = Settings.load(path)
    assert (loaded.layout, loaded.tiles, loaded.tile_width) == ("stacks", "text", 220)
