"""Editor helpers used by field scripts: combined_editor (forward_editor), check_spelling.

In MSE, combined_editor also lets the user edit the combined field and writes the
parts back into field1, field2, ...; we only need the reading half, which builds
the combined value (e.g. the type line from super type + sub type).
"""
from __future__ import annotations

from ..values import to_bool, to_str
from .registry import builtin
from .tags import strip_tags


def _numbered(script, name: str) -> list[object]:
    """`name` or name1, name2, ... (e.g. field1, field2)."""
    values, i = [], 1
    while script.var(f"{name}{i}") is not None:
        values.append(script.var(f"{name}{i}"))
        i += 1
    if not values and script.var(name) is not None:
        values.append(script.var(name))
    return values


@builtin("combined_editor", "forward_editor")
def combined_editor(script, prefix=None, suffix=None, hide_when_empty=False, soft_before_empty=False):
    """field1 <sep>separator</sep> field2 ... A part that is "" is left out with its
    separator (hide_when_empty); a part with no visible text gets a soft separator
    (soft_before_empty)."""
    parts = [to_str(v) for v in _numbered(script, "field")]
    separators = [to_str(v) for v in _numbered(script, "separator")]
    if script.var("separator") is not None and not script.var("separator1"):
        separators = [to_str(script.var("separator"))] * max(0, len(parts) - 1)
    hide, soft = to_bool(hide_when_empty), to_bool(soft_before_empty)

    out = parts[0] if parts else ""
    for i, part in enumerate(parts[1:]):
        sep = separators[i] if i < len(separators) else ""
        if hide and part == "":
            continue
        tag = "sep-soft" if soft and strip_tags(part) == "" else "sep"
        out += f"<{tag}>{sep}</{tag}>{part}"
    if prefix is not None:
        out = f"<prefix>{to_str(prefix)}</prefix>{out}"
    if suffix is not None:
        out = f"{out}<suffix>{to_str(suffix)}</suffix>"
    return out


@builtin("is_default")
def is_default(input):
    """Whether a field value is still its default (not typed by the user). Fields we
    map from our model never override scripted defaults such as card color, so this
    is always true here."""
    return True


@builtin("check_spelling")
def check_spelling(input):
    """MSE marks misspelled words with <error-spelling> tags; we don't spellcheck."""
    return input
