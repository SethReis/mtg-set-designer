"""Survey which MSE script functions and constructs our target styles use.

Usage: python tools/survey_scripts.py [packages_root]

Writes docs/script_survey.md (readable report) and docs/script_survey.json (raw counts).
This is a rough lexical scan, not a parser: its job is to rank what the script
interpreter must support first. Counts are approximate.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from setdesigner.mse.reader import MSEReadError, Node, read_file  # noqa: E402
from setdesigner.mse.snippets import Snippet, is_script_key, scripts_in  # noqa: E402

STYLES = ["magic-m15-altered", "magic-old", "magic-new", "magic-veryold", "magic-old-abu"]
KEYWORDS = {"if", "then", "else", "for", "each", "in", "do", "from", "to", "and", "or",
            "xor", "not", "mod", "div", "true", "false", "nil", "rev", "case", "of"}
OPERATORS = [":=", "==", "!=", "<=", ">=", "+", "-", "*", "/", "^", "<", ">", "@", "(", ")",
             "[", "]", "{", "}", ",", ":", ".", ";", "=", "!"]
DEF_LINE = re.compile(r"^([A-Za-z_]\w*)\s*:=")
# Objects MSE puts in scope; occasionally indexed like calls, never real built-ins.
CONTEXT_NAMES = {"card", "set", "styling", "card_style", "input", "extra_card", "stylesheet"}


# ------------------------------------------------------------------ lexing

@dataclass
class Tok:
    kind: str           # ident | num | op | str
    text: str
    line: int


def tokenize(src: str) -> tuple[list[Tok], int]:
    """Rough MSE-script lexer. Returns code tokens (string contents collapsed to
    one `str` token, but `{...}` inside strings is lexed as code) and the number
    of string interpolations seen."""
    toks: list[Tok] = []
    interpolations = 0
    i, n, line = 0, len(src), 1
    # Stack of contexts: "code" or "string"; each code context opened inside a
    # string tracks its own brace depth so the matching `}` returns to the string.
    stack: list[list] = [["code", 0]]
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
        ctx = stack[-1]
        if ctx[0] == "string":
            if c == "\\":
                i += 2
                continue
            if c == '"':
                stack.pop()
                toks.append(Tok("str", '""', line))
            elif c == "{":
                interpolations += 1
                stack.append(["code", 0])
            i += 1
            continue
        # code context
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if c == '"':
            stack.append(["string", 0])
            i += 1
            continue
        if c == "{":
            ctx[1] += 1
        elif c == "}":
            if ctx[1] == 0 and len(stack) > 1:    # closes an interpolation
                stack.pop()
                i += 1
                continue
            ctx[1] -= 1
        m = re.match(r"[A-Za-z_]\w*", src[i:i + 80])
        if m:
            toks.append(Tok("ident", m.group(), line))
            i += m.end()
            continue
        m = re.match(r"\d+(\.\d+)?", src[i:i + 40])
        if m:
            toks.append(Tok("num", m.group(), line))
            i += m.end()
            continue
        for op in OPERATORS:
            if src.startswith(op, i):
                toks.append(Tok("op", op, line))
                i += len(op)
                break
        else:
            toks.append(Tok("op", c, line))       # unknown char, keep visible
            i += 1
    return toks, interpolations


# ------------------------------------------------------------- extraction

def key_paths(nodes: list[Node], prefix: str = "", depth: int = 0) -> Counter:
    """Count key paths (generic: card style entries are collapsed to `*`)."""
    counts: Counter = Counter()
    for node in nodes:
        key = node.key
        if prefix in ("card style", "set info style", "styling style", "extra card style"):
            key = "*"
        path = f"{prefix} > {key}" if prefix else key
        counts[path] += 1
        if node.block and depth < 3 and not is_script_key(node.key) \
                and not node.value.startswith("{"):
            try:
                counts += key_paths(node.children(), path, depth + 1)
            except MSEReadError:
                pass
    return counts


def symbol_font_deps(nodes: list[Node]) -> list[str]:
    deps = []
    for node in nodes:
        if node.key == "depends on":
            pkg = node.get("package")
            if pkg and pkg.value.endswith(".mse-symbol-font"):
                deps.append(pkg.value)
    return deps


# ---------------------------------------------------------------- analysis

@dataclass
class Usage:
    calls: Counter = field(default_factory=Counter)        # ident( and ident@(
    partial: Counter = field(default_factory=Counter)      # ident@(
    refs: Counter = field(default_factory=Counter)         # any ident in expression position
    keywords: Counter = field(default_factory=Counter)
    ops: Counter = field(default_factory=Counter)
    constructs: Counter = field(default_factory=Counter)
    defined: set[str] = field(default_factory=set)
    examples: dict[str, str] = field(default_factory=dict)  # name -> first line seen


def analyse(snippets: list[Snippet]) -> tuple[Usage, dict[str, set[str]]]:
    """Scan snippets. Returns usage counts and a definition graph
    (top-level `name :=` -> identifiers referenced in its body)."""
    u = Usage()
    graph: dict[str, set[str]] = defaultdict(set)
    for snip in snippets:
        lines = snip.text.splitlines()
        toks, interp = tokenize(snip.text)
        u.constructs["string interpolation \"..{x}..\""] += interp

        # Map each line to the top-level definition it belongs to.
        owner_by_line: dict[int, str | None] = {}
        owner = None
        for ln, text in enumerate(lines, 1):
            m = DEF_LINE.match(text)
            if m:
                owner = m.group(1)
            elif text and not text[0].isspace() and not text.startswith("#"):
                owner = None
            owner_by_line[ln] = owner

        for k, t in enumerate(toks):
            prev = toks[k - 1] if k else None
            nxt = toks[k + 1] if k + 1 < len(toks) else None
            nxt2 = toks[k + 2] if k + 2 < len(toks) else None
            if t.kind == "op":
                u.ops[t.text] += 1
                if t.text == "[":
                    indexing = prev is not None and (prev.kind in ("ident", "str") and prev.text not in KEYWORDS
                                                     or prev.text in (")", "]"))
                    u.constructs["index x[...]" if indexing else "list/map literal [...]"] += 1
                if t.text == "{":
                    u.constructs["closure/block { ... }"] += 1
                continue
            if t.kind != "ident":
                continue
            if t.text in KEYWORDS:
                u.keywords[t.text] += 1
                if t.text == "for" and nxt and nxt.text == "each":
                    u.constructs["for each ... in ... do"] += 1
                elif t.text == "for":
                    u.constructs["for x from a to b do"] += 1
                continue
            if prev is not None and prev.text == ".":
                u.constructs["member access a.b"] += 1
                continue
            if nxt is not None and nxt.text == ":=":
                u.defined.add(t.text)
                u.constructs["assignment :="] += 1
                continue
            if nxt is not None and nxt.text == ":":
                continue                            # named argument or map key
            u.refs[t.text] += 1
            owner = owner_by_line.get(t.line)
            if owner and owner != t.text:
                graph[owner].add(t.text)
            if nxt is not None and nxt.text == "(":
                u.calls[t.text] += 1
            elif nxt is not None and nxt.text == "@" and nxt2 is not None and nxt2.text == "(":
                u.calls[t.text] += 1
                u.partial[t.text] += 1
                u.constructs["partial application f@(...)"] += 1
            if t.text not in u.examples and 0 < t.line <= len(lines):
                u.examples[t.text] = f"{snip.source} :: {snip.path} :: {lines[t.line - 1].strip()[:110]}"
    return u, graph


def reachable(roots: set[str], graph: dict[str, set[str]]) -> set[str]:
    seen, todo = set(), list(roots)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(graph.get(name, ()))
    return seen


# ------------------------------------------------------------------ report

def style_info(nodes: list[Node]) -> dict[str, str]:
    keys = ["short name", "full name", "installer group", "card width", "card height", "card dpi"]
    return {k: next((n.value for n in nodes if n.key == k), "") for k in keys}


def table(rows: list[tuple], headers: tuple) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "resources" / "mse_packages"

    game_nodes, game_stats = read_file(root / "magic.mse-game" / "game", root)
    game_snips = scripts_in(game_nodes, "magic.mse-game")

    style_nodes: dict[str, list[Node]] = {}
    style_snips: dict[str, list[Snippet]] = {}
    font_snips: list[Snippet] = []
    fonts_seen: set[str] = set()
    unresolved = list(game_stats.unresolved)
    for name in STYLES:
        nodes, stats = read_file(root / f"{name}.mse-style" / "style", root)
        unresolved += stats.unresolved
        style_nodes[name] = nodes
        style_snips[name] = scripts_in(nodes, name)
        for font in symbol_font_deps(nodes):
            if font not in fonts_seen and (root / font / "symbol-font").is_file():
                fonts_seen.add(font)
                fnodes, _ = read_file(root / font / "symbol-font", root)
                font_snips += scripts_in(fnodes, font)

    all_snips = game_snips + font_snips + [s for v in style_snips.values() for s in v]
    total, graph = analyse(all_snips)
    builtins = {name for name in total.calls if name not in total.defined and name not in CONTEXT_NAMES}
    keyword_count = sum(1 for n in game_nodes if n.key == "keyword")
    game_defined = analyse(game_snips)[0].defined

    per_style = {}
    for name in STYLES:
        su, _ = analyse(style_snips[name])
        reached = reachable(set(su.refs), graph)
        per_style[name] = {
            "info": style_info(style_nodes[name]),
            "snippets": len(style_snips[name]),
            "script_lines": sum(s.text.count("\n") + 1 for s in style_snips[name]),
            "builtins_direct": sorted(builtins & set(su.calls)),
            "builtins_reachable": sorted(builtins & reached),
            "game_functions_reachable": len(game_defined & reached),
            "constructs": dict(su.constructs),
        }

    m15_builtins = set(per_style["magic-m15-altered"]["builtins_reachable"])
    for name in STYLES[1:]:
        own = set(per_style[name]["builtins_reachable"])
        per_style[name]["builtins_not_needed_by_m15"] = sorted(own - m15_builtins)

    m15_keys = key_paths(style_nodes["magic-m15-altered"])

    # ---- JSON
    docs = REPO / "docs"
    docs.mkdir(exist_ok=True)
    data = {
        "snippet_counts": {"game": len(game_snips), "symbol_fonts": len(font_snips),
                           **{k: len(v) for k, v in style_snips.items()}},
        "builtin_calls": dict(Counter({b: total.calls[b] for b in builtins}).most_common()),
        "builtin_partial_application": dict(Counter({b: total.partial[b] for b in builtins if total.partial[b]}).most_common()),
        "keywords": dict(total.keywords.most_common()),
        "operators": dict(total.ops.most_common()),
        "constructs": dict(total.constructs.most_common()),
        "context_variables": dict(Counter({v: c for v, c in total.refs.items()
                                           if v not in total.defined and v not in total.calls}).most_common(40)),
        "per_style": per_style,
        "m15_style_key_paths": dict(m15_keys.most_common()),
        "unresolved_includes": unresolved,
    }
    (docs / "script_survey.json").write_text(json.dumps(data, indent=1), encoding="utf-8")

    # ---- Markdown
    md = ["# MSE script survey", "",
          "Generated by `tools/survey_scripts.py`. Rough lexical scan of every script in "
          "`magic.mse-game` (all files it includes), the symbol fonts our styles depend on, and the "
          f"five target styles ({', '.join(STYLES)}), after include expansion. Counts are approximate.", "",
          "**Built-in** = called as `f(...)` or `f@(...)` but never defined with `:=` anywhere in the "
          "corpus, so MSE itself must provide it. **Reachable** = used by a style directly or through "
          "game-script functions it references.", "",
          f"Not scanned: the game's {keyword_count} `keyword` definitions (reminder-text templates such as "
          "`{param1}: Attach to ...`); they matter for the mechanics feature, not rendering.", "",
          "See `docs/interpreter_stages.md` for the build order drawn from this report.", ""]

    md += ["## Snippets scanned", "",
           table([(k, v) for k, v in data["snippet_counts"].items()], ("source", "script snippets")), ""]

    md += ["## Target styles", "",
           table([(n, p["info"]["short name"], p["info"]["full name"], p["info"]["installer group"],
                   f'{p["info"]["card width"]}x{p["info"]["card height"]} @{p["info"]["card dpi"]}',
                   p["snippets"], p["script_lines"], len(p["builtins_reachable"]), p["game_functions_reachable"])
                  for n, p in per_style.items()],
                 ("package", "short name", "full name", "installer group", "size", "snippets",
                  "script lines", "built-ins reachable", "game fns reachable")), ""]

    md += ["## Built-in functions, ranked by call count", "",
           table([(b, c, total.partial[b], "yes" if b in m15_builtins else "",
                   ", ".join(n.removeprefix("magic-") for n in STYLES if b in per_style[n]["builtins_reachable"]),
                   f"`{total.examples.get(b, '')}`")
                  for b, c in Counter({b: total.calls[b] for b in builtins}).most_common()],
                 ("built-in", "calls", "as f@()", "M15 needs", "styles reaching it", "first example")), ""]

    md += ["## Constructs", "", table(list(total.constructs.most_common()), ("construct", "count")), "",
           "### Keywords", "", table(list(total.keywords.most_common()), ("keyword", "count")), "",
           "### Operators", "", table(list(total.ops.most_common()), ("operator", "count")), ""]

    md += ["## Context variables (referenced, never defined or called)", "",
           "These are mostly what the interpreter's environment must provide (`card`, `styling`, "
           "`input`, ...), plus loop variables and regex groups the rough scan can't tell apart.", "",
           table(list(data["context_variables"].items()), ("name", "refs")), ""]

    md += ["## Retro styles vs M15", ""]
    for name in STYLES[1:]:
        extra = per_style[name]["builtins_not_needed_by_m15"]
        md.append(f"- **{name}**: {len(per_style[name]['builtins_reachable'])} built-ins reachable; "
                  f"not needed by M15: {', '.join(extra) if extra else 'none'}")
    md += ["", "## M15 Main style: most common key paths (schema layer input)", "",
           table(list(m15_keys.most_common(60)), ("key path", "count")), ""]
    if unresolved:
        md += ["## Unresolved includes", ""] + [f"- {u}" for u in sorted(set(unresolved))] + [""]

    (docs / "script_survey.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(all_snips)} snippets, {len(builtins)} built-ins, "
          f"M15 reaches {len(m15_builtins)}. Wrote docs/script_survey.md and .json")


if __name__ == "__main__":
    main()
