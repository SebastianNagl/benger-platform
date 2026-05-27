"""Coverage for the shared metric-key noise filter.

`metric_filters.metric_key_is_real` is the single source of truth used by
the projects-list tally, the leaderboard aggregator, and the worker
recompute path. Drift between these would silently drop or double-count
metrics in tiles.
"""

from __future__ import annotations

from metric_filters import metric_key_is_real


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

    def test_other_grade_points_keys_still_filtered(self):
        # Override is explicit; unknown `*_grade_points` keys stay filtered.
        assert metric_key_is_real("accuracy_grade_points") == False  # noqa: E712
        assert metric_key_is_real("bleu_grade_points") == False  # noqa: E712
