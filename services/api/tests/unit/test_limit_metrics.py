"""services/limit_metrics.py: counter names and labels, zero-filled series,
recording never raises."""

from prometheus_client import CollectorRegistry

from services import limit_metrics


def _with_registry():
    registry = CollectorRegistry()
    limit_metrics.use_registry(registry)
    return registry


def test_known_series_start_at_zero():
    registry = _with_registry()
    try:
        limit_metrics.record_rate_limited("upload_url")  # creates the counters
        for limit in limit_metrics.LIMITS:
            expected = 1.0 if limit == "upload_url" else 0.0
            assert (
                registry.get_sample_value("benger_rate_limited_total", {"limit": limit})
                == expected
            )
        for status_class in limit_metrics.STATUS_CLASSES:
            assert registry.get_sample_value(
                "benger_api_key_requests_total", {"status_class": status_class}
            ) == 0.0
    finally:
        limit_metrics.use_registry(None)


def test_status_classes_and_unknown_limits():
    registry = _with_registry()
    try:
        for code in (200, 204, 301, 404, 429, 500, None, "x", 999):
            limit_metrics.record_key_request(code)
        sample = lambda c: registry.get_sample_value(  # noqa: E731
            "benger_api_key_requests_total", {"status_class": c}
        )
        assert (sample("2xx"), sample("3xx"), sample("4xx"), sample("5xx")) == (2, 1, 2, 4)
        limit_metrics.record_rate_limited("made_up")
        assert registry.get_sample_value("benger_rate_limited_total", {"limit": "other"}) == 1
    finally:
        limit_metrics.use_registry(None)


def test_recording_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("registry broken")

    monkeypatch.setattr(limit_metrics, "_get", boom)
    limit_metrics.record_key_request(200)
    limit_metrics.record_rate_limited("api_key")
