"""Coverage for the shared metric-key noise filter.

`metric_filters.metric_key_is_real` is the single source of truth used by
the projects-list tally, the leaderboard aggregator, and the worker
recompute path. Drift between these would silently drop or double-count
metrics in tiles.
"""

from __future__ import annotations

from metric_filters import (
    GRADE_POINT_LIFT_BASES,
    metric_key_counts_as_evaluation,
    metric_key_is_real,
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

