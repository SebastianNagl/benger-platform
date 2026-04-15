"""
Tests for Hierarchical Classification Metrics (Path Accuracy, LCA, Hierarchical F1).

Scientific Rigor: All tests verify mathematical correctness with known expected values.
NO MOCKS - All metrics use real implementations.

Used for taxonomy classification, legal code hierarchy, and hierarchical document categorization.
"""

import os
import sys

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHierarchicalF1:
    """Test Hierarchical F1 score calculation.

    Reference: Kiritchenko et al. (2005) "Functional Annotation of Genes Using Hierarchical Text Categorization"

    Hierarchical F1 considers partial credit for predictions that are
    in the same branch of the taxonomy.
    """

    def test_hierarchical_f1_perfect(self):
        """Test Hierarchical F1 = 1.0 for exact path match."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        # Same path in taxonomy
        gt = ["Law", "Civil Law", "Contract Law"]
        pred = ["Law", "Civil Law", "Contract Law"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        assert score == 1.0, f"Identical paths should have F1 1.0, got {score}"

    def test_hierarchical_f1_sibling(self):
        """Test Hierarchical F1 for sibling categories."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        # Same parent, different leaf
        gt = ["Law", "Civil Law", "Contract Law"]
        pred = ["Law", "Civil Law", "Tort Law"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        # Should have partial credit for matching prefix
        assert 0.5 < score < 1.0, f"Sibling match should have partial F1, got {score}"

    def test_hierarchical_f1_distant_categories(self):
        """Test Hierarchical F1 for distant categories."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        # Different branches
        gt = ["Law", "Civil Law", "Contract Law"]
        pred = ["Law", "Criminal Law", "Theft"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        # Only root matches
        assert score < 0.5, f"Distant categories should have low F1, got {score}"

    def test_hierarchical_f1_completely_different(self):
        """Test Hierarchical F1 = 0 for unrelated categories."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        # No common ancestor
        gt = ["Law", "Civil Law"]
        pred = ["Science", "Biology"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        assert score == 0.0, f"Unrelated categories should have F1 0.0, got {score}"


class TestPathAccuracy:
    """Test path accuracy for hierarchical classification."""

    def test_path_accuracy_full_match(self):
        """Test path accuracy = 1.0 for full path match."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "B", "C"]

        score = evaluator._compute_hierarchical_metric("path_accuracy", gt, pred)
        assert score == 1.0, f"Full path match should have accuracy 1.0, got {score}"

    def test_path_accuracy_partial_match(self):
        """Test path accuracy for partial path match."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "B", "D"]  # 2 out of 3 match

        score = evaluator._compute_hierarchical_metric("path_accuracy", gt, pred)
        # Weighted: (1+2)/(1+2+3) = 3/6 = 0.5 (weights: 1,2,3 for levels)
        assert abs(score - 0.5) < 0.01, f"2/3 path match should be ~0.5 (weighted), got {score}"

    def test_path_accuracy_root_only(self):
        """Test path accuracy when only root matches."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "X", "Y"]  # Only root matches

        score = evaluator._compute_hierarchical_metric("path_accuracy", gt, pred)
        # Weighted: 1/(1+2) = 1/3 ≈ 0.333 (stops counting max after divergence)
        assert (
            abs(score - 0.333) < 0.02
        ), f"Root-only match should be ~0.333 (weighted), got {score}"

    def test_path_accuracy_weighted(self):
        """Test path accuracy with level weights (deeper levels more important)."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "B", "C"]

        # With weights [0.1, 0.3, 0.6] giving more importance to leaf
        score = evaluator._compute_hierarchical_metric(
            "path_accuracy", gt, pred, {"weights": [0.1, 0.3, 0.6]}
        )
        assert score == 1.0, f"Full match with weights should still be 1.0, got {score}"


class TestLCAAccuracy:
    """Test Lowest Common Ancestor (LCA) accuracy.

    LCA-based metrics measure how close the predicted and ground truth
    categories are in the taxonomy tree.
    """

    def test_lca_accuracy_same_node(self):
        """Test LCA accuracy = 1.0 for same node."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "B", "C"]

        score = evaluator._compute_hierarchical_metric("lca_accuracy", gt, pred)
        assert score == 1.0, f"Same node should have LCA accuracy 1.0, got {score}"

    def test_lca_accuracy_siblings(self):
        """Test LCA accuracy for sibling nodes."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "B", "D"]  # Siblings under B

        score = evaluator._compute_hierarchical_metric("lca_accuracy", gt, pred)
        # LCA is B (depth 2), with decay
        assert 0.4 <= score <= 0.8, f"Siblings should have moderate LCA accuracy, got {score}"

    def test_lca_accuracy_distant(self):
        """Test LCA accuracy for distant nodes (only root as LCA)."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["A", "X", "Y"]  # Only share root A

        score = evaluator._compute_hierarchical_metric("lca_accuracy", gt, pred)
        # LCA is A (depth 1), max depth is 3
        # score = 1/3 ≈ 0.333
        assert score < 0.5, f"Distant nodes should have low LCA accuracy, got {score}"

    def test_lca_accuracy_no_common_ancestor(self):
        """Test LCA accuracy = 0 for nodes with no common ancestor."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["A", "B", "C"]
        pred = ["X", "Y", "Z"]  # Completely different trees

        score = evaluator._compute_hierarchical_metric("lca_accuracy", gt, pred)
        assert score == 0.0, f"No common ancestor should have accuracy 0.0, got {score}"


class TestHierarchicalMetricsCalculation:
    """Direct tests for hierarchical metric calculations."""

    def test_path_prefix_length(self):
        """Test calculation of common path prefix length."""

        def common_prefix_length(path1, path2):
            """Calculate length of common prefix in two paths."""
            length = 0
            for a, b in zip(path1, path2):
                if a == b:
                    length += 1
                else:
                    break
            return length

        # Full match
        assert common_prefix_length(["A", "B", "C"], ["A", "B", "C"]) == 3

        # Partial match
        assert common_prefix_length(["A", "B", "C"], ["A", "B", "D"]) == 2

        # Root only
        assert common_prefix_length(["A", "B", "C"], ["A", "X", "Y"]) == 1

        # No match
        assert common_prefix_length(["A", "B"], ["X", "Y"]) == 0

    def test_hierarchical_precision_recall(self):
        """Test hierarchical precision and recall calculation."""

        def hierarchical_precision_recall(gt_path, pred_path):
            """Calculate hierarchical precision and recall."""
            gt_set = set(gt_path)
            pred_set = set(pred_path)

            intersection = gt_set & pred_set

            if not pred_set:
                precision = 0.0
            else:
                precision = len(intersection) / len(pred_set)

            if not gt_set:
                recall = 0.0
            else:
                recall = len(intersection) / len(gt_set)

            return precision, recall

        # Same path
        p, r = hierarchical_precision_recall(["A", "B", "C"], ["A", "B", "C"])
        assert p == 1.0 and r == 1.0

        # Subset
        p, r = hierarchical_precision_recall(["A", "B", "C"], ["A", "B"])
        assert p == 1.0  # All predicted are correct
        assert r < 1.0  # Not all ground truth are predicted

    def test_hierarchical_f1_formula(self):
        """Test hierarchical F1 as harmonic mean of precision and recall."""

        def hierarchical_f1(gt_path, pred_path):
            """Calculate hierarchical F1."""
            gt_set = set(gt_path)
            pred_set = set(pred_path)

            intersection = gt_set & pred_set

            if not pred_set:
                precision = 0.0
            else:
                precision = len(intersection) / len(pred_set)

            if not gt_set:
                recall = 0.0
            else:
                recall = len(intersection) / len(gt_set)

            if precision + recall == 0:
                return 0.0

            return 2 * precision * recall / (precision + recall)

        # Same path
        assert hierarchical_f1(["A", "B", "C"], ["A", "B", "C"]) == 1.0

        # Partial overlap
        f1 = hierarchical_f1(["A", "B", "C"], ["A", "B", "D"])
        # intersection = {A, B} = 2
        # precision = 2/3, recall = 2/3
        # F1 = 2 * (2/3) * (2/3) / (4/3) = 2/3
        assert abs(f1 - 2 / 3) < 0.001


class TestHierarchicalWithRealTaxonomy:
    """Test hierarchical metrics with realistic legal taxonomy."""

    def test_legal_taxonomy_exact_match(self):
        """Test with German legal code hierarchy."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        # BGB (Civil Code) hierarchy
        gt = ["BGB", "Schuldrecht", "Kaufrecht", "§433"]
        pred = ["BGB", "Schuldrecht", "Kaufrecht", "§433"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        assert score == 1.0, f"Exact legal taxonomy match should be 1.0, got {score}"

    def test_legal_taxonomy_wrong_paragraph(self):
        """Test with wrong paragraph but correct section."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["BGB", "Schuldrecht", "Kaufrecht", "§433"]
        pred = ["BGB", "Schuldrecht", "Kaufrecht", "§434"]  # Wrong paragraph

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        # Should get partial credit
        assert 0.7 < score < 1.0, f"Wrong paragraph should still score well, got {score}"

    def test_legal_taxonomy_wrong_book(self):
        """Test with completely wrong book."""
        from ml_evaluation.sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator(
            evaluation_id="test", field_configs={"test_field": {"answer_type": "hierarchical"}}
        )

        gt = ["BGB", "Schuldrecht", "Kaufrecht", "§433"]
        pred = ["StGB", "Allgemeiner Teil", "Vorsatz", "§15"]

        score = evaluator._compute_hierarchical_metric("hierarchical_f1", gt, pred)
        # Completely different codes
        assert score == 0.0, f"Different legal codes should score 0.0, got {score}"
