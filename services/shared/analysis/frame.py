"""The analysis frame: one row per generation (or per generation and slot),
in a canonical order.

:func:`build_frame` turns observations into a pandas DataFrame with

* base columns (:data:`analysis.spec.BASE_COLUMNS`): generation, project,
  task, system, model, prompt structure, run index, design, unit and the
  quality flags (``parse_ok``, ``refusal``, ``truncated`` as 1/0,
  ``retried`` as 1/0 or missing, ``finish_reason``);
* in a slot frame (``frame.unit = slot``), the slot index ``slot``: one row
  per slot of the task's ``meta.variant.slots`` (the unpivot of per-slot
  answers such as Label Studio Repeater results ``risk_0``, ``risk_1``, ...),
  a generation whose task has no slots contributes no row;
* one column per design factor found in the observations' ``factors``
  (numbers as float64, text as objects with ``None`` for missing; declared
  types in ``inputs.factor_types`` override the inference) and, in a slot
  frame, one per slot factor;
* the columns of the spec's lookups, joined by their key columns
  (:func:`join_lookups`);
* one column per measure, in dependency order.

Rows are sorted by project, design, unit, task, system, structure, run
index, generation id and slot, so the same observations give the same frame
whatever order a source delivered them in. A frame may stack the
observations of several projects (``inputs.projects``); ``project_id`` keeps
them apart. :func:`frame_hash` hashes the frame's content in a
fixed byte layout (independent of the Parquet writer); :func:`to_parquet`
writes the snapshot that analysis runs store.
"""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from analysis.canonical import sha256_hex
from analysis.measures import MeasureError, RowSlots, as_text, coerce, evaluate_measures
from analysis.observations import Observation
from analysis.spec import BASE_COLUMNS, SLOT_COLUMN, measure_order
from analysis.version import ENGINE_VERSION, FRAME_FORMAT_VERSION

SORT_KEYS = (
    "project_id", "design", "unit", "task_id", "system", "structure_key", "run_index", "generation_id", "slot",
)
_TEXT_BASE = (
    "generation_id", "project_id", "task_id", "system", "model_id", "structure_key", "design", "unit",
    "finish_reason",
)
_FLAG_BASE = ("parse_ok", "refusal", "truncated", "retried")


class FrameError(ValueError):
    pass


@dataclass
class FrameResult:
    frame: Any  # pandas.DataFrame
    factors: List[str]
    measures: List[str]
    warnings: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return frame_hash(self.frame)


def select_observations(
    observations: Iterable[Observation], inputs: Mapping[str, Any], home_project: Optional[str] = None
) -> List[Observation]:
    """The observations the inputs select. An observation of a project
    listed in ``inputs.projects`` must be in that project's designs; any
    other (the run's own project, ``home_project`` when given) in
    ``inputs.designs``."""
    designs = set(inputs["designs"])
    by_project = {p["project_id"]: set(p["designs"]) for p in inputs.get("projects") or []}
    systems = set(inputs.get("systems") or [])
    structures = set(inputs.get("structures") or [])
    out = []
    for obs in observations:
        if obs.project_id in by_project and obs.project_id != home_project:
            if obs.design not in by_project[obs.project_id]:
                continue
        elif obs.design not in designs:
            continue
        if systems and obs.system not in systems and obs.model_id not in systems:
            continue
        if structures and obs.structure_key not in structures:
            continue
        out.append(obs)
    return out


def _factor_kind(values: Sequence[Any]) -> str:
    present = [v for v in values if v is not None]
    if present and all(isinstance(v, (int, float, bool)) for v in present):
        return "number"
    return "text"


def _factor_column(values: Sequence[Any], kind: str) -> Tuple[np.ndarray, int]:
    """(column, count of values that did not fit the declared kind)."""
    bad = 0
    if kind == "number":
        out = np.empty(len(values), dtype=float)
        for i, v in enumerate(values):
            c = coerce(v, "number")
            if v is not None and isinstance(c, float) and math.isnan(c):
                bad += 1
            out[i] = c
        return out, bad
    col = np.empty(len(values), dtype=object)
    for i, v in enumerate(values):
        t = as_text(v)
        if v is not None and t is None:
            bad += 1
        col[i] = t
    return col, bad


