"""Syntax tree for MSE script. Plain frozen dataclasses; `line` is for error messages."""
from __future__ import annotations

from dataclasses import dataclass

# An argument or list entry: (name or None, value). Unnamed call arguments mean `input`.
Arg = tuple["str | None", "Node"]


@dataclass(frozen=True)
class Node:
    line: int


@dataclass(frozen=True)
class Literal(Node):
    value: object                   # None, bool, int, float, str


@dataclass(frozen=True)
class Var(Node):
    name: str


@dataclass(frozen=True)
class Assign(Node):                 # name := value
    name: str
    value: Node


@dataclass(frozen=True)
class Seq(Node):                    # a; b  or statements on separate lines
    items: tuple[Node, ...]


@dataclass(frozen=True)
class If(Node):
    cond: Node
    then: Node
    otherwise: Node | None


@dataclass(frozen=True)
class Case(Node):                   # case subject of v1: r1, v2: r2, else: r
    subject: Node
    cases: tuple[tuple[Node, Node], ...]
    otherwise: Node | None


@dataclass(frozen=True)
class BinOp(Node):                  # arithmetic and comparisons: + - * / div mod ^ == != < > <= >=
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class And(Node):
    left: Node
    right: Node


@dataclass(frozen=True)
class Or(Node):
    left: Node
    right: Node


@dataclass(frozen=True)
class Xor(Node):
    left: Node
    right: Node


@dataclass(frozen=True)
class OrElse(Node):                 # left or else right: right if left is nil or fails
    left: Node
    right: Node


@dataclass(frozen=True)
class Not(Node):
    operand: Node


@dataclass(frozen=True)
class Neg(Node):
    operand: Node


@dataclass(frozen=True)
class Call(Node):                   # f(args)
    func: Node
    args: tuple[Arg, ...]


@dataclass(frozen=True)
class Partial(Node):                # f@(args): f with these arguments bound, not called
    func: Node
    args: tuple[Arg, ...]


@dataclass(frozen=True)
class Member(Node):                 # obj.name, obj.0, obj[key]
    obj: Node
    key: Node


@dataclass(frozen=True)
class ListLit(Node):                # [a, b] or [name: a, other: b]
    items: tuple[Arg, ...]


@dataclass(frozen=True)
class FuncLit(Node):                # { body }
    body: Node


@dataclass(frozen=True)
class ForEach(Node):                # for each [key:]var in collection do body
    key_var: str | None
    var: str
    collection: Node
    body: Node


@dataclass(frozen=True)
class ForRange(Node):               # for [key:]var from start to end do body
    key_var: str | None
    var: str
    start: Node
    end: Node
    body: Node


@dataclass(frozen=True)
class Interp(Node):                 # "text {expr} text": the parts joined with +
    parts: tuple[Node, ...]
