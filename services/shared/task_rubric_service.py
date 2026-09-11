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

Callers own the transaction (``await db.commit()``); every function flushes
so ids and the unique index are settled when it returns.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from project_models import TaskRubric
from rubric_structure import (
    criteria_from_structure,
    mirror_rubric_into_task_data,
    normalize_grade_scale,
    normalize_structure,
    total_points_from_structure,
    validate_grade_scale,
    validate_structure,
)


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
) -> TaskRubric:
    """Persist a new rubric row from a structure (raises RubricValidationError)."""
    normalized, scale, errors = _validated(structure, grade_scale)
    if errors:
        raise RubricValidationError(errors)
    assert normalized is not None
    rubric = TaskRubric(
        id=str(uuid.uuid4()),
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
        # The pre-rendered document text now disagrees with the edited
        # outline — drop it so the judge renders the structure (the full
        # generator document stays as provenance).
        metadata = dict(rubric.generation_metadata or {})
        if metadata.pop("rendered_text", None) is not None:
            metadata["rendered_text_invalidated_by_edit"] = True
            rubric.generation_metadata = metadata
    if scale_changed:
        rubric.grade_scale = scale
    if content_changed and rubric.source == "llm":
        rubric.source = "llm_edited"
    if title_changed:
        rubric.title = _clean_title(title)
    if (content_changed or title_changed) and rubric.status == "active" and task is not None:
        mirror_rubric_into_task_data(task, rubric)
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
    if "contract_version" in old_meta:
        clone_meta["contract_version"] = old_meta["contract_version"]

    if structure is not UNSET:
        clone_structure = structure
        clone_criteria = criteria_from_structure(structure)
        clone_total = float(total_points_from_structure(structure))
    else:
        clone_structure = old.structure
        clone_criteria = old.criteria
        clone_total = float(old.total_points or 100.0)

    clone = TaskRubric(
        id=str(uuid.uuid4()),
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
        created_by=actor_id,
    )
    was_active = old.status == "active"
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
    """Make ``rubric`` the task's active rubric (others → ``demote_to``) and mirror it."""
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
        mirror_rubric_into_task_data(task, rubric)


async def archive_task_rubric(db: AsyncSession, rubric: TaskRubric, task) -> None:
    """Archive ``rubric``; when it was active the task-data mirror is removed."""
    was_active = rubric.status == "active"
    rubric.status = "archived"
    await db.flush()
    if was_active and task is not None:
        mirror_rubric_into_task_data(task, None)
