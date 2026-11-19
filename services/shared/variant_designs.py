"""Variant designs: the pure part (no database).

A variant experiment runs the same item in several controlled variants (a
counterfactual party swap, a reordered case file, an added or removed piece of
evidence) and compares the answers. Its design has two halves with one source
of truth each:

- The design itself (factors with typed levels, the unit that ties variants
  together, optional per-answer slots, outcome, gold and invariance bindings)
  is a first-class ``variant_designs`` row whose ``spec`` follows
  ``schemas/variant_design.schema.json``. It can be frozen and is then hashed.
- Each task's place in the design stays in ``task.meta.variant``
  (``schemas/task_variant.schema.json``), so Label Studio import, export and
  project cloning carry it unchanged. The database derives three columns from
  it (``tasks.variant_design``, ``variant_unit``, ``variant_cell``) and a unique
  index on them allows one task per cell and unit.

This module holds what needs no database: schema and semantic validation of a
spec and of a task's assignment, the balance and span-invariance checks over
the tasks of a design, and the content hash a frozen design records. The
database side (the write-path guard, freeze, import and export) is
``variant_design_guard``.
"""

from __future__ import annotations

import difflib
import functools
import hashlib
import itertools
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

#: Key of a design inside its project (also ``meta.variant.design``).
DESIGN_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")

#: The key of ``task.meta`` that holds the assignment. Reserved: no other
#: feature may store anything else under it.
META_KEY = "variant"

#: Version of the content hash recipe (see :func:`content_hash`).
HASH_VERSION = 1

#: Export document format of one design (``GET .../variant-designs/{key}/export``).
EXPORT_FORMAT = "benger.variant_design.v1"

#: How many problems a check report lists per section (all are counted).
MAX_REPORTED_PROBLEMS = 100

#: Largest number of cells the balance check expands a factor product to.
MAX_EXPECTED_CELLS = 100_000

STATUS_DRAFT = "draft"
STATUS_FROZEN = "frozen"

_SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")


# --------------------------------------------------------------------------- #
# JSON helpers
# --------------------------------------------------------------------------- #


def canonical_json(value: Any) -> str:
    """The one serialization every hash and comparison here uses: sorted
    keys, no whitespace, UTF-8 kept as is."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_path(data: Any, path: str) -> Tuple[bool, Any]:
    """Follow a dotted ``task.data`` path; integer segments index lists.

    Returns ``(found, value)``.
    """
    current = data
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return False, None
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _covers(prefix: str, path: str) -> bool:
    return path == prefix or path.startswith(prefix + ".")


def flatten_leaves(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Every leaf of ``data`` by its dotted path (empty containers are leaves)."""
    out: Dict[str, Any] = {}
    if isinstance(data, dict) and data:
        for key, value in data.items():
            out.update(flatten_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(data, list) and data:
        for index, value in enumerate(data):
            out.update(flatten_leaves(value, f"{prefix}.{index}" if prefix else str(index)))
    else:
        out[prefix] = data
    return out


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


@functools.lru_cache(maxsize=None)
def load_schema(name: str) -> Dict[str, Any]:
    """``name`` is ``"variant_design"`` or ``"task_variant"``."""
    with open(os.path.join(_SCHEMA_DIR, f"{name}.schema.json"), encoding="utf-8") as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=None)
def _validator(name: str):
    from jsonschema import Draft202012Validator

    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer(parts: Iterable[Any]) -> str:
    return "/" + "/".join(str(p) for p in parts) if parts else ""


def _schema_problems(name: str, value: Any, base: str = "") -> List[Dict[str, str]]:
    errors = sorted(
        _validator(name).iter_errors(value), key=lambda e: (list(e.absolute_path), e.message)
    )
    return [
        {"path": base + _pointer(list(e.absolute_path)), "message": e.message}
        for e in errors
    ]


# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #


def _level_key(value: Any) -> Tuple[str, Any]:
    """Typed identity of a level: ``True`` is not ``1``, ``1`` is ``1.0``."""
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, (int, float)):
        return ("n", float(value))
    return ("s", value)


def _level_fits_type(factor_type: str, value: Any) -> bool:
    if factor_type == "boolean":
        return isinstance(value, bool)
    if factor_type == "numeric":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    # nominal and ordinal levels are strings, numbers or booleans
    return isinstance(value, (str, int, float))


