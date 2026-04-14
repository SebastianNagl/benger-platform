"""Coverage tests for ml_evaluation/llm_judge_prompts.py.

Tests: get_template_for_type, get_criteria_for_type, get_all_criteria,
get_template_info, PROMPT_TEMPLATES, TYPE_SPECIFIC_CRITERIA.
"""

import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from ml_evaluation.llm_judge_prompts import (
    TEXT_EVALUATION_PROMPT,
    CHOICES_EVALUATION_PROMPT,
    SPAN_EVALUATION_PROMPT,
    NUMERIC_EVALUATION_PROMPT,
    TYPE_SPECIFIC_CRITERIA,
    PROMPT_TEMPLATES,
    get_template_for_type,
    get_criteria_for_type,
    get_all_criteria,
    get_template_info,
)


class TestGetTemplateForType:
    def test_text(self):
        assert get_template_for_type("text") == TEXT_EVALUATION_PROMPT

    def test_short_text(self):
        assert get_template_for_type("short_text") == TEXT_EVALUATION_PROMPT

    def test_long_text(self):
        assert get_template_for_type("long_text") == TEXT_EVALUATION_PROMPT

    def test_choices(self):
        assert get_template_for_type("choices") == CHOICES_EVALUATION_PROMPT

    def test_single_choice(self):
        assert get_template_for_type("single_choice") == CHOICES_EVALUATION_PROMPT

    def test_binary(self):
        assert get_template_for_type("binary") == CHOICES_EVALUATION_PROMPT

    def test_multiple_choice(self):
        assert get_template_for_type("multiple_choice") == CHOICES_EVALUATION_PROMPT

    def test_span_selection(self):
        assert get_template_for_type("span_selection") == SPAN_EVALUATION_PROMPT

    def test_rating(self):
        assert get_template_for_type("rating") == NUMERIC_EVALUATION_PROMPT

    def test_numeric(self):
        assert get_template_for_type("numeric") == NUMERIC_EVALUATION_PROMPT

    def test_unknown_falls_back_to_text(self):
        assert get_template_for_type("nonexistent") == TEXT_EVALUATION_PROMPT


class TestGetCriteriaForType:
    def test_text(self):
        criteria = get_criteria_for_type("text")
        assert "correctness" in criteria
        assert "coherence" in criteria

    def test_choices(self):
        criteria = get_criteria_for_type("choices")
        assert "accuracy" in criteria

    def test_span_selection(self):
        criteria = get_criteria_for_type("span_selection")
        assert "boundary_accuracy" in criteria

    def test_numeric(self):
        criteria = get_criteria_for_type("numeric")
        assert "precision" in criteria

    def test_unknown_falls_back(self):
        criteria = get_criteria_for_type("nonexistent")
        assert "correctness" in criteria


class TestGetAllCriteria:
    def test_returns_dict(self):
        result = get_all_criteria()
        assert isinstance(result, dict)
        assert "accuracy" in result
        assert "boundary_accuracy" in result
        assert "precision" in result

    def test_each_criterion_has_required_fields(self):
        for name, criterion in get_all_criteria().items():
            assert "name" in criterion
            assert "description" in criterion
            assert "scale" in criterion
            assert "rubric" in criterion


class TestGetTemplateInfo:
    def test_text(self):
        info = get_template_info("text")
        assert "name" in info
        assert "template" in info
        assert "criteria" in info
        assert "hint" in info

    def test_unknown_falls_back_to_text(self):
        info = get_template_info("nonexistent")
        assert info == PROMPT_TEMPLATES["text"]

    def test_all_types_have_info(self):
        for type_name in PROMPT_TEMPLATES:
            info = get_template_info(type_name)
            assert "name" in info
            assert "template" in info


class TestPromptTemplatesCompleteness:
    def test_all_types_present(self):
        expected = [
            "text", "short_text", "long_text", "choices", "single_choice",
            "binary", "multiple_choice", "span_selection", "rating", "numeric",
        ]
        for t in expected:
            assert t in PROMPT_TEMPLATES

    def test_templates_have_placeholders(self):
        for type_name, config in PROMPT_TEMPLATES.items():
            template = config["template"]
            assert "{context}" in template
            assert "{ground_truth}" in template
            assert "{prediction}" in template

    def test_templates_have_json_output(self):
        for type_name, config in PROMPT_TEMPLATES.items():
            template = config["template"]
            assert "score" in template.lower()
