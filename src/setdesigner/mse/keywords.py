"""MSE keyword expansion (a port of src/data/keyword.cpp in MagicSetEditor2).

A keyword such as Cycling is defined by
    match:    "Cycling <atom-param>cost</atom-param>"   literal text and parameters
    reminder: "{param1}, Discard this card: Draw a card."  a template
    mode:     core / expert / pseudo / action / old / custom
and each parameter type (cost, number, ...) by a regex plus optional separators and
scripts. `expand()` finds keywords in tagged rules text and replaces each with
    <kw-X> combine(...) </kw-X>
where X records whether its reminder text is shown: 1/0 = forced on/off (kept from
earlier <kw-1>/<kw-0> tags in the text), A/a = on/off by default (`default_expand`).
The game supplies `condition`, `default_expand` and `combine` as script functions
(see its text_filter), so the exact output format is the game's.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property

import regex

from .reader import MSEReadError, Node
from .script import ast as A
from .script.parser import parse, parse_template
from .script.values import ScriptError, ScriptFunction, to_bool, to_str

TAG = re.compile(r"<[^>]*>")
KW_TAG = re.compile(r"</?kw-[^>]*>")


# ---------------------------------------------------------------- definitions

def make_non_capturing(pattern: str) -> str:
    """Turn capturing groups "(" into "(?:" (escapes and classes respected)."""
    out, i, in_class = [], 0, False
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            out.append(pattern[i:i + 2])
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "(" and pattern[i + 1:i + 2] != "?":
            out.append("(?:")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


@dataclass
class ParamType:
    name: str
    match: str
    separator_before: str = ""          # regex
    separator_after: str = ""           # regex
    optional: bool = True
    eat_separator: bool = True
    placeholder: str = ""
    script: A.Node | None = None            # applied to the tagged value (input)
    reminder_script: A.Node | None = None   # applied to the untagged value (input)
    separator_script: A.Node | None = None  # applied to separators

    @classmethod
    def from_node(cls, node: Node) -> "ParamType":
        children = node.children()
        get = {c.key: c for c in reversed(children)}
        text = lambda key: get[key].text() if key in get else ""
        script = lambda key: parse(get[key].text()) if key in get and get[key].text().strip() else None
        return cls(name=text("name"), match=text("match"),
                   separator_before=text("separator before is"),
                   separator_after=text("separator after is"),
                   optional=text("optional") != "false",
                   eat_separator=text("eat separator") != "false",
                   placeholder=text("placeholder"),
                   script=script("script"), reminder_script=script("reminder script"),
                   separator_script=script("separator script"))

    def strip_before(self, value: str) -> tuple[str, str]:
        """(separator, rest) for a separator at the start of value."""
        if self.separator_before:
            m = regex.match(self.separator_before, value)
            if m:
                return m.group(0), value[m.end():]
        return "", value

    def strip_after(self, value: str) -> tuple[str, str]:
        """(rest, separator) for a separator at the end of value."""
        if self.separator_after:
            m = regex.search("(?:" + self.separator_after + ")$", value)
            if m:
                return value[:m.start()], m.group(0)
        return value, ""


@dataclass
class KeywordDef:
    keyword: str
    match: str
    reminder: A.Node | None
    mode: str
    param_types: dict[str, ParamType]
    from_game: bool = True
    literals: list[str] = field(default_factory=list)       # len(params) + 1
    params: list[ParamType] = field(default_factory=list)
    regex: regex.Pattern | None = None
    valid: bool = True

    def __post_init__(self) -> None:
        self.prepare()

    @property
    def fixed(self) -> bool:
        """Plain keywords (no parameters) are tried after those with parameters."""
        return not self.params

    def prepare(self) -> None:
        """Build the regex: literal groups and parameter groups alternate."""
        parts = re.split(r"<atom-param>(.*?)</atom-param>", self.match)
        texts, names = parts[0::2], parts[1::2]
        pattern, text = "", texts[0]
        for name, next_text in zip(names, texts[1:]):
            param = self.param_types.get(name)
            if param is None:
                self.valid = False
                return
            if param.eat_separator and param.separator_before:
                m = regex.search("(?:" + param.separator_before + ")$", text)
                if m:
                    text = text[:m.start()]
            self.literals.append(text)
            self.params.append(param)
            pattern += "(" + regex.escape(text) + ")"
            pattern += "(" + make_non_capturing(param.match) + ")" + ("?" if param.optional else "")
            text = next_text
            if param.eat_separator and param.separator_after:
                m = regex.match(param.separator_after, text)
                if m:
                    text = text[m.end():]
        self.literals.append(text)
        pattern += "(" + regex.escape(text) + ")"
        try:
            self.regex = regex.compile(r"(?<![\w])" + pattern + r"(?=$|[^a-zA-Z0-9\(])",
                                       regex.IGNORECASE)
        except regex.error:
            self.valid = False
            return
        self.valid = not self.regex.match("")


@dataclass
class KeywordDatabase:
    keywords: list[KeywordDef]
    param_types: dict[str, ParamType]

    @classmethod
    def from_nodes(cls, nodes: list[Node]) -> "KeywordDatabase":
        """Keywords and parameter types from a game file's top-level nodes."""
        param_types = {}
        for node in nodes:
            if node.key == "keyword parameter type":
                pt = ParamType.from_node(node)
                param_types[pt.name] = pt
        db = cls([], param_types)
        for node in nodes:
            if node.key == "keyword":
                db.add(_node_values(node), from_game=True)
        return db

    def add(self, values: dict[str, str], from_game: bool = False) -> KeywordDef:
        reminder = values.get("reminder", "")
        kw = KeywordDef(keyword=values.get("keyword", ""), match=values.get("match", ""),
                        reminder=parse_template(reminder) if reminder else None,
                        mode=values.get("mode", "custom") or "custom",
                        param_types=self.param_types, from_game=from_game)
        self.keywords.append(kw)
        return kw

    @cached_property
    def valid_keywords(self) -> list[KeywordDef]:
        return [k for k in self.keywords if k.valid and k.regex is not None]


