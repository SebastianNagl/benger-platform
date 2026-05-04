"""Tests for the fine-grained MetricRegistry / MetricHandler protocol.

Phase 1 of the academic-rigor overhaul. These tests fix the contract — any
later refactor that breaks a handler's expected return shape will surface
here, not in production.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from ml_evaluation.handlers import MetricHandler, MetricRegistry, extract_value


class _StubHandler(MetricHandler):
    """Bare-float result handler — the simplest case."""

    name = "stub_simple"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "value": 0.42,
            "method": self.name,
            "details": {"echoed_params": parameters or {}},
            "error": None,
        }


class _MultiOutHandler(MetricHandler):
    """Multi-output handler — exposes precision/recall/f1 from one call."""

    name = "stub_multi"
    primary_metric_key = "f1"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "value": {"precision": 0.9, "recall": 0.8, "f1": 0.85},
            "method": self.name,
            "primary_metric_key": self.primary_metric_key,
            "details": None,
            "error": None,
        }


class _NamelessHandler(MetricHandler):
    """Missing the required name attribute — registration must reject."""

    def compute(self, *a, **kw):
        return {"value": 0.0, "method": "?", "details": None, "error": None}


def test_register_and_get_returns_handler():
    reg = MetricRegistry()
    handler = _StubHandler()
    reg.register(handler)
    assert reg.get("stub_simple") is handler


def test_get_missing_metric_returns_none():
    reg = MetricRegistry()
    assert reg.get("does_not_exist") is None


def test_register_rejects_handler_without_name():
    reg = MetricRegistry()
    with pytest.raises(ValueError, match="must set a non-empty `name`"):
        reg.register(_NamelessHandler())


def test_register_replaces_existing_with_warning(caplog):
    reg = MetricRegistry()
    reg.register(_StubHandler())
    # Define a second handler with the same name; registration should
    # replace the first and emit a warning so accidental double-registration
    # at startup is observable.
    class _Replacement(MetricHandler):
        name = "stub_simple"

        def compute(self, *a, **kw):
            return {"value": 0.99, "method": self.name, "details": None, "error": None}

    with caplog.at_level("WARNING"):
        reg.register(_Replacement())
    assert any("already registered" in m for m in caplog.messages)
    assert reg.get("stub_simple").compute(None, None, "text", None)["value"] == 0.99


def test_names_lists_registered_handlers_sorted():
    reg = MetricRegistry()
    reg.register(_MultiOutHandler())
    reg.register(_StubHandler())
    assert reg.names() == ["stub_multi", "stub_simple"]


def test_extract_value_handles_bare_float():
    assert extract_value(0.5) == 0.5
    assert extract_value(1) == 1.0


def test_extract_value_handles_simple_dict_shape():
    assert extract_value({"value": 0.7, "method": "x"}) == 0.7


def test_extract_value_handles_multi_output_with_primary_key():
    result = {
        "value": {"precision": 0.9, "recall": 0.8, "f1": 0.85},
        "primary_metric_key": "f1",
    }
    assert extract_value(result) == 0.85


def test_extract_value_handles_multi_output_without_primary_key():
    # Falls back to the first key in dict insertion order.
    result = {"value": {"precision": 0.9, "recall": 0.8}}
    assert extract_value(result) == 0.9


def test_extract_value_returns_none_on_unrecognized_shape():
    assert extract_value(None) is None
    assert extract_value({"score": 0.5}) is None  # legacy "score" key not supported
    assert extract_value("0.5") is None  # strings rejected; never silently coerced


def test_global_registry_is_a_singleton_per_import():
    """The module-level `metric_registry` is the one production code uses;
    confirm it persists across imports and supports the handler protocol."""
    from ml_evaluation import metric_registry as r1
    from ml_evaluation import metric_registry as r2

    assert r1 is r2

    # Round-trip: register → get → unregister-via-replace
    r1.register(_StubHandler())
    try:
        assert r1.get("stub_simple") is not None
    finally:
        # Restore: registry has no public unregister; clear to avoid pollution
        # for downstream tests in the same pytest run.
        r1._handlers.pop("stub_simple", None)
