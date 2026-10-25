"""MSE's `sort_text(order: ...)` mini-language, ported from src/util/spec_sort.cpp.

An order spec lists which characters to keep and in what order; characters it
doesn't mention are dropped. Spaces in the spec are ignored.

    X              all X's from the input
    \\X            a literal X (for characters with a special meaning)
    <WUBRG>        each of W, U, B, R, G at most once         (also once(...))
    [0123456789]   these characters, in their input order       (also mixed(...))
    (WUBRG)        these characters, rotated around the color wheel so the
                   result is "tightest", e.g. GW -> "GW", RWB -> "WBR" (also cycle(...))
    ordered(abc)   same as plain abc
    any()          everything not yet taken, in input order
    in_place(s)    sort what s matches, but leave other characters where they are
    pattern(./. s) for each window matching the pattern (. = any char), sort the
                   `.` characters with s, e.g. "U/W" -> "W/U"
    compound(ab)   occurrences of the string ab
    reverse_order(a b c)  sort with a, b, c in turn, then output in reverse

This is a faithful port, including two quirks of the original (noted inline).
"""
from __future__ import annotations

REMOVED = "\0"           # marks an input character that has been taken
PLACEHOLDER = "\3"       # a `.` in a pattern(...)


class SpecError(Exception):
    pass


class _SpecIterator:
    def __init__(self, spec: str):
        self.spec = spec
        self.pos = 0
        self.value = ""
        self.value_pos = 0
        self.escaped = False

    def next_until(self, close: str | None, skip_space: bool = True) -> bool:
        """Read the next character into self.value. Returns False at an unescaped
        `close` (or at the end of the spec when close is None)."""
        spec = self.spec
        while True:
            if self.pos >= len(spec):
                if close is None:
                    return False
                raise SpecError(f"expected '{close}' in sort specification {spec!r}")
            c = spec[self.pos]
            if c == " " and skip_space:
                self.pos += 1
                continue
            break
        self.value_pos = self.pos
        self.pos += 1
        if c == "\\":
            if self.pos >= len(spec):
                raise SpecError(f"backslash at end of sort specification {spec!r}")
            self.value, self.escaped = spec[self.pos], True
            self.pos += 1
            return True
        self.value, self.escaped = c, False
        return c != close

    def keyword(self, word: str) -> bool:
        """Does the current character start `word`? If so, skip past it."""
        if not self.escaped and self.spec.startswith(word, self.value_pos):
            self.pos = self.value_pos + len(word)
            return True
        return False

    def read_param(self, close: str) -> str:
        out = []
        while self.next_until(close):
            out.append(self.value)
        return "".join(out)

    def read_raw(self, close1: str, close2: str | None = None) -> str:
        """Raw text up to an unescaped close1/close2 at parenthesis depth 0
        (escapes are kept, spaces are not skipped). The closer goes in self.value."""
        spec, out, depth = self.spec, [], 0
        while self.pos < len(spec):
            c = spec[self.pos]
            self.pos += 1
            if c == "\\" and self.pos < len(spec):
                out.append(c + spec[self.pos])
                self.pos += 1
                continue
            if depth == 0 and (c == close1 or c == close2):
                self.value = c
                return "".join(out)
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            out.append(c)
        return "".join(out)


def _take_all(inp: list[str], ret: list[str], c: str) -> int:
    count = 0
    for i, x in enumerate(inp):
        if x == c:
            inp[i] = REMOVED
            count += 1
    ret.extend([c] * count)
    return count


def _take_once(inp: list[str], ret: list[str], c: str) -> None:
    if c in inp:
        del inp[inp.index(c)]
        ret.append(c)


def _mixed(inp: list[str], ret: list[str], chars: str) -> None:
    for i, x in enumerate(inp):
        if x != REMOVED and x in chars:
            ret.append(x)
            inp[i] = REMOVED


def _compound(inp: list[str], ret: list[str], s: str) -> None:
    i = 0
    while i < len(inp):
        if i + len(s) <= len(inp) and inp[i:i + len(s)] == list(s):
            i += len(s) - 1
            ret.extend(s)
            inp[i] = REMOVED            # quirk: only the last character is marked taken
        i += 1


