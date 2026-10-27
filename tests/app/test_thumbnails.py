"""Overview pictures: cache keys, the cache, the background worker (built-in renderer)."""
import pytest
from PIL import Image

from setdesigner.app.session import SetSession
from setdesigner.app.thumbnails import WIDTH, ThumbnailCache


def builtin(project):
    from setdesigner.render import CardRenderer
    return CardRenderer(project, use_mse=False)


@pytest.fixture
def session(tmp_path):
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", renderer_factory=builtin,
                          thumbnail_dir=tmp_path / "thumbs")
    yield s
    s.close()


def keys(session, cards):
    return session.using_renderer(lambda r: (session.refresh_edited(r), r.render_keys(cards))[1])


def test_keys_change_only_when_the_card_does(session) -> None:
    a, b = session.new_card("Alpha"), session.new_card("Beta")
    first = keys(session, [a, b])
    assert keys(session, [a, b]) == first
    session.update(a, "rules_text", "Flying")
    second = keys(session, [a, b])
    assert second[a.id] != first[a.id] and second[b.id] == first[b.id]
    session.update_info(name="Renamed")                   # set info is on every card
    assert keys(session, [a, b])[b.id] != first[b.id]


def test_cache_replaces_old_pictures(tmp_path) -> None:
    cache = ThumbnailCache(tmp_path)
    picture = Image.new("RGBA", (375, 523), "red")
    old = cache.put("bear", "k1", picture)
    new = cache.put("bear", "k2", picture)
    other = cache.put("bear-2", "k1", picture)            # a different card, similar id
    assert not old.exists() and new.exists() and other.exists()
    assert cache.get("bear", "k2") == new and cache.get("bear", "k1") is None
    with Image.open(new) as img:
        assert img.width == WIDTH


def test_worker_fills_the_cache_and_redraws_edited_cards(session) -> None:
    cards = [session.new_card(f"Card {i}") for i in range(3)]
    worker = session.thumbnails
    worker.request(cards)
    assert worker.wait_idle(), worker.error
    first = {c.id: worker.get(c) for c in cards}
    assert all(p is not None and p.is_file() for p in first.values())

    session.update(cards[0], "name", "Changed")
    assert worker.get(cards[0]) is None                   # out of date at once
    worker.request(cards)
    assert worker.wait_idle(), worker.error
    assert worker.get(cards[0]) != first[cards[0].id]
    assert worker.get(cards[1]) == first[cards[1].id]     # unchanged: same file
    assert not first[cards[0].id].exists()                # old picture removed


def test_render_many_matches_single_renders(session) -> None:
    cards = [session.new_card("One"), session.new_card("Two")]
    session.update(cards[1], "rules_text", "Flying")
    many = session.using_renderer(lambda r: (session.refresh_edited(r), r.render_many(cards))[1])
    for card in cards:
        assert many[card.id, 0].tobytes() == session.render(card).tobytes()
