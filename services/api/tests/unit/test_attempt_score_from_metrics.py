"""Unit tests for the unified attempt-score extractor.

Guards the nested-canonical contract: ``TaskEvaluation.metrics`` is always
``{"<metric_key>": {"value": <0..1>, ...}}`` (no writer produces a top-level
``value``), and the roster/dashboard readers extract through this helper.
"""

from routers.projects.helpers import (
    attempt_grade_points_from_metrics,
    attempt_score_from_metrics,
)


def test_nested_canonical_falloesung_shape():
    metrics = {
        "llm_judge_falloesung": {
            "value": 0.83,
            "method": "llm_judge_falloesung",
            "details": {"raw_score": 83, "grade_points": 12, "passed": True},
            "error": None,
        }
    }
    assert attempt_score_from_metrics(metrics) == 0.83


def test_top_level_value_wins_for_forward_compat():
    assert attempt_score_from_metrics({"value": 0.5, "x": {"value": 0.9}}) == 0.5


def test_multiple_metrics_take_max():
    metrics = {
        "korrektur_falloesung": {"value": 0.66},
        "llm_judge_falloesung": {"value": 0.83},
    }
    assert attempt_score_from_metrics(metrics) == 0.83


def test_error_row_yields_none():
    metrics = {
        "llm_judge_falloesung": {"value": None, "details": {}, "error": "timeout"}
    }
    assert attempt_score_from_metrics(metrics) is None


def test_noise_keys_are_ignored():
    # metric_filters excludes bookkeeping keys ("error", "raw_score", noise
    # suffixes); a stray dict-valued one must not be mistaken for a score.
    assert attempt_score_from_metrics({"error": {"value": 1.0}}) is None
    assert attempt_score_from_metrics({"loesung_details": {"value": 1.0}}) is None
    assert (
        attempt_score_from_metrics(
            {"error": {"value": 1.0}, "korrektur_falloesung": {"value": 0.4}}
        )
        == 0.4
    )


def test_non_dict_inputs():
    assert attempt_score_from_metrics(None) is None
    assert attempt_score_from_metrics([]) is None
    assert attempt_score_from_metrics({}) is None
    # booleans are not scores
    assert attempt_score_from_metrics({"m": {"value": True}}) is None


def _feedback(review=None, value=0.55):
    details = {"feedback_only": True, "grade": {"note": 11.0}}
    if review is not None:
        details["review"] = review
    return {"value": value, "method": "llm_judge_feedback", "details": details, "error": None}


def test_unreleased_feedback_draft_is_no_attempt_score():
    assert attempt_score_from_metrics({"llm_judge_feedback": _feedback()}) is None
    draft = _feedback(review={"status": "draft"})
    assert attempt_score_from_metrics({"llm_judge_feedback": draft}) is None


def test_released_feedback_note_is_an_attempt_score():
    released = _feedback(review={"status": "released"})
    assert attempt_score_from_metrics({"llm_judge_feedback": released}) == 0.55


def test_unreleased_feedback_never_outranks_a_score_on_the_same_row():
    metrics = {
        "llm_judge_feedback": _feedback(value=0.9),
        "llm_judge_falloesung": {"value": 0.65, "details": {"grade_points": 8}},
    }
    assert attempt_score_from_metrics(metrics) == 0.65
    assert attempt_grade_points_from_metrics(metrics) == 8


def test_a_metric_that_is_not_feedback_only_needs_no_release():
    assert attempt_score_from_metrics({"m": {"value": 0.4, "details": {"review": {}}}}) == 0.4


def test_unreleased_feedback_has_no_grade_points():
    draft = _feedback()
    draft["details"]["grade_points"] = 12
    assert attempt_grade_points_from_metrics({"llm_judge_feedback": draft}) is None
