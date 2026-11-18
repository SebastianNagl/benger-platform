"""Observations from the database: the frame builder's data source.

The seam between the platform's tables and the engine. A task belongs to a
variant design through ``tasks.meta.variant`` (``{"design", "unit",
"factors", ...}``; :func:`analysis.observations.variant_of_task_meta`); this
module selects the project's tasks whose design is one of the spec's
``inputs.designs`` and turns every completed generation of those tasks into
an :class:`~analysis.observations.Observation`:

* system: the generation's model id (a parameter-profile key can replace it
  here without touching the engine);
* structure: the prompt structure of its generation job; run index;
* fields: the typed values of ``generations.parsed_annotation``;
* quality flags: ``parse_status == "success"``, ``refusal``, ``truncated``,
  ``finish_reason``, and ``retried`` when the response metadata records a
  format retry.

Failed generations are not observations; their number is reported. The
selection filters on ``meta -> variant -> design`` in SQL (tasks.meta is
plain JSON, cast to JSONB for the operator) and streams generations in
batches. Sync session only: the engine runs in the workers.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from analysis.observations import Observation, typed_field_values, variant_of_task_meta

TASK_BATCH = 500


def _variant_design_expr():
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    from project_models import Task

    return cast(Task.meta, JSONB)["variant"]["design"].astext


def select_variant_tasks(db, project_id: str, designs: Sequence[str]) -> List[Tuple[str, Any, Any]]:
    """``[(task_id, data, variant)]`` of the project's tasks in ``designs``."""
    from sqlalchemy import select

    from project_models import Task

    rows = db.execute(
        select(Task.id, Task.data, Task.meta)
        .where(Task.project_id == project_id)
        .where(_variant_design_expr().in_(list(designs)))
        .order_by(Task.id)
    ).all()
    out = []
    for task_id, data, meta in rows:
        variant = variant_of_task_meta(meta)
        if variant is None or variant["design"] not in designs:
            continue
        out.append((task_id, data or {}, variant))
    return out


def _retried(metadata: Any) -> Optional[bool]:
    if isinstance(metadata, Mapping) and "retried" in metadata:
        value = metadata.get("retried")
        return None if value is None else bool(value)
    return None


def iter_observations(
    db,
    project_id: str,
    inputs: Mapping[str, Any],
    counts: Optional[Dict[str, int]] = None,
) -> Iterator[Observation]:
    """Every completed generation of the project's variant tasks in
    ``inputs["designs"]`` as an observation. ``counts`` (when given)
    receives ``variant_tasks`` and ``failed_generations``."""
    from sqlalchemy import select

    from models import Generation, ResponseGeneration

    designs = list(inputs["designs"])
    tasks = select_variant_tasks(db, project_id, designs)
    if counts is not None:
        counts["variant_tasks"] = len(tasks)
        counts["failed_generations"] = 0
    by_id = {task_id: (data, variant) for task_id, data, variant in tasks}
    ids = list(by_id)
    systems = list(inputs.get("systems") or [])
    structures = list(inputs.get("structures") or [])
    for start in range(0, len(ids), TASK_BATCH):
        batch = ids[start : start + TASK_BATCH]
        stmt = (
            select(
                Generation.id,
                Generation.task_id,
                Generation.model_id,
                Generation.run_index,
                Generation.status,
                Generation.parsed_annotation,
                Generation.parse_status,
                Generation.refusal,
                Generation.truncated,
                Generation.finish_reason,
                Generation.response_metadata,
                ResponseGeneration.structure_key,
            )
            .join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
            .where(Generation.task_id.in_(batch))
            .order_by(Generation.task_id, Generation.id)
        )
        if systems:
            stmt = stmt.where(Generation.model_id.in_(systems))
        if structures:
            stmt = stmt.where(ResponseGeneration.structure_key.in_(structures))
        for row in db.execute(stmt):
            if row.status != "completed":
                if counts is not None:
                    counts["failed_generations"] += 1
                continue
            data, variant = by_id[row.task_id]
            yield Observation(
                generation_id=row.id,
                task_id=row.task_id,
                system=row.model_id,
                model_id=row.model_id,
                design=variant["design"],
                unit=variant["unit"],
                factors=variant["factors"],
                fields=typed_field_values(row.parsed_annotation),
                task_data=data if isinstance(data, Mapping) else {},
                structure_key=row.structure_key,
                run_index=int(row.run_index or 0),
                parse_ok=row.parse_status == "success",
                refusal=bool(row.refusal),
                truncated=bool(row.truncated),
                retried=_retried(row.response_metadata),
                finish_reason=row.finish_reason,
            )
