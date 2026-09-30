"""The shared merge + checks of an ``evaluation_config`` write.

``merge_evaluation_config`` and ``validate_evaluation_config_write`` are used
by both writers of the document (the eval-config PUT and ``PATCH
/projects/{id}``). Pure functions, pinned here without a database.
"""

import pytest
from fastapi import HTTPException

from routers.evaluations.config import (
    merge_evaluation_config,
    validate_evaluation_config_write,
)

STANDARD = {
    "unit": "percent",
    "preset": "standard",
    "thresholds": [13, 26, 39, 50, 54, 57, 60, 64, 67, 70, 74, 77, 80, 84, 87, 90, 94, 97],
    "rounding": "floor",
    "pass_grade": 4,
}


class TestMergeEvaluationConfig:
    def test_siblings_deep_merge(self):
        stored = {"a": {"x": 1, "y": 2}, "keep": True}
        merged = merge_evaluation_config(stored, {"a": {"y": 3}})
        assert merged == {"a": {"x": 1, "y": 3}, "keep": True}

    def test_the_grade_key_is_replaced_not_merged(self):
        absolute = {"thresholds": [0] * 9 + [150] * 9}
        merged = merge_evaluation_config({"grade_scale": STANDARD}, {"grade_scale": absolute})
        assert merged["grade_scale"] == absolute

    def test_a_null_grade_key_deletes_it(self):
        merged = merge_evaluation_config({"grade_scale": STANDARD, "x": 1}, {"grade_scale": None})
        assert merged == {"x": 1}

    def test_a_null_grade_key_on_an_empty_document_leaves_no_key(self):
        assert merge_evaluation_config({}, {"grade_scale": None}) == {}

    @pytest.mark.parametrize("stored", [{}, None, {"runs_per_task": 3}])
    def test_no_top_level_null_is_stored(self, stored):
        """deep_merge_dicts copies the body as is onto an empty document,
        nulls included; the shared merge drops them in every case."""
        merged = merge_evaluation_config(stored, {"runs_per_task": None, "x": 1})
        assert merged == {"x": 1}

    def test_no_grade_key_in_the_body_keeps_the_stored_one(self):
        merged = merge_evaluation_config({"grade_scale": STANDARD}, {"runs_per_task": 2})
        assert merged == {"grade_scale": STANDARD, "runs_per_task": 2}

    def test_inputs_are_not_mutated(self):
        stored = {"grade_scale": dict(STANDARD)}
        body = {"grade_scale": {"thresholds": list(range(18))}}
        merge_evaluation_config(stored, body)
        assert stored == {"grade_scale": STANDARD}

    @pytest.mark.parametrize("stored", [None, [], "x"])
    def test_a_non_dict_stored_document_counts_as_empty(self, stored):
        assert merge_evaluation_config(stored, {"x": 1}) == {"x": 1}


class TestValidateEvaluationConfigWrite:
    def _check(self, stored, body):
        validate_evaluation_config_write(body, merge_evaluation_config(stored, body))

    def test_the_reviewers_case_is_validated_as_stored(self):
        """Absolute thresholds are a valid key on their own. Replaced as a
        whole they stay valid; the check sees the stored form."""
        self._check({"grade_scale": STANDARD}, {"grade_scale": {"thresholds": [0] * 9 + [150] * 9}})

    def test_a_partial_key_is_not_completed_from_the_stored_one(self):
        with pytest.raises(HTTPException) as exc:
            self._check({"grade_scale": STANDARD}, {"grade_scale": {"pass_grade": 5}})
        assert exc.value.status_code == 422
        assert "thresholds" in exc.value.detail

    def test_the_merged_key_is_checked_not_the_body(self):
        """A merged document with an invalid key fails even when the body
        alone would pass. Guards the call order of the two helpers."""
        body = {"grade_scale": {"thresholds": [0] * 9 + [150] * 9}}
        merged = {"grade_scale": {**STANDARD, "thresholds": [0] * 9 + [150] * 9}}
        with pytest.raises(HTTPException) as exc:
            validate_evaluation_config_write(body, merged)
        assert exc.value.status_code == 422

    @pytest.mark.parametrize("value", [0, 26, "3", 1.5])
    def test_runs_per_task_out_of_contract(self, value):
        with pytest.raises(HTTPException) as exc:
            self._check({}, {"runs_per_task": value})
        assert exc.value.status_code == 422

    def test_a_null_runs_per_task_passes(self):
        self._check({"runs_per_task": 3}, {"runs_per_task": None})

    def test_unwritten_keys_are_not_checked(self):
        legacy = {
            "runs_per_task": 99,
            "grade_scale": {"thresholds": [1, 2]},
            "evaluation_configs": [{"metric": "llm_judge_rubric", "metric_parameters": {}}],
        }
        self._check(legacy, {"default_temperature": 0.3})

    @pytest.mark.parametrize("key", ["evaluation_configs", "multi_field_evaluations"])
    def test_every_written_entry_list_is_checked(self, key):
        entry = {
            "id": "a",
            "metric": "bleu",
            "prediction_fields": [],
            "reference_fields": ["task.expected"],
        }
        with pytest.raises(HTTPException) as exc:
            self._check({}, {key: [entry]})
        assert exc.value.status_code == 422
        assert "prediction_fields" in exc.value.detail

    def test_selected_methods_need_both_keys_in_the_body(self):
        stored = {"available_methods": {"answer": {"available_metrics": [], "available_human": []}}}
        # Only selected_methods in the body: the legacy check does not run,
        # the same trigger as the PUT always had.
        self._check(stored, {"selected_methods": {"answer": {"automated": ["bleu"]}}})

    def test_selected_methods_are_checked_on_the_merged_document(self):
        """A stored selection is checked against the newly written offer."""
        stored = {
            "selected_methods": {"old": {"automated": ["bleu"]}},
            "available_methods": {"old": {"available_metrics": ["bleu"], "available_human": []}},
        }
        body = {
            "selected_methods": {"answer": {"automated": ["exact_match"]}},
            "available_methods": {
                "answer": {"available_metrics": ["exact_match"], "available_human": []},
                "old": {"available_metrics": ["rouge"], "available_human": []},
            },
        }
        with pytest.raises(HTTPException) as exc:
            self._check(stored, body)
        assert exc.value.status_code == 400
        assert "bleu" in exc.value.detail
