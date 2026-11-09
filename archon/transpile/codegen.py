"""AST -> Python code generator for Excel formulas.

Per the brief's transpile stage: takes the AST produced by
archon.formula.parser.parse() and emits a Python expression (as source
text) that computes the same value, for later execution against real
cell data and comparison in the parity harness.

CRITICAL CORRECTNESS NOTE, read before touching this file: Python's own
operator precedence/associativity does NOT match Excel's. The clearest
example is unary minus vs. exponentiation: Python's ``-2 ** 2`` evaluates
to ``-4`` (unary minus binds LOOSER than ``**`` in Python), but Excel's
``-2^2`` is ``4`` (unary minus binds TIGHTER than ``^`` in Excel — see
archon.formula.parser's own docstring). Relying on Python's precedence
rules to reproduce Excel's would silently produce wrong numbers.

The fix used throughout this module: every BinOp and UnaryOp node is
generated with FULL, explicit parentheses around itself, so the AST's own
tree structure — which archon.formula.parser already built according to
Excel's exact precedence table — is what determines evaluation order,
never Python's. This is not a style choice; it is the correctness
guarantee of this module. Do not "simplify" by dropping parens that look
redundant.

Generated expressions assume a runtime context object ``ctx`` (see
archon.transpile.runtime) with two methods:
    ctx.get(sheet: str, addr: str) -> Any        -- a single cell's value
    ctx.get_range(sheet, start: str, end: str) -> list[Any]  -- a range

IMPORTANT, non-obvious precondition: generate_expr() must be called on
the AST exactly as archon.formula.parser.parse() produces it -- i.e.
BEFORE archon.formula.r1c1.to_r1c1_ast() is applied. A Ref node's
``r1c1`` field holds the ORIGINAL A1-style address text straight out of
the parser (see ast.py's and parser.py's own documented mismatch between
what the field name implies and what the parser actually puts there).
This codegen module relies on that raw-A1-text behavior to look cells up
by their real spreadsheet address; running it on an already-R1C1-
translated tree would generate code that looks up nonsense addresses
like "RC[-2]". This is a real, sharp-edged coupling between these two
modules -- flagged here deliberately rather than silently assumed.

Known, deliberate gaps (not oversights):
  - Only a fixed set of Excel functions is supported (see FUNCTION_MAP).
    An unmapped function name raises CodegenError at generation time
    (a clean, early failure) rather than generating code that would fail
    at runtime or silently do the wrong thing.
  - Range arguments (A1:A10) are only meaningful as arguments to the
    aggregate functions in RANGE_AWARE_FUNCTIONS (SUM, AVERAGE, COUNT,
    MAX, MIN), which accept a mix of scalars and lists and flatten them
    (so SUM(A1, B2:B10, 5) works). Passing a range to any other function
    (e.g. IF(A1:A10, ...)) generates code that will receive a Python list
    where Excel would use array-context evaluation; this module does not
    implement Excel's array-formula semantics and the resulting runtime
    behavior is not guaranteed to match Excel for that case.
  - No vectorized/Polars code generation exists yet -- only scalar,
    per-row Python expressions, evaluated one formula/one row at a time
    via a runtime ``ctx``. The brief's "Python/Polars" transpile target
    is partially met: this is the Python half. A Polars path (operating
    on whole columns at once) is future work, not started.
  - A bare defined-name Ref (parser.py's own documented gap -- a name
    with no '(' and no sheet '!') generates a lookup via ctx.get() using
    the name text as if it were an address, which will not resolve
    correctly against a real cell-grid runtime context. This mirrors an
    existing, already-flagged gap in the parser rather than introducing
    a new one; a real defined-names registry would need to be threaded
    through ctx.get() to fix this properly.
  - The synthetic ARRAY / ARRAY_ROW Func nodes produced by the parser for
    array literals ({1,2;3,4}) are NOT supported by this codegen and
    raise CodegenError -- array literals have no straightforward scalar
    Python translation and are out of scope for this first pass.
"""

from __future__ import annotations

from archon.formula.ast import BinOp, Func, Lit, Node, Ref, UnaryOp

RUNTIME_MODULE_ALIAS = "rt"


class CodegenError(ValueError):
    """Raised when an AST node cannot be translated into Python code."""


# Excel operator -> Python operator. Only operators that mean something
# different, or nothing at all, in Python need an entry; '+', '-', '*',
# '/', '<', '>', '<=', '>=' are identical in both languages.
_OP_MAP = {
    "^": "**",
    "=": "==",
    "<>": "!=",
}

# Excel function name -> runtime module function name. Every entry here
# must have a matching implementation in archon.transpile.runtime.
FUNCTION_MAP = {
    "SUM": "xl_sum",
    "AVERAGE": "xl_average",
    "COUNT": "xl_count",
    "MAX": "xl_max",
    "MIN": "xl_min",
    "IF": "xl_if",
    "AND": "xl_and",
    "OR": "xl_or",
    "NOT": "xl_not",
    "ROUND": "xl_round",
    "ABS": "xl_abs",
    "CONCATENATE": "xl_concatenate",
}