def cell_key(factors: Dict[str, Any]) -> str:
    """Canonical text of a cell (factor name -> level), for sets and sorting."""
    return canonical_json({k: list(_level_key(v)) for k, v in sorted(factors.items())})


# --------------------------------------------------------------------------- #
# Spec validation
# --------------------------------------------------------------------------- #


def validate_design_key(key: Any) -> List[Dict[str, str]]:
    if not isinstance(key, str) or not DESIGN_KEY_RE.match(key):
        return [
            {
                "path": "/key",
                "message": "must be 1-100 characters of letters, digits, '_', '.' or '-', "
                "starting with a letter or digit",
            }
        ]
    return []


def _factor_problems(factor: Dict[str, Any], path: str, *, slot: bool) -> List[Dict[str, str]]:
    problems: List[Dict[str, str]] = []
    ftype = factor["type"]
    levels = factor.get("levels")
    source = factor.get("source", "task")
    varies = factor.get("varies", "within_unit")
    if ftype in ("nominal", "ordinal") and not levels:
        problems.append({"path": path, "message": f"a {ftype} factor needs levels"})
    if levels:
        for i, level in enumerate(levels):
            if not _level_fits_type(ftype, level):
                problems.append(
                    {"path": f"{path}/levels/{i}", "message": f"not a {ftype} level"}
                )
        keys = [_level_key(v) for v in levels]
        if len(set(keys)) != len(keys):
            problems.append({"path": f"{path}/levels", "message": "levels repeat"})
    for bound in ("minimum", "maximum"):
        if bound in factor and ftype != "numeric":
            problems.append(
                {"path": f"{path}/{bound}", "message": "only numeric factors take bounds"}
            )
    if levels and ftype == "numeric":
        low, high = factor.get("minimum"), factor.get("maximum")
        for i, level in enumerate(levels):
            if not _level_fits_type(ftype, level):
                continue
            if (low is not None and level < low) or (high is not None and level > high):
                problems.append(
                    {"path": f"{path}/levels/{i}", "message": "outside minimum/maximum"}
                )
    if "baseline" in factor:
        baseline = factor["baseline"]
        if not _level_fits_type(ftype, baseline) or (
            levels and _level_key(baseline) not in {_level_key(v) for v in levels}
        ):
            problems.append({"path": f"{path}/baseline", "message": "not one of the levels"})
    if slot:
        if source != "task":
            problems.append(
                {"path": f"{path}/source", "message": "slot factors always come from the task"}
            )
        if varies != "within_unit":
            problems.append(
                {"path": f"{path}/varies", "message": "slot factors cannot be between_units"}
            )
    elif source != "task" and varies != "within_unit":
        problems.append(
            {"path": f"{path}/varies", "message": "only task factors can be between_units"}
        )
    return problems