def _cycle(inp: list[str], ret: list[str], spec: str) -> None:
    counts = [_take_all(inp, [], c) for c in spec]
    n = len(spec)
    best_start, best_score = 0, 0xFFFFFFFF
    for start in range(n):
        score, mul = 0, 1
        for i in range(n):
            mul *= 2
            if counts[(start + i) % n]:
                score = score * mul + 1
                mul = 1
        if score < best_score:
            best_score, best_start = score, start
    for i in range(n):
        pos = (best_start + i) % n
        ret.extend([spec[pos]] * counts[pos])


def _pattern(pattern: str, sub: str, inp: list[str], ret: list[str]) -> None:
    n = len(pattern)
    if n > len(inp):
        return
    end = len(inp) - n + 1
    pos = pos_new = 0
    while pos < end:
        placeholders, ok = [], True
        for j in range(n):
            c, p = inp[pos + j], pattern[j]
            if c == REMOVED:
                ok = False
                break
            if p == PLACEHOLDER:
                placeholders.append(c)
            elif c != p:
                ok = False
                break
        if ok:
            new = sort_spec(sub, "".join(placeholders))
            if len(new) == len(placeholders):
                k = 0
                for p in pattern:
                    if p == PLACEHOLDER:
                        ret.append(new[k])
                        k += 1
                    else:
                        ret.append(p)
                pos += n
                continue
        inp[pos_new] = inp[pos]
        pos_new += 1
        pos += 1
    del inp[pos_new:]                   # quirk: the last n-1 characters are dropped


def _in_place(sub: str, inp: list[str], ret: list[str]) -> None:
    result: list[str] = []
    _spec_sort(sub, inp, result)
    r = 0
    for c in inp:
        if c == REMOVED:
            if r < len(result):
                ret.append(result[r])
                r += 1
        else:
            ret.append(c)
    inp.clear()


def _spec_sort(spec: str, inp: list[str], ret: list[str]) -> None:
    it = _SpecIterator(spec)
    while it.next_until(None):
        v = it.value
        if it.escaped:
            _take_all(inp, ret, v)
        elif v == "<":
            while it.next_until(">"):
                _take_once(inp, ret, it.value)
        elif it.keyword("once("):
            while it.next_until(")"):
                _take_once(inp, ret, it.value)
        elif v == "[":
            _mixed(inp, ret, it.read_param("]"))
        elif it.keyword("mixed("):
            _mixed(inp, ret, it.read_param(")"))
        elif it.keyword("cycle("):
            _cycle(inp, ret, it.read_param(")"))
        elif v == "(":
            _cycle(inp, ret, it.read_param(")"))
        elif it.keyword("compound("):
            _compound(inp, ret, it.read_param(")"))
        elif it.keyword("pattern("):
            pattern = []
            while it.next_until(" ", skip_space=False):
                pattern.append(PLACEHOLDER if it.value == "." and not it.escaped else it.value)
            _pattern("".join(pattern), it.read_raw(")"), inp, ret)
        elif it.keyword("in_place("):
            _in_place(it.read_raw(")"), inp, ret)
        elif it.keyword("any()"):
            ret.extend(c for c in inp if c != REMOVED)
            inp.clear()
        elif it.keyword("reverse_order("):
            parts = []
            while it.value != ")":
                if it.pos >= len(it.spec):      # the original loops forever here
                    raise SpecError(f"expected ')' in sort specification {spec!r}")
                part: list[str] = []
                _spec_sort(it.read_raw(")", " "), inp, part)
                parts.append(part)
            for part in reversed(parts):
                ret.extend(part)
        elif it.keyword("ordered("):
            while it.next_until(")"):
                _take_all(inp, ret, it.value)
        else:
            _take_all(inp, ret, v)


def sort_spec(spec: str, text: str) -> str:
    """Sort `text` by the order specification `spec` (see module docstring)."""
    ret: list[str] = []
    _spec_sort(spec, list(text), ret)
    return "".join(ret)
