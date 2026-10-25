"""Plain string functions: case, trim, substring, contains, reverse, sort_text, regex_escape."""
from __future__ import annotations

import re

from ..spec_sort import sort_spec
from ..values import to_int, to_str
from .registry import builtin


@builtin("to_upper")
def to_upper(input):
    return to_str(input).upper()


@builtin("to_lower")
def to_lower(input):
    return to_str(input).lower()


@builtin("to_title")
def to_title(input):
    """Lower case, then capitalise the first letter of each word."""
    return re.sub(r"(^|\s)(\S)", lambda m: m.group(1) + m.group(2).upper(), to_str(input).lower())


@builtin("reverse")
def reverse(input):
    return to_str(input)[::-1]


@builtin("trim")
def trim(input):
    return to_str(input).strip()


@builtin("substring")
def substring(input, begin=0, end=None):
    """Characters begin..end-1; negative bounds count as 0."""
    text = to_str(input)
    start = max(0, to_int(begin))
    stop = len(text) if end is None else max(0, to_int(end))
    return text[start:stop] if start < stop else ""


@builtin("contains")
def contains(input, match):
    return to_str(match) in to_str(input)


@builtin("sort_text")
def sort_text(input, order=None):
    """Without order: the characters sorted. With order: see spec_sort.py."""
    text = to_str(input)
    if order is None:
        return "".join(sorted(text))
    return sort_spec(to_str(order), text)


@builtin("regex_escape")
def regex_escape(input):
    return re.sub(r"([\\^$.|?*+()\[\]{}])", r"\\\1", to_str(input))


@builtin("curly_quotes")
def curly_quotes(input):
    """Straight quotes to curly ones: a quote opens at the start, after whitespace,
    a bracket or a tag (`>`), and closes otherwise (so "don't" gets an apostrophe)."""
    text, out = to_str(input), []
    for i, c in enumerate(text):
        if c in "'\"":
            prev = text[i - 1] if i else ""
            opening = prev == "" or prev.isspace() or prev in "([{>"
            c = ("‘" if opening else "’") if c == "'" else ("“" if opening else "”")
        out.append(c)
    return "".join(out)


@builtin("trace")
def trace(input, script):
    script.warn(f"Trace: {to_str(input)}")
    return input
