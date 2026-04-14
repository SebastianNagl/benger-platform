"""Tests for model_parameter_config.py - model parameter constraints and reproducibility.

Covers:
- Default behavior (no constraints, no user override)
- User temperature override
- Model constraints: temperature not supported (fixed value)
- Model constraints: min/max temperature clamping
- Model constraints: conflicting parameters
- Unsupported parameters
- Reproducibility level classification
- Project config max_tokens
- Benchmark notes and reproducibility impact overrides
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from model_parameter_config import get_model_generation_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_with_constraints(constraints):
    """Return a mock db session whose model.parameter_constraints == constraints."""
    db = MagicMock()
    model = MagicMock()
    model.parameter_constraints = constraints
    db.query.return_value.filter.return_value.first.return_value = model
    return db


def _mock_db_no_model():
    """Return a mock db session where no model is found."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


class MockModelORM:
    id = "test-model"


# ---------------------------------------------------------------------------
# Default / no constraints
# ---------------------------------------------------------------------------

class TestDefaultBehavior:

    def test_defaults_no_constraints(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "test-model", model_orm_class=MockModelORM)
        assert result["temperature"] == 0.0
        assert result["max_tokens"] == 1500
        assert result["reproducibility_level"] == "HIGH"
        assert result["warnings"] == []

    def test_defaults_without_orm_class(self):
        db = MagicMock()
        result = get_model_generation_params(db, "test-model")
        assert result["temperature"] == 0.0
        assert result["reproducibility_level"] == "HIGH"

    def test_default_max_tokens(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["max_tokens"] == 1500


# ---------------------------------------------------------------------------
# User temperature overrides
# ---------------------------------------------------------------------------

class TestUserTemperature:

    def test_user_temp_zero(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", user_temp=0.0, model_orm_class=MockModelORM)
        assert result["temperature"] == 0.0
        assert result["reproducibility_level"] == "HIGH"

    def test_user_temp_nonzero(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", user_temp=0.7, model_orm_class=MockModelORM)
        assert result["temperature"] == 0.7
        assert result["reproducibility_level"] == "MEDIUM"


# ---------------------------------------------------------------------------
# Temperature not supported (e.g. GPT-5)
# ---------------------------------------------------------------------------

class TestTemperatureNotSupported:

    def test_forced_temperature(self):
        constraints = {"temperature": {"supported": False, "required_value": 1.0, "reason": "API req"}}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "gpt-5", model_orm_class=MockModelORM)
        assert result["temperature"] == 1.0
        assert result["reproducibility_level"] == "NONE"

    def test_user_override_ignored_with_warning(self):
        constraints = {"temperature": {"supported": False, "required_value": 1.0, "reason": "API req"}}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "gpt-5", user_temp=0.0, model_orm_class=MockModelORM)
        assert result["temperature"] == 1.0
        assert len(result["warnings"]) == 1
        assert "Ignoring user setting" in result["warnings"][0]


# ---------------------------------------------------------------------------
# Temperature min/max clamping (e.g. Qwen thinking models min=0.6)
# ---------------------------------------------------------------------------

class TestTemperatureClamping:

    def test_clamp_to_min(self):
        """User sets temp below model minimum -> clamped up with warning."""
        constraints = {
            "temperature": {
                "supported": True,
                "default": 0.6,
                "min": 0.6,
                "max": 2.0,
                "reason": "Qwen thinking issue",
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "qwen", user_temp=0.0, model_orm_class=MockModelORM)
        assert result["temperature"] == 0.6
        assert result["reproducibility_level"] == "MEDIUM"
        assert len(result["warnings"]) == 1
        assert "clamping" in result["warnings"][0].lower()

    def test_clamp_to_max(self):
        """User sets temp above model maximum -> clamped down with warning."""
        constraints = {
            "temperature": {
                "supported": True,
                "default": 0.0,
                "min": 0.0,
                "max": 1.0,
                "reason": "Anthropic limit",
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "claude", user_temp=1.5, model_orm_class=MockModelORM)
        assert result["temperature"] == 1.0
        assert len(result["warnings"]) == 1
        assert "clamping" in result["warnings"][0].lower()

    def test_within_range_no_warning(self):
        """User sets temp within allowed range -> no clamping, no warning."""
        constraints = {
            "temperature": {
                "supported": True,
                "default": 0.6,
                "min": 0.6,
                "max": 2.0,
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "qwen", user_temp=0.8, model_orm_class=MockModelORM)
        assert result["temperature"] == 0.8
        assert result["warnings"] == []

    def test_default_respects_min(self):
        """No user temp, model default is used (already within range)."""
        constraints = {
            "temperature": {
                "supported": True,
                "default": 0.6,
                "min": 0.6,
                "max": 2.0,
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "qwen", model_orm_class=MockModelORM)
        assert result["temperature"] == 0.6
        assert result["warnings"] == []

    def test_system_default_clamped_to_min(self):
        """No user temp, no model default -> system default (0.0) gets clamped to min."""
        constraints = {
            "temperature": {
                "supported": True,
                "min": 0.6,
                "max": 2.0,
                "reason": "Min temp required",
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["temperature"] == 0.6
        assert len(result["warnings"]) == 1

    def test_no_min_max_no_clamping(self):
        """Model has supported temp but no min/max -> standard behavior."""
        constraints = {
            "temperature": {
                "supported": True,
                "default": 0.3,
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", user_temp=1.8, model_orm_class=MockModelORM)
        assert result["temperature"] == 1.8
        assert result["warnings"] == []


# ---------------------------------------------------------------------------
# Conflicting parameters
# ---------------------------------------------------------------------------

class TestConflictingParams:

    def test_conflict_with_temperature(self):
        constraints = {
            "top_p": {
                "conflicts_with": ["temperature"],
                "reason": "Cannot use both",
            }
        }
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert "top_p" in result["params_omitted"]
        assert any("top_p" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Unsupported parameters
# ---------------------------------------------------------------------------

class TestUnsupportedParams:

    def test_unsupported_params_listed(self):
        constraints = {"unsupported_params": ["logprobs", "top_logprobs"]}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert "logprobs" in result["params_omitted"]
        assert "top_logprobs" in result["params_omitted"]


# ---------------------------------------------------------------------------
# Project config max_tokens
# ---------------------------------------------------------------------------

class TestProjectConfig:

    def test_project_max_tokens(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(
            db, "m", project_config={"max_tokens": 4096}, model_orm_class=MockModelORM,
        )
        assert result["max_tokens"] == 4096

    def test_default_max_tokens_without_project_config(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["max_tokens"] == 1500


# ---------------------------------------------------------------------------
# Reproducibility impact / benchmark notes
# ---------------------------------------------------------------------------

class TestReproducibilityImpact:

    def test_critical_impact_overrides_to_none(self):
        constraints = {"reproducibility_impact": "CRITICAL: no determinism possible"}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["reproducibility_level"] == "NONE"

    def test_low_medium_impact_overrides(self):
        constraints = {"reproducibility_impact": "LOW-MEDIUM variability"}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["reproducibility_level"] == "MEDIUM"

    def test_benchmark_notes_returned(self):
        constraints = {"benchmark_notes": "Model requires special handling"}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["benchmark_notes"] == "Model requires special handling"

    def test_empty_benchmark_notes(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["benchmark_notes"] == ""


# ---------------------------------------------------------------------------
# Model default temperature
# ---------------------------------------------------------------------------

class TestModelDefaultTemperature:

    def test_model_default_temp(self):
        constraints = {"temperature": {"default": 0.3}}
        db = _mock_db_with_constraints(constraints)
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert result["temperature"] == 0.3
        assert result["reproducibility_level"] == "MEDIUM"


# ---------------------------------------------------------------------------
# DB errors handled gracefully
# ---------------------------------------------------------------------------

class TestDbErrorHandling:

    def test_db_query_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("connection lost")
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        # Should fall back to defaults
        assert result["temperature"] == 0.0
        assert result["reproducibility_level"] == "HIGH"


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

class TestReturnStructure:

    def test_all_keys_present(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        expected_keys = {
            "temperature",
            "max_tokens",
            "params_used",
            "params_omitted",
            "reproducibility_level",
            "warnings",
            "benchmark_notes",
            "reproducibility_impact",
        }
        assert set(result.keys()) == expected_keys

    def test_params_used_contains_temperature_and_max_tokens(self):
        db = _mock_db_no_model()
        result = get_model_generation_params(db, "m", model_orm_class=MockModelORM)
        assert "temperature" in result["params_used"]
        assert "max_tokens" in result["params_used"]
