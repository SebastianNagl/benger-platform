"""Project questionnaires: the moments, their frequencies and the answer keys.

A project has at most one questionnaire per moment (``trigger``):

- ``before_task``: the participant answers it after the instructions and
  before the task text appears. An exam timer starts only once it is
  answered (or skipped), so it never counts toward the time limit.
- ``after_submit``: shown right after a submission is final, outside the
  timed window (the submission closes the timer session first).
- ``korrektur``: the human grader answers it after saving a Korrektur. Its
  answers are the grader's, linked to the grade row; the extension shows it.

Questionnaires are label-config XML rendered by the annotation interface;
answers are stored in Label Studio result format in ``questionnaire_responses``
(models: ``project_models.ProjectQuestionnaire`` and ``QuestionnaireResponse``).
This module is shared by the API, the export and the import.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BEFORE_TASK = "before_task"
AFTER_SUBMIT = "after_submit"
KORREKTUR = "korrektur"

QUESTIONNAIRE_TRIGGERS: Tuple[str, ...] = (BEFORE_TASK, AFTER_SUBMIT, KORREKTUR)

ONCE_PER_PROJECT = "once_per_project"
ONCE_PER_TASK = "once_per_task"
ONCE_PER_SUBMISSION = "once_per_submission"

QUESTIONNAIRE_FREQUENCIES: Tuple[str, ...] = (ONCE_PER_PROJECT, ONCE_PER_TASK, ONCE_PER_SUBMISSION)

#: The frequencies each moment offers; the first one is its default.
#: ``after_submit`` defaults to one questionnaire per submission, which is what
#: the post-annotation questionnaire always did.
ALLOWED_FREQUENCIES: Dict[str, Tuple[str, ...]] = {
    BEFORE_TASK: (ONCE_PER_PROJECT, ONCE_PER_TASK),
    AFTER_SUBMIT: (ONCE_PER_SUBMISSION, ONCE_PER_TASK, ONCE_PER_PROJECT),
    KORREKTUR: (ONCE_PER_SUBMISSION, ONCE_PER_PROJECT),
}

#: Whether a new questionnaire of the moment must be answered (no skip).
#: ``after_submit`` keeps the post-annotation questionnaire's rule.
DEFAULT_REQUIRED: Dict[str, bool] = {
    BEFORE_TASK: True,
    AFTER_SUBMIT: True,
    KORREKTUR: False,
}


def default_frequency(trigger: str) -> str:
    return ALLOWED_FREQUENCIES[trigger][0]


def config_hash(config: Optional[str]) -> Optional[str]:
    """SHA-256 (hex) of a questionnaire config text, None without one."""
    if not config:
        return None
    return hashlib.sha256(config.encode("utf-8")).hexdigest()


def is_active(questionnaire: Any) -> bool:
    """A questionnaire is shown only when switched on and configured."""
    return bool(
        questionnaire is not None
        and questionnaire.enabled
        and (questionnaire.config or "").strip()
    )


class SubjectError(ValueError):
    """The request lacks the link the questionnaire's frequency counts by."""


def subject_key(
    trigger: str,
    frequency: str,
    *,
    task_id: Optional[str] = None,
    annotation_id: Optional[str] = None,
    generation_id: Optional[str] = None,
    task_evaluation_id: Optional[str] = None,
) -> str:
    """What one answer covers, so the frequency is enforced by a unique key.

    ``once_per_project`` -> ``project``; ``once_per_task`` -> ``task:<id>``;
    ``once_per_submission`` -> the submission: ``annotation:<id>`` (or, for a
    Korrektur of a model output, ``generation:<id>``; ``evaluation:<id>`` when
    the grade row names neither).
    """
    if frequency == ONCE_PER_PROJECT:
        return "project"
    if frequency == ONCE_PER_TASK:
        if not task_id:
            raise SubjectError("task_id is required for a questionnaire asked once per task")
        return f"task:{task_id}"
    if frequency == ONCE_PER_SUBMISSION:
        if annotation_id:
            return f"annotation:{annotation_id}"
        if trigger == KORREKTUR and generation_id:
            return f"generation:{generation_id}"
        if trigger == KORREKTUR and task_evaluation_id:
            return f"evaluation:{task_evaluation_id}"
        raise SubjectError("the submission is required for a questionnaire asked once per submission")
    raise SubjectError(f"unknown frequency {frequency!r}")


# --------------------------------------------------------------------------- #
# Wide CSV: one row per answer, one column per question.
# --------------------------------------------------------------------------- #

WIDE_CSV_BASE_COLUMNS: Tuple[str, ...] = (
    "response_id",
    "trigger",
    "questionnaire_version",
    "config_hash",
    "user_id",
    "task_id",
    "annotation_id",
    "task_evaluation_id",
    "skipped",
    "created_at",
)


def flatten_answer(entry: Dict[str, Any]) -> Any:
    """The plain value of one Label Studio result entry, for a CSV cell.

    Ratings, Likert items and numbers give their number, choices their
    selected values joined by ``|``, text areas their text; anything else is
    written as JSON so no answer is dropped.
    """
    value = entry.get("value")
    if not isinstance(value, dict):
        return value
    for key in ("rating", "likert", "number"):
        if key in value:
            return value[key]
    if "choices" in value:
        choices = value["choices"]
        if isinstance(choices, list):
            return "|".join(str(c) for c in choices)
        return choices
    if "text" in value:
        text = value["text"]
        if isinstance(text, list):
            return "\n".join(str(t) for t in text)
        return text
    if len(value) == 1:
        (only,) = value.values()
        if isinstance(only, (str, int, float, bool)) or only is None:
            return only
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def question_columns(results: Iterable[Sequence[Dict[str, Any]]]) -> List[str]:
    """Every question name (``from_name``) in the results, first seen first."""
    seen: Dict[str, None] = {}
    for result in results:
        for entry in result or []:
            if isinstance(entry, dict) and entry.get("from_name"):
                seen.setdefault(str(entry["from_name"]), None)
    return list(seen)


def wide_row(result: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """``{question name: plain answer}`` of one answer's result."""
    row: Dict[str, Any] = {}
    for entry in result or []:
        if isinstance(entry, dict) and entry.get("from_name"):
            row[str(entry["from_name"])] = flatten_answer(entry)
    return row
