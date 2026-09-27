"""The shared merge of an ``evaluation_config`` write.

``merge_evaluation_config`` is used by both writers of the document (the
eval-config PUT and ``PATCH /projects/{id}``). Pure, pinned here without a
database.
"""

import pytest
from fastapi import HTTPException

from routers.evaluations.config import (
    merge_evaluation_config,
    validate_eval_config_grade_scale,
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


class TestGradeKeyIsCheckedAsStored:
    def test_the_reviewers_case_is_valid_once_replaced(self):
        body = {"grade_scale": {"thresholds": [0] * 9 + [150] * 9}}
        validate_eval_config_grade_scale(merge_evaluation_config({"grade_scale": STANDARD}, body))

    def test_a_partial_key_is_not_completed_from_the_stored_one(self):
        body = {"grade_scale": {"pass_grade": 5}}
        with pytest.raises(HTTPException) as exc:
            validate_eval_config_grade_scale(
                merge_evaluation_config({"grade_scale": STANDARD}, body)
            )
        assert exc.value.status_code == 422
        assert "thresholds" in exc.value.detail
