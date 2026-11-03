"""Print export end to end: pictures (cached), then the PDF."""
import re
import threading
from pathlib import Path

import pytest

from setdesigner.app.printing import Cancelled, export_pdf, pictures, print_cache, summary
from setdesigner.app.session import SetSession
from setdesigner.export.selection import PrintOptions
from setdesigner.model import Rarity
from setdesigner.render import find_mse

PACKAGES = Path(__file__).resolve().parents[2] / "resources" / "mse_packages"
needs_packages = pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")
needs_mse = pytest.mark.skipif(not PACKAGES.is_dir() or find_mse() is None, reason="needs MSE and its templates")


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", renderer_factory=builtin,
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def test_summary_counts_faces_pages_and_the_grid(session) -> None:
    cards = [session.new_card(f"Card {i}") for i in range(4)]
    session.update(cards[0], "rarity", Rarity.RARE)
    options = PrintOptions(distribution="rarity", paper="a4")
    assert summary(cards, options) == (3 * 4 + 1, 2, (3, 3))
    assert summary(cards, PrintOptions(paper="a4")) == (4, 1, (3, 3))


@needs_packages
def test_pictures_are_cached_full_size(session) -> None:
    cards = [session.new_card("Alpha"), session.new_card("Beta")]
    found, rendered, builtin = pictures(session, cards)
    assert rendered == 2 and builtin and set(found) == {(c.id, 0) for c in cards}
    assert all(p.parent == print_cache(session).folder for p in found.values())
    again, rendered, _ = pictures(session, cards)
    assert rendered == 0 and again == found
    session.update(cards[0], "rules_text", "Flying")          # only the edited card is redrawn
    changed, rendered, _ = pictures(session, cards)
    assert rendered == 1 and changed[cards[1].id, 0] == found[cards[1].id, 0]
    assert not found[cards[0].id, 0].exists()                  # its old picture is gone


@needs_packages
def test_export_writes_a_pdf(session, tmp_path) -> None:
    cards = [session.new_card(f"Card {i}") for i in range(10)]
    target = tmp_path / "out.pdf"
    steps = []
    result = export_pdf(session, cards, PrintOptions(paper="letter", bleed_mm=1.0, labels=True),
                        target, progress=lambda text, _: steps.append(text))
    data = target.read_bytes()
    assert result.pages == 2 and result.faces == 10 and result.rendered == 10
    assert len(re.findall(rb"/Type /Page\b", data)) == 2
    assert any(s.startswith("Rendering") for s in steps) and steps[-1] == "Writing page 2 of 2"


@needs_packages
def test_export_can_be_cancelled(session, tmp_path) -> None:
    cards = [session.new_card("Card")]
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        export_pdf(session, cards, PrintOptions(), tmp_path / "out.pdf", cancel=cancel)


@needs_mse
def test_real_mse_pictures_print_and_cache(tmp_path) -> None:
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", thumbnail_dir=tmp_path / "thumbs")
    try:
        cards = [s.new_card(f"Card {i}") for i in range(9)]
        assert not s.uses_builtin_renderer
        first = export_pdf(s, cards, PrintOptions(), tmp_path / "a.pdf")
        assert s.using_renderer(lambda r: r.last_backend) == "mse"
        second = export_pdf(s, cards, PrintOptions(), tmp_path / "b.pdf")
        assert first.rendered == 9 and second.rendered == 0 and second.pages == 1
    finally:
        s.close()


def test_printer_friendly_needs_no_renderer(session, tmp_path) -> None:
    cards = [session.new_card(f"Card {i}") for i in range(3)]
    session.update(cards[0], "rules_text", "Flying. " * 500)
    result = export_pdf(session, cards, PrintOptions(style="friendly"), tmp_path / "out.pdf")
    assert result.pages == 1 and result.rendered == 0 and result.overflow == ["Card 0"]
    assert session._renderer is None                          # never started
