"""The theme: its files, mana symbols in the UI, and the theme setting."""
import re
from pathlib import Path

import pytest

from setdesigner.app.settings import Settings
from setdesigner.ui import theme
from setdesigner.ui.components import mana_glyph, mana_html


def test_stylesheets_and_fonts_exist() -> None:
    for name in theme.STYLESHEETS:
        css = (theme.FOLDER / name).read_text(encoding="utf-8")
        for url in re.findall(r'url\("([^"?#]+)', css):
            assert (theme.FOLDER / name).parent.joinpath(url).is_file(), (name, url)


def test_every_token_used_is_defined() -> None:
    base = (theme.FOLDER / "base.css").read_text(encoding="utf-8")
    tokens = (theme.FOLDER / "tokens.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"(--[\w-]+):", tokens + base))     # tokens, and component-local ones
    used = set(re.findall(r"var\((--[\w-]+)", base))
    inline = {"--dot", "--tile", "--tile-border"}                # set by components in a style=""
    quasar = {u for u in used if u.startswith("--q-")}
    assert used - defined - quasar - inline == set()


@pytest.mark.parametrize("symbol, glyph", [
    ("W", "w"), ("2", "2"), ("10", "10"), ("X", "x"), ("T", "tap"), ("Q", "untap"), ("W/U", "wu"),
    ("G/P", "gp"), ("2/W", "2w"), ("C", "c"), ("S", "s"), ("E", "e"), ("CARDNAME", None), ("slot", None),
])
def test_mana_glyphs(symbol, glyph) -> None:
    assert mana_glyph(symbol) == glyph


def test_mana_html_escapes_text() -> None:
    assert mana_html("{1}{G} <b>") == ('<i class="ms ms-1 ms-cost" title="{1}"></i>'
                                       '<i class="ms ms-g ms-cost" title="{G}"></i> &lt;b&gt;')
    assert mana_html("{effect}") == "{effect}"


def test_theme_setting_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    assert Settings.load(path).theme == "dark"
    Settings(theme="light", rail_open=True).save(path)
    loaded = Settings.load(path)
    assert loaded.theme == "light" and loaded.rail_open
    path.write_text('{"theme": "neon"}', encoding="utf-8")
    assert Settings.load(path).theme == "dark"
    assert theme.dark_value("system") is None and theme.dark_value("light") is False
