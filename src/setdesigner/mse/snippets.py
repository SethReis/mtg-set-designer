"""Find the script snippets inside a parsed MSE package file.

Scripts appear in two forms:
  * keys named `script` or `... script` (`init script:`, `update cards script:`):
    the body is plain script code;
  * values starting with `{` (`top: { 30 + name_font_vertical() }`): the value is
    a *template*, text with `{expr}` holes, parsed like the inside of a string.
"""
from __future__ import annotations

from dataclasses import dataclass

from .reader import MSEReadError, Node

# Keyword definitions hold reminder *text* templates ("{param1}: Attach to ..."), not
# rendering scripts; they belong to the mechanics feature, so they're left out.
NOT_SCRIPT_TOP_KEYS = {"keyword", "keyword parameter type"}
# "... script" keys whose body is more keys (name:, description:, script:), not code.
CONTAINER_SCRIPT_KEYS = {"add cards script", "update cards script"}


@dataclass
class Snippet:
    source: str          # package name
    path: str            # key path, e.g. "card style > name > left"
    text: str
    kind: str            # "script" (code) or "template" (`{ ... }` value)
    line: int = 0        # line of the key within its parent block


def is_script_key(key: str) -> bool:
    return key == "script" or (key.endswith(" script") and key not in CONTAINER_SCRIPT_KEYS)


def scripts_in(nodes: list[Node], source: str, prefix: str = "") -> list[Snippet]:
    """Find script snippets in a keyed tree, recursing into nested keys."""
    out: list[Snippet] = []
    for node in nodes:
        path = f"{prefix} > {node.key}" if prefix else node.key
        if not prefix and node.key in NOT_SCRIPT_TOP_KEYS:
            continue
        if is_script_key(node.key):
            out.append(Snippet(source, path, node.text(), "script", node.line))
        elif node.value.startswith("{"):
            out.append(Snippet(source, path, node.text(), "template", node.line))
        elif node.block:
            try:
                out.extend(scripts_in(node.children(), source, path))
            except MSEReadError:
                pass            # free text body (e.g. descriptions), not keys
    return out
