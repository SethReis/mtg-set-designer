"""Parser for MSE script: tokens -> syntax tree (see ast.py).

Precedence climbing that mirrors MSE's own parser (src/script/parser.cpp in
MagicSetEditor2). Levels, lowest first:

    NEWLINE   a non-operator token starting a new line acts as `;` (statement level only)
    SEQ       a ; b
    SET       name := value                      (right operand at SET)
    AND       and, or, xor                       (right operand at CMP)
              or else                            (right operand at ADD)
    CMP       == != < > <= >=  (= means ==)      (right operand at ADD)
    ADD       + -                                (right operand at MUL)
    MUL       * / div mod                        (right operand at POW)
    POW       ^                                  (right-associative)
    UNARY     -x, not x
    FUN       x.name  x.0  x[k]  f(args)  f@(args)

Operators are checked before the newline rule, so a line that starts with an
operator continues the expression above it (`\\t+ remove_tag@(...)`, `\\tand x`),
and `if/then/else` may be split over several lines. `(`, `[` and `@(` only
continue an expression on the same line.
"""
from __future__ import annotations

from enum import IntEnum

from . import ast as A
from .tokens import ScriptSyntaxError, Token, tokenize, tokenize_template


class Prec(IntEnum):
    ALL = 0
    NEWLINE = 1
    SEQ = 2
    SET = 3
    AND = 4
    CMP = 5
    ADD = 6
    MUL = 7
    POW = 8
    UNARY = 9
    FUN = 10


