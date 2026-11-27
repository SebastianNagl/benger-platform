"""Project questionnaires: definitions, answers and the "is one due?" rule.

The vocabulary (moments, frequencies, subject keys) is shared with the export
and import in ``shared/questionnaires.py``; this module holds what the API
does with it. Every questionnaire is validated on save by the label-config
rules (``services.label_config.questionnaire``) and every answer is checked
against the ``required="true"`` questions of the version it answered.

Compatibility for one release: the project columns ``questionnaire_enabled``
and ``questionnaire_config`` stay in step with the after_submit questionnaire
in both directions (``save_questionnaire`` writes them, a project PATCH of
them goes through ``sync_legacy_after_submit``), so a client that still
reads or writes the two fields keeps working.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models import TaskEvaluation
from project_models import (
    Annotation,
    Project,
    ProjectQuestionnaire,
    ProjectQuestionnaireVersion,
    QuestionnaireResponse,
    Task,
)
from questionnaires import (
    AFTER_SUBMIT,
    ALLOWED_FREQUENCIES,
    BEFORE_TASK,
    DEFAULT_REQUIRED,
    KORREKTUR,
    ONCE_PER_PROJECT,
    ONCE_PER_SUBMISSION,
    ONCE_PER_TASK,
    QUESTIONNAIRE_TRIGGERS,
    SubjectError,
    config_hash,
    default_frequency,
    is_active,
    subject_key,
)
from services.label_config.questionnaire import (
    missing_required_answers,
    validate_questionnaire_config,
)


class QuestionnaireError(Exception):
    """A refused questionnaire write; ``status`` and ``detail`` are the HTTP answer."""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status = status
        self.detail = {"code": code, "message": message, **extra}


def check_trigger(trigger: str) -> None:
    if trigger not in QUESTIONNAIRE_TRIGGERS:
        raise QuestionnaireError(
            404,
            "questionnaire_trigger_unknown",
            f"Unknown questionnaire moment {trigger!r}; use one of "
            + ", ".join(QUESTIONNAIRE_TRIGGERS),
        )


def _select(project_id: str, trigger: str):
    return select(ProjectQuestionnaire).where(
        ProjectQuestionnaire.project_id == project_id,
        ProjectQuestionnaire.trigger == trigger,
    )


async def _from_legacy_columns(
    db: AsyncSession, project_id: str
) -> Optional[ProjectQuestionnaire]:
    """Compatibility read path for one release: a project whose #1208
    columns say it has a post-annotation questionnaire, written by a client
    that bypassed this module, gets its after_submit questionnaire created
    from them (as migration 165 did for every project then; flushed, the
    caller's commit keeps it)."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        return None
    config = project.questionnaire_config
    if config is not None and not config.strip():
        config = None
    if not project.questionnaire_enabled and config is None:
        return None
    row = ProjectQuestionnaire(
        id=str(uuid.uuid4()),
        project_id=project_id,
        trigger=AFTER_SUBMIT,
        enabled=bool(project.questionnaire_enabled),
        config=config,
        required=DEFAULT_REQUIRED[AFTER_SUBMIT],
        frequency=default_frequency(AFTER_SUBMIT),
        version=1 if config else 0,
    )
    db.add(row)
    if config:
        db.add(
            ProjectQuestionnaireVersion(
                id=str(uuid.uuid4()),
                questionnaire_id=row.id,
                version=1,
                config=config,
                config_hash=config_hash(config),
            )
        )
    await db.flush()
    return row


async def get_questionnaire(
    db: AsyncSession, project_id: str, trigger: str
) -> Optional[ProjectQuestionnaire]:
    row = (await db.execute(_select(project_id, trigger))).scalar_one_or_none()
    if row is None and trigger == AFTER_SUBMIT:
        row = await _from_legacy_columns(db, project_id)
    return row


async def list_questionnaires(db: AsyncSession, project_id: str) -> Dict[str, ProjectQuestionnaire]:
    rows = (
        await db.execute(
            select(ProjectQuestionnaire).where(ProjectQuestionnaire.project_id == project_id)
        )
    ).scalars().all()
    by_trigger = {row.trigger: row for row in rows}
    if AFTER_SUBMIT not in by_trigger:
        legacy = await _from_legacy_columns(db, project_id)
        if legacy is not None:
            by_trigger[AFTER_SUBMIT] = legacy
    return by_trigger


def serialize_questionnaire(trigger: str, row: Optional[ProjectQuestionnaire]) -> Dict[str, Any]:
    """The API shape of one moment; a moment never saved shows its defaults."""
    return {
        "trigger": trigger,
        "enabled": bool(row.enabled) if row else False,
        "config": (row.config or "") if row else "",
        "required": bool(row.required) if row else DEFAULT_REQUIRED[trigger],
        "frequency": row.frequency if row else default_frequency(trigger),
        "version": int(row.version or 0) if row else 0,
        "active": is_active(row),
        "allowed_frequencies": list(ALLOWED_FREQUENCIES[trigger]),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def validate_config(config: str) -> List[str]:
    """The reasons a questionnaire config cannot be saved (empty when it can)."""
    if not (config or "").strip():
        return ["The questionnaire is empty: write or upload its XML first"]
    is_valid, errors = validate_questionnaire_config(config)
    return [] if is_valid else list(errors)


async def save_questionnaire(
    db: AsyncSession,
    project: Project,
    trigger: str,
    *,
    enabled: bool,
    config: Optional[str],
    required: Optional[bool],
    frequency: Optional[str],
    user_id: Optional[str],
) -> ProjectQuestionnaire:
    """Create or update a project's questionnaire of one moment (no commit).

    A config is validated whenever it is non-empty, and switching on needs a
    valid one. A changed config text becomes a new version; the old texts
    stay readable for the answers given to them.
    """
    check_trigger(trigger)
    row = await get_questionnaire(db, project.id, trigger)

    new_config = (row.config if row else None) if config is None else config
    if new_config is not None and not new_config.strip():
        new_config = None
    # Only a changed text is validated: echoing back a stored config written
    # before validation existed must not block saving the other settings.
    if new_config is not None and (row is None or new_config != row.config):
        errors = validate_config(new_config)
        if errors:
            raise QuestionnaireError(
                422,
                "questionnaire_config_invalid",
                "The questionnaire cannot be saved: " + "; ".join(errors),
                errors=errors,
            )
    if enabled and new_config is None:
        raise QuestionnaireError(
            422,
            "questionnaire_config_missing",
            "A questionnaire can only be switched on once its XML is written",
            errors=["The questionnaire is empty: write or upload its XML first"],
        )

    new_frequency = frequency or (row.frequency if row else default_frequency(trigger))
    if new_frequency not in ALLOWED_FREQUENCIES[trigger]:
        raise QuestionnaireError(
            422,
            "questionnaire_frequency_invalid",
            f"{new_frequency!r} is not a frequency of the {trigger} questionnaire; use one of "
            + ", ".join(ALLOWED_FREQUENCIES[trigger]),
        )

    if row is None:
        row = ProjectQuestionnaire(
            id=str(uuid.uuid4()),
            project_id=project.id,
            trigger=trigger,
            enabled=False,
            config=None,
            required=DEFAULT_REQUIRED[trigger],
            frequency=new_frequency,
            version=0,
        )
        db.add(row)

    if new_config is not None and new_config != row.config:
        next_version = int(row.version or 0) + 1
        db.add(
            ProjectQuestionnaireVersion(
                id=str(uuid.uuid4()),
                questionnaire_id=row.id,
                version=next_version,
                config=new_config,
                config_hash=config_hash(new_config),
                created_by=user_id,
            )
        )
        row.version = next_version
    row.config = new_config
    row.enabled = bool(enabled)
    if required is not None:
        row.required = bool(required)
    row.frequency = new_frequency
    row.updated_by = user_id

    if trigger == AFTER_SUBMIT:
        # Compatibility for one release: the legacy project fields mirror it.
        project.questionnaire_enabled = row.enabled
        project.questionnaire_config = row.config
    return row


async def sync_legacy_after_submit(
    db: AsyncSession, project: Project, user_id: Optional[str]
) -> None:
    """Carry a PATCH of ``questionnaire_enabled`` / ``questionnaire_config``
    into the after_submit questionnaire (no commit). Validates like a save
    from the settings card; a switched-on flag without a config is kept as
    it is today (shown to nobody), so old clients see what they wrote."""
    config = project.questionnaire_config
    if config is not None and not config.strip():
        config = None
    enabled = bool(project.questionnaire_enabled)
    row = await get_questionnaire(db, project.id, AFTER_SUBMIT)
    if row is None and not enabled and config is None:
        return
    if config is None:
        if row is None:
            row = ProjectQuestionnaire(
                id=str(uuid.uuid4()),
                project_id=project.id,
                trigger=AFTER_SUBMIT,
                enabled=enabled,
                config=None,
                required=DEFAULT_REQUIRED[AFTER_SUBMIT],
                frequency=default_frequency(AFTER_SUBMIT),
                version=0,
            )
            db.add(row)
        row.enabled = enabled
        row.config = None
        row.updated_by = user_id
        return
    await save_questionnaire(
        db,
        project,
        AFTER_SUBMIT,
        enabled=False,
        config=config,
        required=None,
        frequency=None,
        user_id=user_id,
    )
    row = await get_questionnaire(db, project.id, AFTER_SUBMIT)
    row.enabled = enabled
    project.questionnaire_enabled = enabled


# --------------------------------------------------------------------------- #
# Answers
# --------------------------------------------------------------------------- #


@dataclass
class Subject:
    """What an answer is about, resolved and checked for the caller."""

    task_id: Optional[str] = None
    annotation_id: Optional[str] = None
    generation_id: Optional[str] = None
    task_evaluation_id: Optional[str] = None

    def key(self, trigger: str, frequency: str) -> str:
        return subject_key(
            trigger,
            frequency,
            task_id=self.task_id,
            annotation_id=self.annotation_id,
            generation_id=self.generation_id,
            task_evaluation_id=self.task_evaluation_id,
        )


async def _task_of_project(db: AsyncSession, project_id: str, task_id: str) -> Optional[Task]:
    return (
        await db.execute(select(Task).where(Task.id == task_id, Task.project_id == project_id))
    ).scalar_one_or_none()


def grader_of(evaluation: TaskEvaluation) -> Optional[str]:
    """Who graded a Korrektur row: ``created_by``, or for rows from before
    that column the ``judge_prompts_used.grader_user_id`` the extension
    wrote."""
    if evaluation.created_by:
        return str(evaluation.created_by)
    jpu = evaluation.judge_prompts_used
    if isinstance(jpu, dict) and jpu.get("grader_user_id"):
        return str(jpu["grader_user_id"])
    return None


async def resolve_subject(
    db: AsyncSession,
    project: Project,
    trigger: str,
    user_id: str,
    *,
    task_id: Optional[str],
    annotation_id: Optional[str],
    task_evaluation_id: Optional[str],
    task_visible=None,
) -> Subject:
    """Check the links of an answer for its moment and the caller.

    ``task_visible(task_id)`` is the caller's task-assignment check
    (participant moments only). A Korrektur answer belongs to the grader of
    the grade row it names, so only that grader may give it.
    """
    if trigger == KORREKTUR:
        if not task_evaluation_id:
            raise QuestionnaireError(
                422, "questionnaire_subject_missing", "task_evaluation_id is required"
            )
        evaluation = (
            await db.execute(
                select(TaskEvaluation)
                .join(Task, TaskEvaluation.task_id == Task.id)
                .where(TaskEvaluation.id == task_evaluation_id, Task.project_id == project.id)
            )
        ).scalar_one_or_none()
        if evaluation is None:
            raise QuestionnaireError(404, "task_evaluation_not_found", "Grade not found")
        if grader_of(evaluation) != str(user_id):
            raise QuestionnaireError(
                403,
                "questionnaire_not_grader",
                "Only the grader of this Korrektur answers its questionnaire",
            )
        return Subject(
            task_id=evaluation.task_id,
            annotation_id=evaluation.annotation_id,
            generation_id=evaluation.generation_id,
            task_evaluation_id=evaluation.id,
        )

    if trigger == AFTER_SUBMIT:
        if not annotation_id:
            raise QuestionnaireError(
                422, "questionnaire_subject_missing", "annotation_id is required"
            )
        annotation = (
            await db.execute(
                select(Annotation).where(
                    Annotation.id == annotation_id,
                    Annotation.project_id == project.id,
                    Annotation.completed_by == user_id,
                )
            )
        ).scalar_one_or_none()
        if annotation is None:
            raise QuestionnaireError(404, "annotation_not_found", "Annotation not found")
        if task_id and str(annotation.task_id) != str(task_id):
            raise QuestionnaireError(404, "annotation_not_found", "Annotation not found")
        if task_visible is not None and not await task_visible(annotation.task_id):
            raise QuestionnaireError(404, "task_not_found", "Task not found")
        return Subject(task_id=annotation.task_id, annotation_id=annotation.id)

    # before_task
    if task_id:
        task = await _task_of_project(db, project.id, task_id)
        if task is None or (task_visible is not None and not await task_visible(task.id)):
            raise QuestionnaireError(404, "task_not_found", "Task not found")
    return Subject(task_id=task_id)


async def find_answer(
    db: AsyncSession, questionnaire: ProjectQuestionnaire, user_id: str, key: str
) -> Optional[QuestionnaireResponse]:
    return (
        await db.execute(
            select(QuestionnaireResponse).where(
                QuestionnaireResponse.questionnaire_id == questionnaire.id,
                QuestionnaireResponse.user_id == user_id,
                QuestionnaireResponse.subject_key == key,
            )
        )
    ).scalar_one_or_none()


async def is_due(
    db: AsyncSession,
    questionnaire: Optional[ProjectQuestionnaire],
    user_id: str,
    subject: Subject,
) -> bool:
    """Whether ``user_id`` still has to answer (or skip) the questionnaire
    for ``subject``: it is switched on and configured, and the moment its
    frequency counts has no answer yet."""
    if not is_active(questionnaire):
        return False
    try:
        key = subject.key(questionnaire.trigger, questionnaire.frequency)
    except SubjectError:
        return False
    return await find_answer(db, questionnaire, user_id, key) is None


async def record_answer(
    db: AsyncSession,
    project: Project,
    questionnaire: ProjectQuestionnaire,
    user_id: str,
    subject: Subject,
    *,
    result: Sequence[Dict[str, Any]],
    skipped: bool,
    require_config: bool = True,
) -> QuestionnaireResponse:
    """Store one answer (commits). Refuses an inactive questionnaire, a skip
    of a required one, unanswered required questions and a second answer
    for the same moment. ``require_config=False`` is the #1208 route's rule:
    switched on is enough."""
    active = is_active(questionnaire) if require_config else bool(questionnaire.enabled)
    if not active:
        raise QuestionnaireError(
            400,
            "questionnaire_not_enabled",
            "Questionnaire is not enabled for this project",
        )
    try:
        key = subject.key(questionnaire.trigger, questionnaire.frequency)
    except SubjectError as exc:
        raise QuestionnaireError(422, "questionnaire_subject_missing", str(exc)) from None

    result = list(result or [])
    if skipped:
        if questionnaire.required:
            raise QuestionnaireError(
                422,
                "questionnaire_required",
                "This questionnaire must be answered; it cannot be skipped",
            )
        result = []
    else:
        missing = missing_required_answers(questionnaire.config, result)
        if missing:
            raise QuestionnaireError(
                422,
                "questionnaire_required_missing",
                "Required questions are not answered: " + ", ".join(missing),
                missing=missing,
            )

    duplicate = QuestionnaireError(
        409,
        "questionnaire_already_answered",
        "This questionnaire was already answered",
    )
    if await find_answer(db, questionnaire, user_id, key) is not None:
        raise duplicate

    row = QuestionnaireResponse(
        id=str(uuid.uuid4()),
        project_id=project.id,
        questionnaire_id=questionnaire.id,
        trigger=questionnaire.trigger,
        questionnaire_version=questionnaire.version,
        config_hash=config_hash(questionnaire.config),
        user_id=user_id,
        task_id=subject.task_id,
        annotation_id=subject.annotation_id,
        task_evaluation_id=subject.task_evaluation_id,
        subject_key=key,
        skipped=bool(skipped),
        result=result,
    )
    db.add(row)
    questionnaire_id = questionnaire.id  # the rollback below expires the row
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Only an answer that raced in is a duplicate; any other failure (the
        # submission deleted meanwhile) is not reported as one.
        raced = (
            await db.execute(
                select(QuestionnaireResponse.id).where(
                    QuestionnaireResponse.questionnaire_id == questionnaire_id,
                    QuestionnaireResponse.user_id == user_id,
                    QuestionnaireResponse.subject_key == key,
                )
            )
        ).first()
        if raced:
            raise duplicate from None
        raise
    await db.refresh(row)
    return row


def serialize_response(row: QuestionnaireResponse) -> Dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "questionnaire_id": row.questionnaire_id,
        "trigger": row.trigger,
        "questionnaire_version": row.questionnaire_version,
        "config_hash": row.config_hash,
        "user_id": row.user_id,
        "task_id": row.task_id,
        "annotation_id": row.annotation_id,
        "task_evaluation_id": row.task_evaluation_id,
        "subject_key": row.subject_key,
        "skipped": bool(row.skipped),
        "result": row.result or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# --------------------------------------------------------------------------- #
# Sync helper for the overlay (its timer routes run on a sync session)
# --------------------------------------------------------------------------- #


def before_task_questionnaire_pending(
    db: Session, project_id: str, user_id: str, task_id: Optional[str]
) -> bool:
    """True while ``user_id`` still owes the project's before-task
    questionnaire for ``task_id``.

    An exam timer must not start while this holds: the questionnaire never
    counts toward the time limit. The labeling page already starts the timer
    only afterwards; a timer route can call this to refuse a start that
    skipped the page (sync session, as the timer routes use).
    """
    questionnaire = (
        db.execute(
            select(ProjectQuestionnaire).where(
                ProjectQuestionnaire.project_id == project_id,
                ProjectQuestionnaire.trigger == BEFORE_TASK,
            )
        )
    ).scalar_one_or_none()
    if not is_active(questionnaire):
        return False
    try:
        key = subject_key(BEFORE_TASK, questionnaire.frequency, task_id=task_id)
    except SubjectError:
        return False
    answered = db.execute(
        select(func.count())
        .select_from(QuestionnaireResponse)
        .where(
            QuestionnaireResponse.questionnaire_id == questionnaire.id,
            QuestionnaireResponse.user_id == user_id,
            QuestionnaireResponse.subject_key == key,
        )
    ).scalar()
    return not answered


__all__ = [
    "AFTER_SUBMIT",
    "BEFORE_TASK",
    "KORREKTUR",
    "ONCE_PER_PROJECT",
    "ONCE_PER_SUBMISSION",
    "ONCE_PER_TASK",
    "QuestionnaireError",
    "Subject",
    "before_task_questionnaire_pending",
    "check_trigger",
    "find_answer",
    "get_questionnaire",
    "grader_of",
    "is_due",
    "list_questionnaires",
    "record_answer",
    "resolve_subject",
    "save_questionnaire",
    "serialize_questionnaire",
    "serialize_response",
    "sync_legacy_after_submit",
    "validate_config",
]
