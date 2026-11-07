"""Parser for Excel formula text: token stream (from tokenizer.py) -> AST
(node types from ast.py).

Implements Excel's own operator-precedence table exactly, as a set of
recursive-descent levels (one function per precedence level, tightest to
loosest) rather than a generic precedence-climbing loop, because Excel's
precedence order has two quirks that are easy to get backwards with a
generic table:

  - unary minus/plus bind TIGHTER than '^', so ``-2^2`` parses as
    ``(-2)^2`` = 4, not ``-(2^2)`` = -4.
  - postfix '%' binds LOOSER than unary minus/plus but TIGHTER than '^',
    so ``-5%`` parses as ``(-5)%``, not ``-(5%)``.

Excel's full precedence table (tightest to loosest) is:
    : (range)  (space) (intersection)  , (union)   <- reference operators
    – (unary minus/plus)
    % (postfix percent)
    ^ (exponentiation, right-associative)
    * /
    + -
    & (concatenation)
    = <> < > <= >= (comparison)

Known, deliberate gaps (not oversights):
  - Space as the intersection operator is NOT supported. tokenizer.py
    discards whitespace entirely, so by the time this parser sees the
    token stream there is no way to tell "A1 B1" (intersection) apart
    from "A1B1" or a multi-token sequence with incidental spacing. Adding
    this requires the tokenizer to emit a token for "meaningful" adjacent
    whitespace between two reference-shaped tokens, which is a tokenizer
    change, not a parser one.
  - Comma as the reference UNION operator is NOT distinguished from comma
    as a function-argument / array-element separator. Both are lexed as
    the same COMMA token, and disambiguating them requires tracking
    whether the parser is inside a "reference context" (e.g. inside a
    range expression) versus an "argument list context" — that context
    tracking isn't implemented yet. Comma is currently only consumed as
    a separator (function args, array elements).
  - There is no dedicated AST node for an array literal ({1,2;3,4}) in
    ast.py's node list (Lit/Ref/UnaryOp/BinOp/Func only). Array literals
    are represented as a synthetic ``Func(name="ARRAY", ...)`` whose args
    are synthetic ``Func(name="ARRAY_ROW", ...)`` nodes, one per row, so
    no information is lost — but this is a stand-in, not a real node
    type, and should be revisited if/when ast.py grows one.
  - A bare name with no '(' and no sheet '!' (e.g. a defined name like
    ``MyRange``) is parsed as a Ref whose r1c1 field holds the name text
    verbatim. ast.py's Ref.r1c1 is documented as R1C1-form reference
    text; a defined name is not a cell/range reference and is not
    translated to R1C1 by anything here. This is a known mismatch,
    flagged rather than hacked around, since the brief has no dedicated
    "named range" node either.
"""

from __future__ import annotations

from archon.formula.ast import BinOp, Func, Lit, Node, Ref, UnaryOp
from archon.formula.tokenizer import Token, TokenizeError, TokenType, tokenize


class ParseError(ValueError):
    """Raised when a token stream cannot be parsed into a valid AST."""


_COMPARISON_OPS = {"=", "<>", "<", ">", "<=", ">="}


def parse(formula: str) -> Node:
    """Parse Excel formula text (with or without a leading '=') into an AST."""
    try:
        tokens = tokenize(formula)
        return _Parser(tokens).parse()
    except TokenizeError as exc:
        raise ParseError(str(exc)) from exc
    except RecursionError as exc:
        raise ParseError("Formula is nested too deeply to parse") from exc