# operator -> (its precedence, precedence of its right operand)
BINARY = {
    "and": (Prec.AND, Prec.CMP), "or": (Prec.AND, Prec.CMP), "xor": (Prec.AND, Prec.CMP),
    "==": (Prec.CMP, Prec.ADD), "!=": (Prec.CMP, Prec.ADD), "=": (Prec.CMP, Prec.ADD),
    "<": (Prec.CMP, Prec.ADD), ">": (Prec.CMP, Prec.ADD),
    "<=": (Prec.CMP, Prec.ADD), ">=": (Prec.CMP, Prec.ADD),
    "+": (Prec.ADD, Prec.MUL), "-": (Prec.ADD, Prec.MUL),
    "*": (Prec.MUL, Prec.POW), "/": (Prec.MUL, Prec.POW),
    "div": (Prec.MUL, Prec.POW), "mod": (Prec.MUL, Prec.POW),
    "^": (Prec.POW, Prec.POW),
}
WORD_OPERATORS = {"and", "or", "xor", "div", "mod"}
# Tokens that end an expression; they never start a new statement.
CLOSERS = {")", "]", "}", ",", ":"}
CLOSER_WORDS = {"then", "else", "do", "of", "in", "from", "to"}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    # ------------------------------------------------------------ helpers

    @property
    def tok(self) -> Token:
        return self.toks[self.i]

    def peek(self, offset: int = 1) -> Token:
        return self.toks[min(self.i + offset, len(self.toks) - 1)]

    def advance(self) -> Token:
        tok = self.tok
        if tok.kind != "eof":
            self.i += 1
        return tok

    def error(self, message: str, tok: Token | None = None) -> ScriptSyntaxError:
        tok = tok or self.tok
        found = "end of script" if tok.kind == "eof" else repr(tok.value)
        return ScriptSyntaxError(f"{message} (found {found})", tok.line)

    def expect_op(self, text: str) -> Token:
        if not self.tok.is_op(text):
            raise self.error(f"expected '{text}'")
        return self.advance()

    def expect_name(self, text: str | None = None) -> Token:
        if self.tok.kind != "name" or (text is not None and self.tok.value != text):
            raise self.error(f"expected '{text}'" if text else "expected a name")
        return self.advance()

    def at_closer(self) -> bool:
        tok = self.tok
        return (tok.kind == "eof"
                or (tok.kind == "op" and tok.value in CLOSERS)
                or (tok.kind == "name" and tok.value in CLOSER_WORDS))

    # -------------------------------------------------------- entry points

    def parse_all(self) -> A.Node:
        if self.tok.kind == "eof":
            return A.Literal(self.tok.line, None)
        node = self.expr(Prec.ALL)
        if self.tok.kind != "eof":
            raise self.error("unexpected token")
        return node

    # --------------------------------------------------------- expressions

    def expr(self, min_prec: Prec) -> A.Node:
        left = self.primary()
        while True:
            tok = self.tok
            if tok.kind == "eof":
                return left

            if tok.is_op(";") and min_prec <= Prec.SEQ:
                self.advance()
                if self.at_closer():                # trailing `;` before ) } or end
                    return left
                left = self.sequence(left, self.expr(Prec.SET))
                continue

            if tok.is_op(":=") and min_prec <= Prec.SET:
                if not isinstance(left, A.Var):
                    raise self.error("can only assign to a variable name")
                self.advance()
                left = A.Assign(tok.line, left.name, self.expr(Prec.SET))
                continue

            if tok.is_name("or") and self.peek().is_name("else") and min_prec <= Prec.AND:
                self.advance()
                self.advance()
                left = A.OrElse(tok.line, left, self.expr(Prec.ADD))
                continue

            is_word_op = tok.kind == "name" and tok.value in WORD_OPERATORS
            op = tok.value if tok.kind == "op" or is_word_op else None
            if op in BINARY:
                prec, right_prec = BINARY[op]
                if prec < min_prec:
                    return left
                self.advance()
                right = self.expr(right_prec)
                if op == "and":
                    left = A.And(tok.line, left, right)
                elif op == "or":
                    left = A.Or(tok.line, left, right)
                elif op == "xor":
                    left = A.Xor(tok.line, left, right)
                else:
                    left = A.BinOp(tok.line, "==" if op == "=" else op, left, right)
                continue

            postfix = self.postfix(left)
            if postfix is not None:
                left = postfix
                continue

            # Not an operator. At statement level, a token starting a new line
            # begins a new statement (as if a `;` came before it).
            if tok.starts_line and min_prec <= Prec.NEWLINE and not self.at_closer():
                left = self.sequence(left, self.expr(Prec.SET))
                continue
            return left

    def postfix(self, left: A.Node) -> A.Node | None:
        """Member access and calls (FUN level), or None if the token isn't one."""
        tok = self.tok
        if tok.is_op("."):
            self.advance()
            key = self.advance()
            if key.kind == "name":
                return A.Member(tok.line, left, A.Literal(key.line, key.value))
            if key.kind == "string" and len(key.value) == 1 and isinstance(key.value[0], str):
                return A.Member(tok.line, left, A.Literal(key.line, key.value[0]))
            raise self.error("expected a name after '.'", key)
        # `(` and `[` only continue an expression on the same line.
        if tok.starts_line:
            return None
        if tok.is_op("["):
            self.advance()
            key = self.expr(Prec.ALL)
            self.expect_op("]")
            return A.Member(tok.line, left, key)
        if tok.is_op("("):
            return A.Call(tok.line, left, self.arguments())
        if tok.is_op("@"):
            self.advance()
            if not self.tok.is_op("("):
                raise self.error("expected '(' after '@'")
            return A.Partial(tok.line, left, self.arguments())
        return None

    def sequence(self, left: A.Node, right: A.Node) -> A.Seq:
        items = left.items if isinstance(left, A.Seq) else (left,)
        return A.Seq(left.line, items + (right,))

    # ------------------------------------------------------------ primaries

    def primary(self) -> A.Node:
        tok = self.advance()
        line = tok.line

        if tok.kind == "number":
            return A.Literal(line, tok.value)
        if tok.kind == "string":
            return self.string(tok)
        if tok.kind == "eof":
            raise self.error("expected an expression", tok)

        if tok.kind == "op":
            if tok.value == "(":
                inner = self.expr(Prec.ALL)
                self.expect_op(")")
                return inner
            if tok.value == "{":
                if self.tok.is_op("}"):
                    self.advance()
                    return A.FuncLit(line, A.Literal(line, None))
                body = self.expr(Prec.ALL)
                self.expect_op("}")
                return A.FuncLit(line, body)
            if tok.value == "[":
                return A.ListLit(line, self.items("]"))
            if tok.value == "-":
                return A.Neg(line, self.expr(Prec.UNARY))
            raise self.error("expected an expression", tok)

        # names and keywords
        word = tok.value
        if word == "true":
            return A.Literal(line, True)
        if word == "false":
            return A.Literal(line, False)
        if word == "nil":
            return A.Literal(line, None)
        if word == "not":
            return A.Not(line, self.expr(Prec.UNARY))
        if word == "if":
            cond = self.expr(Prec.AND)
            self.expect_name("then")
            then = self.expr(Prec.SET)
            otherwise = None
            if self.tok.is_name("else"):
                self.advance()
                otherwise = self.expr(Prec.SET)
            return A.If(line, cond, then, otherwise)
        if word == "case":
            return self.case(line)
        if word == "for":
            return self.for_loop(line)
        return A.Var(line, word)

    def string(self, tok: Token) -> A.Node:
        parts: list[A.Node] = []
        for part in tok.value:
            if isinstance(part, str):
                if part:
                    parts.append(A.Literal(tok.line, part))
            else:
                parts.append(Parser(part).parse_all())
        if not parts:
            return A.Literal(tok.line, "")
        if len(parts) == 1:                     # "text" or a lone "{expr}"
            return parts[0]
        return A.Interp(tok.line, tuple(parts))

    def items(self, closer: str) -> tuple[A.Arg, ...]:
        """Comma-separated (commas optional) `value` or `name: value` entries, through `closer`."""
        out: list[A.Arg] = []
        while not self.tok.is_op(closer):
            if self.tok.kind == "eof":
                raise self.error(f"expected '{closer}'")
            name = None
            if self.tok.kind in ("name", "number") and self.peek().is_op(":"):
                name = str(self.advance().value)
                self.advance()
            elif self.tok.kind == "string" and self.peek().is_op(":") \
                    and len(self.tok.value) == 1 and isinstance(self.tok.value[0], str):
                name = self.advance().value[0]
                self.advance()
            out.append((name, self.expr(Prec.SEQ)))
            if self.tok.is_op(","):
                self.advance()
        self.advance()
        return tuple(out)

    def arguments(self) -> tuple[A.Arg, ...]:
        self.expect_op("(")
        return self.items(")")

    def case(self, line: int) -> A.Case:
        subject = self.expr(Prec.SET)
        self.expect_name("of")
        cases: list[tuple[A.Node, A.Node]] = []
        otherwise = None
        while True:
            if self.tok.is_name("else"):
                self.advance()
                if self.tok.is_op(":"):
                    self.advance()
                otherwise = self.expr(Prec.SET)
                break
            if self.at_closer() or self.tok.is_op(";"):
                break
            value = self.expr(Prec.SET)
            self.expect_op(":")
            cases.append((value, self.expr(Prec.SET)))
            if self.tok.is_op(","):
                self.advance()
        return A.Case(line, subject, tuple(cases), otherwise)

    def for_loop(self, line: int) -> A.Node:
        each = False
        if self.tok.is_name("each"):
            self.advance()
            each = True
        key_var, var = None, self.expect_name().value
        if self.tok.is_op(":"):
            self.advance()
            key_var, var = var, self.expect_name().value
        if each:
            self.expect_name("in")
            collection = self.expr(Prec.SET)
            self.expect_name("do")
            return A.ForEach(line, key_var, var, collection, self.expr(Prec.SET))
        self.expect_name("from")
        start = self.expr(Prec.SET)
        self.expect_name("to")
        end = self.expr(Prec.SET)
        self.expect_name("do")
        return A.ForRange(line, key_var, var, start, end, self.expr(Prec.SET))


def parse(source: str) -> A.Node:
    """Parse script code (an `init script:` body, a `script:` value, ...)."""
    return Parser(tokenize(source)).parse_all()


def parse_template(text: str) -> A.Node:
    """Parse a template value such as `{ 30 + x }` or `Hello {card.name}`.
    A template that is a single `{expr}` evaluates to that expression's value."""
    return Parser([]).string(tokenize_template(text))
