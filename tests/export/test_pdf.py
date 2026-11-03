"""The PDF: pages, page size, one embedded picture per face, bleed and corners."""
import io
import re

from PIL import Image, ImageDraw

from setdesigner.export.pdf import border_color, image_drawer, label_text, print_picture, write_pdf
from setdesigner.export.selection import PrintOptions, print_faces
from setdesigner.export.sheet import fit, pages
from setdesigner.model import Card, Face, Layout


def picture(color, size=(375, 523)) -> Image.Image:
    """A card-like picture: a black border, a colored inside and transparent round corners."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=18, fill="black")
    ImageDraw.Draw(image).rectangle((20, 20, size[0] - 21, size[1] - 21), fill=color)
    return image


def cards(n, faces=1):
    return [Card(id=f"c{i}", collector_number=str(i + 1),
                 layout=Layout.TRANSFORM if faces == 2 else Layout.NORMAL,
                 faces=[Face(name=f"C{i}") for _ in range(faces)]) for i in range(n)]


def export(card_list, options, pictures):
    out = io.BytesIO()
    grid = fit(options.paper, options.bleed_mm, options.spacing_mm, options.labels)
    count = write_pdf(out, pages(print_faces(card_list, options), grid), grid, image_drawer(pictures),
                      crop_marks=options.crop_marks, title="Test")
    return count, out.getvalue()


def page_count(data: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b", data))


def test_pages_and_page_size() -> None:
    deck = cards(10)
    count, data = export(deck, PrintOptions(paper="a4"), {(c.id, 0): picture("red") for c in deck})
    assert count == 2 and page_count(data) == 2
    box = re.search(rb"/MediaBox \[ ?0 0 ([\d.]+) ([\d.]+) ?\]", data)
    assert abs(float(box.group(1)) - 595.28) < 0.1 and abs(float(box.group(2)) - 841.89) < 0.1


def test_copies_embed_the_picture_once() -> None:
    one = cards(1)
    pictures = {("c0", 0): picture("red")}
    _, single = export(one, PrintOptions(distribution="cube"), pictures)
    _, nine = export(one, PrintOptions(distribution="rarity", copies={"common": 9}), pictures)
    assert len(re.findall(rb"/Subtype /Image", nine)) == 1
    assert len(nine) < len(single) * 1.2


def test_two_faced_cards_get_a_picture_per_face() -> None:
    deck = cards(1, faces=2)
    _, data = export(deck, PrintOptions(), {("c0", 0): picture("red"), ("c0", 1): picture("blue")})
    assert len(re.findall(rb"/Subtype /Image", data)) == 2


def test_bleed_repeats_the_edge_and_corners_take_the_border_color() -> None:
    image = picture("red")
    assert border_color(image) == (0, 0, 0)
    plain = print_picture(image, 0)
    assert plain.mode == "RGB" and plain.getpixel((0, 0)) == (0, 0, 0)       # corner filled
    bled = print_picture(image, 12)
    assert bled.size == (375 + 24, 523 + 24)
    assert bled.getpixel((0, 0)) == (0, 0, 0) and bled.getpixel((200, 0)) == (0, 0, 0)
    assert bled.getpixel((200, 300)) == (255, 0, 0)


def test_white_bordered_cards_keep_white_corners() -> None:
    image = Image.new("RGBA", (375, 523), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, 374, 522), radius=18, fill="white")
    assert print_picture(image, 0).getpixel((0, 0)) == (255, 255, 255)


def test_labels() -> None:
    single, dfc = cards(1)[0], cards(1, faces=2)[0]
    from setdesigner.export.selection import PrintFace
    assert label_text(PrintFace(single, 0, 0), "TST") == "TST 1"
    assert label_text(PrintFace(dfc, 1, 0), "TST") == "TST 1 · back"
