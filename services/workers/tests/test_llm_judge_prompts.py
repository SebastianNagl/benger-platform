"""Tests for ml_evaluation/llm_judge_prompts.py - prompt template registry.

Covers:
- get_template_for_type
- get_criteria_for_type
- get_all_criteria
- get_template_info
- PROMPT_TEMPLATES registry
- TYPE_SPECIFIC_CRITERIA definitions
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.llm_judge_prompts import (
    CHOICES_EVALUATION_PROMPT,
    NUMERIC_EVALUATION_PROMPT,
    PROMPT_TEMPLATES,
    SPAN_EVALUATION_PROMPT,
    TEXT_EVALUATION_PROMPT,
    TYPE_SPECIFIC_CRITERIA,
    get_all_criteria,
    get_criteria_for_type,
    get_template_for_type,
    get_template_info,
)


# ---------------------------------------------------------------------------
# get_template_for_type
# ---------------------------------------------------------------------------

class TestGetTemplateForType:

    def test_text_type(self):
        template = get_template_for_type("text")
        assert template == TEXT_EVALUATION_PROMPT
        assert "{context}" in template
        assert "{ground_truth}" in template

    def test_choices_type(self):
        assert get_template_for_type("choices") == CHOICES_EVALUATION_PROMPT

    def test_single_choice_type(self):
        assert get_template_for_type("single_choice") == CHOICES_EVALUATION_PROMPT

    def test_binary_type(self):
        assert get_template_for_type("binary") == CHOICES_EVALUATION_PROMPT

    def test_multiple_choice_type(self):
        assert get_template_for_type("multiple_choice") == CHOICES_EVALUATION_PROMPT

    def test_span_selection_type(self):
        assert get_template_for_type("span_selection") == SPAN_EVALUATION_PROMPT

    def test_rating_type(self):
        assert get_template_for_type("rating") == NUMERIC_EVALUATION_PROMPT

    def test_numeric_type(self):
        assert get_template_for_type("numeric") == NUMERIC_EVALUATION_PROMPT

    def test_unknown_type_fallback(self):
        template = get_template_for_type("unknown_type")
        assert template == TEXT_EVALUATION_PROMPT

    def test_short_text_type(self):
        assert get_template_for_type("short_text") == TEXT_EVALUATION_PROMPT

    def test_long_text_type(self):
        assert get_template_for_type("long_text") == TEXT_EVALUATION_PROMPT


# ---------------------------------------------------------------------------
# get_criteria_for_type
# ---------------------------------------------------------------------------

class TestGetCriteriaForType:

    def test_text_criteria(self):
        criteria = get_criteria_for_type("text")
        assert "helpfulness" in criteria
        assert "correctness" in criteria

    def test_choices_criteria(self):
        criteria = get_criteria_for_type("choices")
        assert "accuracy" in criteria
        assert "reasoning" in criteria

    def test_span_selection_criteria(self):
        criteria = get_criteria_for_type("span_selection")
        assert "boundary_accuracy" in criteria
        assert "label_accuracy" in criteria
        assert "coverage" in criteria

    def test_rating_criteria(self):
        criteria = get_criteria_for_type("rating")
        assert "precision" in criteria

    def test_numeric_criteria(self):
        criteria = get_criteria_for_type("numeric")
        assert "precision" in criteria
        assert "magnitude_accuracy" in criteria

    def test_multiple_choice_criteria(self):
        criteria = get_criteria_for_type("multiple_choice")
        assert "set_accuracy" in criteria
        assert "partial_credit" in criteria

    def test_unknown_type_fallback(self):
        criteria = get_criteria_for_type("unknown_type")
        assert "helpfulness" in criteria
        assert "correctness" in criteria


# ---------------------------------------------------------------------------
# get_all_criteria
# ---------------------------------------------------------------------------

class TestGetAllCriteria:

    def test_returns_dict(self):
        criteria = get_all_criteria()
        assert isinstance(criteria, dict)
        assert criteria is TYPE_SPECIFIC_CRITERIA

    def test_contains_accuracy(self):
        criteria = get_all_criteria()
        assert "accuracy" in criteria
        assert "name" in criteria["accuracy"]
        assert "description" in criteria["accuracy"]
        assert "rubric" in criteria["accuracy"]

    def test_contains_boundary_accuracy(self):
        criteria = get_all_criteria()
        assert "boundary_accuracy" in criteria

    def test_all_criteria_have_required_fields(self):
        for name, criterion in get_all_criteria().items():
            assert "name" in criterion, f"Missing 'name' in {name}"
            assert "description" in criterion, f"Missing 'description' in {name}"
            assert "rubric" in criterion, f"Missing 'rubric' in {name}"
            assert "scale" in criterion, f"Missing 'scale' in {name}"


# ---------------------------------------------------------------------------
# get_template_info
# ---------------------------------------------------------------------------

class TestGetTemplateInfo:

    def test_text_info(self):
        info = get_template_info("text")
        assert info["name"] == "Free-form Text"
        assert "template" in info
        assert "criteria" in info
        assert "hint" in info

    def test_choices_info(self):
        info = get_template_info("choices")
        assert info["name"] == "Classification (Single Choice)"

    def test_unknown_type_returns_text(self):
        info = get_template_info("unknown_type_xyz")
        assert info["name"] == "Free-form Text"

    def test_all_types_have_complete_info(self):
        for type_name, info in PROMPT_TEMPLATES.items():
            assert "name" in info, f"Missing 'name' in {type_name}"
            assert "description" in info, f"Missing 'description' in {type_name}"
            assert "template" in info, f"Missing 'template' in {type_name}"
            assert "criteria" in info, f"Missing 'criteria' in {type_name}"
            assert "hint" in info, f"Missing 'hint' in {type_name}"


# ---------------------------------------------------------------------------
# Template content validation
# ---------------------------------------------------------------------------

class TestTemplateContent:

    def test_text_template_has_placeholders(self):
        assert "{context}" in TEXT_EVALUATION_PROMPT
        assert "{ground_truth}" in TEXT_EVALUATION_PROMPT
        assert "{prediction}" in TEXT_EVALUATION_PROMPT
        assert "{criterion_name}" in TEXT_EVALUATION_PROMPT

    def test_choices_template_has_placeholders(self):
        assert "{context}" in CHOICES_EVALUATION_PROMPT
        assert "{ground_truth}" in CHOICES_EVALUATION_PROMPT
        assert "{prediction}" in CHOICES_EVALUATION_PROMPT

    def test_span_template_has_placeholders(self):
        assert "{context}" in SPAN_EVALUATION_PROMPT
        assert "{ground_truth}" in SPAN_EVALUATION_PROMPT
        assert "{prediction}" in SPAN_EVALUATION_PROMPT

    def test_numeric_template_has_placeholders(self):
        assert "{context}" in NUMERIC_EVALUATION_PROMPT
        assert "{ground_truth}" in NUMERIC_EVALUATION_PROMPT
        assert "{prediction}" in NUMERIC_EVALUATION_PROMPT

    def test_all_templates_request_json(self):
        """All templates should request JSON format responses."""
        for template in [TEXT_EVALUATION_PROMPT, CHOICES_EVALUATION_PROMPT,
                        SPAN_EVALUATION_PROMPT, NUMERIC_EVALUATION_PROMPT]:
            assert "JSON" in template or "json" in template
