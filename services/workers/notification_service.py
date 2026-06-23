"""Thin re-export shim — canonical implementation in services/shared/mailer/notification_service.py.

Kept so existing worker ``from notification_service import NotificationService,
notify_task_completed, notify_llm_generation_failed, notify_model_api_key_invalid``
callers keep working unchanged. ``/shared`` is on ``sys.path`` in the workers
container, so ``mailer`` resolves bare.

Behavior change vs. the worker's former standalone copy: notifications now go
through the ORM ``NotificationService.create_notification`` (was raw SQL) and
therefore **respect the user's in_app preference** — a recipient who disabled
in-app for a type no longer gets an in-app row from a worker-triggered event.
See the canonical module docstring.

The worker-only logging helpers ``notify_task_completed`` /
``notify_llm_generation_failed`` / ``notify_model_api_key_invalid`` did not
exist on the api side; they are defined below so the worker's existing imports
of those names still resolve.
"""
import logging

from mailer.notification_service import *  # noqa: F401,F403

logger = logging.getLogger(__name__)


def notify_task_completed(task_id: str, task_name: str, user_id: str, **kwargs):
    """Minimal worker-side task-completion notification (logs only).

    Preserved from the worker's former standalone notification_service so
    callers importing this name keep working. The api side never had this.
    """
    logger.info(f"Task completed: {task_name} (ID: {task_id}) for user {user_id}")


def notify_llm_generation_failed(task_id: str, error_message: str, **kwargs):
    """Minimal worker-side LLM-generation-failure notification (logs only).

    NOTE: the canonical (api) ``notification_service`` also exports a
    ``notify_llm_generation_failed`` with a *different* signature
    ``(db, task_id, task_name, model_name, user_id, error_message, ...)`` that
    creates a real DB notification. This worker-local definition intentionally
    shadows that import to preserve the worker's historical lightweight
    ``(task_id, error_message)`` logging contract for its existing callers.
    """
    logger.error(f"LLM generation failed for task {task_id}: {error_message}")


def notify_model_api_key_invalid(model_id: str, user_id: str, **kwargs):
    """Minimal worker-side invalid-API-key notification (logs only).

    Shadows the canonical ``notify_model_api_key_invalid`` (which takes a ``db``
    session and creates a DB notification) to preserve the worker's historical
    ``(model_id, user_id)`` logging contract.
    """
    logger.warning(f"Invalid API key for model {model_id} for user {user_id}")
