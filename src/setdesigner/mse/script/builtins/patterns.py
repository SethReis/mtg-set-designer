"""Regular-expression functions: match, filter_text, break_text, split_text, replace.

MSE uses boost::regex with Perl syntax. The `regex` package is close enough and,
unlike Python's `re`, supports POSIX classes such as `[[:space:]]`. Boost's
defaults (checked with the MSE oracle): `^`/`$` match at line breaks and `.`
matches a newline, hence MULTILINE | DOTALL.

`in_context`: a match only counts if the context regex matches the whole input
with that match replaced by the text "<match>", e.g. in_context: "^<match>" for a
match at the start.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator

import regex

from ..values import ScriptError, is_function, to_str
from .registry import builtin

MAX_RECURSION = 20


@lru_cache(maxsize=1024)
def compile_regex(pattern: str) -> regex.Pattern:
    try:
        return regex.compile(pattern, regex.MULTILINE | regex.DOTALL)
    except regex.error as e:
        raise ScriptError(f"Error in regular expression {pattern!r}: {e}") from None


def find_matches(text: str, match: object, in_context: object = None) -> Iterator[regex.Match]:
    rx = compile_regex(to_str(match))
    context = compile_regex(to_str(in_context)) if in_context is not None else None
    for m in rx.finditer(text):
        if context is None or context.search(text[:m.start()] + "<match>" + text[m.end():]):
            yield m


def expand_sed(template: str, m: regex.Match) -> str:
    """Boost's sed-style replacement: \\1 = group 1, & = the whole match,
    a backslash before anything else makes it literal (\\& is a plain &)."""
    out, i = [], 0
    while i < len(template):
        c = template[i]
        if c == "\\" and i + 1 < len(template):
            nxt = template[i + 1]
            if nxt.isdigit():
                group = int(nxt)
                out.append((m.group(group) or "") if group <= len(m.groups()) else "")
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(m.group(0) if c == "&" else c)
        i += 1
    return "".join(out)


@builtin("match", "match_text")
def match_text(input, match):
    """Does the regex match anywhere in the input?"""
    return compile_regex(to_str(match)).search(to_str(input)) is not None


@builtin("filter_text")
def filter_text(input, match, in_context=None):
    """All matches, joined together."""
    return "".join(m.group(0) for m in find_matches(to_str(input), match, in_context))


@builtin("break_text")
def break_text(input, match, in_context=None):
    """All matches, as a list."""
    return [m.group(0) for m in find_matches(to_str(input), match, in_context)]


@builtin("split_text")
def split_text(input, match, include_empty=True):
    """The pieces between matches."""
    text = to_str(input)
    pieces, start = [], 0
    for m in compile_regex(to_str(match)).finditer(text):
        pieces.append(text[start:m.start()])
        start = m.end()
    pieces.append(text[start:])
    if not include_empty:
        pieces = [p for p in pieces if p]
    return pieces


@builtin("replace", "replace_text")
def replace_text(input, match, replace, script, in_context=None, recursive=False):
    """Replace each match. `replace` is a sed-style string (\\1, &) or a function,
    called with input = the match and _1, _2, ... = its groups (missing groups are "").
    With recursive: true, each replacement is itself rescanned (up to 20 levels)."""
    return _replace(to_str(input), match, replace, script, in_context,
                    MAX_RECURSION if recursive else 0)


def _replace(text: str, match, replace, script, in_context, depth: int) -> str:
    out, last = [], 0
    for m in find_matches(text, match, in_context):
        out.append(text[last:m.start()])
        if is_function(replace):
            groups = {f"_{i}": g or "" for i, g in enumerate(m.groups(), 1)}
            new = to_str(script.call(replace, input=m.group(0), **groups))
        else:
            new = expand_sed(to_str(replace), m)
        if depth > 0 and new != m.group(0):
            new = _replace(new, match, replace, script, in_context, depth - 1)
        out.append(new)
        last = m.end()
    out.append(text[last:])
    return "".join(out)
