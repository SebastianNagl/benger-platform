"""The worker's Celery application object and its configuration.

Extracted from ``tasks.py`` so task modules can import ``app`` without importing
the whole ``tasks`` module — this breaks the import cycle that would otherwise
form once cell-evaluation tasks live in their own module (``cell_evaluator``
needs ``app`` to decorate its tasks; ``tasks`` imports ``cell_evaluator`` to
register them). The worker is still started as ``celery -A tasks`` — ``tasks``
re-exports ``app`` from here, so the ``-A`` target and every registered task
name (``tasks.*``) are unchanged.

Behaviour is byte-identical to the previous inline block: same app name, beat
schedule, timezone, queue routes, email rate limits, and broker/result backend
resolution (prefer ``REDIS_URI``, else build from components).
"""

import os

from celery import Celery
from celery.schedules import crontab

# Celery-App initialisieren
app = Celery("tasks")

# Beat schedule. `process-daily-digests` was removed with the email-digest
# feature (User-model columns commented out in models.py).
#
# `recompute-aggregates`: refresh the precomputed leaderboard + project
# summary tables. The API endpoints read these tables instead of scanning
# task_evaluations on every request (OOMed prod 2026-05-19). Migration 051
# introduced the tables; see services/shared/aggregate_summaries.py for
# the SQL.
#
# Cadence history:
# - 12h (initial): cheap, occasionally stale tiles after annotation rounds.
# - 1h (2026-05-20): tightened after Phase 6.2 routed the projects list
#   through project_summaries; users complained tiles lagged half a day.
# - 2x/day at 10:00 + 22:00 UTC (= 12:00 + 00:00 CEST) (this PR): leaderboards
#   are a research-grade scorecard, not a live tile — a noticeable user
#   refresh window is the right contract. Hourly runs were also adding
#   load without value once the leaderboards moved to TanStack-cached
#   reads with 30s staleTime on the client. Note: during winter (CET) the
#   runs effectively become 11:00 + 23:00 local; the leaderboards page
#   shows a static hint that copy-locks the schedule to CEST.
#
# Event-driven recompute on EvaluationRun finalize was also removed in
# the same change (search for `recompute_aggregates_after_finalize` — the
# `app.send_task` call in the finalize handler is gone).
app.conf.beat_schedule = {
    "recompute-aggregates": {
        "task": "tasks.recompute_aggregates",
        "schedule": crontab(minute=0, hour="10,22"),
        "args": (),
        "kwargs": {},
        "options": {"queue": "default"},
    },
}

app.conf.timezone = "UTC"

# Task routing configuration for different queues
app.conf.task_routes = {
    'emails.*': {'queue': 'emails'},
    'tasks.*': {'queue': 'default'},
}

# Rate limiting for email tasks to prevent overwhelming mail server
app.conf.task_annotations = {
    'emails.send_invitation': {'rate_limit': '30/m'},  # 30 invitations per minute
    'emails.send_bulk_invitations': {'rate_limit': '5/m'},  # 5 bulk operations per minute
}

# Build Redis URLs - prefer REDIS_URI for production compatibility
redis_uri = os.getenv("REDIS_URI")

if redis_uri:
    # Use REDIS_URI directly if provided (production environment)
    broker_url = redis_uri
    result_backend = redis_uri
else:
    # Fall back to building URL from components (development environment)
    redis_password = os.getenv("REDIS_PASSWORD")
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", "6379")

    if redis_password:
        broker_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
        result_backend = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
    else:
        broker_url = f"redis://{redis_host}:{redis_port}/0"
        result_backend = f"redis://{redis_host}:{redis_port}/0"

app.conf.broker_url = os.getenv("CELERY_BROKER_URL", broker_url)
app.conf.result_backend = os.getenv("CELERY_RESULT_BACKEND", result_backend)
