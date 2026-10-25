"""Field definitions from MSE packages: the game's `card field` / `set field` and a
style's `styling field` / `extra card field`.

Each field has a type and optionally:
  initial:  the starting value;
  default:  a script giving the value while the user hasn't set one;
  script:   a script applied to the value (which it sees as `value`); its result
            is the field's value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .reader import MSEReadError, Node, read_file
from .script import ast as A
from .script.parser import parse
from .script.values import to_color


@dataclass
class FieldDef:
    name: str
    type: str
    initial: str | None = None
    first_choice: str | None = None
    default_script: A.Node | None = None
    script: A.Node | None = None
    save_value: bool = True
    first_color: str | None = None              # color fields: the first choice's color
    multi_line: bool = False                    # text fields: wraps over lines

    def initial_value(self) -> object:
        """The value before any script runs: `initial`, else the first choice of a
        choice field (a Color for color fields), else "" (booleans are "yes"/"no")."""
        if self.type == "color":
            text = self.initial if self.initial is not None else self.first_color
            return to_color(text) if text else ""
        if self.initial is not None:
            return self.initial
        if self.type == "choice" and self.first_choice is not None:
            return self.first_choice
        if self.type == "boolean":
            return "yes"
        return ""


def _first_choice(nodes: list[Node]) -> str | None:
    """Name of the first choice; nested groups give "group child"."""
    for node in nodes:
        if node.key != "choice":
            continue
        if node.value:
            return node.value
        try:
            children = node.children()
        except MSEReadError:
            return None
        name = next((c.value for c in children if c.key == "name"), None)
        sub = _first_choice(children)
        if name is None:
            return sub
        return f"{name} {sub}" if sub else name
    return None


def _first_color(nodes: list[Node]) -> str | None:
    """A color field's first `choice:` block's `color:` value."""
    for node in nodes:
        if node.key == "choice" and node.block:
            try:
                color = next((c.value for c in node.children() if c.key == "color"), None)
            except MSEReadError:
                continue
            if color:
                return color
    return None


def _script(node: Node | None) -> A.Node | None:
    return parse(node.text()) if node is not None and node.text().strip() else None


def field_def(node: Node) -> FieldDef | None:
    children = node.children()
    get = {c.key: c for c in reversed(children)}         # first occurrence wins
    if "name" not in get:
        return None
    return FieldDef(
        name=get["name"].value,
        type=get["type"].value if "type" in get else "text",
        initial=get["initial"].value if "initial" in get else None,
        first_choice=_first_choice(children),
        default_script=_script(get.get("default")),
        script=_script(get.get("script")),
        save_value=get["save value"].value != "false" if "save value" in get else True,
        first_color=_first_color(children),
        multi_line=get["multi line"].value in ("true", "yes") if "multi line" in get else False,
    )


def field_defs(path: Path, root: Path, key: str) -> dict[str, FieldDef]:
    """All `key:` definitions (e.g. "card field") in a package file, by field name.
    `info` fields (section headers in MSE's editor) are skipped."""
    nodes, _ = read_file(path, root)
    out: dict[str, FieldDef] = {}
    for node in nodes:
        if node.key == key:
            fd = field_def(node)
            if fd is not None and fd.type != "info":
                out[fd.name] = fd
    return out


@lru_cache(maxsize=None)
def game_fields(root: Path, game: str = "magic") -> tuple[dict[str, FieldDef], dict[str, FieldDef]]:
    """(card fields, set fields) of a game."""
    pkg = root / f"{game}.mse-game"
    return field_defs(pkg / "game", root, "card field"), field_defs(pkg / "game", root, "set field")


@lru_cache(maxsize=None)
def style_fields(root: Path, style: str) -> tuple[dict[str, FieldDef], dict[str, FieldDef]]:
    """(styling fields, extra card fields) of a stylesheet package, e.g. "magic-m15-altered"."""
    path = root / f"{style}.mse-style" / "style"
    return field_defs(path, root, "styling field"), field_defs(path, root, "extra card field")
