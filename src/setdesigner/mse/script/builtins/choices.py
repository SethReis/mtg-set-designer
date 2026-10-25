"""Multiple-choice values: chosen, count_chosen, require_choice, exclusive_choice,
require_exclusive_choice, remove_choice.

A multiple-choice value is a comma-separated list of chosen names, e.g.
"white, blue, hybrid". Results are joined with ", ".

The editing functions take the choices to act on as `choices: "a, b"`, or
`choice: "a"`, or `choice1: "a", choice2: "b", ...`. MSE also uses `last_change`
(what the user just clicked) to decide which choice to keep; we have no live
editor, so the first listed choice wins instead.
"""
from __future__ import annotations

from ..values import ScriptError, to_str
from .registry import builtin


def split_choices(value: object) -> list[str]:
    text = to_str(value)
    return [c.strip() for c in text.split(",") if c.strip()] if text.strip() else []


def join_choices(chosen: list[str]) -> str:
    return ", ".join(chosen)


def choices_param(script) -> list[str]:
    """The choices to act on, from `choices`, `choice` or `choice1`, `choice2`, ..."""
    if script.var("choices") is not None:
        return split_choices(script.var("choices"))
    if script.var("choice") is not None:
        return [to_str(script.var("choice"))]
    out, i = [], 1
    while script.var(f"choice{i}") is not None:
        out.append(to_str(script.var(f"choice{i}")))
        i += 1
    if not out:
        raise ScriptError("expected a 'choices', 'choice' or 'choice1' argument")
    return out


@builtin("chosen")
def chosen(input, choice):
    return to_str(choice) in split_choices(input)


@builtin("count_chosen")
def count_chosen(input, choices=None):
    """How many of `choices` are chosen; without `choices`, how many are chosen at all."""
    if choices is None:
        text = to_str(input)
        return 0 if text == "" else 1 + text.count(",")
    selected = split_choices(input)
    return sum(1 for c in split_choices(choices) if c in selected)


@builtin("remove_choice")
def remove_choice(input, script):
    listed = choices_param(script)
    return join_choices([c for c in split_choices(input) if c not in listed])


def _keep(input, listed: list[str], at_least: int, at_most: int) -> str:
    selected = split_choices(input)
    on = [c for c in listed if c in selected]          # in the order they are listed
    if len(on) < at_least:
        selected.append(listed[0])
    elif len(on) > at_most:
        drop = set(on[at_most:])
        selected = [c for c in selected if c not in drop]
    return join_choices(selected)


@builtin("require_choice")
def require_choice(input, script):
    """At least one of the listed choices is chosen (the first is added if none is)."""
    listed = choices_param(script)
    return _keep(input, listed, 1, len(listed))


@builtin("exclusive_choice")
def exclusive_choice(input, script):
    """At most one of the listed choices is chosen."""
    return _keep(input, choices_param(script), 0, 1)


@builtin("require_exclusive_choice")
def require_exclusive_choice(input, script):
    """Exactly one of the listed choices is chosen."""
    return _keep(input, choices_param(script), 1, 1)
