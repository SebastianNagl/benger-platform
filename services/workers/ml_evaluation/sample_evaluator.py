"""
Per-Sample Evaluation Utility

Evaluates individual samples and stores detailed per-sample results for drill-down analysis.
Issue #763: Per-sample evaluation results and visualization dashboard

SCIENTIFIC RESEARCH PLATFORM - All metrics use established, citable implementations.
NO FALLBACKS - All required dependencies must be installed.

Implements all 44 metrics from EvaluationMethodSelector:
- Classification: exact_match, accuracy, precision, recall, f1, cohen_kappa, confusion_matrix
- Multi-label: jaccard, hamming_loss, subset_accuracy, token_f1
- Regression: mae, rmse, mape, r2, correlation
- Ranking: weighted_kappa, spearman_correlation, kendall_tau, ndcg, map
- Lexical: bleu, rouge, meteor, chrf, edit_distance
- Semantic: bertscore, moverscore, semantic_similarity
- Factuality: factcc, qags, coherence
- Structured: json_accuracy, schema_validation, field_accuracy
- Span: span_exact_match, iou, partial_match, boundary_accuracy
- Hierarchical: hierarchical_f1, path_accuracy, lca_accuracy
"""

import json
import logging
import platform
import time
import uuid
from typing import Any, Dict, List, Optional

# Platform detection for backend selection
IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')

# NLTK imports - REQUIRED for BLEU, METEOR, coherence
import nltk
import numpy as np
from scipy.optimize import linear_sum_assignment
from nltk.tag import pos_tag
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from nltk.translate.meteor_score import meteor_score

# =============================================================================
# REQUIRED DEPENDENCIES - All imports must succeed for scientific rigor
# =============================================================================


NLTK_AVAILABLE = True
try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet', quiet=True)
    nltk.download('omw-1.4', quiet=True)

# Download additional resources for coherence
# Catch both LookupError (not found) and BadZipFile (corrupted data)
import zipfile


def _ensure_nltk_data(resource: str, packages: list):
    """Ensure NLTK data is available, downloading if missing or corrupted."""
    try:
        nltk.data.find(resource)
    except (LookupError, zipfile.BadZipFile, Exception):
        for pkg in packages:
            nltk.download(pkg, quiet=True)


_ensure_nltk_data('tokenizers/punkt', ['punkt'])
_ensure_nltk_data('tokenizers/punkt_tab', ['punkt_tab'])
_ensure_nltk_data('taggers/averaged_perceptron_tagger', ['averaged_perceptron_tagger'])
_ensure_nltk_data('taggers/averaged_perceptron_tagger_eng', ['averaged_perceptron_tagger_eng'])
_ensure_nltk_data('chunkers/maxent_ne_chunker', ['maxent_ne_chunker', 'words'])

# ROUGE imports - REQUIRED
from rouge_score import rouge_scorer

ROUGE_AVAILABLE = True

# SacreBLEU imports - REQUIRED for chrF
import sacrebleu

SACREBLEU_AVAILABLE = True

# Scikit-learn imports - REQUIRED for classification/regression/ranking metrics
from sklearn.metrics import ndcg_score

SKLEARN_AVAILABLE = True


# Scipy imports - REQUIRED for correlation and statistical tests
from scipy.stats import kendalltau, spearmanr

SCIPY_AVAILABLE = True

# JSON Schema validation - REQUIRED
import jsonschema

JSONSCHEMA_AVAILABLE = True

# BERTScore for semantic similarity - REQUIRED
from bert_score import score as bert_score_compute

BERTSCORE_AVAILABLE = True

# Sentence Transformers for semantic similarity - REQUIRED
from sentence_transformers import SentenceTransformer
from sentence_transformers import util as st_util

SENTENCE_TRANSFORMERS_AVAILABLE = True
_sentence_transformer_model = None  # Lazy-loaded

# Backend selector for platform-aware metric computation (MoverScore via POT)
_backend_selector = None


def _get_backend_selector():
    """Lazy load backend selector for platform-aware metric computation."""
    global _backend_selector
    if _backend_selector is None:
        from .backends.selector import backend_selector

        _backend_selector = backend_selector
    return _backend_selector


# Transformers for FactCC - REQUIRED for BERT-based factual consistency
from transformers import BertForSequenceClassification, BertTokenizer

TRANSFORMERS_AVAILABLE = True
# QAGS and SummaC models now handled by backends (see backends/torch_backend.py and backends/onnx_backend.py)

# SummaC factual consistency - now handled by backends (no summac package needed)
# The SummaC algorithm is reimplemented using the ViTC model directly

# PyTorch for model operations - REQUIRED
import torch

TORCH_AVAILABLE = True
_factcc_model = None  # Lazy-loaded FactCC model
_factcc_tokenizer = None  # Lazy-loaded FactCC tokenizer

logger = logging.getLogger(__name__)


def _get_sentence_transformer():
    """Lazy load sentence transformer model for GPU efficiency"""
    global _sentence_transformer_model
    if _sentence_transformer_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        _sentence_transformer_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _sentence_transformer_model


def _get_factcc_model():
    """Lazy load FactCC model and tokenizer for factual consistency checking"""
    global _factcc_model, _factcc_tokenizer
    if _factcc_model is None and TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE:
        logger.info("Loading FactCC model for factual consistency checking...")
        model_path = 'manueldeprada/FactCC'
        _factcc_tokenizer = BertTokenizer.from_pretrained(model_path)
        _factcc_model = BertForSequenceClassification.from_pretrained(model_path)
        if torch.cuda.is_available():
            _factcc_model = _factcc_model.cuda()
        _factcc_model.eval()
    return _factcc_model, _factcc_tokenizer


