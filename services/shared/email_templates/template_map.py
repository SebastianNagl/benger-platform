"""Notification email template lookup. Single source of truth for both
services/api/services/email/email_service.py and
services/workers/email_service.py — previously each had its own copy that
had drifted (worker map missing korrektur_assigned, keys typed differently
because the worker hydrates `notification.type` as a plain string).
"""

from typing import Union

from models import NotificationType

DEFAULT_TEMPLATE = "default_notification.html"

# Keys are NotificationType.value strings. Anything not in this map falls
# back to DEFAULT_TEMPLATE, which renders notification.title + .message.
_TEMPLATE_BY_TYPE: dict[str, str] = {
    NotificationType.TASK_ASSIGNED.value: "task_assigned.html",
    NotificationType.KORREKTUR_ASSIGNED.value: "korrektur_assigned.html",
    NotificationType.ANNOTATION_COMPLETED.value: "annotation_completed.html",
    NotificationType.EVALUATION_COMPLETED.value: "evaluation_completed.html",
    NotificationType.LLM_GENERATION_COMPLETED.value: "llm_generation_completed.html",
    NotificationType.DATA_IMPORT_SUCCESS.value: "data_import_success.html",
    NotificationType.DATA_UPLOAD_COMPLETED.value: "data_import_success.html",
    NotificationType.ORGANIZATION_INVITATION_SENT.value: "organization_invite.html",
    NotificationType.PROJECT_UPDATED.value: "project_updated.html",
    NotificationType.PROJECT_SHARED.value: "project_shared.html",
}


def template_for(notification_type: Union[NotificationType, str, None]) -> str:
    """Return the template filename for a notification type. Accepts the
    enum (API side) or a bare string (worker hydrates from JSON)."""
    if hasattr(notification_type, "value"):
        key = notification_type.value
    elif isinstance(notification_type, str):
        key = notification_type
    else:
        return DEFAULT_TEMPLATE
    return _TEMPLATE_BY_TYPE.get(key, DEFAULT_TEMPLATE)