class _Parser:
    """Recursive-descent parser over a token list."""

    def __init__(self, tokens: list[Token]) -> None:
        """Start parsing at the first token of the stream."""
        self._tokens = tokens
        self._pos = 0

    def parse(self) -> Node:
        """Parse the whole token stream and require it to be fully consumed."""
        node = self._comparison()
        self._expect(TokenType.EOF)
        return node

    # --- precedence levels, loosest to tightest in call order -----------

    def _comparison(self) -> Node:
        """Comparison operators (= <> < > <= >=), the loosest level."""
        left = self._concat()
        while self._peek().type == TokenType.OP and self._peek().text in _COMPARISON_OPS:
            op = self._advance().text
            right = self._concat()
            left = BinOp(op=op, left=left, right=right)
        return left

    def _concat(self) -> Node:
        """String concatenation with '&'."""
        left = self._add_sub()
        while self._peek().type == TokenType.OP and self._peek().text == "&":
            self._advance()
            right = self._add_sub()
            left = BinOp(op="&", left=left, right=right)
        return left

    def _add_sub(self) -> Node:
        """Binary '+' and '-', left-associative."""
        left = self._mul_div()
        while self._peek().type == TokenType.OP and self._peek().text in ("+", "-"):
            op = self._advance().text
            right = self._mul_div()
            left = BinOp(op=op, left=left, right=right)
        return left

    def _mul_div(self) -> Node:
        """Binary '*' and '/', left-associative."""
        left = self._exponent()
        while self._peek().type == TokenType.OP and self._peek().text in ("*", "/"):
            op = self._advance().text
            right = self._exponent()
            left = BinOp(op=op, left=left, right=right)
        return left

    def _exponent(self) -> Node:
        """'^' is left-associative, e.g. 2^3^2 == (2^3)^2."""
        left = self._percent()
        while self._peek().type == TokenType.OP and self._peek().text == "^":
            self._advance()
            right = self._percent()
            left = BinOp(op="^", left=left, right=right)
        return left

    def _percent(self) -> Node:
        """Postfix '%' is looser than unary -/+ but tighter than '^'."""
        node = self._unary()
        while self._peek().type == TokenType.PERCENT:
            self._advance()
            node = UnaryOp(op="%", operand=node, postfix=True)
        return node

    def _unary(self) -> Node:
        """Prefix unary -/+ binds tighter than '^' and tighter than '%'."""
        tok = self._peek()
        if tok.type == TokenType.OP and tok.text in ("-", "+"):
            self._advance()
            operand = self._unary()
            return UnaryOp(op=tok.text, operand=operand)
        return self._range()

    def _range(self) -> Node:
        """':' (range) is the tightest-binding operator — it joins two
        reference corners into a range before anything else applies."""
        left = self._primary()
        while self._peek().type == TokenType.COLON:
            self._advance()
            right = self._primary()
            if (
                isinstance(left, Ref)
                and isinstance(right, Ref)
                and left.sheet is not None
                and right.sheet is None
            ):
                right = Ref(sheet=left.sheet, r1c1=right.r1c1, absolute=right.absolute)
            left = BinOp(op=":", left=left, right=right)
        return left

    # --- primary expressions ---------------------------------------------

    def _primary(self) -> Node:
        """Literals, refs, parenthesised groups, function calls and arrays."""
        tok = self._peek()

        if tok.type == TokenType.NUMBER:
            self._advance()
            return Lit(value=float(tok.text))

        if tok.type == TokenType.STRING:
            self._advance()
            return Lit(value=_unescape_string(tok.text))

        if tok.type == TokenType.BOOLEAN:
            self._advance()
            return Lit(value=tok.text.upper() == "TRUE")

        if tok.type == TokenType.LPAREN:
            self._advance()
            inner = self._comparison()
            self._expect(TokenType.RPAREN)
            return inner

        if tok.type == TokenType.LBRACE:
            return self._array_literal()

        if tok.type == TokenType.SHEET_NAME:
            sheet_tok = self._advance()
            self._expect(TokenType.BANG)
            return self._sheet_qualified(_unquote_sheet(sheet_tok.text))

        if tok.type == TokenType.IDENTIFIER:
            ident_tok = self._advance()
            if self._peek().type == TokenType.BANG:
                self._advance()
                return self._sheet_qualified(ident_tok.text)
            if self._peek().type == TokenType.LPAREN:
                return self._func_call(ident_tok.text)
            # Bare defined-name reference — see module docstring's known
            # gaps: not translated to R1C1, stored as the raw name text.
            return Ref(sheet=None, r1c1=ident_tok.text, absolute=(False, False))

        if tok.type == TokenType.REF:
            self._advance()
            return self._make_ref(tok, sheet=None)

        raise ParseError(
            f"Unexpected token {tok.type.name} ({tok.text!r}) at position {tok.pos}"
        )

    def _func_call(self, name: str) -> Node:
        """Parse a function call's argument list after its name."""
        self._expect(TokenType.LPAREN)
        args: list[Node] = []
        if self._peek().type != TokenType.RPAREN:
            args.append(self._comparison())
            while self._peek().type == TokenType.COMMA:
                self._advance()
                args.append(self._comparison())
        self._expect(TokenType.RPAREN)
        return Func(name=name, args=tuple(args))

    def _array_literal(self) -> Node:
        """Parse {a,b;c,d} into synthetic ARRAY / ARRAY_ROW nodes."""
        self._expect(TokenType.LBRACE)
        rows: list[list[Node]] = [[]]
        if self._peek().type != TokenType.RBRACE:
            rows[-1].append(self._comparison())
            while self._peek().type in (TokenType.COMMA, TokenType.SEMICOLON):
                sep = self._advance()
                if sep.type == TokenType.SEMICOLON:
                    rows.append([])
                rows[-1].append(self._comparison())
        self._expect(TokenType.RBRACE)
        row_nodes = [Func(name="ARRAY_ROW", args=tuple(row)) for row in rows]
        return Func(name="ARRAY", args=tuple(row_nodes))

    def _sheet_qualified(self, sheet: str) -> Ref:
        """Parse what follows 'Sheet!': a cell/range ref or a defined name."""
        if self._peek().type == TokenType.IDENTIFIER:
            name = self._advance().text
            return Ref(sheet=sheet, r1c1=name, absolute=(False, False))
        ref_tok = self._expect(TokenType.REF)
        return self._make_ref(ref_tok, sheet=sheet)

    def _make_ref(self, ref_tok: Token, sheet: str | None) -> Ref:
        """Build a Ref node, recording its absolute-reference flags."""
        row_abs, col_abs = _ref_absolute_flags(ref_tok.text)
        return Ref(sheet=sheet, r1c1=ref_tok.text, absolute=(row_abs, col_abs))

    # --- token-stream helpers ---------------------------------------------

    def _peek(self) -> Token:
        """Return the current token without consuming it."""
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        """Consume and return the current token."""
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, type_: TokenType) -> Token:
        """Consume a token of the given type or raise ParseError."""
        tok = self._peek()
        if tok.type != type_:
            raise ParseError(
                f"Expected {type_.name}, got {tok.type.name} ({tok.text!r}) "
                f"at position {tok.pos}"
            )
        return self._advance()


