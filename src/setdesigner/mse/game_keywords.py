"""Magic's own keywords (Flying, Cycling, Ward, Scry...), from the MSE game's keyword list.

They work on every card without being added to the set: the renderer knows their
reminder text. Whether it is shown follows a policy, like a set mechanic's:
    core keywords (Flying, Haste, Trample...)  -> never, as on real cards
    the rest (Cycling, Kicker, Ward, Scry...)  -> on commons only
A set can change a keyword's policy (SetInfo.keyword_reminders, by lower-case name) and
a card can show or hide it (Card.reminders["kw:<lower-case name>"]).

The reminder text itself can be replaced: by the set (SetInfo.keyword_text) or by our
corrections of the game's (mse.keyword_fixes). MSE's own keyword always wins over another
of the same name, so a replaced text isn't given to MSE as a keyword: MSE's reminder is
switched off and ours is written into the rules text in parentheses, which MSE sets in
italics as reminder text (insert_reminder).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..model import Card, ReminderPolicy, SetProject

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "resources" / "mse_packages"
SKIP_MODES = {"pseudo"}                     # ability words (Landfall) have no reminder text


@dataclass(frozen=True)
class GameKeyword:
    name: str
    mode: str                               # core / expert / action / old
    reminder: str                           # MSE's template ({param1}, script calls)
    regex: object                           # the game's match, on MSE text
    match: str = ""                         # the game's match pattern: "explores", "Ward<atom-param>cost</atom-param>"

    @property
    def literal(self) -> str:
        """The match's first words, as a card says them: "explores", "Ward"."""
        return re.split(r"<atom-param>", self.match or self.name)[0].strip() or self.name

    @property
    def has_param(self) -> bool:
        return "<atom-param>" in self.match

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def card_key(self) -> str:
        """Its key in Card.reminders."""
        return "kw:" + self.key

    @property
    def default_policy(self) -> ReminderPolicy:
        return ReminderPolicy.NEVER if self.mode == "core" else ReminderPolicy.COMMONS_ONLY

    def preview(self) -> str:
        """The reminder text readable without MSE's scripts: "This creature can't be
        blocked except by creatures with flying or reach." (parameters as N)."""
        text = " ".join(_readable(self.reminder).replace("’", "'").split())
        return re.sub(r"(?<=[a-z,] )This ", "this ", text)


def _script(code: str) -> str:
    """A script block as words: a parameter is N, this_or_that("creature") is "This
    creature", anything else is its last quoted text (an if's general case), read again."""
    code = code.strip()
    if code.startswith("protection_code("):
        return "This can't be blocked, targeted, dealt damage, enchanted, or equipped by anything N"
    if re.fullmatch(r"(?:\w+\()*param\d(?:\.value)?\)*", code) or re.match(r"english_number\(param", code):
        return "N"
    m = re.match(r'this_or_that\("([^"]+)"', code)
    if m:
        return "This permanent" if m.group(1) == "type" else f"This {m.group(1)}"
    m = re.match(r'for_mana_costs\(add:"([^"]*)"', code)
    if m:
        return m.group(1) + "N"
    code = re.sub(r'this_or_that\("([^"]+)"[^)]*\)',            # inside an if: just the noun
                  lambda m: '"permanent"' if m.group(1) == "type" else f'"{m.group(1)}"', code)
    quoted = re.findall(r'"((?:[^"\\]|\\.)*)"', code)
    return _readable(quoted[-1]) if quoted else ""


