"""Tagged text: remove_tags, remove_tag, tag_contents, to_text.

MSE text values carry markup tags such as <sym>{T}</sym>, <soft>, <atom-sep> and
<word-list-type>. A literal `<` that is not a tag is stored as ESCAPED_LANGLE.
"""
from __future__ import annotations

import re

from ..tokens import ESCAPED_LANGLE
from ..values import to_str
from .registry import builtin

TAG = re.compile(r"<[^>]*>?")


def strip_tags(text: str) -> str:
    return TAG.sub("", text)


@builtin("remove_tags")
def remove_tags(input):
    """All tags removed. Escaped `<` characters stay escaped."""
    return strip_tags(to_str(input))


@builtin("remove_tag")
def remove_tag(input, tag):
    """Remove the tags starting with `tag` (e.g. "<word-list"), and their close tags,
    keeping what is between them."""
    prefix = to_str(tag)
    close_prefix = "</" + prefix[1:]
    return TAG.sub(lambda m: "" if m.group(0).startswith((prefix, close_prefix)) else m.group(0),
                   to_str(input))


@builtin("to_text")
def to_text(input):
    """Plain text: tags removed and escaped `<` turned back into `<`."""
    return strip_tags(to_str(input)).replace(ESCAPED_LANGLE, "<")


def find_close_tag(text: str, open_tag: str, start: int) -> int:
    """Index of the close tag matching `open_tag` (which ends at `start`), allowing
    nested tags of the same name; -1 if it is never closed."""
    name = open_tag[1:-1]
    close = f"</{name}>"
    depth = 1
    for m in TAG.finditer(text, start):
        if m.group(0) == open_tag:
            depth += 1
        elif m.group(0) == close:
            depth -= 1
            if depth == 0:
                return m.start()
    return -1


@builtin("tag_contents")
def tag_contents(input, tag, contents, script):
    """Replace what is inside each tag starting with `tag` by contents(input: old).
    An unclosed tag stops processing (the rest of the text is dropped, as in MSE)."""
    text, prefix = to_str(input), to_str(tag)
    out, pos = [], 0
    while True:
        start = text.find(prefix, pos)
        if start < 0:
            out.append(text[pos:])
            break
        tag_end = text.find(">", start)
        if tag_end < 0:
            break
        open_tag = text[start:tag_end + 1]
        close_at = find_close_tag(text, open_tag, tag_end + 1)
        if close_at < 0:
            break
        out.append(text[pos:tag_end + 1])
        out.append(to_str(script.call(contents, input=text[tag_end + 1:close_at])))
        pos = close_at
    return "".join(out)