def validate_spec(spec: Any) -> List[Dict[str, str]]:
    """Every problem of a design spec (empty when valid): schema first, then
    the rules the schema cannot state."""
    problems = _schema_problems("variant_design", spec, "/spec")
    if problems:
        return problems

    names: Dict[str, str] = {}

    def _claim(name: str, where: str) -> None:
        if name in names:
            problems.append(
                {"path": where, "message": f"name {name!r} is already used at {names[name]}"}
            )
        else:
            names[name] = where

    _claim(spec["unit"]["name"], "/spec/unit/name")
    factors = spec["factors"]
    for i, factor in enumerate(factors):
        where = f"/spec/factors/{i}"
        _claim(factor["name"], where + "/name")
        problems.extend(_factor_problems(factor, where, slot=False))

    view_factors = {f["name"]: f for f in factors}
    within_task = [
        f
        for f in factors
        if f.get("source", "task") == "task" and f.get("varies", "within_unit") == "within_unit"
    ]
    cells = spec.get("cells")
    if cells is None:
        for f in within_task:
            if not f.get("levels"):
                problems.append(
                    {
                        "path": f"/spec/factors/{factors.index(f)}/levels",
                        "message": "a within-unit task factor needs levels "
                        "(or the design lists its cells)",
                    }
                )
    else:
        wanted = {f["name"] for f in within_task}
        seen = set()
        for i, cell in enumerate(cells):
            where = f"/spec/cells/{i}"
            if set(cell) != wanted:
                problems.append(
                    {
                        "path": where,
                        "message": "a cell names exactly the within-unit task factors "
                        f"({', '.join(sorted(wanted)) or 'none'})",
                    }
                )
                continue
            for name, value in cell.items():
                problems.extend(
                    _value_problems(view_factors[name], value, f"{where}/{name}")
                )
            key = cell_key(cell)
            if key in seen:
                problems.append({"path": where, "message": "cell repeats"})
            seen.add(key)

    slots = spec.get("slots")
    if slots is not None:
        if "count" in slots and "count_from" in slots:
            problems.append(
                {"path": "/spec/slots", "message": "give either count or count_from, not both"}
            )
        for i, factor in enumerate(slots.get("factors", [])):
            where = f"/spec/slots/factors/{i}"
            _claim(factor["name"], where + "/name")
            problems.extend(_factor_problems(factor, where, slot=True))

    for i, outcome in enumerate(spec.get("outcomes", [])):
        where = f"/spec/outcomes/{i}"
        _claim(outcome["name"], where + "/name")
        per_slot = outcome.get("per_slot", False)
        if per_slot and slots is None:
            problems.append({"path": where, "message": "per_slot needs the design's slots"})
        controls = (
            [outcome["control"]]
            if "control" in outcome
            else list(outcome["by_factor"]["controls"].values())
        )
        for control in controls:
            has_idx = "{idx}" in control
            if per_slot and not has_idx:
                problems.append(
                    {"path": where, "message": f"per-slot control {control!r} needs {{idx}}"}
                )
            if not per_slot and has_idx:
                problems.append(
                    {"path": where, "message": f"{{idx}} in {control!r} needs per_slot"}
                )
        if "by_factor" in outcome:
            ref = outcome["by_factor"]
            factor = view_factors.get(ref["factor"])
            if factor is None or not factor.get("levels") or factor["type"] == "numeric":
                problems.append(
                    {
                        "path": where + "/by_factor/factor",
                        "message": "must name a design factor with nominal, ordinal or "
                        "boolean levels",
                    }
                )
            else:
                wanted = {_level_text(v) for v in factor["levels"]}
                if set(ref["controls"]) != wanted:
                    problems.append(
                        {
                            "path": where + "/by_factor/controls",
                            "message": "needs one control per level "
                            f"({', '.join(sorted(wanted))})",
                        }
                    )

    for i, gold in enumerate(spec.get("gold", [])):
        _claim(gold["name"], f"/spec/gold/{i}/name")

    invariance = spec.get("invariance") or {}
    variable = invariance.get("fields", [])
    free = invariance.get("free", [])
    for i, path in enumerate(variable):
        for other in free:
            if _covers(other, path) or _covers(path, other):
                problems.append(
                    {
                        "path": f"/spec/invariance/fields/{i}",
                        "message": f"overlaps the free path {other!r}",
                    }
                )
    return problems


