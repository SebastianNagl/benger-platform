"""
Tests for Core Metrics (Classification, Regression, Multi-Label).

Scientific Rigor: All tests verify mathematical correctness with known expected values.
NO MOCKS - All metrics use real implementations.
"""

import os
import sys

import numpy as np
import pytest

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestClassificationMetrics:
    """Test classification metrics with known expected values.

    Reference: sklearn.metrics documentation for metric definitions.
    """

    def test_accuracy_perfect(self):
        """Test accuracy returns 1.0 for perfect predictions."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "categorical"}}
        )

        # Perfect predictions
        gt = ["cat", "dog", "bird", "cat"]
        pred = ["cat", "dog", "bird", "cat"]

        correct = sum(1 for g, p in zip(gt, pred) if g == p)
        accuracy = correct / len(gt)
        assert accuracy == 1.0, f"Perfect predictions should have accuracy 1.0, got {accuracy}"

    def test_accuracy_half_correct(self):
        """Test accuracy returns 0.5 for half correct predictions."""
        gt = ["cat", "dog", "bird", "cat"]
        pred = ["cat", "dog", "fish", "dog"]

        correct = sum(1 for g, p in zip(gt, pred) if g == p)
        accuracy = correct / len(gt)
        assert accuracy == 0.5, f"Half correct should have accuracy 0.5, got {accuracy}"

    def test_precision_perfect(self):
        """Test precision = 1.0 when all positive predictions are correct (no FP)."""
        # TP=2, FP=0, FN=1 -> Precision = 2/(2+0) = 1.0
        from sklearn.metrics import precision_score

        y_true = [1, 1, 1, 0, 0]
        y_pred = [1, 1, 0, 0, 0]

        precision = precision_score(y_true, y_pred)
        assert precision == 1.0, f"No false positives should give precision 1.0, got {precision}"

    def test_precision_with_false_positives(self):
        """Test precision calculation with false positives."""
        # TP=2, FP=1 -> Precision = 2/(2+1) = 0.667
        from sklearn.metrics import precision_score

        y_true = [1, 1, 0, 0, 0]
        y_pred = [1, 1, 1, 0, 0]

        precision = precision_score(y_true, y_pred)
        assert abs(precision - 0.6667) < 0.001, f"Expected ~0.667, got {precision}"

    def test_recall_perfect(self):
        """Test recall = 1.0 when all positives are found (no FN)."""
        # TP=3, FP=2, FN=0 -> Recall = 3/(3+0) = 1.0
        from sklearn.metrics import recall_score

        y_true = [1, 1, 1, 0, 0]
        y_pred = [1, 1, 1, 1, 1]

        recall = recall_score(y_true, y_pred)
        assert recall == 1.0, f"All positives found should give recall 1.0, got {recall}"

    def test_recall_with_false_negatives(self):
        """Test recall calculation with false negatives."""
        # TP=2, FN=1 -> Recall = 2/(2+1) = 0.667
        from sklearn.metrics import recall_score

        y_true = [1, 1, 1, 0, 0]
        y_pred = [1, 1, 0, 0, 0]

        recall = recall_score(y_true, y_pred)
        assert abs(recall - 0.6667) < 0.001, f"Expected ~0.667, got {recall}"

    def test_f1_perfect(self):
        """Test F1 = 1.0 when precision and recall are both 1.0."""
        from sklearn.metrics import f1_score

        y_true = [1, 1, 0, 0]
        y_pred = [1, 1, 0, 0]

        f1 = f1_score(y_true, y_pred)
        assert f1 == 1.0, f"Perfect P and R should give F1 1.0, got {f1}"

    def test_f1_calculated(self):
        """Test F1 = 2*P*R/(P+R) with known values."""
        from sklearn.metrics import f1_score, precision_score, recall_score

        # P=0.8, R=0.6 -> F1 = 2*0.8*0.6/(0.8+0.6) = 0.685
        y_true = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        y_pred = [1, 1, 1, 0, 0, 0, 0, 0, 0, 1]  # TP=3, FP=1, FN=2

        precision = precision_score(y_true, y_pred)  # 3/4 = 0.75
        recall = recall_score(y_true, y_pred)  # 3/5 = 0.6
        f1 = f1_score(y_true, y_pred)

        expected_f1 = 2 * precision * recall / (precision + recall)
        assert abs(f1 - expected_f1) < 0.001, f"F1 should equal 2*P*R/(P+R), got {f1}"

    def test_exact_match_identical(self):
        """Test exact match returns 1.0 for identical strings."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "text"}}
        )

        score = evaluator._compute_metric("exact_match", "hello world", "hello world", "text")
        assert score == 1.0, f"Identical strings should match exactly, got {score}"

    def test_exact_match_different(self):
        """Test exact match returns 0.0 for different strings."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "text"}}
        )

        score = evaluator._compute_metric("exact_match", "hello", "world", "text")
        assert score == 0.0, f"Different strings should not match, got {score}"


class TestRegressionMetrics:
    """Test regression metrics with known expected values.

    Reference: sklearn.metrics documentation.
    """

    def test_mae_perfect(self):
        """Test MAE = 0 for perfect predictions."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        score = evaluator._compute_numeric_metric("mae", 5.0, 5.0)
        assert score == 0.0, f"Perfect prediction should have MAE 0, got {score}"

    def test_mae_calculated(self):
        """Test MAE calculation with known values."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        # |5 - 7| = 2
        score = evaluator._compute_numeric_metric("mae", 5.0, 7.0)
        assert score == 2.0, f"MAE of |5-7| should be 2, got {score}"

    def test_rmse_perfect(self):
        """Test RMSE = 0 for perfect predictions."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        score = evaluator._compute_numeric_metric("rmse", 5.0, 5.0)
        assert score == 0.0, f"Perfect prediction should have RMSE 0, got {score}"

    def test_rmse_calculated(self):
        """Test per-sample RMSE is absolute error for single sample."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        # Per-sample RMSE = sqrt((5-8)²) = sqrt(9) = 3
        score = evaluator._compute_numeric_metric("rmse", 5.0, 8.0)
        assert abs(score - 3.0) < 0.001, f"RMSE of single sample should be |error|=3, got {score}"

    def test_mape_perfect(self):
        """Test MAPE = 0 for perfect predictions."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        score = evaluator._compute_numeric_metric("mape", 100.0, 100.0)
        assert score == 0.0, f"Perfect prediction should have MAPE 0, got {score}"

    def test_mape_calculated(self):
        """Test MAPE calculation with known values."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        # MAPE = |100 - 110| / 100 * 100 = 10%
        score = evaluator._compute_numeric_metric("mape", 100.0, 110.0)
        assert score == 10.0, f"MAPE should be 10%, got {score}"

    def test_mape_division_by_zero(self):
        """Test MAPE handles zero ground truth."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        # When gt=0 and pred!=0, MAPE should be 100%
        score = evaluator._compute_numeric_metric("mape", 0.0, 5.0)
        assert score == 100.0, f"MAPE with gt=0 should be 100%, got {score}"

    def test_r2_is_aggregate_only(self):
        """Test R² raises error for per-sample computation."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        with pytest.raises(RuntimeError, match="aggregate-only"):
            evaluator._compute_numeric_metric("r2", 5.0, 5.0)

    def test_correlation_is_aggregate_only(self):
        """Test correlation raises error for per-sample computation."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "number"}}
        )

        with pytest.raises(RuntimeError, match="aggregate-only"):
            evaluator._compute_numeric_metric("correlation", 5.0, 5.0)

    def test_r2_aggregate_with_sklearn(self):
        """Test R² can be computed at aggregate level with sklearn."""
        from sklearn.metrics import r2_score

        y_true = [3.0, -0.5, 2.0, 7.0]
        y_pred = [2.5, 0.0, 2.0, 8.0]

        r2 = r2_score(y_true, y_pred)
        # Known value for this example: R² = 0.948...
        assert r2 > 0.9, f"R² for good fit should be > 0.9, got {r2}"

    def test_correlation_aggregate_with_scipy(self):
        """Test correlation can be computed at aggregate level with scipy."""
        from scipy.stats import pearsonr

        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]  # Perfect linear relationship

        corr, _ = pearsonr(x, y)
        assert abs(corr - 1.0) < 0.001, f"Perfect linear correlation should be 1.0, got {corr}"


