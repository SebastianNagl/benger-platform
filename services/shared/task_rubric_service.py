"""Write-side invariants for per-task rubrics (Bewertungsbogen), async.

One implementation of "how a rubric row changes" shared by the platform
router (``routers/task_rubrics.py``) and the extended overlay (the
Bewertungsbogen PATCH endpoint, the Vertretbar exam create/content PUT):

- ``create_task_rubric``: validate → normalize → derive ``criteria`` and
  ``total_points`` from the structure → row (optionally activated).
- ``edit_task_rubric``: a rubric that already scored gradings is never
  rewritten in place — its ``details.rubric_id`` references must keep
  resolving to the instrument the grade was computed against. Such a rubric
  is CLONED (new row carries the edit, old row archived with
  ``superseded_by``); an unreferenced rubric is edited in place.
- ``activate_task_rubric`` / ``archive_task_rubric``: the one-active-per-task
  invariant (``ux_task_rubrics_one_active`` is non-deferred, so demotion is
  flushed before promotion) plus the ``task.data["bewertungsbogen"]`` mirror.
  On a project with ``rubric_review_required`` a sheet is activated only
  when a person confirmed it (``review_state == "confirmed"``), else
  ``RubricReviewRequired`` is raised before any write. Every activation path
  (create with ``status="active"``, the clone of an edited active sheet, the
  platform routes and the overlay's own writes) goes through this rule.
- ``remirror_project_rubrics`` (async) / ``remirror_project_rubrics_sync``:
  the mirror shows the exam's Notenschlüssel, so every writer of
  ``evaluation_config.grade_scale`` re-renders the mirrors of the project
  after a key change. Two entry points over one SQL builder: the extended
  exam router and the project PATCH run on the async lane, the eval-config
  PUT on the sync one.

Callers own the transaction (``await db.commit()``); every function flushes
so ids and the unique index are settled when it returns.
"""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from grade_scale_history import GRADE_SCALE_KEY, grade_scale_changed
from project_models import Project, Task, TaskRubric
from rubric_structure import (
    criteria_from_structure,
    grade_scale_applies,
    mirror_rubric_into_task_data,
    normalize_grade_scale,
    normalize_structure,
    rubric_mirror_text,
    total_points_from_structure,
    validate_grade_scale,
    validate_structure,
)

logger = logging.getLogger(__name__)


