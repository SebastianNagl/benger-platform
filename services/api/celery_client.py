"""
Centralized Celery client for API task dispatch.

All routers should import from this module rather than creating their own
Celery() instances. This ensures:
1. Consistent Redis URL from Settings
2. A single connection pool
3. Automatic reconnection if the Redis backend dies
"""

import logging
import threading

from celery import Celery

logger = logging.getLogger(__name__)

_celery_app: Celery | None = None
_lock = threading.Lock()


def _create_celery_app() -> Celery:
    from app.core.config import get_settings

    # /shared. Imported here rather than at module scope so this module stays
    # importable regardless of when main.py inserts shared_dir into sys.path.
    import celery_queues

    settings = get_settings()
    broker_url = settings.celery_broker
    backend_url = settings.celery_backend

    app = Celery("tasks", broker=broker_url, backend=backend_url)
    app.conf.broker_connection_retry_on_startup = True

    # Same routing table the workers use, so the API cannot publish to a queue
    # no pool consumes. send_task() routes through app.amqp.router, which
    # resolves on the task NAME -- so this correctly routes extended tasks the
    # API never registers (e.g. tasks.grade_and_schedule_card, which previously
    # fell through to the default `celery` queue because its call site passes no
    # queue= at all).
    app.conf.task_routes = (celery_queues.route_task,)
    app.conf.task_queues = celery_queues.celery_queue_defs()
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
