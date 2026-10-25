"""Tokenizer for MSE script.

Follows MSE's own tokenizer (src/script/parser.cpp in MagicSetEditor2):
  * names start with a letter, `_` or a non-ASCII character; a digit run directly
    after `.` is a name too, so `colors.0` is member access;
  * numbers are digit runs, with a `.` making them floats;
  * strings are "..." with backslash escapes, and an unescaped `{` inside a string
    starts an embedded expression up to the matching `}` ("smart strings");
  * `#` starts a comment that runs to the end of the line.

A string token's value is a list of parts: plain `str` pieces and, for each
`{expr}`, the list of tokens of that expression (ending with its own `eof`).
"""
from __future__ import annotations

from dataclasses import dataclass

TWO_CHAR_OPS = (":=", "==", "!=", "<=", ">=")
ONE_CHAR_OPS = set("+-*/!.@%^&:=<>;,()[]{}")
# `\<` becomes a special character meaning "a literal <, not the start of a tag".
ESCAPED_LANGLE = "\x01"
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "&": "", "<": ESCAPED_LANGLE, "\\": "\\",
           '"': '"', "'": "'", "{": "{", "}": "}"}


class ScriptSyntaxError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"line {line}: {message}")
        self.line = line


@dataclass
class Token:
    kind: str                   # name | number | string | op | eof
    value: object               # str, int/float, or list of string parts
    line: int
    starts_line: bool = False   # first token on its line

    def is_op(self, text: str) -> bool:
        return self.kind == "op" and self.value == text

    def is_name(self, text: str) -> bool:
        return self.kind == "name" and self.value == text


def _is_name_start(c: str) -> bool:
    return c.isalpha() or c == "_" or ord(c) >= 128


def _is_name_char(c: str) -> bool:
    return c.isalnum() or c == "_" or ord(c) >= 128


class _Lexer:
    def __init__(self, src: str):
        self.src = src
        self.pos = 0
        self.line = 1
        self.at_line_start = True

    def error(self, message: str) -> ScriptSyntaxError:
        return ScriptSyntaxError(message, self.line)

    def tokens(self, in_string: bool = False) -> list[Token]:
        """Lex code. With in_string=True, stop at the `}` that closes a `{expr}`
        inside a string (and consume it)."""
        src, out, depth = self.src, [], 0
        while True:
            # skip whitespace and comments
            while self.pos < len(src):
                c = src[self.pos]
                if c == "\n":
                    self.line += 1
                    self.at_line_start = True
                    self.pos += 1
                elif c.isspace():
                    self.pos += 1
                elif c == "#":
                    while self.pos < len(src) and src[self.pos] != "\n":
                        self.pos += 1
                else:
                    break
            if self.pos >= len(src):
                if in_string:
                    raise self.error("unterminated '{' inside a string")
                out.append(Token("eof", None, self.line, True))
                return out

            c = src[self.pos]
            starts_line, self.at_line_start = self.at_line_start, False
            line = self.line

            if in_string and c == "}" and depth == 0:
                self.pos += 1
                out.append(Token("eof", None, line, False))
                return out
            if c == '"':
                self.pos += 1
                out.append(Token("string", self.string_body(), line, starts_line))
            elif _is_name_start(c) or (c.isdigit() and out and out[-1].is_op(".")):
                start = self.pos
                while self.pos < len(src) and _is_name_char(src[self.pos]):
                    self.pos += 1
                out.append(Token("name", src[start:self.pos], line, starts_line))
            elif c.isdigit():
                start = self.pos
                while self.pos < len(src) and (src[self.pos].isdigit() or src[self.pos] == "."):
                    self.pos += 1
                text = src[start:self.pos]
                try:
                    value = float(text) if "." in text else int(text)
                except ValueError:
                    raise self.error(f"bad number {text!r}") from None
                out.append(Token("number", value, line, starts_line))
            else:
                op = src[self.pos:self.pos + 2]
                if op not in TWO_CHAR_OPS:
                    op = c
                    if op not in ONE_CHAR_OPS:
                        raise self.error(f"unexpected character {c!r}")
                if op == "{":
                    depth += 1
                elif op == "}":
                    depth -= 1
                self.pos += len(op)
                out.append(Token("op", op, line, starts_line))

    def string_body(self, closing: str | None = '"') -> list:
        """Read string contents after the opening quote, through the closing quote.
        With closing=None, read to the end of the source (template text)."""
        src, parts, buf = self.src, [], []
        while True:
            if self.pos >= len(src):
                if closing is None:
                    break
                raise self.error("unterminated string")
            c = src[self.pos]
            if c == closing:
                self.pos += 1
                break
            if c == "\\":
                nxt = src[self.pos + 1:self.pos + 2]
                if nxt.isdigit():                       # decimal character code
                    end = self.pos + 1
                    while end < len(src) and src[end].isdigit():
                        end += 1
                    buf.append(chr(int(src[self.pos + 1:end])))
                    self.pos = end
                    continue
                if nxt not in ESCAPES:
                    raise self.error(f"unknown escape '\\{nxt}' in string")
                buf.append(ESCAPES[nxt])
                self.pos += 2
                continue
            if c == "{":
                self.pos += 1
                if buf:
                    parts.append("".join(buf))
                    buf = []
                parts.append(self.tokens(in_string=True))
                continue
            if c == "\n":
                self.line += 1
            buf.append(c)
            self.pos += 1
        if buf or not parts:
            parts.append("".join(buf))
        return parts


def tokenize(src: str) -> list[Token]:
    """Tokens of script code, ending with an `eof` token."""
    return _Lexer(src).tokens()


def tokenize_template(text: str) -> Token:
    """A whole template value (`{ 30 + x }`, `Hello {card.name}`) as one string token."""
    lexer = _Lexer(text)
    return Token("string", lexer.string_body(closing=None), 1, True)
