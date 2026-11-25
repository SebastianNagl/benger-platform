"""Coverage for the shared metric-key noise filter.

`metric_filters.metric_key_is_real` is the single source of truth used by
the projects-list tally, the leaderboard aggregator, and the worker
recompute path. Drift between these would silently drop or double-count
metrics in tiles.
"""

from __future__ import annotations

from metric_filters import (
    GRADE_POINT_LIFT_BASES,
    blob_awaits_release,
    details_await_release,
    is_unreleased_feedback,
    metric_awaits_release,
    metric_key_counts_as_evaluation,
    metric_key_is_real,
    row_awaits_release,
)


class TestNoiseSuffixes:
    def test_real_metric_keys_pass(self):
        for k in ("accuracy", "bleu", "rouge", "llm_judge_falloesung"):
            assert metric_key_is_real(k) == True, k  # noqa: E712

    def test_noise_suffix_keys_filtered(self):
        for k in (
            "accuracy_details",
            "bleu_raw",
            "accuracy_passed",
            "bleu_grade_points",
            "rouge_response",
        ):
            assert metric_key_is_real(k) == False, k  # noqa: E712

    def test_excluded_keys_filtered(self):
        assert metric_key_is_real("raw_score") == False  # noqa: E712
        assert metric_key_is_real("error") == False  # noqa: E712

    def test_empty_or_none_filtered(self):
        assert metric_key_is_real(None) == False  # noqa: E712
        assert metric_key_is_real("") == False  # noqa: E712


class TestRegisteredOverrides:
    def test_llm_judge_falloesung_grade_points_passes(self):
        # Even though the key ends in `_grade_points` (normally a noise
        # suffix), it's a registered displayable sub-metric and must reach
        # the leaderboard aggregator.
        assert metric_key_is_real("llm_judge_falloesung_grade_points") == True  # noqa: E712

    def test_llm_judge_rubric_grade_points_passes(self):
        # The Bewertungsbogen judge writes the same companion next to its
        # rubric score. Without the override a rubric-graded project shows
        # n/a in the Notenpunkte column although every row carries the value.
        assert metric_key_is_real("llm_judge_rubric_grade_points") == True  # noqa: E712

    def test_other_grade_points_keys_still_filtered(self):
        # Override is explicit; unknown `*_grade_points` keys stay filtered.
        assert metric_key_is_real("accuracy_grade_points") == False  # noqa: E712
        assert metric_key_is_real("bleu_grade_points") == False  # noqa: E712


class TestCountsAsEvaluation:
    """`metric_key_counts_as_evaluation` feeds the evaluation tiles. A
    Notenpunkte twin is a second view of its judge call, not a second
    evaluation: counting it showed 49 evaluations on a project with 25."""

    def test_base_metrics_count(self):
        for k in (
            "accuracy",
            "llm_judge_falloesung",
            "llm_judge_rubric",
            "korrektur_falloesung",
            "korrektur_custom",
        ):
            assert metric_key_counts_as_evaluation(k) is True, k

    def test_registered_notenpunkte_twins_do_not_count(self):
        for k in (
            "llm_judge_falloesung_grade_points",
            "llm_judge_rubric_grade_points",
        ):
            # Still a real, displayable metric for the leaderboard column ...
            assert metric_key_is_real(k) is True, k
            # ... but never an evaluation of its own.
            assert metric_key_counts_as_evaluation(k) is False, k

    def test_noise_keys_do_not_count(self):
        for k in (
            "raw_score",
            "error",
            "llm_judge_rubric_passed",
            "korrektur_custom_grade_points",
            "accuracy_details",
            None,
            "",
        ):
            assert metric_key_counts_as_evaluation(k) is False, k

    def test_exact_prod_row_counts_once(self):
        # Key set of an immediate Bewertungsbogen judge row as stored in prod.
        row_keys = [
            "raw_score",
            "llm_judge_rubric",
            "llm_judge_rubric_grade_points",
            "llm_judge_rubric_passed",
        ]
        assert sum(metric_key_counts_as_evaluation(k) for k in row_keys) == 1


class TestGradePointLiftBases:
    def test_bases_are_the_registered_twins_without_suffix(self):
        # The leaderboard SQL lifts `details.grade_points` for exactly these
        # bases; deriving them keeps the SQL and the override list in step.
        assert set(GRADE_POINT_LIFT_BASES) == {
            "llm_judge_falloesung",
            "llm_judge_rubric",
        }
        for base in GRADE_POINT_LIFT_BASES:
            assert metric_key_is_real(f"{base}_grade_points") is True


class TestRowAwaitsRelease:
    @staticmethod
    def _feedback(review=None):
        details = {"feedback_only": True}
        if review is not None:
            details["review"] = review
        return {"llm_judge_feedback": {"value": None, "details": details}}

    def test_a_held_back_feedback_row_waits(self):
        assert row_awaits_release(self._feedback()) is True
        assert row_awaits_release(self._feedback({"status": "draft"})) is True

    def test_a_released_feedback_row_does_not_wait(self):
        assert row_awaits_release(self._feedback({"status": "released"})) is False

    def test_scored_and_odd_rows_do_not_wait(self):
        assert row_awaits_release({"exact_match": 1.0}) is False
        assert row_awaits_release({"llm_judge_falloesung": {"value": 0.7, "details": {}}}) is False
        assert row_awaits_release({}) is False
        assert row_awaits_release(None) is False

    def test_a_regraded_score_row_waits_until_released(self):
        draft = {"status": "draft", "reason": "regrade"}
        unified = {"llm_judge_rubric": {"value": 0.6, "details": {"review": draft}}}
        assert row_awaits_release(unified) is True
        assert row_awaits_release(
            {"llm_judge_rubric": {"value": 0.6, "details": {"review": {"status": "released"}}}}
        ) is False

    def test_a_flat_row_waits_through_its_details_sibling(self):
        draft = {"status": "draft", "reason": "regrade"}
        flat = {"llm_judge_custom": 0.6, "llm_judge_custom_details": {"review": draft}}
        assert row_awaits_release(flat) is True
        assert metric_awaits_release(flat, "llm_judge_custom") is True
        stamped = {"llm_judge_custom": 0.6, "llm_judge_custom_details": {"scheme_fingerprint": "x"}}
        assert row_awaits_release(stamped) is False


class TestReleasePredicates:
    def test_details_await_release(self):
        assert details_await_release({"review": {"status": "draft"}}) is True
        # A review without a status is no release state, unless the result
        # is feedback-only (which waits until a release).
        assert details_await_release({"review": {}}) is False
        assert details_await_release({"feedback_only": True, "review": {}}) is True
        assert details_await_release({"feedback_only": True}) is True
        assert details_await_release({"feedback_only": True, "review": {"status": "released"}}) is False
        assert details_await_release({"rubric_id": "r"}) is False
        assert details_await_release(None) is False

    def test_feedback_predicate_keeps_its_meaning(self):
        draft_score = {"value": 0.6, "details": {"review": {"status": "draft"}}}
        assert blob_awaits_release(draft_score) is True
        assert is_unreleased_feedback(draft_score) is False
        assert is_unreleased_feedback({"value": None, "details": {"feedback_only": True}}) is True
