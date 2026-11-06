"""Tokenizer (lexer) for Excel formula text.

Turns formula text such as ``=SUM(A1:A10)*2`` into a flat stream of Tokens
that archon/formula/parser.py consumes to build an AST. This module does no
parsing or precedence handling — it only recognizes the lowest-level pieces:
numbers, strings, booleans, identifiers/function names, cell and range
references, and the punctuation/operator symbols Excel formulas use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """The kind of lexical token produced by tokenize()."""

    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    IDENTIFIER = auto()  # function name or defined name, e.g. SUM, MyRange
    REF = auto()  # a cell or range reference, e.g. A1, $B$2, A1:B10
    SHEET_NAME = auto()  # a sheet name token preceding '!', quoted or bare
    OP = auto()  # + - * / ^ & = <> <= >= < >
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMICOLON = auto()
    COLON = auto()
    BANG = auto()  # '!' sheet-reference separator
    PERCENT = auto()  # postfix '%'
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical token.

    type: the kind of token.
    text: the exact source text the token was lexed from.
    pos: the 0-based index into the original formula string where this
        token starts, useful for error messages.
    """

    type: TokenType
    text: str
    pos: int


class TokenizeError(ValueError):
    """Raised when formula text contains a character or sequence that
    cannot be lexed into a valid token (e.g. an unterminated string)."""


_SINGLE_CHAR_OPS = {
    "+": TokenType.OP,
    "-": TokenType.OP,
    "*": TokenType.OP,
    "/": TokenType.OP,
    "^": TokenType.OP,
    "&": TokenType.OP,
    "=": TokenType.OP,
    "<": TokenType.OP,
    ">": TokenType.OP,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    ":": TokenType.COLON,
    "!": TokenType.BANG,
    "%": TokenType.PERCENT,
}

# A cell or range corner, e.g. A1, $A$1, A, 1 (whole col/row), XFD1048576.
_REF_RE_SOURCE = r"\$?[A-Za-z]{1,3}\$?\d{1,7}|\$?[A-Za-z]{1,3}(?![A-Za-z0-9_])|\$?\d{1,7}(?!\d)"

_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?", re.ASCII
)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_REF_RE = re.compile(_REF_RE_SOURCE, re.ASCII)
_QUOTED_SHEET_RE = re.compile(r"'(?:[^']|'')*'")


def tokenize(formula: str) -> list[Token]:
    """Lex Excel formula text into a list of Tokens, ending with an EOF token.

    A leading '=' is stripped if present (it is not itself a token). Raises
    TokenizeError for an unterminated string/quoted-sheet-name literal or an
    unrecognized character.
    """
    text = formula
    tokens: list[Token] = []
    i = 1 if formula.startswith("=") else 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch == '"':
            end = _find_string_end(text, i)
            tokens.append(Token(TokenType.STRING, text[i : end + 1], i))
            i = end + 1
            continue

        if ch == "'":
            m = _QUOTED_SHEET_RE.match(text, i)
            if not m:
                raise TokenizeError(f"Unterminated quoted sheet name at position {i}")
            tokens.append(Token(TokenType.SHEET_NAME, m.group(), i))
            i = m.end()
            continue

        if ch in "0123456789" or (
            ch == "." and i + 1 < n and text[i + 1] in "0123456789"
        ):
            m = _NUMBER_RE.match(text, i)
            assert m is not None
            lexeme = m.group()
            end = m.end()
            next_char = text[end] if end < n else ""
            prev_was_colon = bool(tokens) and tokens[-1].type == TokenType.COLON
            is_whole_row = (
                lexeme.isdigit()
                and len(lexeme) <= 7
                and (next_char == ":" or prev_was_colon)
            )
            tokens.append(
                Token(TokenType.REF if is_whole_row else TokenType.NUMBER, lexeme, i)
            )
            i = end
            continue

        if ch == "<" and i + 1 < n and text[i + 1] in "=>":
            tokens.append(Token(TokenType.OP, text[i : i + 2], i))
            i += 2
            continue
        if ch == ">" and i + 1 < n and text[i + 1] == "=":
            tokens.append(Token(TokenType.OP, text[i : i + 2], i))
            i += 2
            continue

        if ch.isalpha() or ch == "$" or ch == "_":
            ref_match = _REF_RE.match(text, i)
            ident_match = _IDENT_RE.match(text, i)
            # Prefer the longer match; a plain identifier like "TRUE" or a
            # function name "SUM" should not be mistaken for a reference,
            # but something like "A1" should win over treating it as a bare
            # identifier. Reference wins when it matches the identifier's
            # full span AND looks like row/col shape (handled by preferring
            # longest, then ref on tie since ref requires digit or bounded
            # letters).
            if ref_match and ident_match and ref_match.end() == ident_match.end():
                candidate = ref_match.group()
                upper = candidate.upper()
                end = ident_match.end()
                next_char = text[end] if end < n else ""
                prev_was_colon = bool(tokens) and tokens[-1].type == TokenType.COLON
                if next_char == "(":
                    tokens.append(Token(TokenType.IDENTIFIER, candidate, i))
                elif upper in ("TRUE", "FALSE"):
                    tokens.append(Token(TokenType.BOOLEAN, candidate, i))
                elif _looks_like_ref(candidate) or (
                    candidate.isalpha() and (next_char == ":" or prev_was_colon)
                ):
                    tokens.append(Token(TokenType.REF, candidate, i))
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, candidate, i))
                i = end
                continue
            if ident_match and (not ref_match or ident_match.end() > ref_match.end()):
                candidate = ident_match.group()
                upper = candidate.upper()
                if upper in ("TRUE", "FALSE"):
                    tokens.append(Token(TokenType.BOOLEAN, candidate, i))
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, candidate, i))
                i = ident_match.end()
                continue
            if ref_match:
                tokens.append(Token(TokenType.REF, ref_match.group(), i))
                i = ref_match.end()
                continue
            raise TokenizeError(f"Unrecognized character {ch!r} at position {i}")

        if ch in _SINGLE_CHAR_OPS:
            tokens.append(Token(_SINGLE_CHAR_OPS[ch], ch, i))
            i += 1
            continue

        raise TokenizeError(f"Unrecognized character {ch!r} at position {i}")

    tokens.append(Token(TokenType.EOF, "", n))
    return tokens


def _find_string_end(text: str, start: int) -> int:
    """Return the index of the closing quote for a string literal starting
    at `start` (which must point at the opening '\"'). Handles Excel's
    doubled-quote ("") escape for a literal quote inside the string."""
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == '"':
            if i + 1 < n and text[i + 1] == '"':
                i += 2
                continue
            return i
        i += 1
    raise TokenizeError(f"Unterminated string literal starting at position {start}")


def _looks_like_ref(candidate: str) -> bool:
    """True if `candidate` has the shape of a cell/range reference corner
    (letters+digits, or a bare absolute column/row like $A or $1) rather
    than a plain word. A bare, non-$ alphabetic token (e.g. 'SUM', 'TRUE')
    is never treated as a reference here — only $-prefixed whole col/row or
    a letters-then-digits cell address counts."""
    body = candidate.lstrip("$")
    if body.isdigit():
        return True
    if body.isalpha():
        return candidate.startswith("$")
    return any(c.isdigit() for c in body) and any(c.isalpha() for c in body)
