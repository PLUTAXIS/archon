"""Minimal formula AST plus a mock parser for fixtures.

Isolated in this one file so Senpai's real parser can replace it later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Num:
    """A numeric literal, kept as its source text so output never depends on float repr."""

    text: str


@dataclass(frozen=True)
class Ref:
    """A single-cell reference such as B2."""

    address: str


@dataclass(frozen=True)
class Range:
    """A cell range such as A1:A10."""

    start: str
    end: str


@dataclass(frozen=True)
class BinOp:
    """A binary operation: arithmetic (+ - * /) or comparison (< <= > >= = <>)."""

    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Call:
    """A function call with ordered arguments."""

    name: str
    args: tuple[Node, ...]


Node = Num | Ref | Range | BinOp | Call


class FormulaSyntaxError(ValueError):
    """Raised when the mock parser cannot read a formula."""

    def __init__(self, formula: str, index: int) -> None:
        super().__init__(f"cannot parse {formula!r} near token/offset {index}")


_ADDRESS = re.compile(r"([A-Z]{1,3})(\d+)")
_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<ref>\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?(?![\w(]))"
    r"|(?P<name>[A-Za-z_]\w*)"
    r"|(?P<op><=|>=|<>|[-+*/<>=(),]))"
)
_COMPARE = ("<=", ">=", "<>", "<", ">", "=")


def prior_row_address(address: str) -> str | None:
    """Return the address one row above, in the same column, or None at row 1."""
    match = _ADDRESS.fullmatch(address.upper())
    if match is None or int(match.group(2)) <= 1:
        return None
    return f"{match.group(1)}{int(match.group(2)) - 1}"


def _tokenize(formula: str) -> list[tuple[str, str]]:
    """Split a formula into (kind, text) tokens."""
    text = formula.strip().removeprefix("=")
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None or match.lastgroup is None:
            raise FormulaSyntaxError(formula, pos)
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        pos = match.end()
    return tokens


def _reference(text: str) -> Ref | Range:
    """Build a Ref or Range from reference text, dropping $ markers."""
    clean = text.replace("$", "").upper()
    if ":" in clean:
        start, end = clean.split(":")
        return Range(start, end)
    return Ref(clean)


class _Parser:
    """Recursive-descent parser: compare > add > mul > atom."""

    def __init__(self, formula: str) -> None:
        self.formula = formula
        self.tokens = _tokenize(formula)
        self.pos = 0

    def _peek(self) -> tuple[str, str]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ("end", "")

    def _accept(self, *ops: str) -> str | None:
        kind, value = self._peek()
        if kind == "op" and value in ops:
            self.pos += 1
            return value
        return None

    def _expect(self, op: str) -> None:
        if self._accept(op) is None:
            raise FormulaSyntaxError(self.formula, self.pos)

    def parse(self) -> Node:
        """Parse the whole formula; trailing tokens are an error."""
        node = self._compare()
        if self._peek()[0] != "end":
            raise FormulaSyntaxError(self.formula, self.pos)
        return node

    def _compare(self) -> Node:
        left = self._add()
        op = self._accept(*_COMPARE)
        return BinOp(op, left, self._add()) if op else left

    def _add(self) -> Node:
        node = self._mul()
        while (op := self._accept("+", "-")) is not None:
            node = BinOp(op, node, self._mul())
        return node

    def _mul(self) -> Node:
        node = self._atom()
        while (op := self._accept("*", "/")) is not None:
            node = BinOp(op, node, self._atom())
        return node

    def _atom(self) -> Node:
        kind, value = self._peek()
        self.pos += 1
        if kind == "num":
            return Num(value)
        if kind == "ref":
            return _reference(value)
        if kind == "name":
            return self._call(value.upper())
        if kind == "op" and value == "(":
            node = self._compare()
            self._expect(")")
            return node
        raise FormulaSyntaxError(self.formula, self.pos)

    def _call(self, name: str) -> Call:
        self._expect("(")
        args: list[Node] = []
        if self._accept(")") is None:
            args.append(self._compare())
            while self._accept(",") is not None:
                args.append(self._compare())
            self._expect(")")
        return Call(name, tuple(args))


def parse_mock_formula(formula: str) -> Node:
    """Parse a formula string such as '=D1+B2-C2' into an AST."""
    return _Parser(formula).parse()


def _operand(node: Node) -> str:
    """Text of a binary operand; nested binary operations get parentheses."""
    text = to_formula_text(node)
    return f"({text})" if isinstance(node, BinOp) else text


def to_formula_text(node: Node) -> str:
    """Canonical, deterministic text for a node (no whitespace, upper-case refs)."""
    if isinstance(node, Num):
        return node.text
    if isinstance(node, Ref):
        return node.address
    if isinstance(node, Range):
        return f"{node.start}:{node.end}"
    if isinstance(node, BinOp):
        return f"{_operand(node.left)}{node.op}{_operand(node.right)}"
    return f"{node.name}({','.join(to_formula_text(a) for a in node.args)})"