class _Unset:
    """Sentinel for "field not supplied" (distinct from an explicit ``None``)."""

    _instance: Optional["_Unset"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _Unset()


#: ``review_state`` of a sheet a person checked and confirmed (the value the
#: activation rule reads; every other value, NULL included, is "not confirmed").
REVIEW_STATE_CONFIRMED = "confirmed"

#: Largest ``origin`` (JSON) ``create_task_rubric`` stores.
MAX_ORIGIN_BYTES = 4096


class RubricReviewRequired(Exception):
    """Activation refused: the project requires a confirmed check first."""

    code = "rubric_review_required"

    def __init__(self, rubric_id: str):
        super().__init__(rubric_id)
        self.rubric_id = rubric_id


class RubricValidationError(ValueError):
    """Contract violations of the submitted structure / grade scale.

    ``errors`` is the list of human-readable violations; ``str(exc)`` joins
    them so a router can map the error to ``422 "Invalid Bewertungsbogen: …"``.
    """

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__(self.errors)

    def __str__(self) -> str:
        return "; ".join(self.errors)


# Rows whose LLM or human grading snapshot references the rubric. ``metrics``
# is native JSONB (migration 087); the subquery filters to objects before the
# lateral jsonb_each so scalar blobs never reach the function.
_REFERENCED_SQL = text(
    """
    SELECT 1
    FROM (
        SELECT metrics
        FROM task_evaluations
        WHERE task_id = :task_id AND jsonb_typeof(metrics) = 'object'
    ) te, jsonb_each(te.metrics) j
    WHERE jsonb_typeof(j.value) = 'object'
      AND j.value->'details'->>'rubric_id' = :rubric_id
    LIMIT 1
    """
)


async def _project_evaluation_config(db: AsyncSession, project_id: Optional[str]) -> Any:
    """The project's ``evaluation_config`` (it holds the exam's Notenschlüssel
    that the task-data mirror renders)."""
    if not project_id:
        return None
    result = await db.execute(select(Project.evaluation_config).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def _review_required(db: AsyncSession, project_id: Optional[str]) -> bool:
    """``projects.rubric_review_required`` of ``project_id`` (False when unknown)."""
    if not project_id:
        return False
    result = await db.execute(
        select(Project.rubric_review_required).where(Project.id == project_id)
    )
    return bool(result.scalar_one_or_none())


async def ensure_activation_allowed(
    db: AsyncSession, *, rubric_id: str, project_id: Optional[str], review_state: Optional[str]
) -> None:
    """Raise ``RubricReviewRequired`` when the project requires a confirmed
    check and the sheet has none. Writes nothing, so callers run it before
    their first write."""
    if review_state == REVIEW_STATE_CONFIRMED:
        return
    if await _review_required(db, project_id):
        raise RubricReviewRequired(rubric_id)


def _validated_origin(origin: Any) -> Dict[str, Any]:
    if not isinstance(origin, dict):
        raise RubricValidationError(["origin must be an object"])
    try:
        size = len(json.dumps(origin, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise RubricValidationError(["origin must be JSON"]) from None
    if size > MAX_ORIGIN_BYTES:
        raise RubricValidationError(
            [f"origin is {size} bytes, at most {MAX_ORIGIN_BYTES} are stored"]
        )
    return origin


async def rubric_referenced_by_gradings(db: AsyncSession, rubric_id: str, task_id: str) -> bool:
    """True when any task_evaluations row of ``task_id`` was scored against ``rubric_id``."""
    result = await db.execute(_REFERENCED_SQL, {"task_id": task_id, "rubric_id": rubric_id})
    return result.first() is not None


def _node_signature(node: Dict[str, Any]) -> tuple:
    return (
        node.get("level"),
        node.get("kind"),
        node.get("label") or "",
        node.get("title") or "",
        node.get("note"),
        node.get("key"),
        node.get("max_score"),
        node.get("emphasis"),
        tuple(node.get("hints") or []),
        tuple(
            (r.get("text"), r.get("points"), r.get("standard"), r.get("element"))
            for r in node.get("requirements") or []
        ),
    )


def structure_equal(a: Any, b: Any) -> bool:
    """Content equality of two structures after normalization (ids ignored)."""
    if a is None or b is None:
        return a is None and b is None
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    na = normalize_structure(a)["nodes"]
    nb = normalize_structure(b)["nodes"]
    if len(na) != len(nb):
        return False
    return all(_node_signature(x) == _node_signature(y) for x, y in zip(na, nb))


def _clean_title(title: Any) -> Optional[str]:
    if title is None:
        return None
    return str(title).strip() or None


def _validated(structure: Any, grade_scale: Any, *, total_fallback: Any = None):
    """``(normalized_structure|None, normalized_scale|None|UNSET, errors)``."""
    errors: List[str] = []
    normalized = None
    if structure is not UNSET:
        if structure is None:
            errors.append("structure cannot be null")
        else:
            structure_errors = validate_structure(structure)
            errors.extend(structure_errors)
            if not structure_errors:
                normalized = normalize_structure(structure)
    total = total_points_from_structure(normalized) if normalized is not None else total_fallback
    scale: Any = UNSET
    if grade_scale is not UNSET:
        if grade_scale is None:
            scale = None
        else:
            scale_errors = validate_grade_scale(grade_scale, total)
            errors.extend(scale_errors)
            if not scale_errors:
                scale = normalize_grade_scale(grade_scale)
    return normalized, scale, errors


async def create_task_rubric(
    db: AsyncSession,
    *,
    task,
    project_id: str,
    actor_id: Optional[str],
    structure: Dict[str, Any],
    grade_scale: Optional[Dict[str, Any]],
    title: Optional[str],
    source: str = "human",
    status: str = "candidate",
    generation_metadata: Optional[Dict[str, Any]] = None,
    origin: Optional[Dict[str, Any]] = None,
) -> TaskRubric:
    """Persist a new rubric row from a structure (raises RubricValidationError).

    ``origin`` (where the sheet came from, e.g. ``{"kind": "upload",
    "file_name": ..., "file_sha256": ..., "parser": "table"}`` or
    ``{"kind": "manual"}``; a JSON object of at most 4 KB) is stored as
    ``generation_metadata["origin"]``. A new row has no check recorded, so
    ``status="active"`` on a project that requires the check raises
    ``RubricReviewRequired`` before the row is added.
    """
    normalized, scale, errors = _validated(structure, grade_scale)
    if errors:
        raise RubricValidationError(errors)
    assert normalized is not None
    if origin is not None:
        generation_metadata = {**(generation_metadata or {}), "origin": _validated_origin(origin)}
    rubric_id = str(uuid.uuid4())
    if status == "active":
        await ensure_activation_allowed(
            db, rubric_id=rubric_id, project_id=project_id, review_state=None
        )
    rubric = TaskRubric(
        id=rubric_id,
        task_id=task.id,
        project_id=project_id,
        title=_clean_title(title),
        criteria=criteria_from_structure(normalized),
        total_points=float(total_points_from_structure(normalized)),
        structure=normalized,
        grade_scale=None if scale is UNSET else scale,
        source=source,
        status="candidate",
        generation_metadata=generation_metadata,
        created_by=actor_id,
    )
    db.add(rubric)
    await db.flush()
    if status == "active":
        await activate_task_rubric(db, rubric, task)
    elif status == "archived":
        rubric.status = "archived"
        await db.flush()
    return rubric


async def edit_task_rubric(
    db: AsyncSession,
    rubric: TaskRubric,
    task,
    *,
    structure: Any = UNSET,
    grade_scale: Any = UNSET,
    title: Any = UNSET,
    actor_id: Optional[str],
) -> TaskRubric:
    """Apply an edit; returns the row that now carries it (a clone when the
    rubric already scored gradings — callers re-point to ``result.id``).

    Omitted fields (``UNSET``) are left alone; ``grade_scale=None`` clears
    the scale (default table applies); ``title=None`` clears the title.
    A no-op edit (same structure and scale) never clones.
    """
    normalized, scale, errors = _validated(
        structure, grade_scale, total_fallback=rubric.total_points
    )
    if errors:
        raise RubricValidationError(errors)

    structure_changed = normalized is not None and not structure_equal(normalized, rubric.structure)
    current_scale = normalize_grade_scale(rubric.grade_scale) if isinstance(rubric.grade_scale, dict) else None
    scale_changed = scale is not UNSET and scale != current_scale
    title_changed = title is not UNSET and _clean_title(title) != rubric.title
    content_changed = structure_changed or scale_changed

    if content_changed and await rubric_referenced_by_gradings(db, rubric.id, task.id):
        return await _clone_for_edit(
            db,
            rubric,
            task,
            structure=normalized if structure_changed else UNSET,
            grade_scale=scale if scale_changed else UNSET,
            title=title,
            actor_id=actor_id,
        )

    if structure_changed:
        rubric.structure = normalized
        rubric.criteria = criteria_from_structure(normalized)
        rubric.total_points = float(total_points_from_structure(normalized))
        # The pre-rendered document text and the scoring data written with
        # it now disagree with the edited outline. Drop them, so the judge
        # renders the structure and grades by the requirements the outline
        # itself lists (the full generator document stays as provenance).
        metadata = dict(rubric.generation_metadata or {})
        dropped = [
            metadata.pop(key, None)
            for key in ("rendered_text", "rendered_text_replace", "checklist_spec")
        ]
        if any(value is not None for value in dropped):
            metadata["rendered_text_invalidated_by_edit"] = True
            rubric.generation_metadata = metadata
    if scale_changed:
        rubric.grade_scale = scale
    if content_changed and rubric.source == "llm":
        rubric.source = "llm_edited"
    if title_changed:
        rubric.title = _clean_title(title)
    if (content_changed or title_changed) and rubric.status == "active" and task is not None:
        mirror_rubric_into_task_data(
            task, rubric, await _project_evaluation_config(db, rubric.project_id)
        )
    await db.flush()
    return rubric


async def _clone_for_edit(
    db: AsyncSession,
    old: TaskRubric,
    task,
    *,
    structure: Any,
    grade_scale: Any,
    title: Any,
    actor_id: Optional[str],
) -> TaskRubric:
    old_meta = dict(old.generation_metadata or {})
    clone_meta: Dict[str, Any] = {"cloned_from": old.id}
    # The contract version, and the review notes of a generated sheet with
    # the record of who confirmed them: an overlay asks for the confirmation
    # before a sheet with open notes is activated, and an edit must neither
    # lose the notes nor the confirmation (the edit in place keeps both).
    # Where the sheet came from (``origin``: the uploaded file, the total it
    # states) stays true of the clone as well.
    for key in ("contract_version", "review", "origin"):
        if key in old_meta:
            clone_meta[key] = old_meta[key]
    if structure is UNSET:
        # Only the Notenschlüssel changed: the rendered texts and the scoring
        # data written for the outline still describe the clone, as they do
        # after the same edit in place. Without them the clone would lose
        # the sheet's alternative solution paths.
        for key in ("rendered_text", "rendered_text_replace", "checklist_spec"):
            if key in old_meta:
                clone_meta[key] = old_meta[key]

    if structure is not UNSET:
        clone_structure = structure
        clone_criteria = criteria_from_structure(structure)
        clone_total = float(total_points_from_structure(structure))
    else:
        clone_structure = old.structure
        clone_criteria = old.criteria
        clone_total = float(old.total_points or 100.0)

    clone_id = str(uuid.uuid4())
    was_active = old.status == "active"
    if was_active:
        # The clone takes over the check of the old row (copied below), so
        # it passes exactly when the old row would; refuse before writing,
        # naming the sheet the caller edited (the clone never exists).
        await ensure_activation_allowed(
            db, rubric_id=old.id, project_id=old.project_id, review_state=old.review_state
        )
    clone = TaskRubric(
        id=clone_id,
        task_id=old.task_id,
        project_id=old.project_id,
        title=old.title if title is UNSET else _clean_title(title),
        criteria=clone_criteria,
        total_points=clone_total,
        structure=clone_structure,
        grade_scale=old.grade_scale if grade_scale is UNSET else grade_scale,
        source="human" if old.source == "human" else "llm_edited",
        generator_model_id=old.generator_model_id,
        prompt_key=old.prompt_key,
        prompt_version=old.prompt_version,
        generation_metadata=clone_meta,
        status="candidate",
        # An edit of a checked sheet keeps it checked, as the edit in place
        # does; the overlay's review workflow decides whether an edit
        # reopens the check.
        review_state=old.review_state,
        reviewed_at=old.reviewed_at,
        reviewed_by=old.reviewed_by,
        created_by=actor_id,
    )
    old.status = "archived"
    old.generation_metadata = {**old_meta, "superseded_by": clone.id}
    db.add(clone)
    # The demotion must hit the DB before the promotion (non-deferred
    # partial unique index).
    await db.flush()
    if was_active:
        await activate_task_rubric(db, clone, task)
    return clone


async def activate_task_rubric(
    db: AsyncSession, rubric: TaskRubric, task, *, demote_to: str = "candidate"
) -> None:
    """Make ``rubric`` the task's active rubric (others → ``demote_to``) and mirror it.

    Raises ``RubricReviewRequired`` before any write when the rubric's
    project requires a confirmed check and the rubric has none.
    """
    await ensure_activation_allowed(
        db, rubric_id=rubric.id, project_id=rubric.project_id, review_state=rubric.review_state
    )
    others = await db.execute(
        select(TaskRubric).where(
            TaskRubric.task_id == rubric.task_id,
            TaskRubric.status == "active",
            TaskRubric.id != rubric.id,
        )
    )
    for row in others.scalars().all():
        row.status = demote_to
    await db.flush()
    rubric.status = "active"
    await db.flush()
    if task is not None:
        mirror_rubric_into_task_data(
            task, rubric, await _project_evaluation_config(db, rubric.project_id)
        )


async def archive_task_rubric(db: AsyncSession, rubric: TaskRubric, task) -> None:
    """Archive ``rubric``; when it was active the task-data mirror is removed."""
    was_active = rubric.status == "active"
    rubric.status = "archived"
    await db.flush()
    if was_active and task is not None:
        mirror_rubric_into_task_data(task, None)


# ---------------------------------------------------------------------------
# Re-mirroring after the exam's Notenschlüssel changed
# ---------------------------------------------------------------------------


def _select_active_rubrics_of_project(project_id: str):
    """Every task of the project that has an ACTIVE rubric, with that rubric.

    One round trip for the whole project, however many tasks it has. The
    task comes back as the ORM row (its ``data`` is rewritten; a task the
    session already holds is the same object). The rubric comes back as the
    columns the rendering reads, and of ``generation_metadata`` only
    ``rendered_text``: the metadata of a generated sheet also carries the
    full generator documents, which a re-render never needs. At most one
    rubric per task is active (``ux_task_rubrics_one_active``).
    """
    return (
        select(
            Task,
            TaskRubric.title,
            TaskRubric.structure,
            TaskRubric.criteria,
            TaskRubric.total_points,
            TaskRubric.grade_scale,
            TaskRubric.generation_metadata["rendered_text"].label("rendered_text"),
        )
        .join(
            TaskRubric,
            and_(TaskRubric.task_id == Task.id, TaskRubric.status == "active"),
        )
        .where(Task.project_id == project_id)
    )


def _remirror_rows(rows: Sequence[Any], project_config: Any) -> int:
    """Re-render the mirror of each ``(task, rubric columns…)`` row.

    Only a task whose mirror text actually differs is written, so a project
    whose mirrors already show the key costs no UPDATE. Returns the number
    of tasks rewritten.
    """
    # An explicit document, never None: None would let the mirror fall back
    # to a project the session may hold with the OLD config.
    config = project_config if isinstance(project_config, dict) else {}
    changed = 0
    for row in rows:
        task = row[0]
        sheet = SimpleNamespace(
            title=row.title,
            structure=row.structure,
            criteria=row.criteria,
            total_points=row.total_points,
            grade_scale=row.grade_scale,
            generation_metadata={"rendered_text": row.rendered_text},
        )
        rendered = rubric_mirror_text(sheet, config)
        if (task.data or {}).get("bewertungsbogen") == rendered:
            continue
        mirror_rubric_into_task_data(task, sheet, config)
        changed += 1
    return changed


async def remirror_project_rubrics(
    db: AsyncSession, project_id: str, project_config: Any
) -> int:
    """Re-render every active rubric's task-data mirror of ``project_id``.

    Call it after the project's Notenschlüssel changed, with the project's
    NEW ``evaluation_config``: the mirror shows the key that grades the exam
    (``rubric_structure.resolve_grade_scale``: the exam's key, else the
    sheet's own, else the standard key), and it is otherwise refreshed only
    when a sheet is activated or edited. Returns the number of tasks whose
    mirror changed. Flushes; the caller commits.
    """
    rows = (await db.execute(_select_active_rubrics_of_project(project_id))).all()
    changed = _remirror_rows(rows, project_config)
    if changed:
        await db.flush()
        logger.info(
            "Notenschlüssel change: re-mirrored %s of %s sheets of project %s",
            changed,
            len(rows),
            project_id,
        )
    return changed


def rubric_mirrors_changed(old_config: Any, new_config: Any) -> bool:
    """Whether saving ``new_config`` over ``old_config`` (a project's
    ``evaluation_config``) changes what the sheets' task-data mirrors show:
    the key that grades the exam, or whether a key is shown at all
    (``grade_scale_applies``). Every writer of the config re-mirrors on it."""
    old = old_config if isinstance(old_config, dict) else {}
    new = new_config if isinstance(new_config, dict) else {}
    return grade_scale_changed(
        old.get(GRADE_SCALE_KEY), new.get(GRADE_SCALE_KEY)
    ) or grade_scale_applies(old) != grade_scale_applies(new)


def remirror_project_rubrics_sync(db: Session, project_id: str, project_config: Any) -> int:
    """Sync twin of :func:`remirror_project_rubrics` (psycopg2 lane)."""
    rows = db.execute(_select_active_rubrics_of_project(project_id)).all()
    changed = _remirror_rows(rows, project_config)
    if changed:
        db.flush()
        logger.info(
            "Notenschlüssel change: re-mirrored %s of %s sheets of project %s",
            changed,
            len(rows),
            project_id,
        )
    return changed
