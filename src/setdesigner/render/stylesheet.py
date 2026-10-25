"""Read an MSE stylesheet's `card style` / `extra card style` entries.

Each entry styles one field (`name`, `text`, `card color`, ...). Its properties are
kept as parsed scripts (a plain value is a template that evaluates to itself), with
nested blocks (`font`, `symbol font`, `choice images`) as dicts of the same.
Repeated `card style` blocks are merged, later properties winning, as in MSE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..mse.fields import game_fields, style_fields
from ..mse.reader import MSEReadError, Node, read_file
from ..mse.script import ast as A
from ..mse.script.parser import parse, parse_template

Prop = "A.Node | dict[str, Prop]"


@dataclass
class EntryStyle:
    field: str
    kind: str                            # field type: text, choice, image, color, ...
    extra: bool                          # an extra card field of the style
    order: int                           # file order (ties in z index keep it)
    props: dict[str, object] = field(default_factory=dict)


@dataclass
class Stylesheet:
    package: str
    card_width: int
    card_height: int
    dpi: float
    entries: list[EntryStyle]

    def entry(self, name: str) -> EntryStyle | None:
        return next((e for e in self.entries if e.field == name), None)


def _prop(node: Node) -> object:
    if node.value.startswith("{"):
        return parse_template(node.text())
    if not node.block:
        return parse_template(node.value)
    try:
        children = node.children()
    except MSEReadError:
        return parse_template(node.text())
    if len(children) == 1 and children[0].key == "script":
        return parse(children[0].text())
    out: dict[str, object] = {}
    for child in children:
        out[child.key] = _prop(child)
    return out


def _merge(into: dict, props: dict) -> None:
    for key, value in props.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            _merge(into[key], value)
        else:
            into[key] = value


@lru_cache(maxsize=None)
def load_stylesheet(root: Path, package: str, game: str = "magic") -> Stylesheet:
    nodes, _ = read_file(root / f"{package}.mse-style" / "style", root)
    top = {n.key: n.value for n in nodes if n.value and not n.block}
    card_fields, _ = game_fields(root, game)
    _, extra_fields = style_fields(root, package)
    entries: dict[tuple[bool, str], EntryStyle] = {}
    order = 0
    for block in nodes:
        if block.key not in ("card style", "extra card style"):
            continue
        extra = block.key == "extra card style"
        defs = extra_fields if extra else card_fields
        for node in block.children():
            props = _prop(node) if node.block else {}
            if not isinstance(props, dict):
                continue
            key = (extra, node.key)
            if key not in entries:
                kind = defs[node.key].type if node.key in defs else "unknown"
                entries[key] = EntryStyle(node.key, kind, extra, order)
                order += 1
            _merge(entries[key].props, props)
    return Stylesheet(package, int(top.get("card width", 375)), int(top.get("card height", 523)),
                      float(top.get("card dpi", 150)), list(entries.values()))
