"""Prometheus counters for access-key use and refused requests.

- ``benger_api_key_requests_total{status_class}``: requests authenticated
  with an access key (on ``/api/v1`` and the full API), by response status
  class (``2xx`` ... ``5xx``). Counted by ``middleware/api_usage.py`` next to
  the usage event it writes for the same request.
- ``benger_rate_limited_total{limit}``: requests answered 429 by one of the
  abuse limits: ``api_key`` (a key's own per-minute/per-day budget),
  ``user_bearer`` (``BEARER_TOKEN_RPM``), ``upload_url``
  (``UPLOAD_URLS_PER_DAY``) and ``active_runs`` (``MAX_ACTIVE_RUNS_PER_USER``).

The counters live in ``prometheus_client``'s default registry. The platform
serves no metrics endpoint itself; an extension's ``/internal/metrics`` (which
merges the default registry, or every process's files in multiprocess mode
with ``PROMETHEUS_MULTIPROC_DIR``) exports them. They are created on first
use, not at import, because multiprocess mode needs its directory to exist
before a metric is created. Recording never raises.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

#: ``limit`` label values of ``benger_rate_limited_total``.
LIMITS = ("api_key", "user_bearer", "upload_url", "active_runs")
#: ``status_class`` label values of ``benger_api_key_requests_total``.
STATUS_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx")

_lock = threading.Lock()
_metrics = None


class _Metrics:
    def __init__(self, registry=None):
        from prometheus_client import REGISTRY, Counter

        registry = REGISTRY if registry is None else registry
        self.key_requests = Counter(
            "benger_api_key_requests_total",
            "Requests authenticated with an access key, by response status class.",
            ["status_class"],
            registry=registry,
        )
        self.rate_limited = Counter(
            "benger_rate_limited_total",
            "Requests refused with 429 by an abuse limit, by limit.",
            ["limit"],
            registry=registry,
        )
        # Every known series starts at 0: increase() cannot see the first
        # jump of a series that appears at 1, so the first 429 would not alert.
        for status_class in STATUS_CLASSES:
            self.key_requests.labels(status_class)
        for limit in LIMITS:
            self.rate_limited.labels(limit)


def _get():
    global _metrics
    if _metrics is None:
        with _lock:
            if _metrics is None:
                _metrics = _Metrics()
    return _metrics


def use_registry(registry) -> None:
    """Bind the counters to ``registry`` (tests); None resets to the default
    registry on next use."""
    global _metrics
    with _lock:
        _metrics = _Metrics(registry) if registry is not None else None


def status_class(status_code) -> str:
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return "5xx"
    if 100 <= code < 600:
        return f"{code // 100}xx"
    return "5xx"


def record_key_request(status_code) -> None:
    try:
        _get().key_requests.labels(status_class(status_code)).inc()
    except Exception:  # noqa: BLE001 - metrics must never break a request
        logger.debug("api key request metric not recorded", exc_info=True)


def record_rate_limited(limit: str) -> None:
    try:
        _get().rate_limited.labels(limit if limit in LIMITS else "other").inc()
    except Exception:  # noqa: BLE001 - metrics must never break a request
        logger.debug("rate limit metric not recorded", exc_info=True)
