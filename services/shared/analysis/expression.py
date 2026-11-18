"""Measure expressions: a small, whitelisted, vectorised language.

An expression derives one frame column from others (parsed fields, design
factors, gold values and earlier measures), for example::

    if(x_role == "P", share_p, 100 - share_p)
    100 * (share_f < 50)
    if(level in (0, 100), 100 * (share_f < 50), null)
    100 * sign * log(amount)

Grammar (version :data:`analysis.version.EXPRESSION_GRAMMAR_VERSION`):

* literals: numbers, strings in single or double quotes, ``true``, ``false``,
  ``null``; names refer to frame columns (identifiers only).
* arithmetic ``+ - * / ** %``, unary ``-`` and ``+``.
* comparisons ``== != < <= > >=`` (chains allowed), ``x in (a, b)`` and
  ``x not in (a, b)`` against a list of literals.
* logic ``and``, ``or``, ``not``.
* functions: ``if(cond, a, b)``, ``abs``, ``log`` (natural), ``exp``,
  ``sqrt``, ``sign``, ``round(x[, digits])`` (half to even), ``clip(x, lo,
  hi)``, ``min(a, b, ...)``, ``max(a, b, ...)``, ``isnull``, ``notnull``,
  ``coalesce(a, b, ...)``, ``number(x)`` (text to number, comma or dot as
  decimal separator).

Nothing else parses: no attribute access, indexing, keywords, lambdas or
comprehensions, and the tree is interpreted here, never handed to ``eval``.

Missing values are first-class. Numbers are float64 with NaN for missing;
text is an object array with ``None``. Comparisons and logic follow
three-valued (Kleene) logic and yield 1.0, 0.0 or NaN, so a comparison with a
missing operand is missing rather than false: ``100 * (share_p == 50)`` is
missing where ``share_p`` is. ``if`` with a missing condition is missing.
``isnull``, ``notnull`` and ``coalesce`` are the ways to turn missing into a
value.
"""

from __future__ import annotations

import ast
import io
import math
import re
import tokenize
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

MAX_EXPRESSION_LENGTH = 4000
MAX_NODES = 1000
MAX_DEPTH = 100

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# name -> (min args, max args or None for unbounded)
FUNCTIONS: Dict[str, Tuple[int, Optional[int]]] = {
    "if": (3, 3),
    "abs": (1, 1),
    "log": (1, 1),
    "exp": (1, 1),
    "sqrt": (1, 1),
    "sign": (1, 1),
    "round": (1, 2),
    "clip": (3, 3),
    "min": (2, None),
    "max": (2, None),
    "isnull": (1, 1),
    "notnull": (1, 1),
    "coalesce": (2, None),
    "number": (1, 1),
}

CONSTANT_NAMES = {"null": None, "true": True, "false": False}
_IF_ALIAS = "__benger_if__"


class ExpressionError(ValueError):
    """An expression that does not parse, or cannot be evaluated."""


# --------------------------------------------------------------------------
# Tree
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Const:
    value: Any


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class BinOp:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: Any


@dataclass(frozen=True)
class Logic:
    op: str  # "and" | "or"
    values: Tuple[Any, ...]


@dataclass(frozen=True)
class Compare:
    ops: Tuple[str, ...]
    operands: Tuple[Any, ...]


@dataclass(frozen=True)
class Member:
    operand: Any
    values: Tuple[Any, ...]
    negate: bool


@dataclass(frozen=True)
class Call:
    fn: str
    args: Tuple[Any, ...]


_BIN = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "**",
    ast.Mod: "%",
}
_CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