def _numeric_kind(values: Iterable[Any]) -> bool:
    present = [v for v in values if v is not None]
    return bool(present) and all(isinstance(v, (int, float, bool)) for v in present)


def _typed(values: Sequence[Any], numeric: bool) -> np.ndarray:
    if numeric:
        return np.array([math.nan if v is None else float(v) for v in values], dtype=float)
    return np.array([as_text(v) if v is not None else None for v in values], dtype=object)


def join_lookups(
    columns: Dict[str, np.ndarray],
    n: int,
    lookups: Sequence[Mapping[str, Any]],
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> List[str]:
    """Add every lookup's columns to ``columns`` (in place); returns warnings.

    A frame row matches the lookup row whose key columns equal its own, value
    for value as canonical text (so 1 and 1.0 match, and a missing key matches
    nothing); a key that two lookup rows share is an error. Rows without a
    match take the lookup's ``fill`` value, or missing. A column is numeric
    when every value (and fill) is a number, else text."""
    warnings: List[str] = []
    for lk in lookups:
        lid = lk["id"]
        rows = lk.get("rows")
        if rows is None:
            rows = tables.get(lid)
            if rows is None:
                raise FrameError(f"lookup {lid!r}: its table was not loaded")
        keys = list(lk["keys"].items())
        for frame_col, _ in keys:
            if frame_col not in columns:
                raise FrameError(f"lookup {lid!r}: unknown key column {frame_col!r}")
        index: Dict[Tuple, Mapping[str, Any]] = {}
        for row in rows:
            key = tuple(as_text(row.get(col)) for _, col in keys)
            if any(k is None for k in key):
                continue
            if key in index:
                raise FrameError(f"lookup {lid!r}: the key {key!r} appears in more than one row")
            index[key] = row
        missing_cols = sorted({c for c in lk["columns"].values()} - {c for r in rows for c in r})
        if missing_cols:
            raise FrameError(f"lookup {lid!r}: the table has no column(s) {', '.join(missing_cols)}")
        frame_keys = [columns[frame_col] for frame_col, _ in keys]
        matched: List[Optional[Mapping[str, Any]]] = []
        for i in range(n):
            key = []
            for arr in frame_keys:
                v = arr[i]
                if isinstance(v, (float, np.floating)) and math.isnan(v):
                    v = None
                elif isinstance(v, np.generic):
                    v = v.item()
                key.append(as_text(v))
            matched.append(index.get(tuple(key)) if None not in key else None)
        unmatched = sum(1 for m in matched if m is None)
        if unmatched:
            warnings.append(f"lookup {lid!r}: {unmatched} row(s) without a matching lookup row")
        fill = lk.get("fill") or {}
        for new_col, col in lk["columns"].items():
            values = [m.get(col) if m is not None else fill.get(new_col) for m in matched]
            numeric = _numeric_kind([r.get(col) for r in rows] + [fill.get(new_col)])
            columns[new_col] = _typed(values, numeric)
    return warnings


def build_frame(
    observations: Iterable[Observation],
    spec: Mapping[str, Any],
    *,
    lookup_tables: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
    home_project: Optional[str] = None,
) -> FrameResult:
    """The frame of ``spec`` (normalized) over ``observations``.

    ``lookup_tables`` maps the id of every lookup that names a stored
    ``table`` to its rows (dicts by column name); inline lookups carry their
    rows in the spec."""
    import pandas as pd

    inputs = spec["inputs"]
    slot_frame = (spec.get("frame") or {}).get("unit", "generation") == "slot"
    selected = select_observations(observations, inputs, home_project)
    seen: Dict[str, int] = {}
    unique: List[Observation] = []
    duplicates = 0
    for obs in selected:
        if obs.generation_id in seen:
            duplicates += 1
            continue
        seen[obs.generation_id] = 1
        unique.append(obs)
    warnings: List[str] = []
    if duplicates:
        warnings.append(f"{duplicates} duplicate generation id(s) ignored")

    def key(o: Observation):
        return (
            o.project_id, o.design, o.unit, o.task_id, o.system, o.structure_key or "", o.run_index,
            o.generation_id,
        )

    obs_sorted = sorted(unique, key=key)
    # rows: (observation, own slot or None)
    rows: List[Tuple[Observation, Optional[Mapping[str, Any]]]] = []
    without_slots = 0
    for o in obs_sorted:
        if slot_frame:
            if not o.slots:
                without_slots += 1
            for slot in o.slots:
                rows.append((o, slot))
        else:
            rows.append((o, None))
    if without_slots:
        warnings.append(f"{without_slots} generation(s) of tasks without slots left out of the slot frame")
    obs_list = [o for o, _ in rows]
    n = len(rows)
    measures = spec.get("measures") or {}
    lookups = spec.get("lookups") or []
    lookup_cols = [c for lk in lookups for c in lk["columns"]]

    factor_names = sorted({name for o in obs_list for name in o.factors})
    slot_factor_names = sorted({name for _, s in rows if s is not None for name in s["factors"]})
    reserved = set(BASE_COLUMNS) | set(measures) | set(lookup_cols) | {SLOT_COLUMN if slot_frame else ""}
    clash = [f for f in factor_names + slot_factor_names if f in reserved]
    if clash:
        raise FrameError(
            "factor name(s) collide with frame columns or measure ids: " + ", ".join(sorted(set(clash)))
        )
    both = sorted(set(factor_names) & set(slot_factor_names))
    if both:
        raise FrameError("name(s) used by both a task factor and a slot factor: " + ", ".join(both))
    for name in factor_names + slot_factor_names:
        if not isinstance(name, str) or not name.isidentifier():
            raise FrameError(f"factor name {name!r} is not an identifier")

    columns: Dict[str, np.ndarray] = {}
    for col in _TEXT_BASE:
        columns[col] = np.array([getattr(o, col) for o in obs_list], dtype=object)
    columns["run_index"] = np.array([o.run_index for o in obs_list], dtype=np.int64)
    columns["parse_ok"] = np.array([1.0 if o.parse_ok else 0.0 for o in obs_list])
    columns["refusal"] = np.array([1.0 if o.refusal else 0.0 for o in obs_list])
    columns["truncated"] = np.array([1.0 if o.truncated else 0.0 for o in obs_list])
    columns["retried"] = np.array(
        [math.nan if o.retried is None else (1.0 if o.retried else 0.0) for o in obs_list]
    )
    if slot_frame:
        columns[SLOT_COLUMN] = np.array([s["index"] for _, s in rows], dtype=np.int64)

    declared = inputs.get("factor_types") or {}
    for name in factor_names:
        values = [o.factors.get(name) for o in obs_list]
        kind = declared.get(name) or _factor_kind(values)
        col, bad = _factor_column(values, kind)
        if bad:
            warnings.append(f"factor {name!r}: {bad} value(s) are not {kind} and were set to missing")
        columns[name] = col
    for name in slot_factor_names:
        values = [s["factors"].get(name) for _, s in rows]
        kind = declared.get(name) or _factor_kind(values)
        col, bad = _factor_column(values, kind)
        if bad:
            warnings.append(f"slot factor {name!r}: {bad} value(s) are not {kind} and were set to missing")
        columns[name] = col

    warnings.extend(join_lookups(columns, n, lookups, lookup_tables or {}))

    order = measure_order(measures)
    row_slots = [RowSlots(s["index"] if s is not None else None, o.slots) for o, s in rows]
    try:
        _, measure_warnings = evaluate_measures(
            order,
            measures,
            columns,
            [o.fields for o in obs_list],
            [o.task_data for o in obs_list],
            n,
            row_slots,
        )
    except MeasureError as exc:
        raise FrameError(str(exc)) from None
    warnings.extend(measure_warnings)

    ordered = (
        list(BASE_COLUMNS)
        + ([SLOT_COLUMN] if slot_frame else [])
        + factor_names
        + slot_factor_names
        + lookup_cols
        + [m for m in measures]
    )
    data = {}
    for name in ordered:
        arr = columns[name]
        data[name] = pd.Series(arr, dtype=object) if arr.dtype == object else pd.Series(arr)
    frame = pd.DataFrame(data, columns=ordered)
    counts = {
        "observations": len(obs_sorted),
        "rows": n,
        "projects": len({o.project_id for o in obs_sorted}),
        "designs": int(len({(o.project_id, o.design) for o in obs_sorted})),
        "units": int(len({(o.project_id, o.design, o.unit) for o in obs_sorted})),
        "tasks": int(len({(o.project_id, o.task_id) for o in obs_sorted})),
        "systems": int(len({o.system for o in obs_sorted})),
        "parse_failures": int(sum(1 for o in obs_sorted if not o.parse_ok)),
    }
    if slot_frame:
        counts["generations_without_slots"] = without_slots
    return FrameResult(
        frame=frame,
        factors=factor_names + slot_factor_names,
        measures=list(measures),
        warnings=warnings,
        counts=counts,
    )


# --------------------------------------------------------------------------
# Content hash and Parquet snapshot
# --------------------------------------------------------------------------

_NAN = struct.pack("<d", float("nan"))


def frame_hash(frame) -> str:
    """SHA-256 of a frame's columns, kinds and values in a fixed layout:
    float64 little-endian with one canonical NaN and ``-0.0`` as ``0.0``,
    int64 little-endian, text as a presence byte, an 8-byte length and
    UTF-8."""
    import hashlib

    h = hashlib.sha256()
    h.update(f"benger-analysis-frame\x00{FRAME_FORMAT_VERSION}\x00".encode())
    h.update(struct.pack("<qq", frame.shape[0], frame.shape[1]))
    for name in frame.columns:
        col = frame[name]
        h.update(b"C" + struct.pack("<q", len(name.encode())) + name.encode())
        values = col.to_numpy()
        if values.dtype == object or str(col.dtype) in ("str", "string"):
            h.update(b"s")
            for v in values:
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    h.update(b"\x00")
                else:
                    b = str(v).encode("utf-8")
                    h.update(b"\x01" + struct.pack("<q", len(b)) + b)
        elif np.issubdtype(values.dtype, np.integer):
            h.update(b"i" + np.ascontiguousarray(values, dtype="<i8").tobytes())
        else:
            arr = np.array(values, dtype="<f8", copy=True)
            arr[arr == 0] = 0.0
            raw = bytearray(arr.tobytes())
            nan_idx = np.flatnonzero(np.isnan(arr))
            for i in nan_idx:
                raw[8 * i : 8 * i + 8] = _NAN
            h.update(b"f" + bytes(raw))
    return h.hexdigest()


def to_parquet(frame, *, metadata: Optional[Mapping[str, str]] = None) -> bytes:
    """The frame as Parquet bytes (zstd), with the frame hash and engine
    version in the file's key-value metadata."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    fields = []
    arrays = []
    for name in frame.columns:
        values = frame[name].to_numpy()
        if values.dtype == object or str(frame[name].dtype) in ("str", "string"):
            arrays.append(pa.array([None if v is None else str(v) for v in values], type=pa.string()))
            fields.append(pa.field(name, pa.string()))
        elif np.issubdtype(values.dtype, np.integer):
            arrays.append(pa.array(values.astype(np.int64), type=pa.int64()))
            fields.append(pa.field(name, pa.int64()))
        else:
            arrays.append(pa.array(values.astype(np.float64), type=pa.float64()))
            fields.append(pa.field(name, pa.float64()))
    meta = {
        "benger.frame_hash": frame_hash(frame),
        "benger.engine_version": ENGINE_VERSION,
        "benger.frame_format_version": str(FRAME_FORMAT_VERSION),
    }
    if metadata:
        meta.update({str(k): str(v) for k, v in metadata.items()})
    schema = pa.schema(fields, metadata={k.encode(): v.encode() for k, v in meta.items()})
    table = pa.Table.from_arrays(arrays, schema=schema)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd", write_statistics=False)
    return buf.getvalue()


def from_parquet(data: bytes):
    """Read a snapshot back as a frame with the builder's dtypes."""
    import pandas as pd
    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(data))
    out = {}
    for name, column in zip(table.column_names, table.columns):
        if column.type == "string":
            out[name] = pd.Series(column.to_pylist(), dtype=object)
        else:
            out[name] = pd.Series(column.to_numpy(zero_copy_only=False))
    return pd.DataFrame(out, columns=table.column_names)


def frame_sha256(data: bytes) -> str:
    return sha256_hex(data)
