"""
Centralized Celery client for API task dispatch.

All routers should import from this module rather than creating their own
Celery() instances. This ensures:
1. Consistent Redis URL from Settings
2. A single connection pool
3. Automatic reconnection if the Redis backend dies
"""

import logging
import os
import threading

from celery import Celery

logger = logging.getLogger(__name__)

_celery_app: Celery | None = None
_lock = threading.Lock()


def _create_celery_app() -> Celery:
    from app.core.config import get_settings

    settings = get_settings()
    broker_url = os.getenv("CELERY_BROKER_URL", settings.redis_url)
    backend_url = os.getenv("CELERY_RESULT_BACKEND", settings.redis_url)

    app = Celery("tasks", broker=broker_url, backend=backend_url)
    app.conf.broker_connection_retry_on_startup = True
    return app


def get_celery_app() -> Celery:
    """Get the shared Celery app instance, creating it if needed."""
    global _celery_app
    if _celery_app is None:
        with _lock:
            if _celery_app is None:
                _celery_app = _create_celery_app()
    return _celery_app


def send_task_safe(task_name: str, **kwargs):
    """Send a Celery task with automatic reconnection on failure.

    If send_task fails (e.g. dead Redis connection), recreates the Celery
    app and retries once.
    """
    global _celery_app
    app = get_celery_app()
    try:
        return app.send_task(task_name, **kwargs)
    except Exception as first_error:
        logger.warning(f"Celery send_task failed ({task_name}): {first_error}. Recreating connection.")
        with _lock:
            _celery_app = _create_celery_app()
        app = _celery_app
        return app.send_task(task_name, **kwargs)