def _level_text(value: Any) -> str:
    """How a level names a ``by_factor`` control key (JSON object keys are text)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _value_problems(factor: Dict[str, Any], value: Any, where: str) -> List[Dict[str, str]]:
    ftype = factor["type"]
    if not _level_fits_type(ftype, value):
        return [{"path": where, "message": f"not a {ftype} level of factor {factor['name']!r}"}]
    levels = factor.get("levels")
    if levels and _level_key(value) not in {_level_key(v) for v in levels}:
        return [
            {
                "path": where,
                "message": f"{value!r} is not a level of factor {factor['name']!r}",
            }
        ]
    if ftype == "numeric":
        low, high = factor.get("minimum"), factor.get("maximum")
        if (low is not None and value < low) or (high is not None and value > high):
            return [{"path": where, "message": f"{value!r} is outside the factor's range"}]
    return []


# --------------------------------------------------------------------------- #
# A validated spec, ready for task checks
# --------------------------------------------------------------------------- #


@dataclass
class DesignView:
    """A valid spec, indexed for the per-task and per-design checks."""

    key: str
    spec: Dict[str, Any]
    task_factors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    within: List[str] = field(default_factory=list)
    between: List[str] = field(default_factory=list)
    slot_factors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    expected_cells: Optional[List[Dict[str, Any]]] = None
    expected_too_large: bool = False

    @classmethod
    def build(cls, key: str, spec: Dict[str, Any]) -> "DesignView":
        """``spec`` must already pass :func:`validate_spec`."""
        view = cls(key=key, spec=spec)
        for factor in spec["factors"]:
            if factor.get("source", "task") != "task":
                continue
            view.task_factors[factor["name"]] = factor
            if factor.get("varies", "within_unit") == "within_unit":
                view.within.append(factor["name"])
            else:
                view.between.append(factor["name"])
        for factor in (spec.get("slots") or {}).get("factors", []):
            view.slot_factors[factor["name"]] = factor
        if spec.get("cells") is not None:
            view.expected_cells = [dict(c) for c in spec["cells"]]
        else:
            sizes = [len(view.task_factors[n]["levels"]) for n in view.within]
            total = 1
            for size in sizes:
                total *= size
            if total > MAX_EXPECTED_CELLS:
                view.expected_too_large = True
            else:
                view.expected_cells = [
                    dict(zip(view.within, combo))
                    for combo in itertools.product(
                        *(view.task_factors[n]["levels"] for n in view.within)
                    )
                ]
        return view

    @property
    def variable_paths(self) -> List[str]:
        return list((self.spec.get("invariance") or {}).get("fields", []))

    @property
    def free_paths(self) -> List[str]:
        return list((self.spec.get("invariance") or {}).get("free", []))

    def within_cell(self, factors: Dict[str, Any]) -> Dict[str, Any]:
        return {n: factors[n] for n in self.within if n in factors}


def validate_task_variant(
    view: DesignView, variant: Any, data: Any
) -> List[Dict[str, str]]:
    """Every problem of one task's ``meta.variant`` against its design."""
    base = "/meta/variant"
    problems = _schema_problems("task_variant", variant, base)
    if problems:
        return problems
    if variant["design"] != view.key:
        return [{"path": base + "/design", "message": f"is not design {view.key!r}"}]

    factors = variant["factors"]
    wanted = set(view.task_factors)
    if set(factors) != wanted:
        missing = sorted(wanted - set(factors))
        extra = sorted(set(factors) - wanted)
        message = "must name exactly the design's task factors"
        if missing:
            message += f"; missing {', '.join(missing)}"
        if extra:
            message += f"; unknown {', '.join(extra)}"
        problems.append({"path": base + "/factors", "message": message})
    for name in sorted(set(factors) & wanted):
        problems.extend(
            _value_problems(view.task_factors[name], factors[name], f"{base}/factors/{name}")
        )
    if not problems and view.spec.get("cells") is not None:
        allowed = {cell_key(c) for c in view.expected_cells or []}
        if cell_key(view.within_cell(factors)) not in allowed:
            problems.append(
                {"path": base + "/factors", "message": "is not one of the design's cells"}
            )

    slots_spec = view.spec.get("slots")
    slots = variant.get("slots")
    if slots_spec is None:
        if slots is not None:
            problems.append({"path": base + "/slots", "message": "the design has no slots"})
    else:
        problems.extend(_slot_problems(view, slots_spec, slots or [], data, base))

    problems.extend(_span_problems(view, variant, data, base))

    for i, gold in enumerate(view.spec.get("gold", [])):
        if gold.get("required", True):
            found, value = resolve_path(data, gold["path"])
            if not found or value is None:
                problems.append(
                    {
                        "path": "/data/" + gold["path"].replace(".", "/"),
                        "message": f"gold {gold['name']!r} is missing",
                    }
                )
    return problems


def _slot_problems(view, slots_spec, slots, data, base) -> List[Dict[str, str]]:
    problems: List[Dict[str, str]] = []
    index_base = slots_spec.get("index_base", 1)
    count = slots_spec.get("count")
    if "count_from" in slots_spec:
        found, items = resolve_path(data, slots_spec["count_from"])
        if not found or not isinstance(items, list):
            problems.append(
                {
                    "path": "/data/" + slots_spec["count_from"].replace(".", "/"),
                    "message": "the slot list is missing or not a list",
                }
            )
            count = None
        else:
            count = len(items)
    indexes = [s["index"] for s in slots]
    if len(set(indexes)) != len(indexes):
        problems.append({"path": base + "/slots", "message": "slot indexes repeat"})
    if count is not None:
        if sorted(indexes) != list(range(index_base, index_base + count)):
            problems.append(
                {
                    "path": base + "/slots",
                    "message": f"must list slots {index_base}..{index_base + count - 1}",
                }
            )
    elif not slots:
        problems.append({"path": base + "/slots", "message": "the design needs slots"})
    for i, slot in enumerate(slots):
        where = f"{base}/slots/{i}"
        if slot["index"] < index_base:
            problems.append({"path": where + "/index", "message": f"below {index_base}"})
        slot_factors = slot.get("factors", {})
        wanted = set(view.slot_factors)
        if set(slot_factors) != wanted:
            problems.append(
                {
                    "path": where + "/factors",
                    "message": "must name exactly the design's slot factors "
                    f"({', '.join(sorted(wanted)) or 'none'})",
                }
            )
            continue
        for name, value in slot_factors.items():
            problems.extend(
                _value_problems(view.slot_factors[name], value, f"{where}/factors/{name}")
            )
    return problems


