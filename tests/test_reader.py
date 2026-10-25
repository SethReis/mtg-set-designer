from pathlib import Path

import pytest

from setdesigner.mse.reader import MSEReadError, parse_block, read_file

PACKAGES = Path(__file__).resolve().parent.parent / "resources" / "mse_packages"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Two sibling packages: a style that includes a file from a shared include package."""
    write(tmp_path / "shared.mse-include" / "boxes",
          "name box:\n\tleft: 10\n\ttop: { 30 + offset() }\n")
    write(tmp_path / "test.mse-style" / "local", "local key: 1\n")
    return tmp_path


def test_absolute_and_relative_includes_are_spliced(root: Path) -> None:
    style = write(root / "test.mse-style" / "style",
                  "﻿game: magic\n"
                  "card style:\n"
                  "\tinclude file: /shared.mse-include/boxes\n"
                  "include file: local\n")
    nodes, stats = read_file(style, root)

    assert [n.key for n in nodes] == ["game", "card style", "local key"]
    assert nodes[0].value == "magic"            # BOM stripped from the first key
    name_box = nodes[1].get("name box")
    assert name_box is not None
    assert name_box.get("top").value == "{ 30 + offset() }"
    assert stats.includes_resolved == 2
    assert stats.unresolved == []


def test_key_include_becomes_body_of_key(root: Path) -> None:
    style = write(root / "test.mse-style" / "style",
                  "card style: include file: /shared.mse-include/boxes\n")
    nodes, _ = read_file(style, root)
    assert nodes[0].key == "card style"
    assert [c.key for c in nodes[0].children()] == ["name box"]


def test_unresolved_include_is_recorded_not_dropped(root: Path) -> None:
    style = write(root / "test.mse-style" / "style",
                  "a: 1\ninclude file: /missing.mse-include/nothing\n")
    nodes, stats = read_file(style, root)
    assert len(stats.unresolved) == 1
    assert "missing.mse-include" in stats.unresolved[0]


def test_malformed_line_reports_line_number() -> None:
    with pytest.raises(MSEReadError, match="line 3"):
        parse_block(["a: 1", "# comment", "no colon here"])


def test_script_block_kept_as_raw_text() -> None:
    (node,) = parse_block(["left:", "\tscript:", "\t\tif x then 1", "\t\telse 2", ""])
    assert node.text() == "script:\n\tif x then 1\n\telse 2"


@pytest.mark.skipif(not PACKAGES.is_dir(), reason="resources/mse_packages not populated")
def test_every_real_package_reads_and_m15_name_box_is_intact() -> None:
    mains = {".mse-style": "style", ".mse-game": "game", ".mse-symbol-font": "symbol-font"}
    count = 0
    for pkg in PACKAGES.iterdir():
        main = mains.get(pkg.suffix)
        if main and (pkg / main).is_file():
            read_file(pkg / main, PACKAGES)
            count += 1
    assert count >= 89

    nodes, _ = read_file(PACKAGES / "magic-m15-altered.mse-style" / "style", PACKAGES)
    name_boxes = [c for n in nodes if n.key == "card style" for c in n.children() if c.key == "name"]
    assert name_boxes
    keys = [c.key for c in name_boxes[0].children()]
    for expected in ["left", "top", "right", "height", "alignment", "padding bottom", "z index", "font"]:
        assert expected in keys
