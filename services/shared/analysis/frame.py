"""The analysis frame: one row per generation, in a canonical order.

:func:`build_frame` turns observations into a pandas DataFrame with

* base columns (:data:`analysis.spec.BASE_COLUMNS`): generation, task,
  system, model, prompt structure, run index, design, unit and the quality
  flags (``parse_ok``, ``refusal``, ``truncated`` as 1/0, ``retried`` as
  1/0 or missing, ``finish_reason``);
* one column per design factor found in the observations' ``factors``
  (numbers as float64, text as objects with ``None`` for missing; declared
  types in ``inputs.factor_types`` override the inference);
* one column per measure, in dependency order.

Rows are sorted by design, unit, task, system, structure, run index and
generation id, so the same observations give the same frame whatever order a
source delivered them in. :func:`frame_hash` hashes the frame's content in a
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
from analysis.measures import MeasureError, as_text, coerce, evaluate_measures
from analysis.observations import Observation
from analysis.spec import BASE_COLUMNS, measure_order
from analysis.version import ENGINE_VERSION, FRAME_FORMAT_VERSION

SORT_KEYS = ("design", "unit", "task_id", "system", "structure_key", "run_index", "generation_id")
_TEXT_BASE = ("generation_id", "task_id", "system", "model_id", "structure_key", "design", "unit", "finish_reason")
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


def select_observations(observations: Iterable[Observation], inputs: Mapping[str, Any]) -> List[Observation]:
    designs = set(inputs["designs"])
    systems = set(inputs.get("systems") or [])
    structures = set(inputs.get("structures") or [])
    out = []
    for obs in observations:
        if obs.design not in designs:
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


def build_frame(observations: Iterable[Observation], spec: Mapping[str, Any]) -> FrameResult:
    """The frame of ``spec`` (normalized) over ``observations``."""
    import pandas as pd

    inputs = spec["inputs"]
    selected = select_observations(observations, inputs)
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
        return (o.design, o.unit, o.task_id, o.system, o.structure_key or "", o.run_index, o.generation_id)

    obs_list = sorted(unique, key=key)
    n = len(obs_list)
    measures = spec.get("measures") or {}

    factor_names = sorted({name for o in obs_list for name in o.factors})
    clash = [f for f in factor_names if f in BASE_COLUMNS or f in measures]
    if clash:
        raise FrameError(
            "factor name(s) collide with frame columns or measure ids: " + ", ".join(clash)
        )
    for name in factor_names:
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

    declared = inputs.get("factor_types") or {}
    for name in factor_names:
        values = [o.factors.get(name) for o in obs_list]
        kind = declared.get(name) or _factor_kind(values)
        col, bad = _factor_column(values, kind)
        if bad:
            warnings.append(f"factor {name!r}: {bad} value(s) are not {kind} and were set to missing")
        columns[name] = col

    order = measure_order(measures)
    try:
        _, measure_warnings = evaluate_measures(
            order,
            measures,
            columns,
            [o.fields for o in obs_list],
            [o.task_data for o in obs_list],
            n,
        )
    except MeasureError as exc:
        raise FrameError(str(exc)) from None
    warnings.extend(measure_warnings)

    ordered = list(BASE_COLUMNS) + factor_names + [m for m in measures]
    data = {}
    for name in ordered:
        arr = columns[name]
        data[name] = pd.Series(arr, dtype=object) if arr.dtype == object else pd.Series(arr)
    frame = pd.DataFrame(data, columns=ordered)
    counts = {
        "observations": n,
        "designs": int(frame["design"].nunique()) if n else 0,
        "units": int(frame[["design", "unit"]].drop_duplicates().shape[0]) if n else 0,
        "tasks": int(frame["task_id"].nunique()) if n else 0,
        "systems": int(frame["system"].nunique()) if n else 0,
        "parse_failures": int((frame["parse_ok"] == 0).sum()) if n else 0,
    }
    return FrameResult(frame=frame, factors=factor_names, measures=list(measures), warnings=warnings, counts=counts)


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