def _ref_absolute_flags(text: str) -> tuple[bool, bool]:
    """Return (row_absolute, col_absolute) for a single reference corner
    such as "A1", "$A$1", "A$1", "$A" (whole col), "$1" (whole row), by
    the position of up to two '$' markers relative to the letters/digits.
    """
    i = 0
    col_abs = False
    row_abs = False
    if i < len(text) and text[i] == "$":
        col_abs = True
        i += 1
    while i < len(text) and text[i].isalpha():
        i += 1
    if i < len(text) and text[i] == "$":
        row_abs = True
        i += 1
    if col_abs and not any(c.isalpha() for c in text):
        # A single leading '$' on a token with no letters at all (e.g.
        # "$1", a whole absolute row) marks the row, not the column.
        row_abs, col_abs = True, False
    return (row_abs, col_abs)


def _unquote_sheet(text: str) -> str:
    """Strip the surrounding quotes from a quoted sheet-name token, undoing
    Excel's doubled-quote escaping for a literal quote inside the name."""
    inner = text[1:-1]
    return inner.replace("''", "'")


def _unescape_string(text: str) -> str:
    """Strip the surrounding quotes from a string literal token, undoing
    Excel's doubled-quote escaping for a literal quote inside the string."""
    inner = text[1:-1]
    return inner.replace('""', '"')