def _node_values(node: Node) -> dict[str, str]:
    try:
        return {c.key: c.text() for c in node.children()}
    except MSEReadError:
        return {}


# ------------------------------------------------------------- param values

class KeywordParamValue:
    """A matched keyword parameter, as scripts see it (param1, param2, ...)."""
    type_label = "keyword parameter"

    def __init__(self, type_name: str, value: str, separator_before: str, separator_after: str,
                 param: str):
        self.type_name = type_name
        self.value = value
        self.separator_before = separator_before
        self.separator_after = separator_after
        self.param = param

    def script_member(self, name: object) -> object:
        key = to_str(name).replace(" ", "_")
        if key == "type":
            return self.type_name
        if key in ("value", "separator_before", "separator_after", "param"):
            return getattr(self, key)
        from .script.values import ErrorValue
        return ErrorValue(f"keyword parameter has no member '{key}'")

    def script_string(self) -> str:
        slug = re.sub(r"[() ]", "-", self.type_name)
        return f"<param-{slug}>{self.value}</param-{slug}>"


# ------------------------------------------------------------------ text maps

@dataclass
class TaggedText:
    """Tagged text with its untagged characters and where each one sits."""
    tagged: str
    untagged: str = ""
    index: list[int] = field(default_factory=list)      # untagged position -> tagged position

    def __post_init__(self) -> None:
        chars, idx, i, s = [], [], 0, self.tagged
        while i < len(s):
            if s[i] == "<":
                end = s.find(">", i)
                i = len(s) if end < 0 else end + 1
                continue
            chars.append(s[i])
            idx.append(i)
            i += 1
        self.untagged = "".join(chars)
        self.index = idx

    def tagged_slice(self, start: int, end: int) -> str:
        """Tagged text of untagged[start:end], with tags balanced: closing tags just
        after the slice that close tags opened inside it are included, closing tags at
        its start that close earlier tags are left out."""
        if start >= end:
            return ""
        s = self.tagged
        ts, te = self.index[start], self.index[end - 1] + 1
        out = s[ts:te]
        opened = [t[1:].split(">")[0] for t in TAG.findall(out) if not t.startswith("</")]
        closed = [t[2:-1] for t in TAG.findall(out) if t.startswith("</")]
        pending = [name for name in opened if name not in closed]
        while pending:
            m = TAG.match(s, te)
            if not m or not m.group(0).startswith("</"):
                break
            name = m.group(0)[2:-1]
            if name in pending:
                pending.remove(name)
            out += m.group(0)
            te = m.end()
        return out


# ------------------------------------------------------------------- expand

REMOVE_WITH_CONTENT = ("atom-reminder", "atom-keyword", "atom-kwpph")
REMOVE_TAG_ONLY = ("keyword-param", "param-")


def remove_keyword_tags(text: str) -> str:
    """Strip what a previous expansion produced, so expanding again is stable."""
    for name in REMOVE_WITH_CONTENT:
        text = re.sub(rf"<{name}[^>]*>.*?</{name}[^>]*>", "", text, flags=re.DOTALL)
    return re.sub(r"</?(?:keyword-param|param-)[^>]*>", "", text)


@dataclass
class Match:
    keyword: KeywordDef
    start: int
    end: int
    groups: list[tuple[int, int]]        # untagged spans of each group (-1, -1 if absent)


def find_matches(db: KeywordDatabase, text: TaggedText) -> list[Match]:
    found = []
    for kw in db.valid_keywords:
        for m in kw.regex.finditer(text.untagged, overlapped=True):
            groups = [m.span(g) for g in range(1, len(m.groups()) + 1)]
            found.append(Match(kw, m.start(), m.end(), groups))
    found.sort(key=lambda m: (m.start, m.keyword.fixed, -(m.end - m.start), m.keyword.keyword))
    return found


