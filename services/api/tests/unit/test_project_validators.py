"""Tests for ProjectUpdate validators: conditional_instructions."""

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
        variants = [{"id": "a", "content": "text", "weight": 100.0}]
        update = ProjectUpdate(conditional_instructions=variants)
        assert update.conditional_instructions[0]["weight"] == 100.0

