"""Observations: what the frame builder reads, one per generation.

An :class:`Observation` is one answer of one system to one task of a variant
design, flattened to what an analysis needs:

* identity: generation, task, system (the system key ``<model_id>@<parameter
  profile hash>``, or the model id when none was recorded), model id, prompt
  structure and run index;
* the task's place in its design, read from ``tasks.meta.variant``
  (``{"design", "unit", "factors": {...}, ...}``, see
  :func:`variant_of_task_meta`);
* the parsed answer as typed values per control name (:func:`typed_field_values`
  over Label Studio results);
* the task data, from which gold measures read their paths;
* quality flags (parse status, refusal, truncation, format retry, finish
  reason).

Sources produce observations; :mod:`analysis.frame` never touches the
database. :func:`observations_from_records` reads plain dicts (test fixtures,
JSON files); the database reader lives in :mod:`analysis.db_source`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional


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


class ObservationError(ValueError):
    """A record that cannot become an observation."""


def variant_of_task_meta(meta: Any) -> Optional[Dict[str, Any]]:
    """The ``variant`` block of a task's ``meta``, or None.

    The block is ``{"design": str, "unit": str, "factors": {name: value},
    "slots": [...], "provenance": {...}}``; only ``design``, ``unit`` and
    ``factors`` are read here. A block without a design or a unit is treated
    as absent (the task is not part of a design)."""
    if not isinstance(meta, Mapping):
        return None
    variant = meta.get("variant")
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
    }


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


def observation_from_record(record: Mapping[str, Any]) -> Observation:
    """One plain-dict record -> :class:`Observation`.

    Keys: ``generation_id``, ``task_id``, ``model_id`` (and optionally
    ``system``, defaulting to the model id), ``variant`` (the ``meta.variant``
    block) or ``design``/``unit``/``factors`` directly, ``fields`` (typed
    values) or ``parsed_annotation`` (Label Studio results), ``task_data``,
    ``structure_key``, ``run_index``, ``parse_ok``, ``refusal``,
    ``truncated``, ``retried``, ``finish_reason``."""
    if not isinstance(record, Mapping):
        raise ObservationError("an observation record must be an object")
    variant = None
    if "variant" in record:
        variant = variant_of_task_meta({"variant": record.get("variant")})
    elif "design" in record:
        variant = variant_of_task_meta(
            {"variant": {k: record.get(k) for k in ("design", "unit", "factors")}}
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
    )


def observations_from_records(records: Iterable[Mapping[str, Any]]) -> List[Observation]:
    return [observation_from_record(r) for r in records]
