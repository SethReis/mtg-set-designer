"""Where cards go on the paper."""
import pytest

from setdesigner.export.sheet import CARD, MARGIN, PAPERS, fit, pages


@pytest.mark.parametrize("paper", ["a4", "letter"])
@pytest.mark.parametrize("bleed", [0.0, 1.0])
def test_nine_cards_fit(paper, bleed) -> None:
    grid = fit(paper, bleed=bleed)
    assert (grid.columns, grid.rows) == (3, 3)


def test_three_mm_bleed() -> None:
    assert (fit("a4", bleed=3).columns, fit("a4", bleed=3).rows) == (3, 3)
    assert (fit("letter", bleed=3).columns, fit("letter", bleed=3).rows) == (3, 2)   # 3 x 94 mm is too tall


@pytest.mark.parametrize("paper", ["a4", "letter"])
@pytest.mark.parametrize("bleed,spacing,labels", [(0, 0, False), (1, 2, True), (3, 0, False)])
def test_cards_stay_inside_the_margin_and_never_overlap(paper, bleed, spacing, labels) -> None:
    grid = fit(paper, bleed=bleed, spacing=spacing, labels=labels)
    _, page_w, page_h = PAPERS[paper]
    w, h = CARD
    boxes = [grid.position(i) for i in range(grid.per_page)]
    for x, y in boxes:
        assert MARGIN <= x and x + w <= page_w - MARGIN
        assert MARGIN <= y and y + h <= page_h - MARGIN
    for i, (x1, y1) in enumerate(boxes):
        for x2, y2 in boxes[i + 1:]:          # bleed boxes don't overlap either
            assert abs(x2 - x1) >= w + 2 * bleed - 1e-9 or abs(y2 - y1) >= h + 2 * bleed - 1e-9


def test_grid_is_centred() -> None:
    grid = fit("a4")
    xs, ys = grid.trim_lines()
    assert xs[0] == pytest.approx(210 - xs[-1])
    assert ys[0] == pytest.approx(297 - ys[-1])


def test_a_tenth_card_starts_page_two() -> None:
    grid = fit("a4")
    sheets = pages(list(range(10)), grid)
    assert [len(s) for s in sheets] == [9, 1]
    assert (sheets[1][0].x, sheets[1][0].y) == (sheets[0][0].x, sheets[0][0].y)
    assert [s.item for s in sheets[0][:3]] == [0, 1, 2]
    assert sheets[0][1].y == sheets[0][0].y and sheets[0][3].x == sheets[0][0].x   # row by row
