"""MSE format reader (stage 1 + 2 of the parser).

Turns an MSE package file (style, game, symbol-font, include...) into a plain
tree of keyed nodes. It does NOT interpret what keys mean and does NOT evaluate
scripts: script text is kept as raw strings for the later script module.

Two steps:
  1. expand_includes(): textually splice `include file:` directives, the same
     way MSE does, producing one flat list of lines.
  2. parse_block(): turn indented `key: value` lines into Node objects.
     A node's body is kept raw and only parsed into children on request,
     because the same indented text is a nested key tree in some places and
     script source in others, and only the schema layer knows which.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# `include file: x`, `include localized file: x`, or `some key: include file: x`
_INCLUDE_RE = re.compile(
    r"^(?P<indent>\t*)(?P<prefix>(?:[^:#\s][^:]*:\s*)?)"
    r"include (?P<localized>localized )?file:\s*(?P<path>\S.*?)\s*$"
)
_KEY_RE = re.compile(r"^(?P<key>[^\s:#][^:]*?)\s*:[ ]?(?P<value>.*)$")


class MSEReadError(Exception):
    pass


@dataclass
class Stats:
    includes_resolved: int = 0
    unresolved: list[str] = field(default_factory=list)
    space_indented_lines: int = 0


@dataclass
class Node:
    key: str
    value: str                      # text after "key:" on the same line
    block: list[str]                # indented body, one tab level removed
    line: int                       # 1-based line within the expanded text

    def children(self) -> list["Node"]:
        """Parse the body as nested keys (use when the schema expects keys)."""
        return parse_block(self.block)

    def text(self) -> str:
        """Value as one string (use for scripts and multi-line text)."""
        if not self.block:
            return self.value
        body = "\n".join(self.block)
        return f"{self.value}\n{body}" if self.value else body

    def get(self, key: str) -> "Node | None":
        return next((c for c in self.children() if c.key == key), None)


# ---------------------------------------------------------------- includes

def _read_lines(path: Path) -> list[str]:
    # MSE files are UTF-8 and often start with a BOM.
    return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def expand_includes(
    lines: list[str],
    pkg_dir: Path,
    root: Path,
    stats: Stats,
    lang: str = "en",
    _stack: tuple[Path, ...] = (),
) -> list[str]:
    """Splice `include file:` directives. `root` is the folder holding all
    packages; paths starting with `/` are `/<package>/<file>` under it."""
    out: list[str] = []
    for raw in lines:
        m = _INCLUDE_RE.match(raw)
        if not m:
            out.append(raw)
            continue

        rel = m["path"]
        if rel.startswith("/"):
            target = root / rel.lstrip("/")
            inc_pkg = root / rel.lstrip("/").split("/", 1)[0]
        else:
            target = pkg_dir / rel
            inc_pkg = pkg_dir
        if m["localized"]:
            target = target.with_name(f"{target.name}_{lang}")

        if not target.is_file():
            stats.unresolved.append(f"{rel} (from {pkg_dir.name})")
            out.append(raw)             # keep the line so nothing vanishes silently
            continue
        if target in _stack:
            raise MSEReadError(f"include cycle at {target}")

        included = expand_includes(
            _read_lines(target), inc_pkg, root, stats, lang, _stack + (target,)
        )
        stats.includes_resolved += 1

        indent = m["indent"]
        if m["prefix"].strip():         # `key: include file: x` -> body of key
            out.append(indent + m["prefix"].rstrip())
            indent += "\t"
        out.extend(indent + l if l.strip() else l for l in included)
    return out


# ------------------------------------------------------------------- nodes

def parse_block(lines: list[str], stats: Stats | None = None) -> list[Node]:
    nodes: list[Node] = []
    cur: Node | None = None

    def close() -> None:
        if cur is not None:
            while cur.block and not cur.block[-1].strip():
                cur.block.pop()

    for n, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if raw[:1] == "\t":
            if cur is not None:
                cur.block.append(raw[1:])
            continue
        if raw[:1] == " " and stripped:             # MSE uses tabs; track exceptions
            if stats:
                stats.space_indented_lines += 1
            if cur is not None:
                cur.block.append(stripped)
            continue
        if not stripped:
            if cur is not None:
                cur.block.append("")
            continue
        if stripped.startswith("#"):
            continue
        m = _KEY_RE.match(raw)
        if not m:
            raise MSEReadError(f"line {n}: expected 'key: value', got {raw!r}")
        close()
        cur = Node(m["key"], m["value"].strip(), [], n)
        nodes.append(cur)
    close()
    return nodes


def read_file(path: Path, root: Path, lang: str = "en") -> tuple[list[Node], Stats]:
    """Read one package file with includes expanded. Returns (top-level nodes, stats)."""
    stats = Stats()
    lines = expand_includes(_read_lines(path), path.parent, root, stats, lang, (path,))
    return parse_block(lines, stats), stats
