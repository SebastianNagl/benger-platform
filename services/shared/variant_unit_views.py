"""Read models of the units of a variant design (CORE 2.69).

A unit ties the variants of one item together (the same case under every
level of its manipulated factors). The unit view shows every task of one
unit: its cell, the texts the design lets differ with their declared spans,
its gold values and the answers of one system, with the unit's own
assignment, balance and invariance check (the check a freeze runs, here for
one unit), so a reader can put twin prompts side by side and see that they
differ only where the design says. The unit list pages through the units of
a design with their task counts.

The queries take a sync session (the routes call them through
``run_sync``); :func:`shape_unit_view` builds the answer from rows and needs
no database. Access is the route's job
(``routers/projects/variant_designs.py``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import variant_designs as vd

#: Most tasks one unit view returns (a unit is one item under all its
#: variants, usually a handful of tasks).
MAX_UNIT_TASKS = 500
#: Most characters of one text the view returns; longer texts are cut and
#: marked, the full text stays on the task and generation pages.
MAX_TEXT = 20_000
#: Most generations per task in a unit view (the platform caps runs at 100).
MAX_RUNS_PER_TASK = 100
#: Most data fields of one task the view returns.
MAX_LEAVES = 200
#: Largest page of the unit list.
MAX_UNIT_PAGE = 500


class ViewNotFound(LookupError):
    """The design or the unit does not exist (the route answers 404 with
    ``code``: ``variant_design_not_found`` or ``variant_unit_not_found``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _text(value: Any) -> tuple:
    if value is None:
        return None, False
    text = value if isinstance(value, str) else str(value)
    return (text[:MAX_TEXT], True) if len(text) > MAX_TEXT else (text, False)


def _covered(prefix: str, path: str) -> bool:
    return path == prefix or path.startswith(prefix + ".")


def _task_texts(spec: Mapping[str, Any], data: Any, variant: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Every leaf of the task's data in path order, with its kind: text the
    design lets vary inside declared spans (``spanned``, with the spans of
    ``invariance.fields``), a field that may differ freely (``free``,
    ``invariance.free``) or one that must be the same in every task of the
    unit (``fixed``). At most :data:`MAX_LEAVES` leaves, the varying ones
    first."""
    invariance = spec.get("invariance") or {}
    variable = list(invariance.get("fields") or [])
    free = list(invariance.get("free") or [])
    leaves = vd.flatten_leaves(data if isinstance(data, dict) else {"": data})
    spans = vd.task_spans(variant)
    out = []
    for path in sorted(leaves):
        if any(_covered(v, path) for v in variable):
            kind = "spanned"
        elif any(_covered(f, path) for f in free):
            kind = "free"
        else:
            kind = "fixed"
        text, cut = _text(leaves[path])
        ranges = [list(r) for r in spans.get(path, [])] if kind == "spanned" else []
        if cut:
            ranges = [[a, min(b, MAX_TEXT)] for a, b in ranges if a < MAX_TEXT]
        out.append({"path": path, "kind": kind, "text": text, "truncated": cut, "spans": ranges})
    order = {"spanned": 0, "free": 1, "fixed": 2}
    return sorted(out, key=lambda t: order[t["kind"]])[:MAX_LEAVES]


def _slots(variant: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The task's slots (the items inside one answer) with their factors."""
    from analysis.observations import variant_slots

    return [dict(slot) for slot in variant_slots(variant.get("slots"))]


def _gold_values(spec: Mapping[str, Any], data: Any) -> List[Dict[str, Any]]:
    out = []
    for gold in spec.get("gold") or []:
        found, value = vd.resolve_path(data, gold["path"])
        out.append({"name": gold["name"], "path": gold["path"], "value": value if found else None})
    return out


def _design_or_404(db, project_id: str, design_key: str):
    from variant_design_guard import load_design

    design = load_design(db, project_id, design_key)
    if design is None:
        raise ViewNotFound("variant_design_not_found", f"No variant design {design_key!r}.")
    return design


def list_units(db, project_id: str, design_key: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """The units of a design in name order with their task counts:
    ``{"items": [{"unit", "task_count"}], "total", "limit", "offset"}``."""
    from sqlalchemy import func, select

    from project_models import Task

    _design_or_404(db, project_id, design_key)
    limit = max(1, min(int(limit), MAX_UNIT_PAGE))
    offset = max(0, int(offset))
    where = (Task.project_id == project_id, Task.variant_design == design_key, Task.variant_unit.isnot(None))
    total = db.execute(select(func.count(func.distinct(Task.variant_unit))).where(*where)).scalar_one()
    rows = db.execute(
        select(Task.variant_unit, func.count(Task.id))
        .where(*where)
        .group_by(Task.variant_unit)
        .order_by(Task.variant_unit)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [{"unit": unit, "task_count": count} for unit, count in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def unit_view(db, project_id: str, design_key: str, unit: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Every task and answer of one unit (see the module doc): the queries;
    :func:`shape_unit_view` builds the answer."""
    from sqlalchemy import and_, case, func, select
    from sqlalchemy.dialects.postgresql import JSONB

    from models import Generation, ResponseGeneration
    from project_models import Task

    design = _design_or_404(db, project_id, design_key)
    rows = db.execute(
        select(Task.id, Task.inner_id, Task.data, Task.meta)
        .where(Task.project_id == project_id, Task.variant_design == design_key, Task.variant_unit == unit)
        .order_by(Task.inner_id, Task.id)
        .limit(MAX_UNIT_TASKS + 1)
    ).all()
    if not rows:
        raise ViewNotFound(
            "variant_unit_not_found", f"No unit {unit!r} in the variant design {design_key!r}."
        )
    task_ids = [r[0] for r in rows[:MAX_UNIT_TASKS]]
    first_request = func.jsonb_extract_path(Generation.request_record, "requests", "0", type_=JSONB)
    generations = db.execute(
        select(
            Generation.id,
            Generation.generation_id,
            Generation.task_id,
            Generation.model_id,
            Generation.run_index,
            Generation.status,
            Generation.response_content,
            Generation.parsed_annotation,
            Generation.parse_status,
            Generation.refusal,
            Generation.truncated,
            Generation.finish_reason,
            Generation.retried,
            Generation.response_metadata,
            Generation.request_sha256,
            func.jsonb_typeof(Generation.request_record).label("record_type"),
            case(
                (
                    and_(
                        func.jsonb_typeof(func.jsonb_extract_path(Generation.request_record, "requests"))
                        == "array",
                        func.jsonb_typeof(first_request) == "object",
                    ),
                    first_request,
                ),
                else_=None,
            ).label("first_request"),
            Generation.created_at,
            ResponseGeneration.structure_key,
        )
        .join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
        .where(Generation.task_id.in_(task_ids))
        .order_by(Generation.task_id, ResponseGeneration.structure_key, Generation.run_index, Generation.id)
    ).all()
    return shape_unit_view(project_id, design, rows, generations, unit, system)


def _record_for_check(record_type: Optional[str], first_request: Any) -> Any:
    """What the hash check needs of a stored record, from its JSON type and
    its first request: None without a record, a record holding only the
    first request (the one the hash covers) for an object, and a non-object
    stand-in for anything else."""
    if record_type in (None, "null"):
        return None
    if record_type != "object":
        return []
    return {"requests": [first_request]} if first_request is not None else {}


def shape_unit_view(
    project_id: str,
    design: Any,
    task_rows: list,
    generation_rows: list,
    unit: str,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """The unit view from rows (pure).

    ``design`` has ``key``, ``version``, ``status``, ``content_hash``,
    ``frozen_at`` and ``spec``; ``task_rows`` are ``(id, inner_id, data,
    meta)``, at most one more than :data:`MAX_UNIT_TASKS`; ``generation_rows``
    carry the attributes the query of :func:`unit_view` selects, in task and
    run order. ``system`` keeps the answers of one system (its key or its
    model id); ``systems`` lists every system that answered the unit."""
    from ai_services.request_capture import hash_check
    from analysis.observations import response_metadata_object, system_key, typed_field_values

    truncated = len(task_rows) > MAX_UNIT_TASKS
    spec = design.spec or {}
    records, tasks = [], {}
    for task_id, inner_id, data, meta in task_rows[:MAX_UNIT_TASKS]:
        variant = meta.get(vd.META_KEY) if isinstance(meta, dict) else None
        variant = variant if isinstance(variant, dict) else {}
        records.append(vd.TaskRecord(id=task_id, inner_id=inner_id, data=data, variant=variant))
        tasks[task_id] = {
            "id": task_id,
            "inner_id": inner_id,
            "factors": dict(variant.get("factors") or {}),
            "slots": _slots(variant),
            "texts": _task_texts(spec, data, variant),
            "gold": _gold_values(spec, data),
            "generations": [],
            "generations_truncated": False,
        }
    check = vd.DesignCheck(vd.DesignView.build(design.key, spec))
    for record in records:
        check.feed(record)
    report = check.finish()

    systems: set = set()
    for g in generation_rows:
        if g.task_id not in tasks:
            continue
        key = system_key(g.model_id, response_metadata_object(g.response_metadata))
        systems.add(key)
        if system and system not in (key, g.model_id):
            continue
        entry = tasks[g.task_id]["generations"]
        if len(entry) >= MAX_RUNS_PER_TASK:
            tasks[g.task_id]["generations_truncated"] = True
            continue
        content, cut = _text(g.response_content)
        entry.append(
            {
                "id": g.id,
                "parent_id": g.generation_id,
                "model_id": g.model_id,
                "system_key": key,
                "structure_key": g.structure_key,
                "run_index": int(g.run_index or 0),
                "status": g.status,
                "response": content,
                "response_truncated": cut,
                "fields": typed_field_values(g.parsed_annotation),
                "parse_status": g.parse_status,
                "refusal": bool(g.refusal),
                "truncated": bool(g.truncated),
                "finish_reason": g.finish_reason,
                "retried": bool(g.retried),
                "has_request_record": g.record_type == "object",
                "request_sha256": g.request_sha256,
                "hash_check": hash_check(
                    _record_for_check(g.record_type, g.first_request), g.request_sha256
                )[0],
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
        )
    return {
        "project_id": project_id,
        "design": {
            "key": design.key,
            "version": design.version,
            "status": design.status,
            "content_hash": design.content_hash,
            "frozen_at": design.frozen_at.isoformat() if design.frozen_at else None,
            "unit_name": (spec.get("unit") or {}).get("name"),
            "factors": [
                {k: f[k] for k in ("name", "type", "role", "varies", "source", "levels") if k in f}
                for f in spec.get("factors") or []
            ],
            "invariance": spec.get("invariance") or {},
        },
        "unit": unit,
        "system": system,
        "systems": sorted(systems),
        "tasks": list(tasks.values()),
        "tasks_truncated": truncated,
        "check": {k: report[k] for k in ("ok", "task_count", "assignments", "balance", "invariance")},
    }
