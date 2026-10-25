"""English helpers: english_number (and _a, _multiple, _ordinal), english_singular,
process_english_hints.

Numbers 0-99 become words; anything else is left as digits, and text that isn't a
number is returned unchanged ("X" stays "X").

Keyword reminder text passes parameters as "<param-number>2</param-number>". Then only
the inside is converted, and a <hint-1> (the number is 1) or <hint-2> (anything else)
is put in front, so process_english_hints can later pick "card" or "cards" from
"card(s)".
"""
from __future__ import annotations

import re
from typing import Callable

from ..values import to_str
from .registry import builtin

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORDINAL_ONES = ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
                "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
                "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth"]
PARAM_OPEN = re.compile(r"^<param-[^>]*>")
VOWELS = "aeiouAEIOU"


def _as_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def number_words(n: int) -> str:
    if 0 <= n < 20:
        return ONES[n]
    if 20 <= n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] + (f"-{ONES[ones]}" if ones else "")
    return str(n)


def ordinal_words(n: int) -> str:
    if 0 < n < 20:
        return ORDINAL_ONES[n]
    if 20 <= n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return TENS[tens][:-1] + "ieth"             # twenty -> twentieth
        return f"{TENS[tens]}-{ORDINAL_ONES[ones]}"
    return f"{n}th"


def _param_parts(text: str) -> tuple[int, int] | None:
    """(start, end) of the contents of a leading <param-...> tag, or None."""
    m = PARAM_OPEN.match(text)
    if not m:
        return None
    end = text.find("<", m.end())
    return m.end(), (len(text) if end < 0 else end)


def english_num(input: object, fun: Callable[[int], str]) -> str:
    """Apply a number -> words function, with hints for keyword parameters."""
    text = to_str(input)
    parts = _param_parts(text)
    if parts is None:
        n = _as_int(text)
        return text if n is None else fun(n)
    start, end = parts
    n = _as_int(text[start:end])
    if n is None:
        return "<hint-2>" + text
    return ("<hint-1>" if n == 1 else "<hint-2>") + text[:start] + fun(n) + text[end:]


def english_text(input: object, fun: Callable[[str], str]) -> str:
    """Apply a word function to the input, or to the inside of a <param-...> tag."""
    text = to_str(input)
    parts = _param_parts(text)
    if parts is None:
        return fun(text)
    start, end = parts
    return text[:start] + fun(text[start:end]) + text[end:]


@builtin("english_number")
def english_number(input):
    return english_num(input, number_words)


@builtin("english_number_a")
def english_number_a(input):
    """Like english_number, but 1 is "a" ("a card", "two cards")."""
    return english_num(input, lambda n: "a" if n == 1 else number_words(n))


@builtin("english_number_multiple")
def english_number_multiple(input):
    """Like english_number, but 1 is "" ("a card" -> "card", "two cards")."""
    return english_num(input, lambda n: "" if n == 1 else number_words(n))


@builtin("english_number_ordinal")
def english_number_ordinal(input):
    return english_num(input, ordinal_words)


def singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("oes", "ches", "shes", "sses")):
        return word[:-2]
    if word.endswith(("lves", "rves")):
        return word[:-3] + "f"
    if word.endswith("s"):
        return word[:-1]
    if word.endswith("men"):
        return word[:-3] + "man"
    return word


@builtin("english_singular")
def english_singular(input):
    return english_text(input, singular)


@builtin("process_english_hints")
def process_english_hints(input):
    """Resolve the hints left by english_number & co:
      <hint-1> (singular) / <hint-2> (plural) choose for the next "(...)": singular drops
          it, plural keeps its contents ("card(s)" -> "card" / "cards");
      <singular>x</singular> is kept only when singular, <plural>x</plural> only when plural;
      "a" becomes "an" before a parameter starting with a vowel;
      a space before an empty parameter is dropped."""
    s, out, i, mode = to_str(input), [], 0, 0      # mode: 0 none, 1 singular, 2 plural
    while i < len(s):
        c = s[i]
        if c == "<":
            end = s.find(">", i)
            end = len(s) - 1 if end < 0 else end
            tag = s[i:end + 1]
            after = end + 1
            if tag.startswith("<hint-"):
                mode = int(tag[6]) if tag[6:7].isdigit() else 0
                i = after
                continue
            if tag.startswith(("<singular>", "<plural>")):
                name = tag[1:-1]
                close = s.find(f"</{name}>", after)
                close = len(s) if close < 0 else close
                keep = mode == 1 if name == "singular" else mode == 2
                if keep:
                    out.append(s[after:close])
                if name == "plural":
                    mode = 0
                i = close + len(f"</{name}>")
                continue
            if tag.startswith("<param-"):
                text = "".join(out)
                content_end = s.find("<", after)
                content = s[after:content_end if content_end >= 0 else len(s)]
                if content and content[0] in VOWELS and re.search(r"(^|\s)[aA] $", text):
                    out = [text[:-1] + "n "]            # "a " -> "an "
                elif content == "" and text.endswith(" "):
                    out = [text[:-1]]
                if mode == 1 and s.startswith("a</param-", after):
                    close_end = s.find(">", after) + 1
                    rest = s[close_end:].lstrip(" ")
                    if rest[:1] in tuple(VOWELS):
                        out.append(tag + "an")
                        i = after + 1
                        continue
            out.append(tag)
            i = after
            continue
        if c == "(" and mode != 0:
            close = s.find(")", i)
            close = len(s) if close < 0 else close
            if mode == 2:
                out.append(s[i + 1:close])
            mode = 0
            i = close + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)