class Expander:
    """One expand_keywords call: the database plus the game's script functions."""

    def __init__(self, db: KeywordDatabase, script, condition=None, default_expand=None,
                 combine=None):
        self.db = db
        self.script = script                # a Caller (see script/evaluator.py)
        self.condition = condition
        self.default_expand = default_expand
        self.combine = combine

    def call(self, func, variables: dict[str, object]) -> object:
        return self.script.call(func, **variables)

    def expand(self, text: str) -> str:
        source = TaggedText(remove_keyword_tags(text))
        if not self.db.valid_keywords:
            return source.tagged
        matches = find_matches(self.db, source)
        s, out = source.tagged, []
        i = upos = atom = 0
        expand_type = "a"
        while i < len(s):
            if s[i] == "<":
                end = s.find(">", i)
                end = len(s) - 1 if end < 0 else end
                tag = s[i:end + 1]
                if tag.startswith("<kw-"):
                    expand_type = tag[4:5] or "a"
                elif tag.startswith("</kw-"):
                    expand_type = "a"
                else:
                    if tag.startswith("<atom"):
                        atom += 1
                    elif tag.startswith("</atom"):
                        atom = max(0, atom - 1)
                    out.append(tag)
                i = end + 1
                continue
            if atom == 0:
                done = self.try_matches(matches, source, upos, expand_type)
                if done is not None:
                    replacement, m = done
                    out.append(replacement)
                    # continue after the matched text (with its closing tags)
                    i += len(source.tagged_slice(m.start, m.end))
                    upos = m.end
                    expand_type = "a"
                    continue
            out.append(s[i])
            i += 1
            upos += 1
        return "".join(out)

    def try_matches(self, matches: list[Match], source: TaggedText, upos: int,
                    expand_type: str) -> tuple[str, Match] | None:
        """The first keyword match at this position whose expansion succeeds."""
        for m in matches:
            if m.start != upos:
                continue
            result = self.expand_match(m, source, expand_type)
            if result is not None:
                return result, m
        return None

    def expand_match(self, m: Match, source: TaggedText, expand_type: str) -> str | None:
        kw = m.keyword
        variables: dict[str, object] = {}
        keyword_text: list[str] = []
        correct_case = True
        used_placeholders = False
        for n, literal in enumerate(kw.literals):
            ls, le = m.groups[2 * n]
            matched = source.untagged[ls:le] if ls >= 0 else ""
            correct_case = correct_case and matched == literal
            keyword_text.append(KW_TAG.sub("", source.tagged_slice(ls, le)) if ls >= 0 else "")
            if n == len(kw.params):
                break
            param = kw.params[n]
            ps, pe = m.groups[2 * n + 1]
            raw = source.untagged[ps:pe] if ps >= 0 else ""
            tagged = KW_TAG.sub("", source.tagged_slice(ps, pe)) if ps >= 0 else ""
            sep_before, raw = param.strip_before(raw)
            raw, sep_after = param.strip_after(raw)
            _, tagged = param.strip_before(tagged)
            tagged, _ = param.strip_after(tagged)
            if param.separator_script is not None:
                if sep_before:
                    sep_before = to_str(self.run(param.separator_script, sep_before))
                if sep_after:
                    sep_after = to_str(self.run(param.separator_script, sep_after))
            if raw == "":
                used_placeholders = True
                placeholder = f"<atom-kwpph>{param.placeholder or param.name}</atom-kwpph>"
                part_value = reminder_value = placeholder
            else:
                part_value = to_str(self.run(param.script, tagged)) if param.script else tagged
                reminder_value = to_str(self.run(param.reminder_script, raw)) \
                    if param.reminder_script else raw
            part = KeywordParamValue(param.name, part_value, sep_before, sep_after, raw)
            variables[f"param{n + 1}"] = KeywordParamValue(param.name, reminder_value, sep_before,
                                                           sep_after, raw)
            keyword_text.append(sep_before + part.script_string() + sep_after)

        variables.update(keyword="".join(keyword_text), mode=kw.mode, correct_case=correct_case,
                         used_placeholders=used_placeholders)
        if self.condition is not None and not to_bool(self.call(self.condition, variables)):
            return None
        if expand_type in ("0", "1"):
            expand = expand_type == "1"
            letter = expand_type
        else:
            expand = True if self.default_expand is None \
                else to_bool(self.call(self.default_expand, variables))
            letter = "A" if expand else "a"
        variables["expand"] = expand
        try:
            reminder = to_str(self.call(ScriptFunction(kw.reminder), variables)) \
                if kw.reminder is not None else ""
        except ScriptError as e:
            reminder = f"Error: {e}"
        variables["reminder"] = reminder
        body = to_str(self.call(self.combine, variables)) if self.combine is not None \
            else variables["keyword"]
        return f"<kw-{letter}>{body}</kw-{letter}>"

    def run(self, script: A.Node, value: str) -> object:
        return self.script.call(ScriptFunction(script), input=value)
