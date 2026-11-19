"""Measures: declarative outcome columns of an analysis frame.

Kinds (spec ``measures``):

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
``slot_factor``
    A factor of another slot of the same generation (``meta.benger_variant.slots``):
    ``{"kind": "slot_factor", "factor": "group", "slot": "other"}`` is the
    partner's group in a two-slot design, ``"slot": 1`` the group of slot 1
    (in any frame). Its type is ``number`` when every value is a number,
    else ``text``, unless ``type`` says.
``slot_aggregate``
    A summary over every slot of the row's generation of a per-slot field,
    ``{"kind": "slot_aggregate", "field": "rank_{idx}", "function":
    "is_ranking"}``: ``mean``, ``sum``, ``min``, ``max``, ``sd`` (n-1) and
    ``count`` over the values present, ``is_ranking`` 1 when the values are
    exactly 1..n for the n slots (no value missing, no tie), else 0.
``list``
    An answer's list of items against a gold list (hits, recall, F1,
    Jaccard, ...), :mod:`analysis.list_measures`.
``text_pattern``, ``coder``, ``judge_code``
    Codes read off the answer by a versioned regex set, a coder plugin or
    another system's coding in a coding project, :mod:`analysis.codes`.

Per-slot fields: a field name with ``{idx}`` (``"risk_{idx}"``) reads the
control of one slot, ``{idx}`` replaced by the slot index as the task's
``meta.benger_variant.slots`` and the label config's indexed names use it. Its
``slot`` says which slot: ``own`` (the row's slot in a slot frame, the
default there), ``other`` (the generation's other slot when it has exactly
two) or a slot index.

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


IDX = "{idx}"


class RowSlots:
    """The slots a frame row sees: its own slot index (slot frames) and the
    slots of its generation, ``({"index", "factors"}, ...)``."""

    __slots__ = ("own", "slots", "_by_index")

    def __init__(self, own: Optional[int], slots: Sequence[Mapping[str, Any]]):
        self.own = own
        self.slots = tuple(slots)
        self._by_index = {s["index"]: s for s in self.slots}

    def resolve(self, ref: Any) -> Optional[int]:
        """The slot index ``ref`` (own, other or an index) names, or None."""
        if ref == "own":
            return self.own
        if ref == "other":
            if self.own is None or len(self.slots) != 2:
                return None
            others = [s["index"] for s in self.slots if s["index"] != self.own]
            return others[0] if len(others) == 1 else None
        return int(ref) if ref in self._by_index else None

    def factor(self, index: Optional[int], name: str) -> Any:
        slot = self._by_index.get(index) if index is not None else None
        return (slot.get("factors") or {}).get(name) if slot is not None else None

    def indexes(self) -> List[int]:
        return [s["index"] for s in self.slots]


NO_SLOTS = RowSlots(None, ())


def slot_field_name(template: str, index: Optional[int]) -> Optional[str]:
    if IDX not in template:
        return template
    return template.replace(IDX, str(index)) if index is not None else None


def _infer_kind(values: Sequence[Any]) -> str:
    present = [v for v in values if v is not None]
    if present and all(isinstance(v, (int, float, bool)) for v in present):
        return "number"
    return "text"


def _aggregate(function: str, values: List[float]) -> float:
    present = [v for v in values if not math.isnan(v)]
    if function == "is_ranking":
        if not values or len(present) != len(values):
            return 0.0 if values else math.nan
        return 1.0 if sorted(present) == [float(i) for i in range(1, len(values) + 1)] else 0.0
    if function == "count":
        return float(len(present)) if values else math.nan
    if not present:
        return math.nan
    arr = np.array(present, dtype=float)
    if function == "mean":
        return float(arr.mean())
    if function == "sum":
        return float(arr.sum())
    if function == "min":
        return float(arr.min())
    if function == "max":
        return float(arr.max())
    if function == "sd":
        return float(arr.std(ddof=1)) if len(arr) > 1 else math.nan
    raise MeasureError(f"unknown slot aggregate {function!r}")  # pragma: no cover - schema


def evaluate_measures(
    order: Sequence[str],
    measures: Mapping[str, Mapping[str, Any]],
    columns: Dict[str, np.ndarray],
    fields: Sequence[Mapping[str, Any]],
    task_data: Sequence[Mapping[str, Any]],
    n: int,
    row_slots: Optional[Sequence[RowSlots]] = None,
    codes=None,
) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Compute every measure in ``order`` into ``columns`` (updated in place
    and returned) and return warnings. ``row_slots`` gives every row's
    slots (per-slot fields, slot factors and aggregates need it). ``codes``
    (an :class:`analysis.codes.CodeInputs`) carries what code and list
    measures read besides fields and task data."""
    from analysis.codes import CODE_KINDS, CodeError, CodeInputs, evaluate_code_measure

    warnings: List[str] = []
    slots = row_slots if row_slots is not None else [NO_SLOTS] * n
    if codes is None:
        codes = CodeInputs()
    for mid in order:
        m = measures[mid]
        kind = m["kind"]
        ambiguous: List[str] = []
        if kind in CODE_KINDS:
            try:
                values, vtype = evaluate_code_measure(mid, m, fields, task_data, n, codes)
            except CodeError as exc:
                raise MeasureError(str(exc)) from None
            arr = _array(values, vtype)
            missing = codes.report[-1]["missing"] if codes.report else 0
            if n and missing == n:
                warnings.append(f"measure {mid!r}: the code is missing for every row")
        elif kind == "list":
            from analysis.list_measures import list_measure_value

            name = m["field"]
            values = [list_measure_value(m, f.get(name), d) for f, d in zip(fields, task_data)]
            if n and all(name not in f for f in fields):
                warnings.append(f"measure {mid!r}: no answer has the field {name!r}")
            arr = _array(values, "number")
        elif kind == "field" and "field" in m and IDX in m["field"]:
            vtype = m.get("type", "number")
            ref = m.get("slot", "own")
            values = []
            unresolved = 0
            seen_any = False
            for f, rs in zip(fields, slots):
                name = slot_field_name(m["field"], rs.resolve(ref))
                if name is None:
                    unresolved += 1
                    values.append(coerce(None, vtype))
                    continue
                seen_any = seen_any or name in f
                values.append(coerce(f.get(name), vtype, ambiguous))
            if unresolved:
                warnings.append(f"measure {mid!r}: {unresolved} row(s) have no slot {ref!r}; set to missing")
            if n and not seen_any:
                warnings.append(f"measure {mid!r}: no answer has the field {m['field']!r} for its slot")
            arr = _array(values, "text" if vtype == "text" else "number")
        elif kind == "field":
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
                ref = m.get("slot", "own")
                values = []
                for f, key, rs in zip(fields, keys, slots):
                    text = key if isinstance(key, str) else as_text(
                        None if (isinstance(key, float) and math.isnan(key)) else key
                    )
                    name = mapping.get(text) if text is not None else None
                    if name is not None and IDX in name:
                        name = slot_field_name(name, rs.resolve(ref))
                    values.append(coerce(f.get(name), vtype, ambiguous) if name else coerce(None, vtype))
            arr = _array(values, "text" if vtype == "text" else "number")
        elif kind == "slot_factor":
            raw = [rs.factor(rs.resolve(m["slot"]), m["factor"]) for rs in slots]
            vtype = m.get("type") or _infer_kind(raw)
            unresolved = sum(1 for rs in slots if rs.resolve(m["slot"]) is None)
            if unresolved:
                warnings.append(f"measure {mid!r}: {unresolved} row(s) have no slot {m['slot']!r}; set to missing")
            bad = 0
            values = []
            for v in raw:
                c = coerce(v, vtype)
                if v is not None and (c is None or (isinstance(c, float) and math.isnan(c))):
                    bad += 1
                values.append(c)
            if bad:
                warnings.append(f"measure {mid!r}: {bad} value(s) are not {vtype} and were set to missing")
            arr = _array(values, vtype)
        elif kind == "slot_aggregate":
            values = []
            for f, rs in zip(fields, slots):
                per_slot = [
                    coerce(f.get(slot_field_name(m["field"], i)), "number", ambiguous) for i in rs.indexes()
                ]
                values.append(_aggregate(m["function"], per_slot))
            arr = _array(values, "number")
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