def task_spans(variant: Dict[str, Any]) -> Dict[str, List[Tuple[int, int]]]:
    """All declared spans of a task (task level and every slot), per data path,
    sorted and merged."""
    raw: Dict[str, List[Tuple[int, int]]] = {}
    sources = [variant.get("spans") or {}] + [
        s.get("spans") or {} for s in variant.get("slots") or []
    ]
    for spans in sources:
        for path, ranges in spans.items():
            raw.setdefault(path, []).extend((int(a), int(b)) for a, b in ranges)
    merged: Dict[str, List[Tuple[int, int]]] = {}
    for path, ranges in raw.items():
        out: List[Tuple[int, int]] = []
        for start, end in sorted(ranges):
            if out and start <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], end))
            else:
                out.append((start, end))
        merged[path] = out
    return merged


def _span_problems(view, variant, data, base) -> List[Dict[str, str]]:
    problems: List[Dict[str, str]] = []
    variable = view.variable_paths
    sources = [("", variant.get("spans") or {})] + [
        (f"/slots/{i}", s.get("spans") or {}) for i, s in enumerate(variant.get("slots") or [])
    ]
    for prefix, spans in sources:
        for path, ranges in spans.items():
            where = f"{base}{prefix}/spans/{path}"
            if not any(_covers(v, path) for v in variable):
                problems.append(
                    {
                        "path": where,
                        "message": "the design's invariance.fields do not declare this "
                        "path as variable",
                    }
                )
                continue
            found, value = resolve_path(data, path)
            if not found or not isinstance(value, str):
                problems.append({"path": where, "message": "is not a text field of the task"})
                continue
            for start, end in ranges:
                if start > end or end > len(value):
                    problems.append(
                        {
                            "path": where,
                            "message": f"span [{start}, {end}) is outside the text "
                            f"(length {len(value)})",
                        }
                    )
    return problems


# --------------------------------------------------------------------------- #
# Design checks: assignments, balance, invariance, content hash
# --------------------------------------------------------------------------- #


@dataclass
class TaskRecord:
    id: str
    data: Any
    variant: Any
    inner_id: Optional[int] = None


class _Section:
    def __init__(self) -> None:
        self.count = 0
        self.problems: List[Dict[str, Any]] = []

    def add(self, problem: Dict[str, Any]) -> None:
        self.count += 1
        if len(self.problems) < MAX_REPORTED_PROBLEMS:
            self.problems.append(problem)

    def report(self, **extra) -> Dict[str, Any]:
        return {
            "ok": self.count == 0,
            "problem_count": self.count,
            "problems": self.problems,
            **extra,
        }


def _excerpt(text: str, start: int, end: int, context: int = 30) -> str:
    left = max(0, start - context)
    right = min(len(text), end + context)
    return (
        ("..." if left else "")
        + text[left:start]
        + "[["
        + text[start:end]
        + "]]"
        + text[end:right]
        + ("..." if right < len(text) else "")
    )


def _inside(ranges: Sequence[Tuple[int, int]], start: int, end: int) -> bool:
    if start == end:  # an insertion point: inside or at the edge of a span
        return any(a <= start <= b for a, b in ranges)
    return any(a <= start and end <= b for a, b in ranges)


def _outside_segments(text: str, ranges: Sequence[Tuple[int, int]]) -> List[str]:
    out, cursor = [], 0
    for start, end in ranges:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return out


