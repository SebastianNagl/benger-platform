"""Observations from the database: the frame builder's data source.

The seam between the platform's tables and the engine. A task belongs to a
variant design through ``tasks.meta.variant`` (``{"design", "unit",
"factors", ...}``; :func:`analysis.observations.variant_of_task_meta`); this
module selects the project's tasks whose design is one of the spec's
``inputs.designs`` and turns every completed generation of those tasks into
an :class:`~analysis.observations.Observation`:

* system: the generation's system key ``response_metadata.system.key``
  (``"<model_id>@<parameter profile hash>"``, recorded since CORE 2.56), or
  the model id for answers generated before; ``model_id`` stays the model id.
  The generation worker stores the metadata as JSON text in the JSON column,
  so both a JSON object and its text are read;
* structure: the prompt structure of its generation job; run index;
* fields: the typed values of ``generations.parsed_annotation``;
* slots: ``meta.variant.slots`` (index and factors per slot), which slot
  frames unpivot;
* quality flags: ``parse_status == "success"``, ``refusal``, ``truncated``,
  ``finish_reason`` and ``retried`` (a format retry, CORE 2.61).

Failed generations are not observations; their number is reported. The
selection filters on ``meta -> variant -> design`` and on ``inputs.structures``
in SQL (tasks.meta is plain JSON, cast to JSONB for the operator) and streams
generations in batches; ``inputs.systems`` is matched in Python against either
the system key or the model id.

A cross-project frame (``inputs.projects``) reads every listed project with
its own designs (:func:`iter_run_observations`). Stored lookup tables are
loaded by :func:`load_lookup_tables`. Sync session only: the engine runs in
the workers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from analysis.ols import EngineError
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


def response_metadata_object(raw: Any) -> Optional[Mapping[str, Any]]:
    """The response metadata as an object: a mapping as it is, JSON text
    decoded; anything else (no metadata, invalid JSON, a non-object) is None."""
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if isinstance(raw, Mapping) else None


def _system(model_id: str, metadata: Optional[Mapping[str, Any]]) -> str:
    block = metadata.get("system") if isinstance(metadata, Mapping) else None
    key = block.get("key") if isinstance(block, Mapping) else None
    return key if isinstance(key, str) and key else model_id


def iter_observations(
    db,
    project_id: str,
    inputs: Mapping[str, Any],
    counts: Optional[Dict[str, int]] = None,
    designs: Optional[Sequence[str]] = None,
) -> Iterator[Observation]:
    """Every completed generation of the project's variant tasks in
    ``designs`` (default ``inputs["designs"]``) as an observation. ``counts``
    (when given) receives ``variant_tasks`` and ``failed_generations``,
    added to what it holds."""
    from sqlalchemy import select

    from models import Generation, ResponseGeneration

    designs = list(designs if designs is not None else inputs["designs"])
    tasks = select_variant_tasks(db, project_id, designs)
    if counts is not None:
        counts["variant_tasks"] = counts.get("variant_tasks", 0) + len(tasks)
        counts.setdefault("failed_generations", 0)
    by_id = {task_id: (data, variant) for task_id, data, variant in tasks}
    ids = list(by_id)
    systems = set(inputs.get("systems") or [])
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
                Generation.retried,
                ResponseGeneration.structure_key,
            )
            .join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
            .where(Generation.task_id.in_(batch))
            .order_by(Generation.task_id, Generation.id)
        )
        if structures:
            stmt = stmt.where(ResponseGeneration.structure_key.in_(structures))
        for row in db.execute(stmt):
            system = _system(row.model_id, response_metadata_object(row.response_metadata))
            if systems and system not in systems and row.model_id not in systems:
                continue
            if row.status != "completed":
                if counts is not None:
                    counts["failed_generations"] += 1
                continue
            data, variant = by_id[row.task_id]
            yield Observation(
                generation_id=row.id,
                task_id=row.task_id,
                system=system,
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
                retried=bool(row.retried),
                finish_reason=row.finish_reason,
                project_id=project_id,
                slots=variant["slots"],
            )


def iter_run_observations(
    db,
    project_id: str,
    inputs: Mapping[str, Any],
    counts: Optional[Dict[str, int]] = None,
) -> Iterator[Observation]:
    """The observations of a run: its own project's ``inputs.designs`` and,
    for a cross-project frame, every project of ``inputs.projects`` with its
    designs."""
    yield from iter_observations(db, project_id, inputs, counts)
    for other in inputs.get("projects") or []:
        if other["project_id"] == project_id:
            continue
        yield from iter_observations(db, other["project_id"], inputs, counts, designs=other["designs"])


def load_lookup_tables(
    db, project_id: str, lookups: Sequence[Mapping[str, Any]]
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """``(rows by lookup id, resolved records)`` of the spec's stored lookup
    tables (inline lookups need nothing). A table is looked up in its
    ``project_id`` (default: the run's project) by name and version; a
    missing table or a ``content_hash`` that differs from the stored one
    fails the run."""
    from sqlalchemy import select

    from models import AnalysisLookupTable

    tables: Dict[str, List[Dict[str, Any]]] = {}
    resolved: List[Dict[str, Any]] = []
    for lk in lookups:
        ref = lk.get("table")
        if not ref:
            continue
        owner = ref.get("project_id") or project_id
        row = db.execute(
            select(AnalysisLookupTable)
            .where(AnalysisLookupTable.project_id == owner)
            .where(AnalysisLookupTable.name == ref["name"])
            .where(AnalysisLookupTable.version == int(ref["version"]))
        ).scalar_one_or_none()
        if row is None:
            raise EngineError(
                f"lookup {lk['id']!r}: table {ref['name']!r} version {ref['version']} does not exist"
                + ("" if owner == project_id else f" in project {owner}")
            )
        if ref.get("content_hash") and ref["content_hash"] != row.content_hash:
            raise EngineError(
                f"lookup {lk['id']!r}: table {ref['name']!r} version {ref['version']} has content hash "
                f"{row.content_hash}, not {ref['content_hash']}"
            )
        columns = list(row.columns)
        tables[lk["id"]] = [dict(zip(columns, values)) for values in row.rows]
        resolved.append(
            {
                "id": lk["id"],
                "project_id": owner,
                "name": row.name,
                "version": row.version,
                "content_hash": row.content_hash,
                "row_count": row.row_count,
            }
        )
    return tables, resolved