class SampleEvaluator:
    """
    Evaluates individual samples and creates detailed per-sample result records.

    This class bridges the gap between aggregate evaluation metrics and per-sample
    performance tracking, enabling drill-down analysis and visualization.
    """

    def __init__(
        self,
        evaluation_id: str,
        field_configs: Dict[str, Any],
        metric_parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        Initialize sample evaluator.

        Args:
            evaluation_id: ID of the parent evaluation
            field_configs: Dict mapping field names to their evaluation configuration
            metric_parameters: Optional dict mapping field_name -> {metric_name -> parameters}
        """
        self.evaluation_id = evaluation_id
        self.field_configs = field_configs
        self.metric_parameters = metric_parameters or {}

    def evaluate_sample(
        self,
        task_id: str,
        field_name: str,
        ground_truth: Any,
        prediction: Any,
        metrics_to_compute: List[str],
        generation_id: Optional[str] = None,
        parse_status: Optional[str] = None,
        allow_unparsed: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate a single sample and return detailed results.

        Args:
            task_id: ID of the task being evaluated
            field_name: Name of the field being evaluated
            ground_truth: Ground truth value
            prediction: Predicted value
            metrics_to_compute: List of metrics to compute
            generation_id: Optional ID of the generation that produced the prediction
            parse_status: Optional parse status of the generation (for LLM responses)
            allow_unparsed: If True, allows evaluation of generations with failed parse status
                (useful when using raw response_content for LLM Judge evaluations)

        Returns:
            Dictionary containing per-sample results ready for database storage

        Raises:
            ValueError: If attempting to evaluate unparsed generation without allow_unparsed=True
        """
        start_time = time.time()

        # Verify that generation has been successfully parsed (unless allow_unparsed is set)
        if generation_id is not None and parse_status != "success" and not allow_unparsed:
            error_msg = (
                f"Cannot evaluate generation {generation_id} with parse_status='{parse_status}'. "
                f"Only generations with parse_status='success' can be evaluated. "
                f"Please ensure the generation response has been parsed before evaluation."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        try:
            # Get field configuration
            field_config = self.field_configs.get(field_name, {})
            answer_type = field_config.get("type", "unknown")

            # Compute metrics for this sample
            sample_metrics = {}
            passed = True  # Assume pass unless a metric fails threshold

            for metric_name in metrics_to_compute:
                try:
                    # Get parameters for this metric
                    field_params = self.metric_parameters.get(field_name, {})
                    metric_params = field_params.get(metric_name, {})

                    metric_value = self._compute_metric(
                        metric_name, ground_truth, prediction, answer_type, metric_params
                    )
                    sample_metrics[metric_name] = metric_value

                    # Check if this metric indicates failure
                    # (e.g., exact_match = 0, or score below threshold)
                    if self._is_failure_metric(metric_name, metric_value):
                        passed = False

                except Exception as e:
                    logger.warning(
                        f"Failed to compute metric {metric_name} for sample {task_id}: {e}"
                    )
                    sample_metrics[metric_name] = None

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Calculate confidence score based on metrics
            confidence_score = self._calculate_confidence(sample_metrics)

            return {
                "id": str(uuid.uuid4()),
                "evaluation_id": self.evaluation_id,
                "task_id": task_id,
                "generation_id": generation_id,
                "field_name": field_name,
                "answer_type": answer_type,
                "ground_truth": self._serialize_value(ground_truth),
                "prediction": self._serialize_value(prediction),
                "metrics": sample_metrics,
                "passed": passed,
                "confidence_score": confidence_score,
                "error_message": None,
                "processing_time_ms": processing_time_ms,
            }

        except Exception as e:
            logger.error(f"Error evaluating sample {task_id}: {e}")
            processing_time_ms = int((time.time() - start_time) * 1000)

            return {
                "id": str(uuid.uuid4()),
                "evaluation_id": self.evaluation_id,
                "task_id": task_id,
                "generation_id": generation_id,
                "field_name": field_name,
                "answer_type": "error",
                "ground_truth": self._serialize_value(ground_truth),
                "prediction": self._serialize_value(prediction),
                "metrics": {},
                "passed": False,
                "confidence_score": 0.0,
                "error_message": str(e),
                "processing_time_ms": processing_time_ms,
            }

    def _compute_metric(
        self,
        metric_name: str,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Compute a single metric for a sample.

        Args:
            metric_name: Name of the metric to compute
            ground_truth: Ground truth value
            prediction: Predicted value
            answer_type: Type of answer being evaluated
            parameters: Optional metric-specific parameters (uses defaults if None)

        Returns:
            Metric value as float
        """
        if parameters is None:
            parameters = {}

        # Normalize values for comparison
        gt = self._normalize_value(ground_truth, answer_type)
        pred = self._normalize_value(prediction, answer_type)

        # ===== EXACT MATCH =====
        if metric_name == "exact_match":
            return 1.0 if gt == pred else 0.0

        # ===== CLASSIFICATION METRICS =====
        elif metric_name == "accuracy":
            return 1.0 if gt == pred else 0.0

        elif metric_name == "precision":
            return self._compute_classification_metric("precision", gt, pred, parameters)

        elif metric_name == "recall":
            return self._compute_classification_metric("recall", gt, pred, parameters)

        elif metric_name == "f1":
            return self._compute_classification_metric("f1", gt, pred, parameters)

        elif metric_name == "cohen_kappa":
            return self._compute_classification_metric("cohen_kappa", gt, pred, parameters)

        elif metric_name == "confusion_matrix":
            # For single sample, return 1.0 if correct, 0.0 if not
            return 1.0 if gt == pred else 0.0

        # ===== MULTI-LABEL/SET METRICS =====
        elif metric_name == "jaccard":
            return self._compute_set_metric("jaccard", gt, pred)

        elif metric_name == "hamming_loss":
            return self._compute_set_metric("hamming_loss", gt, pred)

        elif metric_name == "subset_accuracy":
            return self._compute_set_metric("subset_accuracy", gt, pred)

        elif metric_name == "token_f1":
            return self._compute_token_f1(gt, pred)

        # ===== REGRESSION METRICS =====
        elif metric_name in ["mae", "rmse", "mape"]:
            return self._compute_numeric_metric(metric_name, gt, pred)

        elif metric_name == "r2":
            return self._compute_numeric_metric("r2", gt, pred)

        elif metric_name == "correlation":
            return self._compute_numeric_metric("correlation", gt, pred)

        # ===== RANKING METRICS =====
        elif metric_name == "weighted_kappa":
            return self._compute_ranking_metric("weighted_kappa", gt, pred, parameters)

        elif metric_name == "spearman_correlation":
            return self._compute_ranking_metric("spearman", gt, pred, parameters)

        elif metric_name == "kendall_tau":
            return self._compute_ranking_metric("kendall", gt, pred, parameters)

        elif metric_name == "ndcg":
            return self._compute_ranking_metric("ndcg", gt, pred, parameters)

        elif metric_name == "map":
            return self._compute_ranking_metric("map", gt, pred, parameters)

        # ===== TEXT SIMILARITY METRICS =====
        elif metric_name in ["bleu", "rouge", "edit_distance", "meteor", "chrf"]:
            return self._compute_text_similarity(metric_name, gt, pred, parameters)

        # ===== SEMANTIC SIMILARITY METRICS =====
        elif metric_name == "bertscore":
            return self._compute_semantic_metric("bertscore", gt, pred, parameters)

        elif metric_name == "moverscore":
            return self._compute_semantic_metric("moverscore", gt, pred, parameters)

        elif metric_name == "semantic_similarity":
            return self._compute_semantic_metric("semantic_similarity", gt, pred, parameters)

        # ===== FACTUALITY & COHERENCE METRICS =====
        elif metric_name == "factcc":
            return self._compute_factuality_metric("factcc", gt, pred, parameters)

        elif metric_name == "qags":
            return self._compute_factuality_metric("qags", gt, pred, parameters)

        elif metric_name == "coherence":
            return self._compute_factuality_metric("coherence", gt, pred, parameters)

        # ===== STRUCTURED DATA METRICS =====
        elif metric_name == "json_accuracy":
            return self._compute_structured_metric("json_accuracy", gt, pred, parameters)

        elif metric_name == "schema_validation":
            return self._compute_structured_metric("schema_validation", gt, pred, parameters)

        # ===== SPAN/SEQUENCE METRICS =====
        elif metric_name == "span_exact_match":
            return self._compute_span_metric("exact_match", gt, pred)

        elif metric_name == "iou":
            return self._compute_span_metric("iou", gt, pred)

        # ===== HIERARCHICAL METRICS =====
        elif metric_name == "hierarchical_f1":
            return self._compute_hierarchical_metric("hierarchical_f1", gt, pred, parameters)

        # ===== SPECIALIZED NLP METRICS =====
        elif metric_name == "field_accuracy":
            return self._compute_field_accuracy(gt, pred, parameters)

        elif metric_name == "partial_match":
            return self._compute_partial_match(gt, pred, parameters)

        elif metric_name == "boundary_accuracy":
            return self._compute_boundary_accuracy(gt, pred, parameters)

        elif metric_name == "path_accuracy":
            return self._compute_path_accuracy(gt, pred, parameters)

        elif metric_name == "lca_accuracy":
            return self._compute_lca_accuracy(gt, pred, parameters)

        # Default: exact match
        else:
            logger.warning(f"Unknown metric {metric_name}, defaulting to exact match")
            return 1.0 if gt == pred else 0.0

    def _compute_text_similarity(
        self, metric_name: str, gt: str, pred: str, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute text similarity metrics with configurable parameters.

        Args:
            metric_name: Name of the metric
            gt: Ground truth text
            pred: Predicted text
            parameters: Optional metric-specific parameters

        Returns:
            Similarity score (0.0-1.0)
        """
        if parameters is None:
            parameters = {}

        if metric_name == "edit_distance":
            # Levenshtein distance normalized to [0, 1]
            max_len = max(len(gt), len(pred))
            if max_len == 0:
                return 1.0
            return 1.0 - (self._levenshtein_distance(gt, pred) / max_len)

        elif metric_name == "bleu":
            # BLEU score - NO FALLBACK, real implementation required
            max_order = parameters.get("max_order", 4)
            smoothing_method = parameters.get("smoothing", "method1")

            default_weights = {
                1: [1.0],
                2: [0.5, 0.5],
                3: [0.33, 0.33, 0.34],
                4: [0.25, 0.25, 0.25, 0.25],
            }
            weights = parameters.get("weights", default_weights.get(max_order, [0.25] * 4))

            reference = [gt.lower().split()]
            candidate = pred.lower().split()

            if not candidate:
                return 0.0

            smoothing = SmoothingFunction()
            smoothing_func = getattr(smoothing, smoothing_method, smoothing.method1)

            score = sentence_bleu(
                reference,
                candidate,
                smoothing_function=smoothing_func,
                weights=tuple(weights[:max_order]),
            )
            return score

        elif metric_name == "rouge":
            # ROUGE score - NO FALLBACK, real implementation required
            variant = parameters.get("variant", "rougeL")
            use_stemmer = parameters.get("use_stemmer", True)

            scorer = rouge_scorer.RougeScorer([variant], use_stemmer=use_stemmer)
            scores = scorer.score(gt, pred)
            return scores[variant].fmeasure

        elif metric_name == "meteor":
            # METEOR score - NO FALLBACK, real implementation required
            reference = gt.lower().split()
            candidate = pred.lower().split()

            if not candidate:
                return 0.0

            score = meteor_score([reference], candidate)
            return score

        elif metric_name == "chrf":
            # chrF score - NO FALLBACK, real implementation required
            char_order = parameters.get("char_order", 6)
            word_order = parameters.get("word_order", 0)
            beta = parameters.get("beta", 2)

            score = sacrebleu.sentence_chrf(
                pred, [gt], char_order=char_order, word_order=word_order, beta=beta
            )
            return score.score / 100.0  # Normalize to [0, 1]

        return 0.0

    def _compute_numeric_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """Compute numeric evaluation metrics including r2 and correlation"""
        try:
            gt_val = float(gt)
            pred_val = float(pred)

            if metric_name == "mae":
                return abs(gt_val - pred_val)
            elif metric_name == "rmse":
                # Per-sample RMSE is the absolute error (sqrt of squared error for n=1).
                # RMSE = sqrt(1/n * sum(errors²)), for n=1: sqrt(error²) = |error|
                # NOTE: For aggregate RMSE, collect squared errors and use sqrt(mean).
                # Returning absolute error here for per-sample interpretability.
                import math

                return math.sqrt((gt_val - pred_val) ** 2)  # = abs(gt_val - pred_val)
            elif metric_name == "mape":
                if gt_val == 0:
                    return 100.0 if pred_val != 0 else 0.0
                return abs((gt_val - pred_val) / gt_val) * 100
            elif metric_name == "r2":
                # R² (coefficient of determination) is an aggregate-only metric.
                # It measures variance explained and requires multiple samples.
                # Reference: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.r2_score.html
                raise RuntimeError(
                    "R² score is an aggregate-only metric and cannot be computed per-sample. "
                    "Use sklearn.metrics.r2_score at the aggregate level."
                )
            elif metric_name == "correlation":
                # Pearson correlation is an aggregate-only metric.
                # It measures linear relationship and requires multiple paired observations.
                # Reference: scipy.stats.pearsonr
                raise RuntimeError(
                    "Pearson correlation is an aggregate-only metric and cannot be computed per-sample. "
                    "Use scipy.stats.pearsonr at the aggregate level."
                )

        except (ValueError, TypeError):
            return 0.0  # Return 0 for invalid numeric conversion

        return 0.0

    def _compute_classification_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute classification metrics for single sample.
        For single samples, these are binary (correct/incorrect).
        True metrics are computed at aggregate level.
        """
        # For single sample classification, treat as binary correct/incorrect
        is_correct = gt == pred

        if metric_name in ["precision", "recall", "f1"]:
            # For single sample: 1.0 if correct (TP), 0.0 if wrong
            return 1.0 if is_correct else 0.0

        elif metric_name == "cohen_kappa":
            # For single sample, return accuracy equivalent
            return 1.0 if is_correct else 0.0

        return 1.0 if is_correct else 0.0

    def _compute_set_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """
        Compute set-based metrics for multi-label classification.
        Handles list/set comparisons.
        """
        # Convert to sets for comparison
        gt_set = self._to_set(gt)
        pred_set = self._to_set(pred)

        if metric_name == "jaccard":
            # Jaccard similarity = |intersection| / |union|
            if not gt_set and not pred_set:
                return 1.0  # Both empty = perfect match
            if not gt_set or not pred_set:
                return 0.0
            intersection = len(gt_set & pred_set)
            union = len(gt_set | pred_set)
            return intersection / union if union > 0 else 0.0

        elif metric_name == "hamming_loss":
            # Hamming loss = fraction of wrong labels
            # For sets, count symmetric difference
            if not gt_set and not pred_set:
                return 0.0  # No loss if both empty
            all_labels = gt_set | pred_set
            if not all_labels:
                return 0.0
            symmetric_diff = len(gt_set ^ pred_set)
            return symmetric_diff / len(all_labels)

        elif metric_name == "subset_accuracy":
            # Exact match of entire set
            return 1.0 if gt_set == pred_set else 0.0

        return 0.0

    def _to_set(self, value: Any) -> set:
        """Convert a value to a set for comparison"""
        if isinstance(value, set):
            return value
        elif isinstance(value, (list, tuple)):
            return set(value)
        elif isinstance(value, str):
            # Try to parse as list
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return set(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
            # Treat as single-element set
            return {value}
        elif value is None:
            return set()
        else:
            return {value}

    def _compute_token_f1(self, gt: Any, pred: Any) -> float:
        """
        Compute token-level F1 score.
        Treats text as bag of tokens and computes F1.
        """
        gt_str = str(gt).lower()
        pred_str = str(pred).lower()

        gt_tokens = set(gt_str.split())
        pred_tokens = set(pred_str.split())

        if not gt_tokens and not pred_tokens:
            return 1.0
        if not gt_tokens or not pred_tokens:
            return 0.0

        intersection = len(gt_tokens & pred_tokens)

        precision = intersection / len(pred_tokens) if pred_tokens else 0.0
        recall = intersection / len(gt_tokens) if gt_tokens else 0.0

        if precision + recall == 0:
            return 0.0

        f1 = 2 * (precision * recall) / (precision + recall)
        return f1

    def _compute_ranking_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute ranking metrics.
        For single samples, these are approximations - true metrics computed at aggregate level.
        """
        if parameters is None:
            parameters = {}

        if metric_name == "weighted_kappa":
            # Weighted Cohen's Kappa is an aggregate-only metric.
            # It measures inter-rater agreement across multiple observations.
            # Reference: sklearn.metrics.cohen_kappa_score(weights='quadratic')
            raise RuntimeError(
                "Weighted Kappa is an aggregate-only metric and cannot be computed per-sample. "
                "Use sklearn.metrics.cohen_kappa_score(weights='quadratic') at the aggregate level."
            )

        elif metric_name == "spearman":
            # For single sample, use rank comparison
            try:
                gt_list = self._to_list(gt)
                pred_list = self._to_list(pred)
                if gt_list == pred_list:
                    return 1.0
                if len(gt_list) != len(pred_list):
                    return 0.0
                if len(gt_list) > 1:
                    corr, _ = spearmanr(gt_list, pred_list)
                    return max(0.0, corr) if not np.isnan(corr) else 0.0
                # Single element lists have perfect correlation
                return 1.0
            except Exception as e:
                raise RuntimeError(f"Spearman correlation failed: {e}")

        elif metric_name == "kendall":
            # Kendall's tau
            try:
                gt_list = self._to_list(gt)
                pred_list = self._to_list(pred)
                if gt_list == pred_list:
                    return 1.0
                if len(gt_list) != len(pred_list):
                    return 0.0
                if len(gt_list) > 1:
                    tau, _ = kendalltau(gt_list, pred_list)
                    return max(0.0, tau) if not np.isnan(tau) else 0.0
                # Single element lists have perfect correlation
                return 1.0
            except Exception as e:
                raise RuntimeError(f"Kendall tau correlation failed: {e}")

        elif metric_name == "ndcg":
            # NDCG for relevance ranking
            try:
                gt_list = self._to_list(gt)
                pred_list = self._to_list(pred)
                if not gt_list or not pred_list:
                    return 1.0 if gt_list == pred_list else 0.0
                # Reshape for sklearn
                gt_arr = np.array([gt_list])
                pred_arr = np.array([pred_list])
                return ndcg_score(gt_arr, pred_arr)
            except Exception as e:
                raise RuntimeError(f"NDCG score computation failed: {e}")

        elif metric_name == "map":
            # Mean Average Precision
            try:
                gt_set = self._to_set(gt)
                pred_list = self._to_list(pred)
                if not gt_set or not pred_list:
                    return 1.0 if not gt_set and not pred_list else 0.0
                # Calculate AP
                hits = 0
                sum_precisions = 0.0
                for i, item in enumerate(pred_list):
                    if item in gt_set:
                        hits += 1
                        sum_precisions += hits / (i + 1)
                return sum_precisions / len(gt_set) if gt_set else 0.0
            except Exception:
                return 1.0 if gt == pred else 0.0

        return 0.0

    def _to_list(self, value: Any) -> List[Any]:
        """Convert a value to a list for ranking comparisons"""
        if isinstance(value, list):
            return value
        elif isinstance(value, (tuple, set)):
            return list(value)
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            # Try comma-separated
            if ',' in value:
                return [v.strip() for v in value.split(',')]
            return [value]
        elif value is None:
            return []
        else:
            return [value]

    def _compute_semantic_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute semantic similarity metrics using neural models.
        NO FALLBACKS - All models must be available for scientific rigor.

        Args:
            metric_name: One of 'bertscore', 'moverscore', 'semantic_similarity'
            gt: Ground truth text
            pred: Predicted text
            parameters: Optional metric-specific parameters
                - lang: Language code for BERTScore (default: 'de')
                - method: For FactCC, one of 'summac' or 'factcc' (default: 'summac')

        Returns:
            Similarity score (0.0-1.0)

        Raises:
            RuntimeError: If required dependencies are not available
        """
        if parameters is None:
            parameters = {}

        gt_str = str(gt)
        pred_str = str(pred)

        if metric_name == "bertscore":
            # BERTScore - Use backend selector for platform compatibility
            lang = parameters.get("lang", "de")  # Default to German

            if IS_ARM64:
                # Use ONNX backend on ARM64
                selector = _get_backend_selector()
                backend = selector.get_bertscore_backend()
                P, R, F1 = backend.compute([pred_str], [gt_str], lang=lang)
                return float(F1)
            else:
                # Use original bert-score library on x86_64 for best accuracy
                P, R, F1 = bert_score_compute(
                    [pred_str], [gt_str], lang=lang, rescale_with_baseline=True, verbose=False
                )
                return float(F1.mean().item())

        elif metric_name == "moverscore":
            # MoverScore via POT backend (platform-independent, replaces moverscore_v2/pyemd)
            if not gt_str or not gt_str.strip():
                raise ValueError("MoverScore requires non-empty ground truth text")
            if not pred_str or not pred_str.strip():
                raise ValueError("MoverScore requires non-empty prediction text")
            if len(gt_str.strip()) < 3 or len(pred_str.strip()) < 3:
                raise ValueError("MoverScore requires text longer than 3 characters")

            selector = _get_backend_selector()
            computer = selector.get_moverscore_computer()
            n_gram = parameters.get("n_gram", 1)
            remove_subwords = parameters.get("remove_subwords", True)
            scores = computer.compute_moverscore(
                [gt_str], [pred_str], n_gram=n_gram, remove_subwords=remove_subwords
            )
            return float(scores[0]) if scores else 0.0

        elif metric_name == "semantic_similarity":
            # Semantic similarity - Use backend selector for platform compatibility
            if IS_ARM64:
                # Use ONNX backend on ARM64
                selector = _get_backend_selector()
                backend = selector.get_embedding_backend()
                emb_gt = backend.encode([gt_str])[0]
                emb_pred = backend.encode([pred_str])[0]
                # Compute cosine similarity
                similarity = np.dot(emb_gt, emb_pred) / (
                    np.linalg.norm(emb_gt) * np.linalg.norm(emb_pred) + 1e-9
                )
                return max(0.0, float(similarity))
            else:
                # Use sentence-transformers on x86_64
                model = _get_sentence_transformer()
                if model is None:
                    raise RuntimeError(
                        "Sentence transformer model could not be loaded. "
                        "Ensure sentence-transformers package is installed."
                    )
                emb_gt = model.encode(gt_str, convert_to_tensor=True)
                emb_pred = model.encode(pred_str, convert_to_tensor=True)
                similarity = st_util.cos_sim(emb_gt, emb_pred).item()
                return max(0.0, similarity)

        raise ValueError(f"Unknown semantic metric: {metric_name}")

    def _compute_factuality_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute factuality and coherence metrics.
        NO FALLBACKS - These metrics require proper model implementations.

        Args:
            metric_name: One of 'factcc', 'qags', 'coherence'
            gt: Ground truth/source text
            pred: Predicted/generated text
            parameters: Optional metric-specific parameters
                - method: For FactCC, one of 'summac' or 'factcc' (default: 'summac')

        Returns:
            Score (0.0-1.0)

        Raises:
            NotImplementedError: If metric implementation is not yet available
        """
        if parameters is None:
            parameters = {}

        if metric_name == "factcc":
            # FactCC - Real factual consistency checking
            # Supports both SummaC (2022) and original FactCC (2020)
            # User selects method via parameters: 'summac' (default) or 'factcc'
            gt_str = str(gt)
            pred_str = str(pred)
            method = parameters.get("method", "summac")

            if method == "summac":
                # SummaC: NLI-based consistency scoring using ViTC model
                # Uses backend selector for platform compatibility (ONNX on ARM64, PyTorch on x86_64)
                # Reference: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models"
                try:
                    selector = _get_backend_selector()
                    backend = selector.get_summac_backend()
                    score = backend.score_consistency(gt_str, pred_str)
                    return float(score)
                except Exception as e:
                    logger.error(f"SummaC scoring failed: {e}")
                    raise RuntimeError(f"SummaC scoring failed: {e}")

            elif method == "factcc":
                # Original FactCC: BERT-based binary classification
                model, tokenizer = _get_factcc_model()
                if model is None or tokenizer is None:
                    raise RuntimeError(
                        "FactCC model could not be loaded. "
                        "Ensure transformers package is installed with BERT models."
                    )

                try:
                    # FactCC expects claim-context pairs in specific format
                    # Format: [CLS] claim [SEP] context [SEP]
                    inputs = tokenizer(
                        pred_str,
                        gt_str,
                        max_length=512,
                        truncation='only_second',
                        padding='max_length',
                        return_tensors='pt',
                    )

                    # Move to same device as model
                    if torch.cuda.is_available():
                        inputs = {k: v.cuda() for k, v in inputs.items()}

                    # Get prediction
                    with torch.no_grad():
                        outputs = model(**inputs)
                        logits = outputs.logits
                        # Apply softmax to get probabilities
                        probs = torch.nn.functional.softmax(logits, dim=-1)
                        # FactCC: class 0 = incorrect, class 1 = correct
                        score = probs[0][1].item()

                    return float(score)
                except Exception as e:
                    logger.error(f"FactCC scoring failed: {e}")
                    raise RuntimeError(f"FactCC scoring failed: {e}")
            else:
                raise ValueError(
                    f"Unknown FactCC method: {method}. " f"Must be 'summac' or 'factcc'"
                )

        elif metric_name == "qags":
            # QAGS - Question Generation + Question Answering pipeline
            # Uses backend selector for platform compatibility (ONNX on ARM64, PyTorch on x86_64)
            # Reference: Wang et al. (2020) "Asking and Answering Questions to Evaluate
            # the Factual Consistency of Summaries"
            gt_str = str(gt)
            pred_str = str(pred)

            # Parameters
            num_questions = parameters.get("num_questions", 5)  # Number of questions to generate
            min_answer_overlap = parameters.get(
                "min_answer_overlap", 0.5
            )  # Threshold for answer match

            try:
                # Get QAGS backend (ONNX on ARM64, PyTorch on x86_64)
                selector = _get_backend_selector()
                qags_backend = selector.get_qags_backend()

                # Step 1: Question Generation from ground truth
                questions = qags_backend.generate_questions(gt_str, num_questions=num_questions)

                if not questions:
                    logger.warning("QAGS: No questions generated from ground truth")
                    return 0.0

                # Step 2: Answer questions using both ground truth and prediction
                matching_answers = 0
                total_questions = 0

                for question in questions:
                    try:
                        # Answer using ground truth
                        gt_answer = qags_backend.answer_question(question, gt_str)
                        # Answer using prediction
                        pred_answer = qags_backend.answer_question(question, pred_str)

                        # Compare answers
                        if self._answers_match_qags(
                            gt_answer['answer'], pred_answer['answer'], threshold=min_answer_overlap
                        ):
                            matching_answers += 1

                        total_questions += 1

                    except Exception as e:
                        logger.debug(f"QAGS: Failed to answer question '{question}': {e}")
                        # Count as non-matching
                        total_questions += 1
                        continue

                # Step 3: Calculate QAGS score
                if total_questions == 0:
                    logger.warning("QAGS: No valid question-answer pairs generated")
                    return 0.0

                qags_score = matching_answers / total_questions
                return qags_score

            except Exception as e:
                logger.error(f"QAGS computation failed: {e}")
                raise RuntimeError(f"QAGS computation failed: {e}")

        elif metric_name == "coherence":
            """
            Coherence - Entity-based coherence using Entity Grid Method + Semantic Coherence

            Implementation based on:
            - Barzilay & Lapata (2008): "Modeling Local Coherence: An Entity-based Approach"
            - Combines entity grid transitions with sentence embedding similarity

            Method:
            1. Entity Grid: Extract entities (nouns) and track their grammatical roles across sentences
            2. Transition Analysis: Measure smoothness of entity transitions between sentences
            3. Semantic Coherence: Measure cosine similarity of adjacent sentence embeddings
            4. Combined Score: Weighted average of entity-based and semantic coherence

            Returns score between 0.0-1.0 where higher = more coherent
            """
            pred_str = str(pred)

            # Parameters
            method = parameters.get("method", "hybrid")  # 'entity', 'semantic', or 'hybrid'
            entity_weight = parameters.get(
                "entity_weight", 0.6
            )  # Weight for entity-based coherence
            semantic_weight = parameters.get(
                "semantic_weight", 0.4
            )  # Weight for semantic coherence

            try:
                # Validate text is suitable for coherence analysis
                self._validate_text_for_coherence(pred_str)

                # Split into sentences
                sentences = sent_tokenize(pred_str)

                coherence_scores = []

                # Method 1: Entity-based coherence (Entity Grid Method)
                if method in ["entity", "hybrid"]:
                    entity_score = self._compute_entity_coherence(sentences)
                    coherence_scores.append((entity_score, entity_weight))

                # Method 2: Semantic coherence (sentence embedding transitions)
                if method in ["semantic", "hybrid"]:
                    semantic_score = self._compute_semantic_coherence(sentences)
                    coherence_scores.append((semantic_score, semantic_weight))

                # Combine scores with weights
                if not coherence_scores:
                    raise ValueError(f"Invalid coherence method: {method}")

                # Normalize weights
                total_weight = sum(w for _, w in coherence_scores)
                if total_weight == 0:
                    return 0.0

                weighted_score = sum(
                    score * (weight / total_weight) for score, weight in coherence_scores
                )

                return max(0.0, min(1.0, weighted_score))  # Clamp to [0, 1]

            except Exception as e:
                logger.error(f"Coherence computation failed: {e}")
                raise RuntimeError(f"Coherence computation failed: {e}")

        raise ValueError(f"Unknown factuality metric: {metric_name}")

    def _compute_structured_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute structured data metrics for JSON and schema validation.
        """
        if parameters is None:
            parameters = {}

        if metric_name == "json_accuracy":
            # Parse both as JSON and compare
            try:
                gt_json = self._parse_json(gt)
                pred_json = self._parse_json(pred)

                if gt_json is None and pred_json is None:
                    return 1.0  # Both not JSON
                if gt_json is None or pred_json is None:
                    return 0.0  # One is JSON, other is not

                # Compare JSON structures
                return self._json_field_accuracy(gt_json, pred_json)
            except Exception:
                return 0.0

        elif metric_name == "schema_validation":
            # Validate prediction against a schema
            schema = parameters.get("schema")
            if not schema:
                # No schema provided, just check if valid JSON
                try:
                    pred_json = self._parse_json(pred)
                    return 1.0 if pred_json is not None else 0.0
                except Exception:
                    return 0.0

            try:
                pred_json = self._parse_json(pred)
                if pred_json is None:
                    return 0.0
                jsonschema.validate(pred_json, schema)
                return 1.0  # Valid
            except jsonschema.ValidationError:
                return 0.0  # Invalid
            except jsonschema.SchemaError as e:
                raise RuntimeError(f"Invalid JSON schema: {e}")
            except Exception as e:
                raise RuntimeError(f"Schema validation failed: {e}")

        return 0.0

    def _parse_json(self, value: Any) -> Optional[Any]:
        """Parse a value as JSON"""
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    def _json_field_accuracy(self, gt_json: Any, pred_json: Any) -> float:
        """Calculate field-level accuracy for JSON structures"""
        if type(gt_json) != type(pred_json):
            return 0.0

        if isinstance(gt_json, dict):
            if not gt_json:
                return 1.0 if not pred_json else 0.0

            all_keys = set(gt_json.keys()) | set(pred_json.keys())
            matching_keys = 0
            for key in all_keys:
                if key in gt_json and key in pred_json:
                    if gt_json[key] == pred_json[key]:
                        matching_keys += 1
                    elif isinstance(gt_json[key], (dict, list)):
                        matching_keys += self._json_field_accuracy(gt_json[key], pred_json[key])
            return matching_keys / len(all_keys) if all_keys else 1.0

        elif isinstance(gt_json, list):
            if not gt_json:
                return 1.0 if not pred_json else 0.0
            if len(gt_json) != len(pred_json):
                return 0.0
            matching = sum(1 for g, p in zip(gt_json, pred_json) if g == p)
            return matching / len(gt_json)

        else:
            return 1.0 if gt_json == pred_json else 0.0

    def _compute_span_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """
        Compute span-based metrics for sequence labeling.
        Handles start/end positions for text spans.
        """
        # Parse span information
        gt_spans = self._parse_spans(gt)
        pred_spans = self._parse_spans(pred)

        if metric_name == "exact_match":
            # Exact span boundary match
            return 1.0 if gt_spans == pred_spans else 0.0

        elif metric_name == "iou":
            # Intersection over Union for spans with optimal bipartite matching
            if not gt_spans and not pred_spans:
                return 1.0
            if not gt_spans or not pred_spans:
                return 0.0

            total_iou = self._optimal_span_matching(
                gt_spans, pred_spans, self._span_iou
            )
            return total_iou / max(len(gt_spans), len(pred_spans))

        return 0.0

    def _parse_spans(self, value: Any) -> List[Dict[str, Any]]:
        """Parse span information from various formats, preserving labels when present."""
        if isinstance(value, list):
            spans = []
            for item in value:
                if isinstance(item, dict) and 'start' in item and 'end' in item:
                    span: Dict[str, Any] = {'start': int(item['start']), 'end': int(item['end'])}
                    # Preserve labels for label-aware matching
                    if 'labels' in item and isinstance(item['labels'], list):
                        span['labels'] = item['labels']
                    elif 'label' in item and item['label']:
                        span['labels'] = [item['label']] if isinstance(item['label'], str) else item['label']
                    spans.append(span)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    spans.append({'start': int(item[0]), 'end': int(item[1])})
            return spans
        elif isinstance(value, dict) and 'start' in value and 'end' in value:
            span = {'start': int(value['start']), 'end': int(value['end'])}
            if 'labels' in value and isinstance(value['labels'], list):
                span['labels'] = value['labels']
            elif 'label' in value and value['label']:
                span['labels'] = [value['label']] if isinstance(value['label'], str) else value['label']
            return [span]
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                return self._parse_spans(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def _spans_label_compatible(self, gt_span: Dict[str, Any], pred_span: Dict[str, Any]) -> bool:
        """Check if two spans have compatible labels.

        Returns True if labels overlap or if either side has no labels
        (backwards compatible with position-only data).
        """
        gt_labels = set(gt_span.get('labels', []))
        pred_labels = set(pred_span.get('labels', []))
        if not gt_labels or not pred_labels:
            return True  # No labels = position-only matching
        return bool(gt_labels & pred_labels)

    def _optimal_span_matching(
        self,
        gt_spans: List[Dict[str, Any]],
        pred_spans: List[Dict[str, Any]],
        score_fn,
    ) -> float:
        """Optimal bipartite matching between GT and pred spans using Hungarian algorithm.

        Uses scipy.optimize.linear_sum_assignment for optimal assignment.
        Only matches spans with compatible labels.

        Args:
            gt_spans: Ground truth spans
            pred_spans: Predicted spans
            score_fn: Function(span1, span2) -> float score (higher is better)

        Returns:
            Total score across optimal matches
        """
        n_gt = len(gt_spans)
        n_pred = len(pred_spans)

        # Build score matrix
        score_matrix = np.zeros((n_gt, n_pred))
        for i, gt_span in enumerate(gt_spans):
            for j, pred_span in enumerate(pred_spans):
                if self._spans_label_compatible(gt_span, pred_span):
                    score_matrix[i][j] = score_fn(gt_span, pred_span)

        # Hungarian algorithm minimizes cost, so negate scores
        row_ind, col_ind = linear_sum_assignment(-score_matrix)
        return float(score_matrix[row_ind, col_ind].sum())

    def _span_iou(self, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
        """Calculate IoU for two spans"""
        start1, end1 = span1['start'], span1['end']
        start2, end2 = span2['start'], span2['end']

        # Calculate intersection
        inter_start = max(start1, start2)
        inter_end = min(end1, end2)
        intersection = max(0, inter_end - inter_start)

        # Calculate union
        union = (end1 - start1) + (end2 - start2) - intersection

        return intersection / union if union > 0 else 0.0

    def _compute_hierarchical_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute hierarchical classification metrics.
        Handles tree-structured label hierarchies.
        """
        if parameters is None:
            parameters = {}

        if metric_name == "hierarchical_f1":
            # Parse hierarchical paths
            gt_path = self._parse_hierarchy_path(gt)
            pred_path = self._parse_hierarchy_path(pred)

            if not gt_path and not pred_path:
                return 1.0
            if not gt_path or not pred_path:
                return 0.0

            # Calculate overlap considering hierarchy
            gt_ancestors = set()
            pred_ancestors = set()

            # Build ancestor sets (path from root to label)
            for i in range(len(gt_path)):
                gt_ancestors.add(tuple(gt_path[: i + 1]))
            for i in range(len(pred_path)):
                pred_ancestors.add(tuple(pred_path[: i + 1]))

            # F1 on ancestor sets
            intersection = len(gt_ancestors & pred_ancestors)
            precision = intersection / len(pred_ancestors) if pred_ancestors else 0.0
            recall = intersection / len(gt_ancestors) if gt_ancestors else 0.0

            if precision + recall == 0:
                return 0.0
            return 2 * (precision * recall) / (precision + recall)

        elif metric_name == "path_accuracy":
            return self._compute_path_accuracy(gt, pred, parameters)

        elif metric_name == "lca_accuracy":
            return self._compute_lca_accuracy(gt, pred, parameters)

        return 0.0

    def _parse_hierarchy_path(self, value: Any) -> List[str]:
        """Parse a hierarchical label path"""
        if isinstance(value, list):
            return [str(v) for v in value]
        elif isinstance(value, str):
            # Try JSON first
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
            # Try delimiter-separated (/, >, ::)
            for delim in ['/', '>', '::', ' > ', ' / ']:
                if delim in value:
                    return [v.strip() for v in value.split(delim) if v.strip()]
            return [value]
        elif value is None:
            return []
        else:
            return [str(value)]

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Compute Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # j+1 instead of j since previous_row and current_row are one character longer than s2
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _normalize_value(self, value: Any, answer_type: str) -> Any:
        """Normalize a value for comparison based on answer type"""
        if isinstance(value, str):
            return value.strip().lower()
        elif isinstance(value, (list, dict)):
            return str(value)
        return value

    def _serialize_value(self, value: Any) -> Dict[str, Any]:
        """Serialize a value for JSON storage"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return {"value": value, "type": type(value).__name__}
        elif isinstance(value, (list, dict)):
            return {"value": value, "type": type(value).__name__}
        else:
            return {"value": str(value), "type": "string"}

    def _is_failure_metric(self, metric_name: str, metric_value: Optional[float]) -> bool:
        """Determine if a metric value indicates failure"""
        if metric_value is None:
            return True

        # Binary metrics (0 = fail, 1 = pass) - threshold at 0.5
        if metric_name in [
            "exact_match",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "subset_accuracy",
            "confusion_matrix",
            "span_exact_match",
        ]:
            return metric_value < 0.5

        # Similarity/agreement metrics (threshold at 0.7)
        if metric_name in [
            "bleu",
            "rouge",
            "edit_distance",
            "meteor",
            "chrf",
            "semantic_similarity",
            "bertscore",
            "moverscore",
            "jaccard",
            "token_f1",
            "json_accuracy",
            "iou",
            "hierarchical_f1",
            "coherence",
            "factcc",
            "qags",
            "field_accuracy",
            "partial_match",
            "boundary_accuracy",
            "path_accuracy",
            "lca_accuracy",
        ]:
            return metric_value < 0.7

        # Correlation/agreement metrics (threshold at 0.6)
        if metric_name in [
            "cohen_kappa",
            "weighted_kappa",
            "correlation",
            "spearman_correlation",
            "kendall_tau",
            "r2",
        ]:
            return metric_value < 0.6

        # Ranking metrics (threshold at 0.5)
        if metric_name in ["ndcg", "map"]:
            return metric_value < 0.5

        # Schema validation (binary)
        if metric_name == "schema_validation":
            return metric_value < 1.0

        # Error metrics (higher is worse)
        if metric_name in ["mae", "rmse", "mape", "hamming_loss"]:
            return metric_value > 0.3

        # Default: don't mark as failure unless clearly wrong
        return False

    def _calculate_confidence(self, metrics: Dict[str, Optional[float]]) -> float:
        """Calculate overall confidence score from metrics"""
        valid_metrics = [v for v in metrics.values() if v is not None]

        if not valid_metrics:
            return 0.0

        # Metrics where higher is better (0-1 scale)
        positive_metrics = [
            # Classification
            "exact_match",
            "accuracy",
            "precision",
            "recall",
            "f1",
            # Multi-label
            "jaccard",
            "subset_accuracy",
            "token_f1",
            # Regression (normalized)
            "r2",
            "correlation",
            # Ranking
            "weighted_kappa",
            "spearman_correlation",
            "kendall_tau",
            "ndcg",
            "map",
            # Text similarity
            "bleu",
            "rouge",
            "edit_distance",
            "meteor",
            "chrf",
            # Semantic
            "bertscore",
            "moverscore",
            "semantic_similarity",
            # Factuality
            "factcc",
            "qags",
            "coherence",
            # Structured
            "json_accuracy",
            "schema_validation",
            "field_accuracy",
            # Span
            "span_exact_match",
            "iou",
            "partial_match",
            "boundary_accuracy",
            # Hierarchical
            "hierarchical_f1",
            "path_accuracy",
            "lca_accuracy",
            # Agreement
            "cohen_kappa",
        ]

        # Metrics where lower is better (need to invert)
        error_metrics = ["mae", "rmse", "mape", "hamming_loss"]

        positive_values = []
        for m in positive_metrics:
            if m in metrics and metrics[m] is not None:
                positive_values.append(metrics[m])

        # Invert error metrics (1 - normalized_error)
        for m in error_metrics:
            if m in metrics and metrics[m] is not None:
                # Normalize error to 0-1 range and invert
                error_val = metrics[m]
                if m == "mape":
                    # MAPE is percentage, cap at 100%
                    normalized = max(0.0, 1.0 - min(error_val, 100.0) / 100.0)
                else:
                    # For mae, rmse, hamming_loss - assume typical range 0-1
                    normalized = max(0.0, 1.0 - min(error_val, 1.0))
                positive_values.append(normalized)

        if positive_values:
            return sum(positive_values) / len(positive_values)

        # Fallback: average of all valid metrics
        return sum(valid_metrics) / len(valid_metrics)

    def _compute_field_accuracy(
        self, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        JSON field-level comparison with nested support.
        For STRUCTURED_TEXT annotation type.

        Compares JSON fields between prediction and ground truth with support for
        nested objects and path matching. Returns accuracy as percentage of matching fields.

        Args:
            gt: Ground truth JSON (dict/string)
            pred: Predicted JSON (dict/string)
            parameters: Optional parameters
                - ignore_keys: List of keys to ignore in comparison (default: [])
                - strict_types: If True, enforce type matching (default: False)

        Returns:
            Accuracy score (0.0-1.0) representing percentage of matching fields
        """
        if parameters is None:
            parameters = {}

        ignore_keys = set(parameters.get("ignore_keys", []))
        strict_types = parameters.get("strict_types", False)

        # Parse as JSON
        gt_json = self._parse_json(gt)
        pred_json = self._parse_json(pred)

        # Handle non-JSON cases
        if gt_json is None and pred_json is None:
            return 1.0
        if gt_json is None or pred_json is None:
            return 0.0

        return self._compare_json_fields(gt_json, pred_json, ignore_keys, strict_types)

    def _compare_json_fields(
        self, gt_obj: Any, pred_obj: Any, ignore_keys: set, strict_types: bool, path: str = ""
    ) -> float:
        """Recursively compare JSON fields with path tracking"""
        # Type mismatch
        if type(gt_obj) != type(pred_obj):
            return 0.0

        if isinstance(gt_obj, dict):
            if not gt_obj and not pred_obj:
                return 1.0

            # Get all keys (excluding ignored)
            all_keys = (set(gt_obj.keys()) | set(pred_obj.keys())) - ignore_keys
            if not all_keys:
                return 1.0

            matching_score = 0.0
            for key in all_keys:
                key_path = f"{path}.{key}" if path else key

                # Both missing
                if key not in gt_obj and key not in pred_obj:
                    matching_score += 1.0
                # One missing
                elif key not in gt_obj or key not in pred_obj:
                    matching_score += 0.0
                # Both present
                else:
                    gt_val = gt_obj[key]
                    pred_val = pred_obj[key]

                    # Type checking if strict
                    if strict_types and type(gt_val) != type(pred_val):
                        matching_score += 0.0
                    # Recursive comparison for nested structures
                    elif isinstance(gt_val, (dict, list)):
                        matching_score += self._compare_json_fields(
                            gt_val, pred_val, ignore_keys, strict_types, key_path
                        )
                    # Direct value comparison
                    else:
                        matching_score += 1.0 if gt_val == pred_val else 0.0

            return matching_score / len(all_keys)

        elif isinstance(gt_obj, list):
            if not gt_obj and not pred_obj:
                return 1.0
            if len(gt_obj) != len(pred_obj):
                return 0.0

            matching_score = sum(
                self._compare_json_fields(g, p, ignore_keys, strict_types, f"{path}[{i}]")
                for i, (g, p) in enumerate(zip(gt_obj, pred_obj))
            )
            return matching_score / len(gt_obj)

        else:
            # Primitive values
            return 1.0 if gt_obj == pred_obj else 0.0

    def _compute_partial_match(
        self, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Fuzzy span matching with partial credit.
        For SPAN_SELECTION annotation type.

        Calculates partial overlap between spans with partial credit based on
        character-level overlap. Not just binary match.

        Args:
            gt: Ground truth span(s)
            pred: Predicted span(s)
            parameters: Optional parameters
                - min_overlap: Minimum overlap to consider (default: 0.0)
                - mode: 'best' or 'average' matching (default: 'best')

        Returns:
            Score (0.0-1.0) based on character-level overlap
        """
        if parameters is None:
            parameters = {}

        min_overlap = parameters.get("min_overlap", 0.0)
        mode = parameters.get("mode", "best")

        # Parse spans
        gt_spans = self._parse_spans(gt)
        pred_spans = self._parse_spans(pred)

        if not gt_spans and not pred_spans:
            return 1.0
        if not gt_spans or not pred_spans:
            return 0.0

        if mode == "average":
            # Average overlap with all label-compatible predicted spans per GT span
            overlap_scores = []
            for gt_span in gt_spans:
                compatible = [p for p in pred_spans if self._spans_label_compatible(gt_span, p)]
                if not compatible:
                    overlap_scores.append(0.0)
                    continue
                total_overlap = sum(
                    self._calculate_span_overlap(gt_span, pred_span) for pred_span in compatible
                )
                avg_overlap = total_overlap / len(compatible)
                overlap_scores.append(avg_overlap if avg_overlap >= min_overlap else 0.0)
            return sum(overlap_scores) / len(overlap_scores) if overlap_scores else 0.0

        # Default: optimal bipartite matching
        def overlap_fn(gt_span, pred_span):
            overlap = self._calculate_span_overlap(gt_span, pred_span)
            return overlap if overlap >= min_overlap else 0.0

        total_overlap = self._optimal_span_matching(gt_spans, pred_spans, overlap_fn)
        return total_overlap / len(gt_spans) if gt_spans else 0.0

    def _calculate_span_overlap(self, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
        """
        Calculate character-level overlap between two spans.

        Returns overlap ratio relative to the ground truth span length.
        """
        start1, end1 = span1["start"], span1["end"]
        start2, end2 = span2["start"], span2["end"]

        # Calculate intersection
        inter_start = max(start1, start2)
        inter_end = min(end1, end2)
        intersection = max(0, inter_end - inter_start)

        # Calculate overlap ratio relative to ground truth span
        gt_length = end1 - start1
        if gt_length == 0:
            return 1.0 if intersection > 0 else 0.0

        return intersection / gt_length

    def _compute_boundary_accuracy(
        self, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Boundary-only comparison for spans.
        For SPAN_SELECTION annotation type.

        Only compares start/end positions:
        - Score 0.5 for matching start OR end
        - Score 1.0 for matching both start AND end

        Args:
            gt: Ground truth span(s)
            pred: Predicted span(s)
            parameters: Optional parameters
                - tolerance: Boundary tolerance in characters (default: 0)
                - mode: 'strict' or 'lenient' matching (default: 'strict')

        Returns:
            Score (0.0-1.0) based on boundary matching
        """
        if parameters is None:
            parameters = {}

        tolerance = parameters.get("tolerance", 0)
        mode = parameters.get("mode", "strict")

        # Parse spans
        gt_spans = self._parse_spans(gt)
        pred_spans = self._parse_spans(pred)

        if not gt_spans and not pred_spans:
            return 1.0
        if not gt_spans or not pred_spans:
            return 0.0

        def boundary_fn(gt_span, pred_span):
            return self._calculate_boundary_score(gt_span, pred_span, tolerance)

        if mode == "lenient":
            # Return max score across any label-compatible match
            best_scores = []
            for gt_span in gt_spans:
                best_score = 0.0
                for pred_span in pred_spans:
                    if self._spans_label_compatible(gt_span, pred_span):
                        score = boundary_fn(gt_span, pred_span)
                        best_score = max(best_score, score)
                best_scores.append(best_score)
            return max(best_scores) if best_scores else 0.0
        else:  # strict - use optimal bipartite matching
            total_score = self._optimal_span_matching(gt_spans, pred_spans, boundary_fn)
            return total_score / len(gt_spans) if gt_spans else 0.0

    def _calculate_boundary_score(
        self, gt_span: Dict[str, Any], pred_span: Dict[str, Any], tolerance: int
    ) -> float:
        """
        Calculate boundary matching score between two spans.

        Returns:
            0.0: No boundaries match
            0.5: One boundary matches (start OR end)
            1.0: Both boundaries match (start AND end)
        """
        start_match = abs(gt_span["start"] - pred_span["start"]) <= tolerance
        end_match = abs(gt_span["end"] - pred_span["end"]) <= tolerance

        if start_match and end_match:
            return 1.0
        elif start_match or end_match:
            return 0.5
        else:
            return 0.0

    def _compute_path_accuracy(
        self, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Full hierarchical path matching.
        For TAXONOMY annotation type.

        Compares full path from root to leaf with support for level weights.
        Deeper matches are worth more.

        Args:
            gt: Ground truth path (e.g., "Law > Civil > Contract > Breach")
            pred: Predicted path
            parameters: Optional parameters
                - level_weights: List of weights for each level (default: linear increasing)
                - normalize: If True, normalize score by max possible (default: True)

        Returns:
            Score (0.0-1.0) based on hierarchical path matching
        """
        if parameters is None:
            parameters = {}

        normalize = parameters.get("normalize", True)

        # Parse hierarchical paths
        gt_path = self._parse_hierarchy_path(gt)
        pred_path = self._parse_hierarchy_path(pred)

        if not gt_path and not pred_path:
            return 1.0
        if not gt_path or not pred_path:
            return 0.0

        # Get level weights (default: increasing weights for deeper levels)
        max_depth = max(len(gt_path), len(pred_path))
        default_weights = [i + 1 for i in range(max_depth)]  # 1, 2, 3, 4, ...
        level_weights = parameters.get("level_weights", default_weights)

        # Ensure we have enough weights
        while len(level_weights) < max_depth:
            level_weights.append(level_weights[-1] + 1 if level_weights else 1)

        # Calculate weighted matching score
        matching_score = 0.0
        max_possible_score = 0.0

        for i in range(max_depth):
            weight = level_weights[i]
            max_possible_score += weight

            if i < len(gt_path) and i < len(pred_path):
                if gt_path[i] == pred_path[i]:
                    matching_score += weight
                else:
                    # Path diverged - no credit for remaining levels
                    break

        if normalize:
            return matching_score / max_possible_score if max_possible_score > 0 else 0.0
        else:
            return matching_score

    def _compute_lca_accuracy(
        self, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Lowest Common Ancestor proximity scoring.
        For TAXONOMY annotation type.

        Finds LCA in taxonomy tree and scores based on proximity to actual node.
        Closer LCA = higher score.

        Args:
            gt: Ground truth path
            pred: Predicted path
            parameters: Optional parameters
                - decay_rate: How quickly score decreases with distance (default: 0.5)
                - min_score: Minimum score for any common ancestor (default: 0.1)

        Returns:
            Score (0.0-1.0) based on LCA proximity
        """
        if parameters is None:
            parameters = {}

        decay_rate = parameters.get("decay_rate", 0.5)
        min_score = parameters.get("min_score", 0.1)

        # Parse hierarchical paths
        gt_path = self._parse_hierarchy_path(gt)
        pred_path = self._parse_hierarchy_path(pred)

        if not gt_path and not pred_path:
            return 1.0
        if not gt_path or not pred_path:
            return 0.0

        # Exact match
        if gt_path == pred_path:
            return 1.0

        # Find LCA depth (last matching level)
        lca_depth = 0
        for i in range(min(len(gt_path), len(pred_path))):
            if gt_path[i] == pred_path[i]:
                lca_depth = i + 1
            else:
                break

        # No common ancestor
        if lca_depth == 0:
            return 0.0

        # Calculate distance from LCA to ground truth node
        distance_to_gt = len(gt_path) - lca_depth

        # Score based on distance with exponential decay
        # LCA at depth d, GT at depth d+k: score = decay_rate^k
        score = decay_rate**distance_to_gt

        # Apply minimum score threshold
        return max(score, min_score)

    def _answers_match_qags(self, answer1: str, answer2: str, threshold: float = 0.5) -> bool:
        """
        Check if two answers match for QAGS scoring.

        Uses token overlap (F1-based) to determine if answers are similar enough.

        Args:
            answer1: First answer
            answer2: Second answer
            threshold: Minimum F1 score for match (default: 0.5)

        Returns:
            True if answers match, False otherwise
        """
        # Normalize answers
        ans1 = answer1.lower().strip()
        ans2 = answer2.lower().strip()

        # Exact match
        if ans1 == ans2:
            return True

        # Empty answers
        if not ans1 or not ans2:
            return False

        # Token-level F1 score
        tokens1 = set(ans1.split())
        tokens2 = set(ans2.split())

        if not tokens1 or not tokens2:
            return False

        intersection = len(tokens1 & tokens2)

        if intersection == 0:
            return False

        precision = intersection / len(tokens2)
        recall = intersection / len(tokens1)

        f1 = 2 * (precision * recall) / (precision + recall)

        return f1 >= threshold

    def _validate_text_for_coherence(self, text: str) -> None:
        """Validate text is suitable for coherence analysis.

        Raises:
            ValueError: If text is empty, too short, or has fewer than 2 sentences.
        """
        if not text or not text.strip():
            raise ValueError("Coherence requires non-empty text")
        if len(text.strip()) < 20:
            raise ValueError("Coherence requires text of at least 20 characters")

        sentences = sent_tokenize(text)
        if len(sentences) < 2:
            raise ValueError(f"Coherence requires at least 2 sentences, found {len(sentences)}")

    def _detect_language_heuristic(self, sentences: List[str]) -> str:
        """
        Detect whether text is German or English using simple heuristics.

        German detection signals:
        - Sentences starting with common German articles/pronouns
        - Presence of German-specific characters (umlauts, eszett)
        - High ratio of capitalized non-sentence-initial words (German noun capitalization)

        Args:
            sentences: List of sentences to analyze

        Returns:
            'de' for German, 'en' for English (default fallback)
        """
        german_articles = {
            'der', 'die', 'das', 'ein', 'eine', 'dem', 'den', 'des',
            'einem', 'einer', 'eines', 'im', 'am', 'zum', 'zur',
        }
        german_char_pattern = any(
            ch in text for text in sentences for ch in 'äöüÄÖÜß'
        )

        german_start_count = 0
        for sentence in sentences:
            words = sentence.strip().split()
            if words and words[0].lower() in german_articles:
                german_start_count += 1

        german_start_ratio = german_start_count / max(len(sentences), 1)

        capitalized_non_initial = 0
        total_non_initial = 0
        for sentence in sentences:
            words = sentence.strip().split()
            for word in words[1:]:
                cleaned = word.strip('.,;:!?()[]"\'')
                if cleaned.isalpha() and len(cleaned) >= 2:
                    total_non_initial += 1
                    if cleaned[0].isupper():
                        capitalized_non_initial += 1

        cap_ratio = capitalized_non_initial / max(total_non_initial, 1)

        if german_char_pattern or german_start_ratio > 0.3 or cap_ratio > 0.15:
            return 'de'

        return 'en'

    def _extract_entities_german(self, sentences: List[str]) -> Dict[str, List[str]]:
        """
        Extract entities from German text using the capitalization rule.

        In German, all nouns are capitalized. Words that are capitalized but not
        at the start of a sentence are therefore nouns (or proper nouns). This is
        a well-established grammatical rule in Standard German orthography.

        Args:
            sentences: List of sentences to analyze

        Returns:
            Entity grid: dict mapping entity (lowercase) -> list of roles per sentence
        """
        german_pronouns = {
            'er', 'sie', 'es', 'ihm', 'ihr', 'ihnen', 'ihn',
            'wir', 'uns', 'dieser', 'diese', 'dieses', 'diesen',
            'diesem', 'jener', 'jene', 'jenes', 'welcher', 'welche',
            'welches', 'man', 'sich',
        }

        entity_grid = {}

        for sent_idx, sentence in enumerate(sentences):
            tokens = word_tokenize(sentence)

            for token_idx, token in enumerate(tokens):
                cleaned = token.strip('.,;:!?()[]"\'-')
                if not cleaned or len(cleaned) < 2:
                    continue

                is_entity = False

                if cleaned.lower() in german_pronouns:
                    is_entity = True
                elif token_idx > 0 and cleaned[0].isupper() and cleaned.isalpha():
                    is_entity = True

                if is_entity:
                    entity = cleaned.lower()
                    if entity not in entity_grid:
                        entity_grid[entity] = ['-'] * len(sentences)
                    entity_grid[entity][sent_idx] = 'X'

        return entity_grid

    def _extract_entities_english(self, sentences: List[str]) -> Dict[str, List[str]]:
        """
        Extract entities from English text using NLTK POS tagging.

        Uses the Penn Treebank POS tagger to identify nouns (NN, NNS, NNP, NNPS)
        and pronouns (PRP, PRP$) as entities for the Entity Grid Method.

        Args:
            sentences: List of sentences to analyze

        Returns:
            Entity grid: dict mapping entity (lowercase) -> list of roles per sentence
        """
        entity_grid = {}

        for sent_idx, sentence in enumerate(sentences):
            tokens = word_tokenize(sentence)
            pos_tags = pos_tag(tokens)

            for word, pos in pos_tags:
                if pos.startswith('NN') or pos.startswith('PRP'):
                    entity = word.lower()
                    if entity not in entity_grid:
                        entity_grid[entity] = ['-'] * len(sentences)
                    entity_grid[entity][sent_idx] = 'X'

        return entity_grid

    def _compute_entity_coherence(self, sentences: List[str]) -> float:
        """
        Compute entity-based coherence using Entity Grid Method.

        Based on Barzilay & Lapata (2008): "Modeling Local Coherence: An Entity-based Approach"

        Language-aware entity extraction:
        - German: Uses capitalization rule (all German nouns are capitalized)
        - English: Uses NLTK POS tagger (NN, NNS, NNP, NNPS, PRP, PRP$)

        Args:
            sentences: List of sentences to analyze

        Returns:
            Coherence score between 0.0-1.0 (higher = more coherent)
        """
        try:
            lang = self._detect_language_heuristic(sentences)

            if lang == 'de':
                entity_grid = self._extract_entities_german(sentences)
            else:
                entity_grid = self._extract_entities_english(sentences)

            if not entity_grid:
                raise RuntimeError(
                    f"No entities found in text (detected language: {lang}). "
                    "Text may lack proper nouns/pronouns or entity detection "
                    "failed for this language."
                )

            smooth_transitions = 0
            total_transitions = 0

            for entity, roles in entity_grid.items():
                for i in range(len(roles) - 1):
                    if roles[i] != '-' and roles[i + 1] != '-':
                        smooth_transitions += 2.0
                    elif roles[i] != '-' or roles[i + 1] != '-':
                        smooth_transitions += 0.5

                    total_transitions += 1

            if total_transitions == 0:
                raise RuntimeError("No entity transitions found across sentences")

            coherence_score = smooth_transitions / (
                total_transitions * 2.0
            )
            return max(0.0, min(1.0, coherence_score))

        except Exception as e:
            logger.error(f"Entity coherence computation failed: {e}")
            raise RuntimeError(f"Entity coherence computation failed: {e}") from e

    def _compute_semantic_coherence(self, sentences: List[str]) -> float:
        """
        Compute semantic coherence using sentence embeddings.

        Measures coherence as the average cosine similarity between adjacent sentences.
        Coherent texts have semantically related adjacent sentences.

        Algorithm:
        1. Encode each sentence using sentence transformer model
        2. Compute cosine similarity between adjacent sentence pairs
        3. Average similarities to get overall coherence score

        Args:
            sentences: List of sentences to analyze

        Returns:
            Coherence score between 0.0-1.0 (higher = more coherent)
        """
        try:
            # Load sentence transformer model
            model = _get_sentence_transformer()
            if model is None:
                raise RuntimeError(
                    "Sentence transformer model could not be loaded. "
                    "Ensure sentence-transformers package is installed."
                )

            # Encode all sentences
            embeddings = model.encode(sentences, convert_to_tensor=True)

            # Compute cosine similarities between adjacent sentences
            similarities = []
            for i in range(len(embeddings) - 1):
                # Cosine similarity between adjacent sentences
                sim = st_util.cos_sim(embeddings[i], embeddings[i + 1]).item()
                similarities.append(sim)

            if not similarities:
                return 1.0  # Single sentence is perfectly coherent

            # Average similarity is the coherence score
            avg_similarity = sum(similarities) / len(similarities)

            # Normalize to [0, 1] range (cosine similarity is already in [-1, 1])
            # Map [-1, 1] to [0, 1] where 1 = high similarity (coherent)
            coherence_score = (avg_similarity + 1.0) / 2.0

            return max(0.0, min(1.0, coherence_score))

        except Exception as e:
            raise RuntimeError(f"Semantic coherence computation failed: {e}")
