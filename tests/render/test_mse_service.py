"""Real MSE as the renderer (setdesigner/render/mse_service.py).

Needs the MSE program (Full-Magic-Pack-main/magicseteditor.com, or $SETDESIGNER_MSE);
skipped without it."""
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fixtures.keyword_project import keyword_project
from fixtures.oracle_project import oracle_project
from render_compare import ORACLE, flatten
from setdesigner.render import CardRenderer, find_mse, render_card
from setdesigner.render.mse_layout import MSELayoutBuilder

pytestmark = pytest.mark.skipif(find_mse() is None, reason="Magic Set Editor not available")


@pytest.fixture(scope="module")
def renderer():
    with CardRenderer(oracle_project()) as r:
        yield r


def rarity_box(r: CardRenderer, card, face=0):
    builder = MSELayoutBuilder(r.env, r.env.card_object(card, face))
    box = builder.box(builder.entry("rarity"))
    return (int(box.left), int(box.top), int(box.right) + 1, int(box.bottom) + 1)


def test_preview_equals_a_whole_set_render(renderer) -> None:
    """A one-card preview set gives exactly MSE's render from the whole set (set-wide
    values such as collector numbers are carried over), apart from the rarity symbol."""
    for index, card_id, face in [(0, "grizzly-bears", 0), (1, "boros-guildmage", 0), (7, "delver", 1)]:
        card = renderer.project.card(card_id)
        ours = flatten(renderer.render(card, face))
        assert renderer.last_backend == "mse"
        theirs = flatten(Image.open(ORACLE / "images" / f"renders-{index:03d}.png"))
        diff = np.abs(ours - theirs).mean(axis=2)
        x0, y0, x1, y1 = rarity_box(renderer, card, face)
        diff[y0:y1, x0:x1] = 0
        assert diff.mean() < 0.05, card_id


def test_batch_equals_single_renders(renderer) -> None:
    """render_many (one load for many cards, for the overview) gives the preview's pictures."""
    cards = [renderer.project.card(c) for c in ("grizzly-bears", "boros-guildmage", "delver")]
    many = renderer.render_many(cards)
    assert set(many) == {("grizzly-bears", 0), ("boros-guildmage", 0), ("delver", 0), ("delver", 1)}
    for card in cards:
        for face in range(len(card.faces)):
            single = flatten(renderer.render(card, face))
            assert np.abs(flatten(many[card.id, face]) - single).mean() < 0.01, (card.id, face)


def test_art_is_packed_cropped_and_follows_the_crop(tmp_path) -> None:
    """MSE draws our art (packed into the set, cropped to the art box) like the built-in
    renderer does, and a different crop gives a different picture."""
    from setdesigner.model import ArtCrop
    art = tmp_path / "art.png"
    picture = Image.new("RGB", (1200, 800), (40, 40, 160))
    picture.paste((220, 30, 30), (0, 0, 600, 800))            # left half red, right half blue
    picture.save(art)
    project = oracle_project()
    bears = project.card("grizzly-bears")
    bears.faces[0].art_path = str(art)
    with CardRenderer(project) as r:
        r.card_changed(bears)
        centred = flatten(r.render(bears))
        assert r.last_backend == "mse"
        w, h = r.art_box(bears)
        builtin = flatten(render_card(r.env, bears))
        bears.faces[0].art_crop = ArtCrop(x=0.0, y=0.5, zoom=2)     # zoom into the red side
        r.card_changed(bears)
        left = flatten(r.render(bears))
        assert np.abs(left - centred).mean() > 5
        many = flatten(r.render_many([bears])[bears.id, 0])
        assert np.abs(many - left).mean() < 0.01
    # the middle of the art box: MSE agrees with the built-in renderer on the centred crop
    y, x0 = 150, 187
    assert np.abs(centred[y, x0 - 40:x0 + 40] - builtin[y, x0 - 40:x0 + 40]).mean() < 12
    assert left[y, x0][0] > 150 and left[y, x0][2] < 100       # red after zooming left


