"""Tests for ProjectUpdate validators: conditional_instructions and strict_timer."""

import pytest
from pydantic import ValidationError

from project_schemas import ProjectUpdate


class TestConditionalInstructionsValidator:
    """Validate conditional_instructions field on ProjectUpdate."""

    def test_none_is_valid(self):
        update = ProjectUpdate(conditional_instructions=None)
        assert update.conditional_instructions is None

    def test_valid_variants(self):
        variants = [
            {"id": "a", "content": "Instruction A", "weight": 50},
            {"id": "b", "content": "Instruction B", "weight": 50},
        ]
        update = ProjectUpdate(conditional_instructions=variants)
        assert len(update.conditional_instructions) == 2

    def test_single_variant_valid(self):
        variants = [{"id": "only", "content": "Only variant", "weight": 100}]
        update = ProjectUpdate(conditional_instructions=variants)
        assert update.conditional_instructions[0]["id"] == "only"

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string 'id'"):
            ProjectUpdate(conditional_instructions=[{"id": "", "content": "text", "weight": 50}])

    def test_missing_id_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string 'id'"):
            ProjectUpdate(conditional_instructions=[{"content": "text", "weight": 50}])

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string 'content'"):
            ProjectUpdate(conditional_instructions=[{"id": "a", "content": "", "weight": 50}])

    def test_missing_content_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string 'content'"):
            ProjectUpdate(conditional_instructions=[{"id": "a", "weight": 50}])

    def test_zero_weight_rejected(self):
        with pytest.raises(ValidationError, match="positive numeric 'weight'"):
            ProjectUpdate(conditional_instructions=[{"id": "a", "content": "text", "weight": 0}])

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError, match="positive numeric 'weight'"):
            ProjectUpdate(conditional_instructions=[{"id": "a", "content": "text", "weight": -1}])

    def test_missing_weight_rejected(self):
        with pytest.raises(ValidationError, match="positive numeric 'weight'"):
            ProjectUpdate(conditional_instructions=[{"id": "a", "content": "text"}])

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate variant id"):
            ProjectUpdate(
                conditional_instructions=[
                    {"id": "a", "content": "first", "weight": 50},
                    {"id": "a", "content": "second", "weight": 50},
                ]
            )

    def test_whitespace_only_id_rejected(self):
        with pytest.raises(ValidationError, match="non-empty string 'id'"):
            ProjectUpdate(conditional_instructions=[{"id": "   ", "content": "text", "weight": 50}])

    def test_float_weight_accepted(self):
        variants = [{"id": "a", "content": "text", "weight": 1.5}]
        update = ProjectUpdate(conditional_instructions=variants)
        assert update.conditional_instructions[0]["weight"] == 1.5


class TestStrictTimerValidator:
    """Validate strict_timer cross-field constraint on ProjectUpdate."""

    def test_strict_timer_without_time_limit_rejected(self):
        with pytest.raises(ValidationError, match="strict_timer_enabled requires"):
            ProjectUpdate(strict_timer_enabled=True, annotation_time_limit_enabled=False)

    def test_strict_timer_with_time_limit_accepted(self):
        update = ProjectUpdate(strict_timer_enabled=True, annotation_time_limit_enabled=True)
        assert update.strict_timer_enabled is True

    def test_strict_timer_alone_accepted(self):
        """When annotation_time_limit_enabled is not in the update (None), no error."""
        update = ProjectUpdate(strict_timer_enabled=True)
        assert update.strict_timer_enabled is True

    def test_disable_time_limit_alone_accepted(self):
        update = ProjectUpdate(annotation_time_limit_enabled=False)
        assert update.annotation_time_limit_enabled is False

    def test_both_false_accepted(self):
        update = ProjectUpdate(strict_timer_enabled=False, annotation_time_limit_enabled=False)
        assert update.strict_timer_enabled is False
