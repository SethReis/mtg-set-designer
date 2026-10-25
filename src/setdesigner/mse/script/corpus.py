"""The real-world script corpus: every snippet from magic.mse-game and our target
styles. Used by tests and tools to check the parser against actual packages."""
from __future__ import annotations

from pathlib import Path

from ..reader import Node, read_file
from ..snippets import Snippet, scripts_in
from . import ast as A
from .parser import parse, parse_template

STYLES = ["magic-m15-altered", "magic-old", "magic-new", "magic-veryold", "magic-old-abu"]


def _symbol_font_deps(nodes: list[Node]) -> list[str]:
    deps = []
    for node in nodes:
        if node.key == "depends on":
            pkg = node.get("package")
            if pkg and pkg.value.endswith(".mse-symbol-font"):
                deps.append(pkg.value)
    return deps


def target_snippets(root: Path) -> list[Snippet]:
    """Snippets from the game file, the target styles and their symbol fonts."""
    nodes, _ = read_file(root / "magic.mse-game" / "game", root)
    out = scripts_in(nodes, "magic.mse-game")
    fonts: list[str] = []
    for style in STYLES:
        nodes, _ = read_file(root / f"{style}.mse-style" / "style", root)
        out += scripts_in(nodes, style)
        fonts += [f for f in _symbol_font_deps(nodes) if f not in fonts]
    for font in fonts:
        path = root / font / "symbol-font"
        if path.is_file():
            nodes, _ = read_file(path, root)
            out += scripts_in(nodes, font)
    return out


def parse_snippet(snip: Snippet) -> A.Node:
    return parse(snip.text) if snip.kind == "script" else parse_template(snip.text)
