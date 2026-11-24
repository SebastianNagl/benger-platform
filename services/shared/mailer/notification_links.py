"""Where a notification points in the web app.

The email path uses this to build an absolute link for the recipient's brand.
The frontend mirrors it in src/lib/notificationLinks.ts to route the in-app
notification by the viewer's UI mode. Keep the two in step.
"""

from collections.abc import Mapping
from typing import Any

from models import NotificationType

EVALUATION_RECEIVED_TYPES = frozenset(
    {
        NotificationType.EVALUATION_RECEIVED_HUMAN.value,
        NotificationType.EVALUATION_RECEIVED_IMMEDIATE.value,
        NotificationType.EVALUATION_RECEIVED_BATCH.value,
        NotificationType.EVALUATION_RELEASED.value,
    }
)


#: Notices about the recipient's own submission: a new grading, or the
#: submission returned by an editor. They open the page that shows it.
SUBMISSION_NOTICE_TYPES = EVALUATION_RECEIVED_TYPES | frozenset(
    {NotificationType.SUBMISSION_RETURNED.value}
)


def _value(notification_type: Any) -> Any:
    return getattr(notification_type, "value", notification_type)


def is_evaluation_received_type(notification_type: Any) -> bool:
    """True for the "new grading on your submission" types (enum or value)."""
    value = _value(notification_type)
    return isinstance(value, str) and value in EVALUATION_RECEIVED_TYPES


def is_submission_notice_type(notification_type: Any) -> bool:
    """True for every notice about the recipient's own submission (enum or value)."""
    value = _value(notification_type)
    return isinstance(value, str) and value in SUBMISSION_NOTICE_TYPES


def evaluation_received_path(
    data: Mapping[str, Any] | None, student_surface: bool
) -> str | None:
    """Path of the page that shows a submission (and its gradings) to its author.

    Used by every :data:`SUBMISSION_NOTICE_TYPES` notice.

    A student reads an exam's gradings on the exam page of the student
    surface. Everyone else, and every non-exam project, uses the project's
    My Tasks list, which opens the submission with its scores. None when the
    notification names no project.
    """
    data = data or {}
    project_id = data.get("project_id")
    if not project_id:
        return None
    if student_surface and data.get("project_kind") == "exam":
        return f"/student/exams/{project_id}"
    return f"/projects/{project_id}/my-tasks"