def text_differs_outside_spans(
    a: str, spans_a: Sequence[Tuple[int, int]], b: str, spans_b: Sequence[Tuple[int, int]]
) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """``None`` when every difference between ``a`` and ``b`` lies inside the
    declared spans of each side, else the first offending ranges.

    Fast path: the text outside the spans is the same, piece for piece. Else
    a character diff, where each differing range of ``a`` must lie inside a
    span of ``a`` and the matching range of ``b`` inside a span of ``b``.
    """
    if a == b:
        return None
    if len(spans_a) == len(spans_b) and _outside_segments(a, spans_a) == _outside_segments(
        b, spans_b
    ):
        return None
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if not (_inside(spans_a, i1, i2) and _inside(spans_b, j1, j2)):
            return (i1, i2), (j1, j2)
    return None


class DesignCheck:
    """Runs the checks over the tasks of one design, one unit at a time.

    Feed every task of the design with :meth:`feed`, grouped by unit (all
    tasks of a unit in a row), then call :meth:`finish`. Memory stays at one
    unit plus a short digest per task (for the content hash).
    """

    def __init__(self, view: DesignView) -> None:
        self.view = view
        self.assignments = _Section()
        self.balance = _Section()
        self.invariance = _Section()
        self.task_count = 0
        self.unit_count = 0
        self.pair_count = 0
        self._entries: List[Tuple[str, str, str]] = []
        self._units_seen: set = set()
        self._unit: Optional[str] = None
        self._records: List[TaskRecord] = []

    def feed(self, record: TaskRecord) -> None:
        self.task_count += 1
        variant = record.variant
        problems = validate_task_variant(self.view, variant, record.data)
        if problems:
            self.assignments.add(
                {"task_id": record.id, "inner_id": record.inner_id, "errors": problems}
            )
        unit = variant.get("unit") if isinstance(variant, dict) else None
        if unit != self._unit:
            self._close_unit()
            if unit in self._units_seen:
                raise ValueError("tasks must be fed grouped by unit")
            self._unit = unit
            self._units_seen.add(unit)
        self._records.append(record)
        factors = variant.get("factors") if isinstance(variant, dict) else None
        self._entries.append(
            (
                str(unit),
                cell_key(factors if isinstance(factors, dict) else {}),
                sha256_hex(canonical_json({"data": record.data, "variant": variant})),
            )
        )

    def _close_unit(self) -> None:
        if self._unit is None and not self._records:
            return
        records, unit = self._records, self._unit
        self._records = []
        if not records:
            return
        self.unit_count += 1
        valid = [r for r in records if isinstance(r.variant, dict)]
        self._check_balance(unit, valid)
        self._check_invariance(unit, valid)

    def _check_balance(self, unit, records: List[TaskRecord]) -> None:
        view = self.view
        for name in view.between:
            values = {
                canonical_json(r.variant.get("factors", {}).get(name)) for r in records
            }
            if len(values) > 1:
                self.balance.add(
                    {
                        "unit": unit,
                        "kind": "between_units_factor_varies",
                        "factor": name,
                        "task_ids": [r.id for r in records],
                    }
                )
        present: Dict[str, List[str]] = {}
        cells: Dict[str, Dict[str, Any]] = {}
        for r in records:
            factors = r.variant.get("factors") or {}
            cell = view.within_cell(factors)
            key = cell_key(cell)
            present.setdefault(key, []).append(r.id)
            cells[key] = cell
        for key, ids in present.items():
            if len(ids) > 1:
                self.balance.add(
                    {"unit": unit, "kind": "duplicate_cell", "cell": cells[key], "task_ids": ids}
                )
        if view.expected_cells is None:
            return
        expected = {cell_key(c): c for c in view.expected_cells}
        missing = [expected[k] for k in expected if k not in present]
        unexpected = [cells[k] for k in present if k not in expected]
        if missing or unexpected:
            self.balance.add(
                {
                    "unit": unit,
                    "kind": "cells_differ",
                    "missing": missing[:20],
                    "missing_count": len(missing),
                    "unexpected": unexpected[:20],
                    "unexpected_count": len(unexpected),
                }
            )

    def _check_invariance(self, unit, records: List[TaskRecord]) -> None:
        view = self.view
        variable, free = view.variable_paths, view.free_paths
        prepared = [
            (r, flatten_leaves(r.data if isinstance(r.data, dict) else {"": r.data}),
             task_spans(r.variant))
            for r in records
        ]
        for (ra, leaves_a, spans_a), (rb, leaves_b, spans_b) in itertools.combinations(
            prepared, 2
        ):
            self.pair_count += 1
            for path in sorted(set(leaves_a) | set(leaves_b)):
                if any(_covers(f, path) for f in free):
                    continue
                problem = {"unit": unit, "task_a": ra.id, "task_b": rb.id, "path": path}
                if path not in leaves_a or path not in leaves_b:
                    self.invariance.add({**problem, "kind": "field_missing"})
                    continue
                va, vb = leaves_a[path], leaves_b[path]
                spanned = any(_covers(v, path) for v in variable)
                if spanned and isinstance(va, str) and isinstance(vb, str):
                    hit = text_differs_outside_spans(
                        va, spans_a.get(path, []), vb, spans_b.get(path, [])
                    )
                    if hit is not None:
                        (i1, i2), (j1, j2) = hit
                        self.invariance.add(
                            {
                                **problem,
                                "kind": "differs_outside_spans",
                                "range_a": [i1, i2],
                                "range_b": [j1, j2],
                                "excerpt_a": _excerpt(va, i1, i2),
                                "excerpt_b": _excerpt(vb, j1, j2),
                            }
                        )
                elif canonical_json(va) != canonical_json(vb):
                    self.invariance.add({**problem, "kind": "value_differs"})

    def finish(self) -> Dict[str, Any]:
        self._close_unit()
        view = self.view
        if view.expected_too_large:
            self.balance.add(
                {
                    "kind": "too_many_cells",
                    "message": f"the factor product exceeds {MAX_EXPECTED_CELLS} cells; "
                    "list the design's cells instead",
                }
            )
        if self.task_count == 0:
            self.assignments.add({"kind": "no_tasks", "message": "the design has no tasks"})
        report = {
            "design": view.key,
            "task_count": self.task_count,
            "unit_count": self.unit_count,
            "assignments": self.assignments.report(),
            "balance": self.balance.report(
                expected_cells_per_unit=(
                    len(view.expected_cells) if view.expected_cells is not None else None
                )
            ),
            "invariance": self.invariance.report(checked_pairs=self.pair_count),
        }
        report["ok"] = all(report[s]["ok"] for s in ("assignments", "balance", "invariance"))
        return report

    def content_hash(self) -> str:
        """See :func:`content_hash`; valid after :meth:`finish`."""
        return content_hash(self.view.key, self.view.spec, self._entries)