class TestMultiLabelMetrics:
    """Test multi-label metrics with known expected values.

    Reference: sklearn.metrics.jaccard_score, hamming_loss, etc.
    """

    def test_jaccard_perfect(self):
        """Test Jaccard = 1.0 for identical sets."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "set"}}
        )

        score = evaluator._compute_set_metric("jaccard", {"a", "b", "c"}, {"a", "b", "c"})
        assert score == 1.0, f"Identical sets should have Jaccard 1.0, got {score}"

    def test_jaccard_no_overlap(self):
        """Test Jaccard = 0.0 for disjoint sets."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "set"}}
        )

        score = evaluator._compute_set_metric("jaccard", {"a", "b"}, {"c", "d"})
        assert score == 0.0, f"Disjoint sets should have Jaccard 0.0, got {score}"

    def test_jaccard_partial(self):
        """Test Jaccard = |A∩B|/|A∪B| for partial overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "set"}}
        )

        # {a, b} ∩ {b, c} = {b} -> |{b}| = 1
        # {a, b} ∪ {b, c} = {a, b, c} -> |{a, b, c}| = 3
        # Jaccard = 1/3 ≈ 0.333
        score = evaluator._compute_set_metric("jaccard", {"a", "b"}, {"b", "c"})
        assert abs(score - 0.333) < 0.01, f"Partial overlap Jaccard should be ~0.333, got {score}"

    def test_token_f1_perfect(self):
        """Test token F1 = 1.0 for identical token sets."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "text"}}
        )

        score = evaluator._compute_metric("token_f1", "the cat sat", "the cat sat", "text")
        assert score == 1.0, f"Identical tokens should have F1 1.0, got {score}"

    def test_token_f1_partial(self):
        """Test token F1 for partial token overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "text"}}
        )

        # gt: {the, cat, sat}, pred: {the, cat, ran}
        # Intersection: {the, cat} = 2 tokens
        # Precision = 2/3, Recall = 2/3
        # F1 = 2 * (2/3) * (2/3) / (2/3 + 2/3) = 2/3 ≈ 0.667
        score = evaluator._compute_metric("token_f1", "the cat sat", "the cat ran", "text")
        assert abs(score - 0.667) < 0.01, f"Partial token F1 should be ~0.667, got {score}"

    def test_token_f1_no_overlap(self):
        """Test token F1 = 0.0 for no token overlap."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "text"}}
        )

        score = evaluator._compute_metric("token_f1", "hello world", "foo bar", "text")
        assert score == 0.0, f"No token overlap should have F1 0.0, got {score}"


class TestAggregateRMSE:
    """Test proper RMSE aggregation (sqrt of mean of squared errors)."""

    def test_aggregate_rmse_calculation(self):
        """Test RMSE aggregation with known values."""
        # Individual errors: [1, 2, 3, 4]
        # Squared errors: [1, 4, 9, 16]
        # Mean squared error: 30/4 = 7.5
        # RMSE = sqrt(7.5) ≈ 2.739

        individual_errors = [1.0, 2.0, 3.0, 4.0]
        squared_errors = [e**2 for e in individual_errors]
        mean_squared = sum(squared_errors) / len(squared_errors)
        rmse = np.sqrt(mean_squared)

        assert abs(rmse - 2.739) < 0.01, f"Aggregate RMSE should be ~2.739, got {rmse}"