def _rename_if(text: str) -> str:
    """``if`` is a Python keyword: rename ``if(`` so ``ast`` can parse it.

    Done on the token stream, so an ``if`` inside a string literal stays."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        raise ExpressionError(f"does not parse: {exc}") from None
    out = []
    for i, tok in enumerate(tokens):
        string = tok.string
        if tok.type == tokenize.NAME and string == "if":
            nxt = next(
                (t for t in tokens[i + 1 :] if t.type not in (tokenize.NL, tokenize.NEWLINE)),
                None,
            )
            if nxt is not None and nxt.string == "(":
                string = _IF_ALIAS
        out.append((tok.type, string))
    return tokenize.untokenize(out)


def _literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and (
        node.value is None or isinstance(node.value, (bool, int, float, str))
    ):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTANT_NAMES:
        return CONSTANT_NAMES[node.id]
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    ):
        v = node.operand.value
        return -v if isinstance(node.op, ast.USub) else v
    raise ExpressionError("the list after 'in' may only hold literals")


class _Builder:
    def __init__(self) -> None:
        self.nodes = 0
        self.depth = 0

    def build(self, node: ast.AST):
        self.depth += 1
        try:
            if self.depth > MAX_DEPTH:
                raise ExpressionError(f"nested too deeply (more than {MAX_DEPTH} levels)")
            return self._build(node)
        finally:
            self.depth -= 1

    def _build(self, node: ast.AST):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ExpressionError(f"too complex (more than {MAX_NODES} nodes)")
        if isinstance(node, ast.Constant):
            v = node.value
            if v is None or isinstance(v, (bool, int, float, str)):
                if isinstance(v, float) and not math.isfinite(v):
                    raise ExpressionError("non-finite literal")
                return Const(v)
            raise ExpressionError(f"unsupported literal {v!r}")
        if isinstance(node, ast.Name):
            if node.id in CONSTANT_NAMES:
                return Const(CONSTANT_NAMES[node.id])
            if node.id == _IF_ALIAS or node.id.startswith("__"):
                raise ExpressionError(f"unsupported name {node.id!r}")
            return Ref(node.id)
        if isinstance(node, ast.BinOp):
            op = _BIN.get(type(node.op))
            if op is None:
                raise ExpressionError(f"unsupported operator {type(node.op).__name__}")
            return BinOp(op, self.build(node.left), self.build(node.right))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return UnaryOp("-", self.build(node.operand))
            if isinstance(node.op, ast.UAdd):
                return UnaryOp("+", self.build(node.operand))
            if isinstance(node.op, ast.Not):
                return UnaryOp("not", self.build(node.operand))
            raise ExpressionError(f"unsupported operator {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            return Logic(op, tuple(self.build(v) for v in node.values))
        if isinstance(node, ast.Compare):
            if len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)):
                right = node.comparators[0]
                if not isinstance(right, (ast.Tuple, ast.List)):
                    raise ExpressionError(
                        "'in' needs a list of literals: x in (1, 2); for one value write "
                        "x in ['a'] or x == 'a'"
                    )
                values = tuple(_literal(e) for e in right.elts)
                if not values:
                    raise ExpressionError("'in' needs a non-empty list")
                kinds = {isinstance(v, str) for v in values if v is not None}
                if len(kinds) > 1:
                    raise ExpressionError("an 'in' list mixes text and numbers")
                return Member(
                    self.build(node.left), values, isinstance(node.ops[0], ast.NotIn)
                )
            ops = []
            for o in node.ops:
                sym = _CMP.get(type(o))
                if sym is None:
                    raise ExpressionError(
                        "'in' cannot be chained with other comparisons"
                        if isinstance(o, (ast.In, ast.NotIn))
                        else f"unsupported comparison {type(o).__name__}"
                    )
                ops.append(sym)
            operands = (self.build(node.left),) + tuple(self.build(c) for c in node.comparators)
            return Compare(tuple(ops), operands)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ExpressionError("only plain function names can be called")
            name = "if" if node.func.id == _IF_ALIAS else node.func.id
            if name not in FUNCTIONS:
                raise ExpressionError(
                    f"unknown function {name!r}; available: {', '.join(sorted(FUNCTIONS))}"
                )
            if node.keywords:
                raise ExpressionError(f"{name}() takes no keyword arguments")
            if any(isinstance(a, ast.Starred) for a in node.args):
                raise ExpressionError(f"{name}() takes no starred arguments")
            lo, hi = FUNCTIONS[name]
            n = len(node.args)
            if n < lo or (hi is not None and n > hi):
                want = f"{lo}" if lo == hi else (f"{lo}+" if hi is None else f"{lo}-{hi}")
                raise ExpressionError(f"{name}() takes {want} arguments, got {n}")
            return Call(name, tuple(self.build(a) for a in node.args))
        raise ExpressionError(f"unsupported syntax: {type(node).__name__}")


def _collect_names(node, out: set) -> None:
    if isinstance(node, Ref):
        out.add(node.name)
    elif isinstance(node, BinOp):
        _collect_names(node.left, out)
        _collect_names(node.right, out)
    elif isinstance(node, UnaryOp):
        _collect_names(node.operand, out)
    elif isinstance(node, (Logic,)):
        for v in node.values:
            _collect_names(v, out)
    elif isinstance(node, Compare):
        for v in node.operands:
            _collect_names(v, out)
    elif isinstance(node, Member):
        _collect_names(node.operand, out)
    elif isinstance(node, Call):
        for a in node.args:
            _collect_names(a, out)


@dataclass(frozen=True)
class Expression:
    text: str
    root: Any
    names: FrozenSet[str]

    def evaluate(self, columns: Mapping[str, Any], n: int):
        """Evaluate over ``columns`` (name -> numpy array of length ``n``).

        Returns ``(kind, array)`` with kind ``"num"`` (float64) or ``"str"``
        (object array of str/None). A bare ``null`` evaluates to an all-missing
        number column."""
        ev = _Evaluator(columns, n)
        value = ev.eval(self.root)
        if value.kind == "null":
            import numpy as np

            return "num", np.full(n, np.nan)
        return value.kind, value.data


def parse_expression(text: str) -> Expression:
    """Parse and check ``text``. Raises :class:`ExpressionError`."""
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("an expression must be a non-empty string")
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(f"longer than {MAX_EXPRESSION_LENGTH} characters")
    if "\n" in text or "\r" in text:
        text = " ".join(text.splitlines())
    source = _rename_if(text.strip())
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"does not parse: {exc.msg}") from None
    except (RecursionError, MemoryError):
        raise ExpressionError(f"nested too deeply (more than {MAX_DEPTH} levels)") from None
    root = _Builder().build(tree.body)
    names: set = set()
    _collect_names(root, names)
    for name in names:
        if not IDENTIFIER.match(name):
            raise ExpressionError(f"invalid column name {name!r}")
    return Expression(text=text, root=root, names=frozenset(names))


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


@dataclass
class _V:
    kind: str  # "num" | "str" | "null"
    data: Any = None


class _Evaluator:
    def __init__(self, columns: Mapping[str, Any], n: int) -> None:
        import numpy as np

        self.np = np
        self.columns = columns
        self.n = n

    # -- helpers ------------------------------------------------------------
    def _num(self, v: _V, what: str):
        if v.kind == "null":
            return self.np.full(self.n, self.np.nan)
        if v.kind != "num":
            raise ExpressionError(f"{what} needs a number, got text")
        return v.data

    def _str_missing(self, a):
        return self.np.fromiter((x is None for x in a), dtype=bool, count=len(a))

    def _bool(self, values, missing):
        np = self.np
        out = values.astype(float)
        out[missing] = np.nan
        return _V("num", out)

    def _truthy(self, v: _V, what: str):
        """(true mask, missing mask) of a condition."""
        np = self.np
        a = self._num(v, what)
        missing = np.isnan(a)
        return (a != 0) & ~missing, missing

    # -- dispatch -----------------------------------------------------------
    def eval(self, node) -> _V:
        np = self.np
        if isinstance(node, Const):
            v = node.value
            if v is None:
                return _V("null")
            if isinstance(v, str):
                return _V("str", np.full(self.n, v, dtype=object))
            return _V("num", np.full(self.n, float(v)))
        if isinstance(node, Ref):
            if node.name not in self.columns:
                raise ExpressionError(f"unknown column {node.name!r}")
            data = self.columns[node.name]
            if getattr(data, "dtype", None) is not None and data.dtype == object:
                return _V("str", data)
            return _V("num", np.asarray(data, dtype=float))
        if isinstance(node, BinOp):
            a = self._num(self.eval(node.left), f"'{node.op}'")
            b = self._num(self.eval(node.right), f"'{node.op}'")
            with np.errstate(all="ignore"):
                if node.op == "+":
                    r = a + b
                elif node.op == "-":
                    r = a - b
                elif node.op == "*":
                    r = a * b
                elif node.op == "/":
                    r = a / b
                elif node.op == "**":
                    r = np.power(a, b)
                else:
                    r = np.mod(a, b)
            return _V("num", r)
        if isinstance(node, UnaryOp):
            v = self.eval(node.operand)
            if node.op == "not":
                t, m = self._truthy(v, "'not'")
                return self._bool(~t, m)
            a = self._num(v, f"unary '{node.op}'")
            return _V("num", -a if node.op == "-" else a.copy())
        if isinstance(node, Logic):
            return self._logic(node)
        if isinstance(node, Compare):
            result = None
            for i, op in enumerate(node.ops):
                part = self._compare(op, self.eval(node.operands[i]), self.eval(node.operands[i + 1]))
                result = part if result is None else self._and(result, part)
            return result
        if isinstance(node, Member):
            return self._member(node)
        if isinstance(node, Call):
            return self._call(node)
        raise ExpressionError(f"cannot evaluate {node!r}")  # pragma: no cover

    def _and(self, a: _V, b: _V) -> _V:
        ta, ma = self._truthy(a, "'and'")
        tb, mb = self._truthy(b, "'and'")
        false = (~ta & ~ma) | (~tb & ~mb)
        missing = (ma | mb) & ~false
        return self._bool(ta & tb & ~missing, missing)

    def _or(self, a: _V, b: _V) -> _V:
        ta, ma = self._truthy(a, "'or'")
        tb, mb = self._truthy(b, "'or'")
        true = ta | tb
        missing = (ma | mb) & ~true
        return self._bool(true, missing)

    def _logic(self, node: Logic) -> _V:
        acc = self.eval(node.values[0])
        for v in node.values[1:]:
            acc = self._and(acc, self.eval(v)) if node.op == "and" else self._or(acc, self.eval(v))
        if len(node.values) == 1:  # pragma: no cover - ast never builds this
            t, m = self._truthy(acc, node.op)
            return self._bool(t, m)
        return acc

    def _compare(self, op: str, a: _V, b: _V) -> _V:
        np = self.np
        if a.kind == "null" or b.kind == "null":
            return _V("num", np.full(self.n, np.nan))
        if a.kind != b.kind:
            raise ExpressionError(f"'{op}' compares text with a number")
        if a.kind == "num":
            missing = np.isnan(a.data) | np.isnan(b.data)
            with np.errstate(invalid="ignore"):
                values = {
                    "==": a.data == b.data,
                    "!=": a.data != b.data,
                    "<": a.data < b.data,
                    "<=": a.data <= b.data,
                    ">": a.data > b.data,
                    ">=": a.data >= b.data,
                }[op]
            return self._bool(values, missing)
        if op not in ("==", "!="):
            raise ExpressionError(f"'{op}' is not defined for text")
        missing = self._str_missing(a.data) | self._str_missing(b.data)
        eq = np.fromiter((x == y for x, y in zip(a.data, b.data)), dtype=bool, count=self.n)
        return self._bool(eq if op == "==" else ~eq, missing)

    def _member(self, node: Member) -> _V:
        np = self.np
        v = self.eval(node.operand)
        values = [x for x in node.values if x is not None]
        if v.kind == "null":
            return _V("num", np.full(self.n, np.nan))
        text = bool(values) and isinstance(values[0], str)
        if v.kind == "str":
            if values and not text:
                raise ExpressionError("'in' compares text with numbers")
            allowed = set(values)
            missing = self._str_missing(v.data)
            hit = np.fromiter((x in allowed for x in v.data), dtype=bool, count=self.n)
        else:
            if text:
                raise ExpressionError("'in' compares a number with text")
            missing = np.isnan(v.data)
            hit = np.isin(v.data, np.array([float(x) for x in values], dtype=float))
        return self._bool(~hit if node.negate else hit, missing)

    def _same_kind(self, values: Sequence[_V], fn: str) -> str:
        kinds = {v.kind for v in values if v.kind != "null"}
        if len(kinds) > 1:
            raise ExpressionError(f"{fn}() mixes text and numbers")
        return kinds.pop() if kinds else "null"

    def _materialize(self, v: _V, kind: str):
        np = self.np
        if v.kind != "null":
            return v.data
        if kind == "str":
            return np.full(self.n, None, dtype=object)
        return np.full(self.n, np.nan)

    def _call(self, node: Call) -> _V:
        np = self.np
        fn = node.fn
        args = [self.eval(a) for a in node.args]
        if fn == "if":
            t, m = self._truthy(args[0], "if()")
            kind = self._same_kind(args[1:], "if")
            if kind == "null":
                return _V("null")
            a = self._materialize(args[1], kind)
            b = self._materialize(args[2], kind)
            out = np.where(t, a, b)
            if kind == "str":
                out = out.astype(object)
                out[m] = None
            else:
                out = out.astype(float)
                out[m] = np.nan
            return _V(kind, out)
        if fn in ("isnull", "notnull"):
            v = args[0]
            if v.kind == "null":
                missing = np.ones(self.n, dtype=bool)
            elif v.kind == "str":
                missing = self._str_missing(v.data)
            else:
                missing = np.isnan(v.data)
            return _V("num", (missing if fn == "isnull" else ~missing).astype(float))
        if fn == "coalesce":
            kind = self._same_kind(args, "coalesce")
            if kind == "null":
                return _V("null")
            out = self._materialize(args[0], kind).copy()
            for v in args[1:]:
                nxt = self._materialize(v, kind)
                gap = self._str_missing(out) if kind == "str" else np.isnan(out)
                out[gap] = nxt[gap]
            return _V(kind, out)
        if fn == "number":
            v = args[0]
            if v.kind != "str":
                return _V("num", self._num(v, "number()").copy())
            return _V("num", np.array([_to_number(x) for x in v.data], dtype=float))
        nums = [self._num(a, f"{fn}()") for a in args]
        with np.errstate(all="ignore"):
            if fn == "abs":
                return _V("num", np.abs(nums[0]))
            if fn == "log":
                return _V("num", np.log(nums[0]))
            if fn == "exp":
                return _V("num", np.exp(nums[0]))
            if fn == "sqrt":
                return _V("num", np.sqrt(nums[0]))
            if fn == "sign":
                return _V("num", np.sign(nums[0]))
            if fn == "round":
                if len(nums) == 1:
                    return _V("num", np.round(nums[0]))
                digits = nums[1]
                if np.isnan(digits).any() or not np.all(digits == digits[0]) or digits[0] != int(digits[0]):
                    raise ExpressionError("round() needs a constant whole number of digits")
                return _V("num", np.round(nums[0], int(digits[0])))
            if fn == "clip":
                x, lo, hi = nums
                out = np.minimum(np.maximum(x, lo), hi)
                return _V("num", out)
            if fn == "min":
                out = nums[0]
                for b in nums[1:]:
                    out = np.minimum(out, b)
                return _V("num", out)
            if fn == "max":
                out = nums[0]
                for b in nums[1:]:
                    out = np.maximum(out, b)
                return _V("num", out)
        raise ExpressionError(f"unknown function {fn!r}")  # pragma: no cover


def _to_number(x) -> float:
    if x is None:
        return math.nan
    s = str(x).strip().replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return math.nan
    return v if math.isfinite(v) else math.nan
