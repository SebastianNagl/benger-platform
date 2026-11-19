"""Variant designs: the database side (CORE 2.59).

- :func:`check_session_tasks` runs before every ORM flush (registered in
  ``project_models``) and validates ``meta.benger_variant`` of each task the flush
  writes against its design, so every write path (JSON and CSV import, the
  meta PATCH routes, project import and clone, wizard drafts) is covered by
  one rule. Writes outside the ORM are covered by the database itself: the
  trigger keeps the derived columns and refuses edits of frozen designs,
  ``uq_tasks_variant_cell`` allows one task per cell and unit, and
  ``fk_tasks_variant_design`` requires the design.
- The sync service functions below (checks, freeze, spec update, delete,
  serialization) are shared by the API routes (run in a thread) and the
  importers.

The pure rules live in ``variant_designs``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from sqlalchemy import inspect, select, text

import variant_designs as vd

#: Text the trigger's errors start with (SQLSTATE 23001).
FROZEN_MARKER = "variant_design_frozen"
#: The unique index of one task per cell and unit.
CELL_INDEX = "uq_tasks_variant_cell"
#: The foreign key from a task to its design.
DESIGN_FK = "fk_tasks_variant_design"

#: A flat import row (a CSV column, or a key of a row without ``data``)
#: holding ``meta.benger_variant`` as JSON text or an object.
FLAT_META_COLUMN = f"meta.{vd.META_KEY}"

_STREAM_BATCH = 500


class VariantDesignError(Exception):
    """A refused variant-design write. ``status_code`` is the HTTP status
    (422 invalid, 409 conflict with stored state, 404 unknown design)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        problems: Optional[List[Dict[str, Any]]] = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.problems = problems or []
        self.extra = extra

    @property
    def detail(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.problems:
            out["problems"] = self.problems[: vd.MAX_REPORTED_PROBLEMS]
        out.update(self.extra)
        return out


def error_from_db(exc: BaseException) -> Optional[VariantDesignError]:
    """The :class:`VariantDesignError` a database error stands for, if it
    came from the variant guards (trigger, unique cell index, design key)."""
    text = str(getattr(exc, "orig", None) or exc)
    if FROZEN_MARKER in text:
        message = text.split(FROZEN_MARKER + ":", 1)[-1].strip().splitlines()[0]
        return VariantDesignError(409, "variant_design_frozen", message.rstrip(".") + ".")
    if CELL_INDEX in text:
        detail = ""
        for line in text.splitlines():
            if "Key (" in line or "DETAIL" in line:
                detail = " " + line.strip()
                break
        return VariantDesignError(
            409,
            "variant_cell_duplicate",
            "Two tasks would hold the same cell of the same unit of a variant "
            "design." + detail,
        )
    if DESIGN_FK in text and 'update or delete on table "variant_designs"' in text:
        return VariantDesignError(
            409,
            "variant_design_in_use",
            "Tasks name this variant design; it was not deleted.",
        )
    if DESIGN_FK in text:
        return VariantDesignError(
            422,
            "variant_design_unknown",
            "A task names a variant design its project does not have.",
        )
    return None


def _models():
    from project_models import Task, VariantDesign

    return Task, VariantDesign


# --------------------------------------------------------------------------- #
# Flat rows (CSV)
# --------------------------------------------------------------------------- #


def lift_flat_meta(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Split a flat import row into ``(data, meta)``: the reserved
    :data:`FLAT_META_COLUMN` becomes ``meta.benger_variant`` (JSON text is parsed;
    an empty cell means no assignment). Rows without it pass unchanged."""
    if FLAT_META_COLUMN not in row:
        return row, None
    data = {k: v for k, v in row.items() if k != FLAT_META_COLUMN}
    raw = row[FLAT_META_COLUMN]
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return data, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise VariantDesignError(
                422,
                "variant_invalid",
                f"The {FLAT_META_COLUMN!r} column must hold JSON: {exc}",
            )
    return data, {vd.META_KEY: raw}


# --------------------------------------------------------------------------- #
# The flush guard
# --------------------------------------------------------------------------- #


def _task_label(task) -> str:
    parts = [f"task {task.id}"]
    if getattr(task, "inner_id", None) is not None:
        parts.append(f"#{task.inner_id}")
    if getattr(task, "source_task_id", None):
        parts.append(f"(source {task.source_task_id})")
    return " ".join(parts)


def _changed(task, names: Iterable[str]) -> bool:
    state = inspect(task)
    return any(state.attrs[name].history.has_changes() for name in names)


def check_session_tasks(session) -> None:
    """Validate the assignment of every task ``session`` is about to write.

    New tasks with a ``meta.benger_variant`` and changed tasks whose ``meta``,
    ``data`` or project changed are checked against their design: it must
    exist in the task's project, the assignment must fit it, and a frozen
    design takes no new tasks. Frozen edits are refused by the trigger
    (which sees the stored values); a duplicate cell by the unique index.
    """
    Task, VariantDesign = _models()
    pending: List[Any] = []
    for obj in session.new:
        if isinstance(obj, Task) and _variant_of(obj) is not None:
            pending.append(obj)
    for obj in session.dirty:
        if (
            isinstance(obj, Task)
            and _variant_of(obj) is not None
            and _changed(obj, ("meta", "data", "project_id"))
        ):
            pending.append(obj)
    if not pending:
        return

    # The design each stored task is in now (the derived column holds the
    # stored value; an in-place edit of meta leaves no old value in the
    # attribute history).
    stored_keys: Dict[int, Optional[str]] = {}
    with session.no_autoflush:
        for task in pending:
            stored_keys[id(task)] = None if task in session.new else task.variant_design

    # Designs written in this same flush win over the stored rows.
    in_session: Dict[Tuple[str, str], Any] = {}
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, VariantDesign) and obj.project_id and obj.key:
            in_session.setdefault((obj.project_id, obj.key), obj)

    wanted = set()
    for task in pending:
        variant = _variant_of(task)
        key = variant.get("design") if isinstance(variant, dict) else None
        for candidate in (key, stored_keys[id(task)]):
            if isinstance(candidate, str) and task.project_id:
                wanted.add((task.project_id, candidate))
    stored: Dict[Tuple[str, str], Tuple[str, Dict[str, Any], str]] = {}
    missing = [k for k in wanted if k not in in_session]
    if missing:
        with session.no_autoflush:
            for project_id in {p for p, _ in missing}:
                keys = [k for p, k in missing if p == project_id]
                rows = session.execute(
                    select(VariantDesign.key, VariantDesign.spec, VariantDesign.status)
                    .where(
                        VariantDesign.project_id == project_id,
                        VariantDesign.key.in_(keys),
                    )
                    .with_for_update(read=True)
                ).all()
                for key, spec, status in rows:
                    stored[(project_id, key)] = (key, spec, status)
    for (project_id, key), obj in in_session.items():
        if (project_id, key) in wanted:
            stored[(project_id, key)] = (obj.key, obj.spec, obj.status)

    views: Dict[Tuple[str, str], vd.DesignView] = {}
    for task in pending:
        stored_key = stored_keys[id(task)]
        current = stored.get((task.project_id, stored_key)) if stored_key else None
        if (
            current is not None
            and current[2] == vd.STATUS_FROZEN
            and not _changed(task, ("project_id",))
        ):
            # A stored task of a frozen design is the trigger's case: it
            # compares the stored data and assignment and refuses a change
            # with 409, while other meta edits (tags) pass.
            continue
        variant = _variant_of(task)
        problems = vd._schema_problems("task_variant", variant, vd.META_PATH)
        if problems:
            raise VariantDesignError(
                422,
                "variant_invalid",
                f"meta.benger_variant of {_task_label(task)} is invalid.",
                problems,
            )
        found = stored.get((task.project_id, variant["design"]))
        if found is None:
            raise VariantDesignError(
                422,
                "variant_design_unknown",
                f"{_task_label(task)} names the variant design {variant['design']!r}, "
                "which its project does not have. Create or import the design "
                "first.",
            )
        key, spec, status = found
        if status == vd.STATUS_FROZEN:
            # The task is not in this frozen design yet (see above).
            raise VariantDesignError(
                409,
                "variant_design_frozen",
                f"The variant design {key!r} is frozen and takes no new tasks.",
            )
        view = views.get((task.project_id, key))
        if view is None:
            spec_problems = vd.validate_spec(spec)
            if spec_problems:
                raise VariantDesignError(
                    422,
                    "variant_design_invalid",
                    f"The variant design {key!r} is invalid.",
                    spec_problems,
                )
            view = views[(task.project_id, key)] = vd.DesignView.build(key, spec)
        problems = vd.validate_task_variant(view, variant, task.data)
        if problems:
            raise VariantDesignError(
                422,
                "variant_invalid",
                f"meta.benger_variant of {_task_label(task)} does not fit the variant "
                f"design {key!r}.",
                problems,
            )


def _variant_of_meta(meta: Any) -> Any:
    if isinstance(meta, dict):
        return meta.get(vd.META_KEY)
    return None


def _variant_of(task) -> Any:
    return _variant_of_meta(task.meta)


# --------------------------------------------------------------------------- #
# Service functions (sync sessions)
# --------------------------------------------------------------------------- #


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def serialize_design(row, **counts: int) -> Dict[str, Any]:
    out = {
        "id": row.id,
        "project_id": row.project_id,
        "key": row.key,
        "version": row.version,
        "status": row.status,
        "spec": row.spec,
        "spec_sha256": vd.sha256_hex(vd.canonical_json(row.spec)),
        "content_hash": row.content_hash,
        "frozen_at": _iso(row.frozen_at),
        "frozen_by": row.frozen_by,
        "provenance": row.provenance,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    out.update(counts)
    return out


def export_document(row) -> Dict[str, Any]:
    return vd.export_document(
        {
            "key": row.key,
            "version": row.version,
            "status": row.status,
            "spec": row.spec,
            "content_hash": row.content_hash,
            "frozen_at": _iso(row.frozen_at),
            "provenance": row.provenance,
        }
    )


def validate_new_design(key: Any, spec: Any, provenance: Any = None) -> None:
    problems = vd.validate_design_key(key) + vd.validate_spec(spec)
    if provenance is not None and not isinstance(provenance, dict):
        problems.append({"path": "/provenance", "message": "must be an object"})
    if problems:
        raise VariantDesignError(422, "variant_design_invalid", "The variant design is invalid.", problems)


def new_design_row(
    project_id: str,
    key: str,
    spec: Dict[str, Any],
    *,
    created_by: Optional[str],
    provenance: Optional[Dict[str, Any]] = None,
    version: int = 1,
):
    _, VariantDesign = _models()
    validate_new_design(key, spec, provenance)
    return VariantDesign(
        id=str(uuid.uuid4()),
        project_id=project_id,
        key=key,
        version=version,
        spec=spec,
        status=vd.STATUS_DRAFT,
        provenance=provenance,
        created_by=created_by,
    )


def load_design(db, project_id: str, key: str, *, lock: bool = False):
    _, VariantDesign = _models()
    stmt = select(VariantDesign).where(
        VariantDesign.project_id == project_id, VariantDesign.key == key
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalar_one_or_none()


def iter_design_records(db, project_id: str, key: str) -> Iterator[vd.TaskRecord]:
    """The tasks of one design, grouped by unit (database order within)."""
    Task, _ = _models()
    stmt = (
        select(Task.id, Task.inner_id, Task.data, Task.meta)
        .where(Task.project_id == project_id, Task.variant_design == key)
        .order_by(Task.variant_unit, Task.id)
        .execution_options(yield_per=_STREAM_BATCH)
    )
    for task_id, inner_id, data, meta in db.execute(stmt):
        yield vd.TaskRecord(
            id=task_id, inner_id=inner_id, data=data, variant=_variant_of_meta(meta)
        )


def run_checks(db, design) -> Tuple[Dict[str, Any], str]:
    """Balance, invariance and assignment checks over a design's tasks, and
    the content hash they would freeze with."""
    problems = vd.validate_spec(design.spec)
    if problems:
        raise VariantDesignError(
            422, "variant_design_invalid", f"The variant design {design.key!r} is invalid.", problems
        )
    check = vd.DesignCheck(vd.DesignView.build(design.key, design.spec))
    for record in iter_design_records(db, design.project_id, design.key):
        check.feed(record)
    report = check.finish()
    return report, check.content_hash()


def freeze_design(
    db,
    project_id: str,
    key: str,
    user_id: Optional[str],
    *,
    expected_hash: Optional[str] = None,
    frozen_at: Optional[datetime] = None,
):
    """Freeze a draft design (caller commits). Locks the design row first,
    so no task write can slip in between the checks and the status change.
    Raises 409 ``variant_design_checks_failed`` with the report when a check
    fails, 422 ``variant_design_hash_mismatch`` when ``expected_hash`` (an
    imported design's recorded hash) differs."""
    design = load_design(db, project_id, key, lock=True)
    if design is None:
        raise VariantDesignError(404, "variant_design_not_found", f"No variant design {key!r}.")
    if design.status == vd.STATUS_FROZEN:
        raise VariantDesignError(
            409, "variant_design_frozen", f"The variant design {key!r} is already frozen."
        )
    report, digest = run_checks(db, design)
    if not report["ok"]:
        raise VariantDesignError(
            409,
            "variant_design_checks_failed",
            f"The variant design {key!r} fails its checks and stays a draft.",
            report=report,
        )
    if expected_hash is not None and expected_hash != digest:
        raise VariantDesignError(
            422,
            "variant_design_hash_mismatch",
            f"The tasks of the variant design {key!r} do not hash to the recorded "
            f"content hash ({expected_hash}); the file was changed after export.",
            content_hash=digest,
        )
    design.status = vd.STATUS_FROZEN
    design.content_hash = digest
    design.frozen_at = frozen_at or datetime.now(timezone.utc)
    design.frozen_by = user_id
    db.flush()
    return design, report


def update_design_spec(
    db,
    project_id: str,
    key: str,
    spec: Any,
    *,
    expected_version: Optional[int] = None,
    provenance: Any = None,
    set_provenance: bool = False,
):
    """Replace the spec of a draft (caller commits). Every task already in
    the design must fit the new spec, so stored assignments stay valid, and
    the stored cells are derived again from it (two tasks that would share
    a cell refuse the update with a unique violation of ``CELL_INDEX``)."""
    design = load_design(db, project_id, key, lock=True)
    if design is None:
        raise VariantDesignError(404, "variant_design_not_found", f"No variant design {key!r}.")
    if design.status == vd.STATUS_FROZEN:
        raise VariantDesignError(
            409, "variant_design_frozen", f"The variant design {key!r} is frozen."
        )
    if expected_version is not None and expected_version != design.version:
        raise VariantDesignError(
            409,
            "variant_design_version_conflict",
            f"The variant design {key!r} is at version {design.version}, "
            f"not {expected_version}.",
            version=design.version,
        )
    validate_new_design(key, spec, provenance if set_provenance else None)
    view = vd.DesignView.build(key, spec)
    failing: List[Dict[str, Any]] = []
    count = 0
    for record in iter_design_records(db, project_id, key):
        problems = vd.validate_task_variant(view, record.variant, record.data)
        if problems:
            count += 1
            if len(failing) < vd.MAX_REPORTED_PROBLEMS:
                failing.append(
                    {"task_id": record.id, "inner_id": record.inner_id, "errors": problems}
                )
    if count:
        raise VariantDesignError(
            422,
            "variant_design_tasks_misfit",
            f"{count} task(s) of the variant design {key!r} do not fit the new spec.",
            failing,
        )
    design.spec = spec
    design.version = design.version + 1
    if set_provenance:
        design.provenance = provenance
    db.flush()
    db.execute(
        text("UPDATE tasks SET meta = meta WHERE project_id = :p AND variant_design = :k"),
        {"p": project_id, "k": key},
    )
    return design
