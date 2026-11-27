"""Seed questionnaires and answers for tests (sync session).

Answers live in ``questionnaire_responses`` and belong to a project
questionnaire of their moment; ``after_submit_answer`` makes the
post-annotation answer the way the #1208 table used to hold it.
"""

import uuid
from typing import Any, Optional

from project_models import ProjectQuestionnaire, QuestionnaireResponse


def questionnaire(
    db,
    project_id: str,
    trigger: str = "after_submit",
    *,
    enabled: bool = True,
    config: Optional[str] = None,
    required: bool = True,
    frequency: Optional[str] = None,
    version: int = 0,
) -> ProjectQuestionnaire:
    """The project's questionnaire of ``trigger``, created when missing."""
    row = (
        db.query(ProjectQuestionnaire)
        .filter(
            ProjectQuestionnaire.project_id == project_id,
            ProjectQuestionnaire.trigger == trigger,
        )
        .first()
    )
    if row is None:
        row = ProjectQuestionnaire(
            id=str(uuid.uuid4()),
            project_id=project_id,
            trigger=trigger,
            enabled=enabled,
            config=config,
            required=required,
            frequency=frequency
            or {"before_task": "once_per_project"}.get(trigger, "once_per_submission"),
            version=version,
        )
        db.add(row)
        db.flush()
    return row


def after_submit_answer(
    db,
    *,
    project_id: str,
    annotation_id: str,
    task_id: str,
    user_id: str,
    result: Any,
    config_hash: Optional[str] = None,
    id: Optional[str] = None,
) -> QuestionnaireResponse:
    """An after_submit answer for ``annotation_id`` (added, not committed)."""
    q = questionnaire(db, project_id)
    row = QuestionnaireResponse(
        id=id or str(uuid.uuid4()),
        project_id=project_id,
        questionnaire_id=q.id,
        trigger="after_submit",
        config_hash=config_hash,
        user_id=user_id,
        task_id=task_id,
        annotation_id=annotation_id,
        subject_key=f"annotation:{annotation_id}",
        result=result,
    )
    db.add(row)
    return row