def _readable(template: str) -> str:
    """A reminder template with its {script} blocks (nested braces too) replaced by words."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(template):
        if ch == "{":
            if depth == 0:
                out.append(template[start:i])
                start = i + 1
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                out.append(_script(template[start:i]))
                start = i + 1
    out.append(template[start:] if depth == 0 else "")
    return "".join(out)


@lru_cache(maxsize=4)
def game_keywords(root: Path = DEFAULT_ROOT) -> tuple[GameKeyword, ...]:
    """The game's keywords that have reminder text, one per name (empty without the MSE
    packages)."""
    from .keywords import KeywordDatabase, _node_values
    from .reader import read_file
    game = Path(root) / "magic.mse-game" / "game"
    if not game.is_file():
        return ()
    nodes, _ = read_file(game, Path(root))
    db = KeywordDatabase.from_nodes([n for n in nodes if n.key == "keyword parameter type"])
    out, seen = [], set()
    for node in nodes:
        if node.key != "keyword":
            continue
        values = _node_values(node)
        name, reminder = values.get("keyword", "").strip(), values.get("reminder", "").strip()
        if not name or not reminder or name.lower() in seen or values.get("mode") in SKIP_MODES:
            continue
        kw = db.add(values, from_game=True)
        if kw.valid and kw.regex is not None:
            seen.add(name.lower())
            out.append(GameKeyword(name, kw.mode, reminder, kw.regex, values.get("match", "")))
    return tuple(out)


def find(name: str, keywords=None) -> GameKeyword | None:
    keywords = game_keywords() if keywords is None else keywords
    return next((k for k in keywords if k.key == name.lower()), None)


def used(card: Card, project: SetProject | None = None, keywords=None) -> list[GameKeyword]:
    """The game keywords the card's rules text uses, in list order. One the set defines as
    its own mechanic doesn't count (the mechanic replaces it)."""
    from .mapping import mse_text
    keywords = game_keywords() if keywords is None else keywords
    own = {m.name.lower() for m in project.mechanics} if project is not None else set()
    texts = [mse_text(face.rules_text) for face in card.faces if face.rules_text]
    if not texts:
        return []
    lower = "\n".join(texts).lower()
    out = []
    for kw in keywords:
        if kw.key in own:
            continue
        head = re.split(r"[^a-z ]", kw.key)[0].strip()
        if head and head not in lower:
            continue                        # cheap: most keywords aren't on most cards
        if any(kw.regex.search(t) for t in texts):
            out.append(kw)
    return out


MSE_SHOWN_MODES = {"old", "expert", "action", "custom"}   # the game's "automatic reminder text"


def mse_default(keyword: GameKeyword) -> bool:
    """Whether MSE shows the keyword's reminder text when nothing says otherwise."""
    return keyword.mode in MSE_SHOWN_MODES


def custom_text(info, keyword: GameKeyword, rules_text: str = "") -> str | None:
    """The reminder text replacing the game's, if any: the set's own (SetInfo.keyword_text),
    else our correction (mse.keyword_fixes; some depend on the card's text). {N} is the
    keyword's value."""
    own = (getattr(info, "keyword_text", None) or {}).get(keyword.key)
    if own and own.strip():
        return own.strip()
    from .keyword_fixes import FIXES
    fix = FIXES.get(keyword.key)
    return fix(rules_text) if callable(fix) else fix


def reminder_text(info, keyword: GameKeyword, rules_text: str = "") -> str:
    """The reminder text in use, readable (the game's as a preview when not replaced)."""
    return custom_text(info, keyword, rules_text) or keyword.preview()


def insert_reminder(text: str, keyword: GameKeyword, reminder: str) -> str:
    """The rules text with "(reminder)" after the keyword's first mention, as MSE places
    it: after the keyword and its value ("Ward {2} (...)"), or at the end of the sentence
    for a keyword action ("it explores. (...)"). {N} / {param1} become the value."""
    m = re.search(r"(?<![\w])" + re.escape(keyword.literal) + r"(?![\w])", text, re.IGNORECASE)
    if m is None:
        return text
    end, value = m.end(), ""
    if keyword.has_param:
        param = re.match(r"[ \t]*[—-]?[ \t]*([^\n,.;(]+)", text[end:])
        if param:
            value = param.group(1).rstrip()
            end += param.start(1) + len(value)
    if keyword.mode == "action":
        line_end = text.find("\n", end)
        line_end = len(text) if line_end < 0 else line_end
        stop = text.find(".", end, line_end)
        end = line_end if stop < 0 else stop + 1
    filled = " ".join(re.sub(r"\{(?:N|param1?)\}", lambda _: value, reminder).split())
    return f"{text[:end]} ({filled}){text[end:]}"


def policy(project: SetProject, keyword: GameKeyword) -> ReminderPolicy:
    return project.info.keyword_reminders.get(keyword.key, keyword.default_policy)
