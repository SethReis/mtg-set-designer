"""End to end: M15's own frame scripts (`card style > card color > image`/`mask`) for
our fixture cards, generated at card size. Pixel agreement with real MSE for these
scripts is checked in tests/script/test_image_oracle.py (card_background cases)."""
from pathlib import Path

import numpy as np
import pytest

from fixtures.oracle_project import oracle_project
from setdesigner.mse.script import images as I

PACKAGES = Path(__file__).resolve().parents[1] / "resources" / "mse_packages"
pytestmark = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")


@pytest.fixture(scope="module")
def env():
    from setdesigner.mse.environment import ScriptEnvironment
    return ScriptEnvironment(oracle_project(), PACKAGES)


def frame(env, card_id: str, face: int = 0) -> np.ndarray:
    card = env.card_object(env.project.card(card_id), face)
    value = env.style_value(card, "card color", "image")
    raster = I.as_image(value).generate_conform(env.image_options(card.style, 375, 523))
    assert raster.size == (375, 523)
    return raster.rgb.astype(int)


def border(rgb: np.ndarray, side: str) -> np.ndarray:
    """Mean colour of the coloured frame border beside the art, left or right."""
    x = 18 if side == "left" else 375 - 22
    return rgb[150:250, x:x + 4].reshape(-1, 3).mean(0)


def test_green_creature_has_a_green_frame(env) -> None:
    r, g, b = border(frame(env, "grizzly-bears"), "left")
    assert g > r + 20 and g > b + 40


def test_hybrid_frame_is_red_on_the_left_and_white_on_the_right(env) -> None:
    rgb = frame(env, "boros-guildmage")
    r, g, b = border(rgb, "left")
    assert r > g + 80                                   # red
    assert border(rgb, "right").min() > 190             # white


def test_artifact_and_blue_frames(env) -> None:
    r, g, b = border(frame(env, "steel-overseer"), "left")
    assert b > r and abs(int(g) - int(b)) < 30          # cool silver-blue
    r, g, b = border(frame(env, "delver"), "left")
    assert b > g > r                                    # blue


def test_masks_and_back_faces_render(env) -> None:
    card = env.card_object(env.project.card("delver"), 1)
    mask = I.as_image(env.style_value(card, "card color", "mask"))
    assert mask.generate_conform(env.image_options(card.style, 375, 523)).size == (375, 523)
    frame(env, "delver", 1)


def test_no_field_script_falls_back(env) -> None:
    """Every game and style field script runs for every fixture card."""
    for card in env.set.cards:
        card.fields.all()
        card.extra_card.fields.all()
        assert card.warnings == [], card.warnings