# Functions that are range-aware: a range argument (A1:A10) flattens into
# the function's input rather than being an error. All other functions
# treat a range argument as an opaque list value (see module docstring's
# "known gaps" on array-context semantics).
RANGE_AWARE_FUNCTIONS = frozenset({"SUM", "AVERAGE", "COUNT", "MAX", "MIN"})


def generate_expr(node: Node, default_sheet: str) -> str:
    """Generate a Python expression (as source text) for one AST node.

    default_sheet is used for any Ref whose own `sheet` field is None
    (an unqualified reference belongs to whatever sheet the formula
    itself lives on -- see ast.py's Ref docstring).
    """
    if isinstance(node, Lit):
        return _generate_lit(node)
    if isinstance(node, Ref):
        return _generate_ref(node, default_sheet)
    if isinstance(node, UnaryOp):
        return _generate_unary(node, default_sheet)
    if isinstance(node, BinOp):
        return _generate_binop(node, default_sheet)
    if isinstance(node, Func):
        return _generate_func(node, default_sheet)
    raise CodegenError(f"Unsupported AST node type: {type(node).__name__}")


def generate_python_function(
    node: Node, default_sheet: str, func_name: str = "formula"
) -> str:
    """Wrap generate_expr()'s output in a complete, callable Python
    function definition: ``def <func_name>(ctx): return <expr>``.
    """
    body = generate_expr(node, default_sheet)
    return f"def {func_name}(ctx):\n    return {body}\n"


def _generate_lit(node: Lit) -> str:
    """A literal: emit its Python repr() directly (safe for float/str/bool)."""
    return repr(node.value)


def _generate_ref(node: Ref, default_sheet: str) -> str:
    """A single cell reference: ctx.get(sheet, address)."""
    sheet = node.sheet if node.sheet is not None else default_sheet
    return f"ctx.get({sheet!r}, {node.r1c1!r})"


def _generate_range(node: BinOp, default_sheet: str) -> str:
    """A ':' range whose corners are both Refs: ctx.get_range(sheet, start, end).

    Raises CodegenError if either corner isn't a plain Ref (shouldn't
    happen from the parser's own grammar, but checked defensively) or if
    the two corners disagree on sheet (a cross-sheet range, which Excel
    itself does not support either).
    """
    left, right = node.left, node.right
    if not isinstance(left, Ref) or not isinstance(right, Ref):
        raise CodegenError("Range operator ':' used with non-reference operands")
    left_sheet = left.sheet if left.sheet is not None else default_sheet
    right_sheet = right.sheet if right.sheet is not None else default_sheet
    if left_sheet != right_sheet:
        raise CodegenError(
            f"Cross-sheet range not supported: {left_sheet!r} vs {right_sheet!r}"
        )
    return f"ctx.get_range({left_sheet!r}, {left.r1c1!r}, {right.r1c1!r})"


def _generate_unary(node: UnaryOp, default_sheet: str) -> str:
    """A unary operation, fully parenthesized -- see module docstring."""
    operand_code = generate_expr(node.operand, default_sheet)
    if node.op == "%":
        return f"(({operand_code}) / 100)"
    if node.op == "-":
        return f"(-({operand_code}))"
    if node.op == "+":
        return f"(+({operand_code}))"
    raise CodegenError(f"Unsupported unary operator: {node.op!r}")


def _generate_binop(node: BinOp, default_sheet: str) -> str:
    """A binary operation, fully parenthesized -- see module docstring.

    ':' (range) is handled separately since it has no scalar meaning of
    its own; '&' (concatenation) coerces both sides to str, matching
    Excel's behavior of concatenating numbers and text alike.
    """
    if node.op == ":":
        return _generate_range(node, default_sheet)

    left_code = generate_expr(node.left, default_sheet)
    right_code = generate_expr(node.right, default_sheet)

    if node.op == "&":
        return f"(str({left_code}) + str({right_code}))"

    py_op = _OP_MAP.get(node.op, node.op)
    return f"(({left_code}) {py_op} ({right_code}))"


def _generate_func(node: Func, default_sheet: str) -> str:
    """A function call: dispatch through FUNCTION_MAP to a runtime function."""
    name = node.name.upper()
    if name in ("ARRAY", "ARRAY_ROW"):
        raise CodegenError(
            "Array literals ({1,2;3,4}) are not supported by this codegen"
        )
    if name not in FUNCTION_MAP:
        raise CodegenError(f"Unsupported function: {node.name!r}")

    runtime_name = FUNCTION_MAP[name]
    arg_codes: list[str] = []
    for arg in node.args:
        if isinstance(arg, BinOp) and arg.op == ":":
            if name not in RANGE_AWARE_FUNCTIONS:
                raise CodegenError(
                    f"{node.name} does not accept a range argument "
                    f"(only {sorted(RANGE_AWARE_FUNCTIONS)} do)"
                )
            arg_codes.append(_generate_range(arg, default_sheet))
        else:
            arg_codes.append(generate_expr(arg, default_sheet))

    joined_args = ", ".join(arg_codes)
    return f"{RUNTIME_MODULE_ALIAS}.{runtime_name}({joined_args})"