def content_hash(key: str, spec: Dict[str, Any], entries: Iterable[Tuple[str, str, str]]) -> str:
    """The hash a frozen design records: the key, the spec and, per task in
    (unit, cell) order, the digest of its data and assignment. Independent of
    task ids, database collation and JSON key order, so an exported and
    re-imported design hashes the same."""
    return sha256_hex(
        canonical_json(
            {
                "hash_version": HASH_VERSION,
                "key": key,
                "spec": spec,
                "tasks": sorted(list(e) for e in entries),
            }
        )
    )


def iter_grouped(records: Iterable[TaskRecord]) -> Iterator[TaskRecord]:
    """``records`` grouped by unit (stable), for callers that cannot sort in
    the database. Holds all records in memory."""
    groups: Dict[Any, List[TaskRecord]] = {}
    for record in records:
        unit = record.variant.get("unit") if isinstance(record.variant, dict) else None
        groups.setdefault(unit, []).append(record)
    for unit_records in groups.values():
        yield from unit_records


def check_design(view: DesignView, records: Iterable[TaskRecord]) -> Tuple[Dict[str, Any], str]:
    """Run every check over ``records`` (any order). Returns the report and
    the content hash."""
    check = DesignCheck(view)
    for record in iter_grouped(records):
        check.feed(record)
    report = check.finish()
    return report, check.content_hash()


def export_document(row: Dict[str, Any]) -> Dict[str, Any]:
    """The portable form of one design (also the element of the
    ``variant_designs`` array in project exports)."""
    return {
        "format": EXPORT_FORMAT,
        "key": row["key"],
        "version": row.get("version", 1),
        "status": row.get("status", STATUS_DRAFT),
        "spec": row["spec"],
        "content_hash": row.get("content_hash"),
        "frozen_at": row.get("frozen_at"),
        "provenance": row.get("provenance"),
    }
