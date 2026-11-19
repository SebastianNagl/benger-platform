"""Observations: what the frame builder reads, one per generation.

An :class:`Observation` is one answer of one system to one task of a variant
design, flattened to what an analysis needs:

* identity: generation, task, system (the system key ``<model_id>@<parameter
  profile hash>``, or the model id when none was recorded), model id, prompt
  structure and run index;
* the project it belongs to (frames may stack the observations of several
  projects);
* the task's place in its design, read from ``tasks.meta.benger_variant``
  (``{"design", "unit", "factors": {...}, "slots": [...], ...}``, see
  :func:`variant_of_task_meta`), including the task's slots: the records
  inside one answer (one per person or case) with their own factors;
* the parsed answer as typed values per control name (:func:`typed_field_values`
  over Label Studio results);
* the task data, from which gold measures read their paths;
* quality flags (parse status, refusal, truncation, format retry, finish
  reason);
* the full answer text, when a code measure reads it.

Sources produce observations; :mod:`analysis.frame` never touches the
database. :func:`observations_from_records` reads plain dicts (test fixtures,
JSON files); the database reader lives in :mod:`analysis.db_source`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from variant_designs import META_KEY as VARIANT_META_KEY


@dataclass(frozen=True)
class Observation:
    generation_id: str
    task_id: str
    system: str
    model_id: str
    design: str
    unit: str
    factors: Mapping[str, Any]
    fields: Mapping[str, Any]
    task_data: Mapping[str, Any] = field(default_factory=dict)
    structure_key: Optional[str] = None
    run_index: int = 0
    parse_ok: bool = True
    refusal: bool = False
    truncated: bool = False
    retried: Optional[bool] = None
    finish_reason: Optional[str] = None
    project_id: str = ""
    #: The task's slots, ``({"index": int, "factors": {...}}, ...)`` sorted by
    #: index (``meta.benger_variant.slots``; the index is the one the per-slot
    #: control names use, in the design's index base).
    slots: Tuple[Mapping[str, Any], ...] = ()
    #: The full answer text (``generations.response_content``), read only
    #: when a code measure codes the full answer.
    answer_text: Optional[str] = None


class ObservationError(ValueError):
    """A record that cannot become an observation."""


def variant_of_task_meta(meta: Any) -> Optional[Dict[str, Any]]:
    """The ``variant`` block of a task's ``meta``, or None.

    The block is ``{"design": str, "unit": str, "factors": {name: value},
    "slots": [{"index": int, "factors": {...}}, ...], "provenance": {...}}``;
    ``design``, ``unit``, ``factors`` and ``slots`` are read here (see
    :func:`variant_slots`). A block without a design or a unit is treated as
    absent (the task is not part of a design)."""
    if not isinstance(meta, Mapping):
        return None
    variant = meta.get(VARIANT_META_KEY)
    if not isinstance(variant, Mapping):
        return None
    design, unit = variant.get("design"), variant.get("unit")
    if not isinstance(design, str) or not design or unit is None or unit == "":
        return None
    factors = variant.get("factors")
    return {
        "design": design,
        "unit": str(unit),
        "factors": dict(factors) if isinstance(factors, Mapping) else {},
        "slots": variant_slots(variant.get("slots")),
    }


def variant_slots(raw: Any) -> Tuple[Dict[str, Any], ...]:
    """The slots of a ``meta.benger_variant`` block, ``({"index", "factors"}, ...)``
    sorted by index. Entries without a whole-number index are skipped and a
    repeated index keeps its first entry (the design validator refuses
    both when the task is written)."""
    if not isinstance(raw, (list, tuple)):
        return ()
    out: Dict[int, Dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        index = entry.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index in out:
            continue
        factors = entry.get("factors")
        out[index] = {"index": index, "factors": dict(factors) if isinstance(factors, Mapping) else {}}
    return tuple(out[i] for i in sorted(out))


def response_metadata_object(raw: Any) -> Optional[Mapping[str, Any]]:
    """The response metadata as an object: a mapping as it is, JSON text
    decoded; anything else (no metadata, invalid JSON, a non-object) is None."""
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if isinstance(raw, Mapping) else None


def system_key(model_id: str, metadata: Optional[Mapping[str, Any]]) -> str:
    """The system key of a generation as frames name it:
    ``response_metadata.system.key``, else the model id."""
    block = metadata.get("system") if isinstance(metadata, Mapping) else None
    key = block.get("key") if isinstance(block, Mapping) else None
    return key if isinstance(key, str) and key else model_id


def typed_field_values(results: Any) -> Dict[str, Any]:
    """Control name -> typed value of a Label Studio result list.

    Unlike :func:`annotation_utils.extract_all_field_values` (which returns
    numbers and ratings as strings and the first choice only), this keeps
    types: ``number`` and ``rating`` stay numbers, ``choices`` stay a list,
    ``textarea`` gives its text (the first entry of a list), ``labels`` gives
    the span list, anything else its raw value. A result without a
    ``from_name`` is skipped; a repeated control keeps its first result."""
    out: Dict[str, Any] = {}
    if not isinstance(results, list):
        return out
    for item in results:
        if not isinstance(item, Mapping):
            continue
        name = item.get("from_name")
        if not isinstance(name, str) or not name or name in out:
            continue
        value = item.get("value")
        kind = item.get("type")
        if isinstance(value, Mapping):
            if kind == "labels" or "spans" in value:
                out[name] = value.get("spans")
            elif "number" in value:
                out[name] = value.get("number")
            elif "rating" in value:
                out[name] = value.get("rating")
            elif "choices" in value:
                choices = value.get("choices")
                out[name] = list(choices) if isinstance(choices, (list, tuple)) else choices
            elif "text" in value:
                text = value.get("text")
                if isinstance(text, (list, tuple)):
                    text = text[0] if text else None
                out[name] = text
            elif "markdown" in value:
                out[name] = value.get("markdown")
            else:
                out[name] = dict(value)
        else:
            out[name] = value
    return out


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _opt_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _opt_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ObservationError("'answer_text' must be a string")
    return value


def observation_from_record(record: Mapping[str, Any]) -> Observation:
    """One plain-dict record -> :class:`Observation`.

    Keys: ``generation_id``, ``task_id``, ``model_id`` (and optionally
    ``system``, defaulting to the model id), ``project_id``, ``variant`` (the
    ``meta.benger_variant`` block) or ``design``/``unit``/``factors``/``slots`` directly, ``fields`` (typed
    values) or ``parsed_annotation`` (Label Studio results), ``task_data``,
    ``structure_key``, ``run_index``, ``parse_ok``, ``refusal``,
    ``truncated``, ``retried``, ``finish_reason``, ``answer_text``."""
    if not isinstance(record, Mapping):
        raise ObservationError("an observation record must be an object")
    variant = None
    if "variant" in record:
        variant = variant_of_task_meta({VARIANT_META_KEY: record.get("variant")})
    elif "design" in record:
        variant = variant_of_task_meta(
            {VARIANT_META_KEY: {k: record.get(k) for k in ("design", "unit", "factors", "slots")}}
        )
    if variant is None:
        raise ObservationError(
            f"record {record.get('generation_id')!r} has no variant design and unit"
        )
    for key in ("generation_id", "task_id", "model_id"):
        if not isinstance(record.get(key), str) or not record.get(key):
            raise ObservationError(f"record is missing {key!r}")
    if "fields" in record:
        fields = record.get("fields")
        if not isinstance(fields, Mapping):
            raise ObservationError("'fields' must be an object")
        fields = dict(fields)
    else:
        fields = typed_field_values(record.get("parsed_annotation"))
    run_index = record.get("run_index", 0)
    if isinstance(run_index, bool) or not isinstance(run_index, int):
        if isinstance(run_index, float) and math.isfinite(run_index) and run_index.is_integer():
            run_index = int(run_index)
        else:
            raise ObservationError("'run_index' must be a whole number")
    task_data = record.get("task_data")
    if task_data is None:
        task_data = {}
    if not isinstance(task_data, Mapping):
        raise ObservationError("'task_data' must be an object")
    return Observation(
        generation_id=record["generation_id"],
        task_id=record["task_id"],
        system=str(record.get("system") or record["model_id"]),
        model_id=record["model_id"],
        design=variant["design"],
        unit=variant["unit"],
        factors=variant["factors"],
        fields=fields,
        task_data=dict(task_data),
        structure_key=record.get("structure_key"),
        run_index=run_index,
        parse_ok=_bool(record.get("parse_ok"), True),
        refusal=_bool(record.get("refusal"), False),
        truncated=_bool(record.get("truncated"), False),
        retried=_opt_bool(record.get("retried")),
        finish_reason=record.get("finish_reason"),
        project_id=str(record.get("project_id") or ""),
        slots=variant["slots"],
        answer_text=_opt_text(record.get("answer_text")),
    )


def observations_from_records(records: Iterable[Mapping[str, Any]]) -> List[Observation]:
    return [observation_from_record(r) for r in records]
