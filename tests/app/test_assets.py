"""Importing art and the set symbol into a set folder (built-in renderer, no MSE)."""
import io

import pytest
from PIL import Image

from setdesigner.app.assets import AssetError, import_art, import_symbol, remove_art
from setdesigner.app.session import SetSession
from setdesigner.model import ArtCrop, load_project
from setdesigner.ui.uploads import receive_art


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", renderer_factory=builtin,
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def image_bytes(fmt: str, color="red", size=(120, 80)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


def test_art_is_copied_converted_and_replaced(session) -> None:
    card = session.new_card("Bear")
    path = import_art(session, card, image_bytes("PNG"), "bear.png")
    assert path == "assets/art/bear.png" and card.faces[0].art_path == path
    assert (session.folder / path).read_bytes() == image_bytes("PNG")      # kept as it is
    session.update(card, "art_crop", {"x": 0.2, "y": 0.5, "zoom": 2})
    assert card.faces[0].art_crop == ArtCrop(x=0.2, y=0.5, zoom=2)

    path = import_art(session, card, image_bytes("BMP", "blue"), "bear.bmp")   # converted
    assert path == "assets/art/bear.png" and card.faces[0].art_crop is None    # crop reset
    with Image.open(session.folder / path) as img:
        assert img.format == "PNG" and img.getpixel((5, 5))[:3] == (0, 0, 255)
    import_art(session, card, image_bytes("JPEG"), "bear.jpg")
    assert sorted(p.name for p in (session.folder / "assets" / "art").iterdir()) == ["bear.jpg"]

    session.flush()
    reloaded = load_project(session.folder)
    face = reloaded.card(card.id).faces[0]
    assert face.art_path == "assets/art/bear.jpg"
    assert reloaded.resolve(face.art_path) == session.folder / "assets" / "art" / "bear.jpg"


def test_non_images_are_rejected(session) -> None:
    card = session.new_card()
    with pytest.raises(AssetError):
        import_art(session, card, b"not an image", "notes.txt")
    assert card.faces[0].art_path is None


def test_remove_art(session) -> None:
    card = session.new_card()
    path = import_art(session, card, image_bytes("PNG"), "a.png")
    version = session.art_version
    remove_art(session, card)
    assert not (session.folder / path).exists() and card.faces[0].art_path is None
    assert session.art_version == version + 1


def test_symbol_import(session) -> None:
    path = import_symbol(session, image_bytes("PNG", "black"), "symbol.png")
    assert path == "assets/symbol.png" and session.project.info.symbol_path == path
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    assert import_symbol(session, svg, "symbol.svg") == "assets/symbol.svg"
    assert not (session.folder / "assets" / "symbol.png").exists()
    with pytest.raises(AssetError):
        import_symbol(session, b"plain text", "symbol.svg")


def test_upload_route_logic(session) -> None:
    card = session.new_card("Bear")
    status, body = receive_art(session, card.id, image_bytes("PNG"), "bear.png")
    assert status == 200 and body["path"] == "assets/art/bear.png"
    assert session.art_notice[0] == "positive"
    assert receive_art(session, "nope", b"", "x.png")[0] == 404
    assert receive_art(session, card.id, b"junk", "x.png")[0] == 400
    assert receive_art(None, card.id, b"", "x.png")[0] == 409


def test_art_shows_and_keys_change(session) -> None:
    card = session.new_card("Bear")
    session.update(card, "types", "Creature")
    blank = session.render(card)
    keys = lambda: session.using_renderer(lambda r: (session.refresh_edited(r), r.render_keys([card]))[1])
    before = keys()
    import_art(session, card, image_bytes("PNG", (255, 0, 0), (400, 300)), "red.png")
    with_art = session.render(card)
    assert with_art.tobytes() != blank.tobytes()
    assert with_art.convert("RGB").getpixel((187, 150)) == (255, 0, 0)   # middle of the art box
    after = keys()
    assert after != before
    session.update(card, "art_crop", {"x": 0.1, "y": 0.5, "zoom": 2})
    assert keys() != after
