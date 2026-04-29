"""
Unit tests for evaluation results helper functions and score extraction.

Targets: routers/evaluations/results.py — 7.37% coverage
Tests the _extract_primary_score function and request/response models.
"""

import pytest


class TestExtractPrimaryScore:
    """Test _extract_primary_score helper."""

    def test_none_metrics_returns_none(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score(None) is None

    def test_empty_metrics_returns_none(self):
        from routers.evaluations.results import _extract_primary_score
        assert _extract_primary_score({}) is None

    def test_llm_judge_custom_first_priority(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_custom": 0.85,
            "llm_judge_coherence": 0.7,
            "score": 0.5,
        }
        assert _extract_primary_score(metrics) == 0.85

    def test_generic_llm_judge_key(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_coherence": 0.91,
        }
        assert _extract_primary_score(metrics) == 0.91

    def test_llm_judge_skip_suffixes(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_response": "some text",
            "llm_judge_passed": True,
            "llm_judge_details": {"key": "val"},
            "llm_judge_raw": "raw output",
            "score": 0.88,
        }
        # All llm_judge_ keys have skip suffixes, so falls through to score
        assert _extract_primary_score(metrics) == 0.88

    def test_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0.92}
        assert _extract_primary_score(metrics) == 0.92

    def test_overall_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"overall_score": 0.77}
        assert _extract_primary_score(metrics) == 0.77

    def test_non_numeric_score_ignored(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {
            "llm_judge_custom": "not a number",
            "score": "also not",
        }
        assert _extract_primary_score(metrics) is None

    def test_integer_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 12}
        assert _extract_primary_score(metrics) == 12

    def test_float_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"llm_judge_custom": 14.5}
        assert _extract_primary_score(metrics) == 14.5

    def test_zero_score(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"score": 0}
        assert _extract_primary_score(metrics) == 0

    def test_no_matching_keys(self):
        from routers.evaluations.results import _extract_primary_score
        metrics = {"accuracy": 0.95, "f1": 0.88}
        # No recognized primary score key — returns None (no guessing)
        assert _extract_primary_score(metrics) is None


class TestEvaluationMetadataModels:
    """Test Pydantic models for evaluation metadata."""

    def test_statistics_request(self):
        from routers.evaluations.metadata import StatisticsRequest
        sr = StatisticsRequest(metrics=["accuracy", "f1"])
        assert sr.metrics == ["accuracy", "f1"]
        assert sr.aggregation == "model"
        assert sr.methods == ["ci"]

    def test_metric_statistics(self):
        from routers.evaluations.metadata import MetricStatistics
        ms = MetricStatistics(
            mean=0.85, std=0.05, ci_lower=0.80, ci_upper=0.90, n=100,
        )
        assert ms.mean == 0.85
        assert ms.n == 100

    def test_pairwise_comparison(self):
        from routers.evaluations.metadata import PairwiseComparison
        pc = PairwiseComparison(
            model_a="gpt-4o", model_b="claude-3", metric="accuracy",
        )
        assert pc.model_a == "gpt-4o"