def test_mechanic_reminder_text_and_card_override() -> None:
    """A set mechanic's reminder text is drawn by MSE; hiding it on the card gives the
    same picture as no mechanic at all."""
    from setdesigner.model import Mechanic, MechanicKind
    project = oracle_project()
    bears = project.card("grizzly-bears")
    bears.faces[0].rules_text = "When this creature enters, want target creature."
    with CardRenderer(project) as r:
        plain = flatten(r.render(bears))
    project.mechanics = [Mechanic(id="want", name="Want", kind=MechanicKind.KEYWORD_ACTION,
                                  reminder_text="Put a bounty counter on it.")]
    with CardRenderer(project) as r:
        shown = flatten(r.render(bears))
        bears.reminders["want"] = False
        r.card_changed(bears)
        hidden = flatten(r.render(bears))
    assert np.abs(shown - plain).mean() > 0.5          # reminder text added (common: shown)
    assert np.abs(hidden - plain).mean() < 0.05


def test_ability_word_is_italic_without_reminder() -> None:
    """An ability word of the set is set in italics by MSE (its "pseudo" keyword mode) and
    gets no reminder text: the picture differs from the plain line only in that word."""
    from setdesigner.model import AbilityTemplate, Mechanic, MechanicKind
    project = oracle_project()
    bears = project.card("grizzly-bears")
    bears.faces[0].rules_text = "Settled — When this creature dies, draw a card."
    with CardRenderer(project) as r:
        plain = flatten(r.render(bears))
    project.mechanics = [Mechanic(id="settled", name="Settled", kind=MechanicKind.ABILITY_WORD,
                                  templates=[AbilityTemplate(label="Trigger", text="{trigger}, {effect}")])]
    with CardRenderer(project) as r:
        italic = flatten(r.render(bears))
        text = r.env.card_object(bears).fields.get("rule text")
    assert "Settled" in str(text) and "(" not in str(text)      # no reminder text added
    changed = np.abs(italic - plain).sum(axis=2) > 60
    rows = np.where(changed.any(axis=1))[0]
    assert rows.size and rows.max() - rows.min() < 30          # only the first line differs


def test_our_symbol_is_drawn_in_the_rarity_box(renderer) -> None:
    card = renderer.project.card("steel-overseer")                     # rare: gold
    image = np.asarray(renderer.render(card).convert("RGB"), int)
    x0, y0, x1, y1 = rarity_box(renderer, card)
    region = image[y0:y1, x0:x1].reshape(-1, 3)
    gold = (region[:, 0] > region[:, 2] + 50) & (region[:, 1] > region[:, 2] + 20)
    assert gold.sum() > 20


def test_edits_show_up_and_are_fast() -> None:
    project = keyword_project()
    with CardRenderer(project) as r:
        card = project.card("kicker")
        before = np.asarray(r.render(card))
        timings = []
        for text in ("Kicker {2}{R}\nCARDNAME deals 3 damage to any target.", "Flying, haste"):
            card.faces[0].rules_text = text
            start = time.perf_counter()
            r.card_changed(card)
            after = np.asarray(r.render(card))
            timings.append(time.perf_counter() - start)
        assert not np.array_equal(before, after)
        assert min(timings) < 0.6, timings          # target ~0.25 s; slack for slow machines


def test_recovers_from_a_crash(renderer) -> None:
    card = renderer.project.card("lightning-helix")
    first = np.asarray(renderer.render(card))
    renderer.mse.process.proc.kill()
    again = np.asarray(renderer.render(card))
    assert renderer.last_backend == "mse"
    assert np.array_equal(first, again)


def test_whole_set_for_print(renderer, tmp_path) -> None:
    files = renderer.render_set(tmp_path)
    faces = sum(len(c.faces) for c in renderer.project.cards)
    assert len(files) == faces and all(f.is_file() for f in files)
    with Image.open(files[0]) as img:
        assert img.size == (375, 523)


def test_falls_back_without_mse(tmp_path) -> None:
    project = oracle_project()
    with CardRenderer(project, mse_exe=tmp_path / "missing.com") as r:
        image = r.render(project.card("forest"))
        assert r.last_backend == "builtin" and image.size == (375, 523)
        assert any("built-in renderer" in w for w in r.warnings)
