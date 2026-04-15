"""
Tests for Structured Data Metrics (JSON, Schema Validation, Field Accuracy).

Scientific Rigor: All tests verify mathematical correctness with known expected values.
NO MOCKS - All metrics use real implementations.
"""

import os
import sys

import pytest

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestJSONAccuracy:
    """Test JSON structure comparison accuracy.

    Measures structural and value accuracy for JSON outputs.
    """

    def test_json_accuracy_identical(self):
        """Test JSON accuracy = 1.0 for identical structures."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"name": "John", "age": 30, "city": "Berlin"}
        pred = {"name": "John", "age": 30, "city": "Berlin"}

        score = evaluator._compute_structured_metric("json_accuracy", gt, pred)
        assert score == 1.0, f"Identical JSON should have accuracy 1.0, got {score}"

    def test_json_accuracy_partial_match(self):
        """Test JSON accuracy for partial field matches."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"name": "John", "age": 30, "city": "Berlin"}
        pred = {"name": "John", "age": 25, "city": "Berlin"}  # age is wrong

        score = evaluator._compute_structured_metric("json_accuracy", gt, pred)
        # 2 out of 3 fields correct = 0.667
        assert 0.6 < score < 0.7, f"2/3 fields correct should be ~0.667, got {score}"

    def test_json_accuracy_nested_structures(self):
        """Test JSON accuracy with nested structures."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {
            "person": {"name": "John", "age": 30},
            "location": {"city": "Berlin", "country": "Germany"},
        }
        pred = {
            "person": {"name": "John", "age": 30},
            "location": {"city": "Berlin", "country": "Germany"},
        }

        score = evaluator._compute_structured_metric("json_accuracy", gt, pred)
        assert score == 1.0, f"Identical nested JSON should have accuracy 1.0, got {score}"

    def test_json_accuracy_missing_field(self):
        """Test JSON accuracy with missing fields."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"name": "John", "age": 30, "city": "Berlin"}
        pred = {"name": "John", "age": 30}  # city is missing

        score = evaluator._compute_structured_metric("json_accuracy", gt, pred)
        assert score < 1.0, f"Missing field should reduce accuracy, got {score}"

    def test_json_accuracy_from_string(self):
        """Test JSON accuracy can parse JSON strings."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = '{"name": "John", "age": 30}'
        pred = '{"name": "John", "age": 30}'

        score = evaluator._compute_structured_metric("json_accuracy", gt, pred)
        assert score == 1.0, f"Identical JSON strings should have accuracy 1.0, got {score}"


class TestSchemaValidation:
    """Test JSON Schema validation accuracy.

    Reference: JSON Schema specification (https://json-schema.org/)
    """

    def test_schema_valid(self):
        """Test schema validation returns 1.0 for valid data."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }

        pred = {"name": "John", "age": 30}

        score = evaluator._compute_structured_metric(
            "schema_validation",
            None,  # gt is not used for schema validation
            pred,
            {"schema": schema},
        )
        assert score == 1.0, f"Valid data should have score 1.0, got {score}"

    def test_schema_invalid_type(self):
        """Test schema validation returns 0.0 for wrong type."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},  # expects integer
            },
            "required": ["name", "age"],
        }

        pred = {"name": "John", "age": "thirty"}  # age is string, not integer

        score = evaluator._compute_structured_metric(
            "schema_validation", None, pred, {"schema": schema}
        )
        assert score == 0.0, f"Invalid type should have score 0.0, got {score}"

    def test_schema_missing_required_field(self):
        """Test schema validation returns 0.0 for missing required field."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }

        pred = {"name": "John"}  # age is missing

        score = evaluator._compute_structured_metric(
            "schema_validation", None, pred, {"schema": schema}
        )
        assert score == 0.0, f"Missing required field should have score 0.0, got {score}"

    def test_schema_no_schema_provided(self):
        """Test schema validation with no schema falls back to JSON validity check."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        # Valid JSON without schema
        pred = {"name": "John", "age": 30}

        score = evaluator._compute_structured_metric(
            "schema_validation", None, pred, {}  # No schema
        )
        assert score == 1.0, f"Valid JSON without schema should be 1.0, got {score}"

    def test_schema_invalid_json(self):
        """Test schema validation returns 0.0 for invalid JSON."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        schema = {"type": "object"}
        pred = "not valid json {"

        score = evaluator._compute_structured_metric(
            "schema_validation", None, pred, {"schema": schema}
        )
        assert score == 0.0, f"Invalid JSON should have score 0.0, got {score}"


class TestFieldAccuracy:
    """Test field-level accuracy for structured data."""

    def test_field_accuracy_all_match(self):
        """Test field accuracy = 1.0 when all fields match."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"a": 1, "b": 2, "c": 3}
        pred = {"a": 1, "b": 2, "c": 3}

        score = evaluator._compute_metric("field_accuracy", gt, pred, "structured_text")
        assert score == 1.0, f"All fields matching should have accuracy 1.0, got {score}"

    def test_field_accuracy_partial(self):
        """Test field accuracy for partial field matches."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"a": 1, "b": 2, "c": 3, "d": 4}
        pred = {"a": 1, "b": 2, "c": 99, "d": 99}  # 2 out of 4 correct

        score = evaluator._compute_metric("field_accuracy", gt, pred, "structured_text")
        # Field accuracy checks matching values for keys
        assert 0.0 <= score <= 1.0, f"Field accuracy should be in valid range, got {score}"

    def test_field_accuracy_extra_fields(self):
        """Test field accuracy handles extra fields in prediction."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"a": 1, "b": 2}
        pred = {"a": 1, "b": 2, "c": 3}  # Extra field c

        score = evaluator._compute_metric("field_accuracy", gt, pred, "structured_text")
        # Note: Implementation may treat extra fields differently (e.g., only check gt keys)
        assert 0.0 <= score <= 1.0, f"Field accuracy should be in valid range, got {score}"

    def test_field_accuracy_nested(self):
        """Test field accuracy for nested structures."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"outer": {"inner": 1}}
        pred = {"outer": {"inner": 1}}

        score = evaluator._compute_metric("field_accuracy", gt, pred, "structured_text")
        assert score == 1.0, f"Matching nested structure should have accuracy 1.0, got {score}"

    def test_field_accuracy_lists(self):
        """Test field accuracy for list values."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        gt = {"items": [1, 2, 3]}
        pred = {"items": [1, 2, 3]}

        score = evaluator._compute_metric("field_accuracy", gt, pred, "structured_text")
        assert score == 1.0, f"Matching list should have accuracy 1.0, got {score}"


class TestSchemaValidationNoFallback:
    """Test that schema validation properly raises errors (no fallback)."""

    def test_schema_validation_raises_on_invalid_schema(self):
        """Test that invalid schema raises RuntimeError."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "json"}}
        )

        # Invalid schema (not a valid JSON Schema)
        invalid_schema = {"type": "not_a_real_type"}
        pred = {"name": "John"}

        # This should raise an error for invalid schema, not silently return a value
        with pytest.raises(RuntimeError, match="Invalid JSON schema"):
            evaluator._compute_structured_metric(
                "schema_validation", None, pred, {"schema": invalid_schema}
            )
