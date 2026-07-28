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

import celery_queues  # /shared -- single source of truth for task -> queue routing

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
# - 2x/day at 10:00 + 22:00 UTC (2026-06): leaderboards treated as a slow
#   scorecard; the projects-list tile counts (annotations / evaluations) then
#   lagged up to 12h behind reality, which read as "evaluations missing".
# - 1h (top of every hour): back to hourly so the projects list reflects an
#   in-progress exam within the hour. The recompute is cheap relative to the
#   confusion a half-day-stale count causes during live annotation rounds.
#
# `sweep-missing-immediate-evals`: hourly server-side backstop for the
# client-fired KI-Votum. Any annotation on an immediate-eval project that ends
# up without a grade (lost client POST, server auto-submit, worker crash) is
# re-dispatched via the idempotent ensure_immediate_evaluation. `min_age_minutes`
# skips very recent submits so an in-flight client eval isn't raced.
#
# Event-driven recompute on EvaluationRun finalize was removed earlier
# (search for `recompute_aggregates_after_finalize`).
app.conf.beat_schedule = {
    "recompute-aggregates": {
        "task": "tasks.recompute_aggregates",
        "schedule": crontab(minute=0),
        "args": (),
        "kwargs": {},
    },
    "sweep-missing-immediate-evals": {
        "task": "tasks.sweep_missing_immediate_evals",
        "schedule": crontab(minute=30),
        "args": (),
        "kwargs": {},
    },
}
# Beat entries deliberately carry no ``options: {"queue": ...}``. Beat options go
# through the same router as any other send and would override task_routes, so
# pinning a queue here would let the schedule drift away from celery_queues.
# ``test_celery_queues.py`` asserts that stays true.

app.conf.timezone = "UTC"

# Task routing. Queues are served by DISJOINT worker pools (see workers.queues +
# workerPools in infra/helm/benger/values.yaml) so that long generation/evaluation
# work can never occupy the execution slots user-blocking tasks need. The old
# 'emails.*'/'tasks.*' globs put everything except mail on one queue, which is
# how immediate evaluation ended up behind hours of bulk work.
app.conf.task_routes = (celery_queues.route_task,)
app.conf.task_queues = celery_queues.celery_queue_defs()

# Time limits (per queue class) + the email rate limits, both derived from the
# routing table so they cannot drift away from queue membership.
app.conf.task_annotations = celery_queues.task_annotations()

# Default prefetch of 1: with acks_late cell tasks, a bigger reservation just
# means more messages to redeliver when a pod is OOM-killed, and it lets one pod
# claim a burst its siblings could have shared. The `aux` pool overrides this to
# 4 on the command line -- rate-limited tasks hold their prefetch slot while
# waiting for a token, so they need headroom to wait in.
app.conf.worker_prefetch_multiplier = 1

# kombu's default visibility_timeout is 3600s, which is below the `bulk` hard
# time limit (5400s). A long acks_late export/import would otherwise outlive its
# visibility window and get delivered a second time while still running.
app.conf.broker_transport_options = {"visibility_timeout": 7200}

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
