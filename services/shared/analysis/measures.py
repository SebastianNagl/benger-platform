"""Measures: declarative outcome columns of an analysis frame.

Three kinds (spec ``measures``):

``field``
    A parsed answer value by control name, ``{"kind": "field", "field":
    "share_p", "type": "number"}``, or a choice of control by the value of a
    factor, ``{"kind": "field", "by": "x_role", "fields": {"P": "share_p",
    "D": "share_d"}}`` (role-dependent outcomes).
``expression``
    A derived column, ``{"kind": "expression", "expr": "..."}`` in the
    language of :mod:`analysis.expression`, over fields, factors, gold and
    earlier measures.
``gold``
    A value from the task data, ``{"kind": "gold", "path": "gold.bench_lo"}``
    (dotted path; a numeric segment indexes a list). Gold lives in the task
    and is never part of what a system answers.

Coercion (``type``):

``number``
    int and float as they are, booleans 1/0, numeric text read by
    :func:`analysis.expression.number_from_text` (which never guesses between
    a thousands and a decimal separator), a one-element list by its element;
    anything else is missing. A text with an ambiguous separator
    (``"1,000"``, ``"1.000.000"``) is missing and reported per measure.
``text``
    strings as they are, whole numbers without a decimal point, booleans
    ``true``/``false``, a one-element list by its element; an empty or
    longer list is missing.
``bool``
    booleans and 0/1 as 1.0/0.0, ``"true"``/``"false"`` in any case.

Non-finite numbers (a log of zero, a division by zero) and number texts
with an ambiguous separator (in a ``number`` field or gold value, or read by
``number()`` in an expression) become missing; the frame builder reports how
many per measure.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from analysis.expression import ExpressionError, number_from_text, parse_expression


class MeasureError(ValueError):
    pass


def as_text(value: Any) -> Optional[str]:
    """Canonical text of a scalar (also used for factor values)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
    if isinstance(value, str):
        return value
    return None


def _unwrap(value: Any) -> Tuple[Any, bool]:
    """(scalar, ok): one-element lists unwrap; longer lists are not scalars."""
    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return value[0], True
        return None, False
    return value, True


def coerce(value: Any, kind: str, ambiguous: Optional[List[str]] = None) -> Any:
    """``value`` as ``kind``; ``ambiguous`` (when given) receives every number
    text set to missing for an ambiguous separator."""
    value, ok = _unwrap(value)
    if not ok or value is None:
        return math.nan if kind != "text" else None
    if kind == "number":
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            v = float(value)
            return v if math.isfinite(v) else math.nan
        if isinstance(value, str):
            return number_from_text(value, ambiguous)
        return math.nan
    if kind == "bool":
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)) and value in (0, 1):
            return float(value)
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return 1.0 if value.strip().lower() == "true" else 0.0
        return math.nan
    return as_text(value)


def lookup_path(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, Mapping):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)) and part.lstrip("-").isdigit():
            i = int(part)
            cur = cur[i] if -len(cur) <= i < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _array(values: Sequence[Any], kind: str) -> np.ndarray:
    if kind == "text":
        return np.array(list(values), dtype=object)
    return np.array(list(values), dtype=float)


def evaluate_measures(
    order: Sequence[str],
    measures: Mapping[str, Mapping[str, Any]],
    columns: Dict[str, np.ndarray],
    fields: Sequence[Mapping[str, Any]],
    task_data: Sequence[Mapping[str, Any]],
    n: int,
) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Compute every measure in ``order`` into ``columns`` (updated in place
    and returned) and return warnings."""
    warnings: List[str] = []
    for mid in order:
        m = measures[mid]
        kind = m["kind"]
        ambiguous: List[str] = []
        if kind == "field":
            vtype = m.get("type", "number")
            if "field" in m:
                name = m["field"]
                values = [coerce(f.get(name), vtype, ambiguous) for f in fields]
                if n and all(name not in f for f in fields):
                    warnings.append(f"measure {mid!r}: no answer has the field {name!r}")
            else:
                by = m["by"]
                if by not in columns:
                    raise MeasureError(f"measure {mid!r}: unknown column {by!r}")
                keys = columns[by]
                mapping = m["fields"]
                values = []
                for f, key in zip(fields, keys):
                    text = key if isinstance(key, str) else as_text(
                        None if (isinstance(key, float) and math.isnan(key)) else key
                    )
                    name = mapping.get(text) if text is not None else None
                    values.append(coerce(f.get(name), vtype, ambiguous) if name else coerce(None, vtype))
            arr = _array(values, "text" if vtype == "text" else "number")
        elif kind == "gold":
            vtype = m.get("type", "number")
            values = [coerce(lookup_path(d, m["path"]), vtype, ambiguous) for d in task_data]
            arr = _array(values, "text" if vtype == "text" else "number")
        elif kind == "expression":
            try:
                expr = parse_expression(m["expr"])
                missing = sorted(name for name in expr.names if name not in columns)
                if missing:
                    raise MeasureError(
                        f"measure {mid!r}: unknown column(s) {', '.join(missing)}"
                    )
                _, arr = expr.evaluate(columns, n, ambiguous)
            except ExpressionError as exc:
                raise MeasureError(f"measure {mid!r}: {exc}") from None
        else:  # pragma: no cover - the schema allows nothing else
            raise MeasureError(f"measure {mid!r}: unknown kind {kind!r}")
        if ambiguous:
            warnings.append(
                f"measure {mid!r}: {len(ambiguous)} number text(s) with an ambiguous separator set to missing"
            )
        if arr.dtype != object:
            arr = np.asarray(arr, dtype=float)
            bad = ~np.isfinite(arr) & ~np.isnan(arr)
            if bad.any():
                warnings.append(
                    f"measure {mid!r}: {int(bad.sum())} non-finite value(s) set to missing"
                )
                arr = np.where(bad, np.nan, arr)
        columns[mid] = arr
    return columns, warnings
