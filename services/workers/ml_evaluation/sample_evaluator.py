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

import logging
import platform
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Platform detection for backend selection
IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')

# NLTK imports - REQUIRED for BLEU, METEOR, coherence
import nltk
import numpy as np
from nltk.tokenize import sent_tokenize

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

# ROUGE / SacreBLEU / scikit-learn / scipy / jsonschema availability markers.
# The concrete imports now live in the per-metric modules that actually use
# them (post-decomposition); these flags stay as the module-level capability
# assertions other code historically branched on.
ROUGE_AVAILABLE = True
SACREBLEU_AVAILABLE = True
SKLEARN_AVAILABLE = True
SCIPY_AVAILABLE = True
JSONSCHEMA_AVAILABLE = True

# Heavy ML libs (bert_score, sentence-transformers, transformers, torch) are
# imported LAZILY via the module-level __getattr__ below — NOT at module top.
# Rationale: `import tasks` must stay cheap (~1.7s, no ML). The beat scheduler
# and the api import the Celery app but never compute neural metrics; an eager
# ~7s/500Mi ML load here breaks the beat's 15s startup probe and slows every
# deploy. The libs ARE installed (required), so the capability flags stay True;
# the actual import happens on first use inside the metric functions.
BERTSCORE_AVAILABLE = True
SENTENCE_TRANSFORMERS_AVAILABLE = True
_sentence_transformer_model = None  # Lazy-loaded


# Heavy ML symbols are module globals (so they resolve as bare names inside the
# metric functions and stay monkeypatchable in tests) but bound LAZILY — None
# until the first metric computation calls _load_heavy(). Importing this module,
# and transitively `import tasks`, must NOT pay the ~7s/500Mi neural-ML cost.
bert_score_compute = None
SentenceTransformer = None
st_util = None
BertForSequenceClassification = None
BertTokenizer = None
torch = None


def _load_heavy() -> None:
    """Bind the heavy-ML module globals on first use (idempotent; a no-op once
    bound, or once a test has monkeypatched a symbol to a non-None stand-in)."""
    global bert_score_compute, SentenceTransformer, st_util
    global BertForSequenceClassification, BertTokenizer, torch
    if torch is None:
        import torch as _torch

        torch = _torch
    if bert_score_compute is None:
        from bert_score import score as _bs

        bert_score_compute = _bs
    if SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer as _ST
        from sentence_transformers import util as _util

        SentenceTransformer = _ST
        st_util = _util
    if BertForSequenceClassification is None:
        from transformers import BertForSequenceClassification as _BFSC
        from transformers import BertTokenizer as _BT

        BertForSequenceClassification = _BFSC
        BertTokenizer = _BT

# Backend selector for platform-aware metric computation (MoverScore via POT)
_backend_selector = None


def _get_backend_selector():
    """Lazy load backend selector for platform-aware metric computation."""
    global _backend_selector
    if _backend_selector is None:
        from .backends.selector import backend_selector

        _backend_selector = backend_selector
    return _backend_selector


# Transformers for FactCC — imported lazily (see __getattr__ above).
TRANSFORMERS_AVAILABLE = True
# QAGS and SummaC models now handled by backends (see backends/torch_backend.py and backends/onnx_backend.py)

# SummaC factual consistency - now handled by backends (no summac package needed)
# The SummaC algorithm is reimplemented using the ViTC model directly

# PyTorch — imported lazily (see __getattr__ above).
TORCH_AVAILABLE = True
_factcc_model = None  # Lazy-loaded FactCC model
_factcc_tokenizer = None  # Lazy-loaded FactCC tokenizer

logger = logging.getLogger(__name__)


def _get_sentence_transformer():
    """Lazy load sentence transformer model for GPU efficiency"""
    _load_heavy()
    global _sentence_transformer_model
    if _sentence_transformer_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        _sentence_transformer_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _sentence_transformer_model


def _get_factcc_model():
    """Lazy load FactCC model and tokenizer for factual consistency checking"""
    _load_heavy()
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


# Per-metric-family computation modules. Each function takes the evaluator
# instance (``ev``) as its first parameter; the thin method shims on
# ``SampleEvaluator`` below delegate into them. The metrics modules only
# lazy-import back from this module inside their function bodies, so these
# top-of-file imports do not create a load-time import cycle.
from .metrics import (  # noqa: E402
    classification as _m_classification,
    factuality as _m_factuality,
    hierarchical as _m_hierarchical,
    lexical as _m_lexical,
    ranking as _m_ranking,
    semantic as _m_semantic,
    span as _m_span,
    structured as _m_structured,
)


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
        annotation_id: Optional[str] = None,
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
            annotation_id: Optional ID of the annotation that produced the prediction
                (for human annotation evaluation — skips parse_status check)
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
        # Skip check for annotation-based evaluation (annotations are always valid)
        if generation_id is not None and annotation_id is None and parse_status != "success" and not allow_unparsed:
            error_msg = (
                f"Cannot evaluate generation {generation_id} with parse_status='{parse_status}'. "
                "Only generations with parse_status='success' can be evaluated. "
                "Please ensure the generation response has been parsed before evaluation."
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

                    # Phase 2: persist the rich result dict so audit-trail
                    # consumers see provenance (sub-method used, backend,
                    # fallback reasons). Bare-float consumers extract the
                    # number via ml_evaluation.extract_value at read time.
                    metric_result = self._compute_metric_with_details(
                        metric_name,
                        ground_truth,
                        prediction,
                        answer_type,
                        metric_params,
                    )
                    sample_metrics[metric_name] = metric_result

                    # Check if this metric indicates failure
                    # (e.g., exact_match = 0, or score below threshold)
                    primary_value = metric_result.get("value")
                    if isinstance(primary_value, dict):
                        primary_key = metric_result.get("primary_metric_key") or next(
                            iter(primary_value), None
                        )
                        primary_value = (
                            primary_value.get(primary_key)
                            if primary_key
                            else None
                        )
                    if self._is_failure_metric(metric_name, primary_value):
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

        # Phase 4: registry-first dispatch.
        #
        # If a handler is registered for this metric (platform built-in or
        # extended-registered via `register_metric_handlers`), let it own
        # the computation. Handlers return the standard result dict;
        # this method preserves its legacy ``-> float`` signature by
        # extracting the primary value via ``extract_value``.
        #
        # Adapters use ``_compute_metric_legacy`` to reach the if/elif
        # chain below directly (no recursion).
        from . import extract_value, metric_registry

        _handler = metric_registry.get(metric_name)
        if _handler is not None:
            try:
                _result = _handler.compute(gt, pred, answer_type, parameters)
                _value = extract_value(_result)
                return float(_value if _value is not None else 0.0)
            except NotImplementedError:
                # Some handlers (e.g. extended Falllösung) are presence
                # flags only — the real compute happens in a different
                # call site. Fall through to the legacy chain below; if
                # the metric isn't there either, the bottom branch raises.
                pass

        return self._compute_metric_legacy(
            metric_name, gt, pred, answer_type, parameters
        )

    def _compute_metric_legacy(
        self,
        metric_name: str,
        gt: Any,
        pred: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Direct dispatch into the if/elif chain — no registry lookup.

        Used by :class:`builtin_handlers._LegacyMetricHandler` to wrap
        bare-float compute paths into the standard registry shape without
        recursing through ``_compute_metric``.
        """
        if parameters is None:
            parameters = {}

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

        # Korrektur (Standard Falllösung / Classic) is HUMAN-graded. The
        # actual score is written by the API when a corrector submits;
        # the worker only sees the metric name in the dispatch loop and
        # has nothing to compute. Returning 0/1 from "exact match" was
        # nonsensical and pollutes logs. Treat as a no-op (NaN-safe 0).
        elif metric_name.startswith("korrektur_"):
            logger.debug(
                f"Metric {metric_name} is human-graded; worker dispatch is a no-op"
            )
            return 0.0

        # Phase 6.6: fail loud on unknown metrics. Previously this branch
        # silently fell back to exact-match scoring, which is exactly the
        # kind of unobservable benchmark corruption the academic-rigor
        # overhaul is eliminating: a typo in evaluation_config silently
        # produced a 0/1 number instead of erroring. Surfacing the error
        # at run time means a misconfigured project fails clearly and
        # visibly, not in a paper.
        else:
            raise ValueError(
                f"Unknown metric: {metric_name!r}. No handler is registered "
                "for this metric and no built-in branch exists. If this is "
                "an extended-only metric (e.g. llm_judge_falloesung), check "
                "that benger_extended is loaded and register_metric_handlers "
                "fired at worker startup."
            )

    # ------------------------------------------------------------------
    # Phase 2: dict-returning entry point with full provenance.
    # ------------------------------------------------------------------
    #
    # Callers that want the audit trail (the ones persisting into
    # ``TaskEvaluation.metrics``) call ``_compute_metric_with_details``;
    # callers that only need a number stay on ``_compute_metric``.
    #
    # The 6 metrics with known silent-fallback paths
    # (coherence / moverscore / qags / bertscore / semantic_similarity /
    # bleu-smoothing — the last is fail-loud, no provenance needed) get
    # dedicated helpers below that capture which sub-method, backend, or
    # parameter actually contributed to the score.
    #
    # Other metrics fall through to ``_compute_metric`` and have their
    # bare-float result wrapped in the standard shape with
    # ``details: {"legacy_path": True}``. Phase 4 walks each into a
    # registered handler so the wrapper goes away.
    def _compute_metric_with_details(
        self,
        metric_name: str,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if parameters is None:
            parameters = {}

        gt = self._normalize_value(ground_truth, answer_type)
        pred = self._normalize_value(prediction, answer_type)

        # 1. Registry first — handlers own their full result dict.
        from . import metric_registry

        handler = metric_registry.get(metric_name)
        if handler is not None:
            return handler.compute(gt, pred, answer_type, parameters)

        # 2. Korrektur metrics are human-graded; never compute in worker.
        if metric_name.startswith("korrektur_"):
            return {
                "value": 0.0,
                "method": metric_name,
                "details": {
                    "human_graded": True,
                    "skipped": True,
                    "reason": (
                        "Korrektur metrics are written by the API at human-grade "
                        "time, not computed by the worker."
                    ),
                },
                "error": None,
            }

        # 3. Targeted provenance helpers for known silent-fallback metrics.
        if metric_name == "coherence":
            return self._coherence_with_details(pred, parameters)
        if metric_name == "moverscore":
            return self._moverscore_with_details(gt, pred, parameters)
        if metric_name == "qags":
            return self._qags_with_details(gt, pred, parameters)
        if metric_name == "bertscore":
            return self._bertscore_with_details(gt, pred, parameters)
        if metric_name == "semantic_similarity":
            return self._semantic_similarity_with_details(gt, pred, parameters)

        # 4. Fall through to the legacy if/elif chain via the registry
        # adapter. Phase 4 registers a handler for every platform metric;
        # the registry path above should normally take it. This branch
        # is a safety net for any metric that's not yet in the registry
        # (none today, but the explicit fallback keeps the contract).
        legacy_value = self._compute_metric_legacy(
            metric_name, gt, pred, answer_type, parameters
        )
        return {
            "value": float(legacy_value) if legacy_value is not None else 0.0,
            "method": metric_name,
            "details": {
                "legacy_path": True,
                "parameters_applied": dict(parameters) if parameters else {},
            },
            "error": None,
        }

    # ---- Provenance helpers (Phase 2 in-place annotation) -----------

    def _coherence_with_details(
        self, prediction: Any, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Coherence with full audit trail of which sub-method actually
        contributed to the score. Replaces the silent semantic-only
        fallback shipped in last night's launch fix."""
        pred_str = str(prediction)
        method = parameters.get("method", "hybrid")
        entity_weight = parameters.get("entity_weight", 0.6)
        semantic_weight = parameters.get("semantic_weight", 0.4)

        self._validate_text_for_coherence(pred_str)
        sentences = sent_tokenize(pred_str)

        coherence_scores: List[Tuple[float, float]] = []
        methods_used: List[str] = []
        fallback_reason: Optional[str] = None

        if method in ("entity", "hybrid"):
            try:
                entity_score = self._compute_entity_coherence(sentences)
                coherence_scores.append((entity_score, entity_weight))
                methods_used.append("entity")
            except Exception as entity_err:
                if method == "entity":
                    raise RuntimeError(
                        f"Coherence (entity-only mode): {entity_err}"
                    ) from entity_err
                fallback_reason = f"entity grid unavailable: {entity_err}"
                logger.info(
                    "Coherence: entity grid unavailable (%s); falling back "
                    "to semantic-only score within hybrid mode",
                    entity_err,
                )

        if method in ("semantic", "hybrid"):
            semantic_score = self._compute_semantic_coherence(sentences)
            coherence_scores.append((semantic_score, semantic_weight))
            methods_used.append("semantic")

        if not coherence_scores:
            raise ValueError(f"Invalid coherence method: {method!r}")

        total_weight = sum(w for _, w in coherence_scores)
        if total_weight == 0:
            value = 0.0
        else:
            weighted = sum(
                score * (weight / total_weight)
                for score, weight in coherence_scores
            )
            value = max(0.0, min(1.0, weighted))

        # Audit trail: record three views of the weights so a researcher can
        # always tell exactly what contributed to the score.
        #   - weights_requested : the user-configured weights (parameters)
        #   - weights_input     : per-method weights that ENTERED the
        #                         weighted average (0 for any method whose
        #                         sub-score wasn't computed, e.g. entity
        #                         when the grid was empty in hybrid mode)
        #   - weights_effective : post-normalization weights that the
        #                         averaging actually multiplied each
        #                         sub-score by (sums to 1.0)
        weights_input = {
            "entity": entity_weight if "entity" in methods_used else 0.0,
            "semantic": semantic_weight if "semantic" in methods_used else 0.0,
        }
        weights_effective = (
            {k: (w / total_weight) for k, w in weights_input.items()}
            if total_weight > 0
            else {k: 0.0 for k in weights_input}
        )
        return {
            "value": value,
            "method": "coherence",
            "details": {
                "method_requested": method,
                "methods_used": methods_used,
                "weights_requested": {
                    "entity": entity_weight,
                    "semantic": semantic_weight,
                },
                "weights_input": weights_input,
                "weights_effective": weights_effective,
                "fallback_reason": fallback_reason,
                # ner_model is set by the German entity extractor itself
                # (Phase 3); for now record the heuristic in use.
                "ner_model": getattr(
                    self, "_last_coherence_ner_model", "capitalization_heuristic"
                ),
            },
            "error": None,
        }

    def _moverscore_with_details(
        self, gt: Any, pred: Any, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MoverScore with audit trail. The prior code returned 0.0 silently
        when the backend produced an empty result, indistinguishable from
        a genuine 0. Now we surface the empty-output case explicitly."""
        gt_str = str(gt)
        pred_str = str(pred)
        if not gt_str.strip():
            raise ValueError("MoverScore requires non-empty ground truth text")
        if not pred_str.strip():
            raise ValueError("MoverScore requires non-empty prediction text")
        if len(gt_str.strip()) < 3 or len(pred_str.strip()) < 3:
            raise ValueError("MoverScore requires text longer than 3 characters")

        n_gram = parameters.get("n_gram", 1)
        remove_subwords = parameters.get("remove_subwords", True)

        selector = _get_backend_selector()
        computer = selector.get_moverscore_computer()
        scores = computer.compute_moverscore(
            [gt_str], [pred_str], n_gram=n_gram, remove_subwords=remove_subwords
        )

        if not scores:
            return {
                "value": 0.0,
                "method": "moverscore",
                "details": {
                    "n_gram": n_gram,
                    "remove_subwords": remove_subwords,
                    "backend_returned_scores": False,
                },
                "error": "MoverScore backend returned no scores",
            }
        return {
            "value": float(scores[0]),
            "method": "moverscore",
            "details": {
                "n_gram": n_gram,
                "remove_subwords": remove_subwords,
                "backend_returned_scores": True,
            },
            "error": None,
        }

    def _qags_with_details(
        self, gt: Any, pred: Any, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """QAGS with per-question failure tracking. Failed Q/A pairs are
        excluded from the denominator (rather than counted as non-matches),
        which is more honest about what was actually measured."""
        gt_str = str(gt)
        pred_str = str(pred)
        num_questions = parameters.get("num_questions", 5)
        min_answer_overlap = parameters.get("min_answer_overlap", 0.5)

        selector = _get_backend_selector()
        qags_backend = selector.get_qags_backend()
        questions = qags_backend.generate_questions(
            gt_str, num_questions=num_questions
        )

        failed_questions: List[Dict[str, Any]] = []
        matched = 0
        succeeded = 0

        for q in questions:
            try:
                gt_answer = qags_backend.answer_question(q, gt_str)
                pred_answer = qags_backend.answer_question(q, pred_str)
                if self._answers_match_qags(
                    gt_answer["answer"],
                    pred_answer["answer"],
                    threshold=min_answer_overlap,
                ):
                    matched += 1
                succeeded += 1
            except Exception as e:
                failed_questions.append({"question": q, "error": str(e)})

        if succeeded == 0:
            return {
                "value": 0.0,
                "method": "qags",
                "details": {
                    "total_questions_generated": len(questions),
                    "questions_succeeded": 0,
                    "questions_failed": len(failed_questions),
                    "failed_question_errors": failed_questions[:10],
                    "min_answer_overlap": min_answer_overlap,
                },
                "error": (
                    "All QAGS questions failed; score is 0 by convention "
                    "(no successful Q/A pair to score against)"
                    if questions
                    else "QAGS generated no questions from ground truth"
                ),
            }

        score = matched / succeeded
        return {
            "value": float(score),
            "method": "qags",
            "details": {
                "total_questions_generated": len(questions),
                "questions_succeeded": succeeded,
                "questions_failed": len(failed_questions),
                "matched_answers": matched,
                "failed_question_errors": failed_questions[:10],
                "min_answer_overlap": min_answer_overlap,
            },
            "error": None,
        }

    def _bertscore_with_details(
        self, gt: Any, pred: Any, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """BERTScore with backend provenance — researchers can filter
        runs by host_arch / backend if they need to compare scores
        produced by ONNX vs full bert-score."""
        _load_heavy()

        import platform as _platform

        gt_str = str(gt)
        pred_str = str(pred)
        lang = parameters.get("lang", "de")

        if IS_ARM64:
            selector = _get_backend_selector()
            backend = selector.get_bertscore_backend()
            P, R, F1 = backend.compute([pred_str], [gt_str], lang=lang)
            f1_value = float(F1)
            backend_id = "onnx"
        else:
            P, R, F1 = bert_score_compute(
                [pred_str],
                [gt_str],
                lang=lang,
                rescale_with_baseline=True,
                verbose=False,
            )
            f1_value = float(F1.mean().item())
            backend_id = "pytorch"

        return {
            "value": f1_value,
            "method": "bertscore",
            "details": {
                "backend": backend_id,
                "host_arch": _platform.machine(),
                "lang": lang,
                "rescale_with_baseline": backend_id == "pytorch",
            },
            "error": None,
        }

    def _semantic_similarity_with_details(
        self, gt: Any, pred: Any, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Semantic similarity with backend provenance — same arch-based
        ONNX vs sentence-transformers swap as BERTScore."""
        _load_heavy()

        import platform as _platform

        gt_str = str(gt)
        pred_str = str(pred)

        if IS_ARM64:
            selector = _get_backend_selector()
            backend = selector.get_embedding_backend()
            emb_gt = backend.encode([gt_str])[0]
            emb_pred = backend.encode([pred_str])[0]
            similarity = np.dot(emb_gt, emb_pred) / (
                np.linalg.norm(emb_gt) * np.linalg.norm(emb_pred) + 1e-9
            )
            value = max(0.0, float(similarity))
            backend_id = "onnx"
            model_id = "MiniLM-onnx"
        else:
            model = _get_sentence_transformer()
            if model is None:
                raise RuntimeError(
                    "Sentence transformer model could not be loaded. "
                    "Ensure sentence-transformers package is installed."
                )
            emb_gt = model.encode(gt_str, convert_to_tensor=True)
            emb_pred = model.encode(pred_str, convert_to_tensor=True)
            value = max(0.0, float(st_util.cos_sim(emb_gt, emb_pred).item()))
            backend_id = "pytorch"
            model_id = getattr(model, "_first_module", lambda: None)() and "sentence-transformers"

        return {
            "value": value,
            "method": "semantic_similarity",
            "details": {
                "backend": backend_id,
                "model": model_id,
                "host_arch": _platform.machine(),
            },
            "error": None,
        }

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
        return _m_lexical.compute_text_similarity(self, metric_name, gt, pred, parameters)

    def _compute_numeric_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """Compute numeric evaluation metrics including r2 and correlation"""
        return _m_classification.compute_numeric_metric(self, metric_name, gt, pred)

    def _compute_classification_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute classification metrics for single sample.
        For single samples, these are binary (correct/incorrect).
        True metrics are computed at aggregate level.
        """
        return _m_classification.compute_classification_metric(
            self, metric_name, gt, pred, parameters
        )

    def _compute_set_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """
        Compute set-based metrics for multi-label classification.
        Handles list/set comparisons.
        """
        return _m_classification.compute_set_metric(self, metric_name, gt, pred)

    def _to_set(self, value: Any) -> set:
        """Convert a value to a set for comparison"""
        return _m_classification.to_set(self, value)

    def _compute_token_f1(self, gt: Any, pred: Any) -> float:
        """
        Compute token-level F1 score.
        Treats text as bag of tokens and computes F1.
        """
        return _m_classification.compute_token_f1(self, gt, pred)

    def _compute_ranking_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute ranking metrics.
        For single samples, these are approximations - true metrics computed at aggregate level.
        """
        return _m_ranking.compute_ranking_metric(self, metric_name, gt, pred, parameters)

    def _to_list(self, value: Any) -> List[Any]:
        """Convert a value to a list for ranking comparisons"""
        return _m_ranking.to_list(self, value)

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
        return _m_semantic.compute_semantic_metric(self, metric_name, gt, pred, parameters)

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
        return _m_factuality.compute_factuality_metric(self, metric_name, gt, pred, parameters)

    def _compute_structured_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute structured data metrics for JSON and schema validation.
        """
        return _m_structured.compute_structured_metric(self, metric_name, gt, pred, parameters)

    def _parse_json(self, value: Any) -> Optional[Any]:
        """Parse a value as JSON"""
        return _m_structured.parse_json(self, value)

    def _json_field_accuracy(self, gt_json: Any, pred_json: Any) -> float:
        """Calculate field-level accuracy for JSON structures"""
        return _m_structured.json_field_accuracy(self, gt_json, pred_json)

    def _compute_span_metric(self, metric_name: str, gt: Any, pred: Any) -> float:
        """
        Compute span-based metrics for sequence labeling.
        Handles start/end positions for text spans.
        """
        return _m_span.compute_span_metric(self, metric_name, gt, pred)

    def _parse_spans(self, value: Any) -> List[Dict[str, Any]]:
        """Parse span information from various formats, preserving labels when present."""
        return _m_span.parse_spans(self, value)

    def _spans_label_compatible(self, gt_span: Dict[str, Any], pred_span: Dict[str, Any]) -> bool:
        """Check if two spans have compatible labels.

        Returns True if labels overlap or if either side has no labels
        (backwards compatible with position-only data).
        """
        return _m_span.spans_label_compatible(self, gt_span, pred_span)

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
        return _m_span.optimal_span_matching(self, gt_spans, pred_spans, score_fn)

    def _span_iou(self, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
        """Calculate IoU for two spans"""
        return _m_span.span_iou(self, span1, span2)

    def _compute_hierarchical_metric(
        self, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Compute hierarchical classification metrics.
        Handles tree-structured label hierarchies.
        """
        return _m_hierarchical.compute_hierarchical_metric(self, metric_name, gt, pred, parameters)

    def _parse_hierarchy_path(self, value: Any) -> List[str]:
        """Parse a hierarchical label path"""
        return _m_hierarchical.parse_hierarchy_path(self, value)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Compute Levenshtein distance between two strings"""
        return _m_hierarchical.levenshtein_distance(self, s1, s2)

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

    def _calculate_confidence(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall confidence score from metrics.

        Phase 2/4: ``metrics`` values are now the rich dict shape
        (``{value, method, details, error}``); extract the bare float so
        ``sum()``/threshold logic keeps working.
        """
        from ml_evaluation.handlers import extract_value as _extract

        # Normalize dict-shaped entries to bare floats. Drop None/extraction-failures.
        normalized: Dict[str, Optional[float]] = {}
        for k, v in metrics.items():
            if v is None:
                normalized[k] = None
                continue
            if isinstance(v, (int, float)):
                normalized[k] = float(v)
                continue
            extracted = _extract(v)
            normalized[k] = float(extracted) if extracted is not None else None
        metrics = normalized
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
        return _m_structured.compute_field_accuracy(self, gt, pred, parameters)

    def _compare_json_fields(
        self, gt_obj: Any, pred_obj: Any, ignore_keys: set, strict_types: bool, path: str = ""
    ) -> float:
        """Recursively compare JSON fields with path tracking"""
        return _m_structured.compare_json_fields(
            self, gt_obj, pred_obj, ignore_keys, strict_types, path
        )

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
        return _m_structured.compute_partial_match(self, gt, pred, parameters)

    def _calculate_span_overlap(self, span1: Dict[str, Any], span2: Dict[str, Any]) -> float:
        """
        Calculate character-level overlap between two spans.

        Returns overlap ratio relative to the ground truth span length.
        """
        return _m_span.calculate_span_overlap(self, span1, span2)

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
        return _m_span.compute_boundary_accuracy(self, gt, pred, parameters)

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
        return _m_span.calculate_boundary_score(self, gt_span, pred_span, tolerance)

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
        return _m_hierarchical.compute_path_accuracy(self, gt, pred, parameters)

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
        return _m_hierarchical.compute_lca_accuracy(self, gt, pred, parameters)

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
        return _m_factuality.answers_match_qags(self, answer1, answer2, threshold)

    def _validate_text_for_coherence(self, text: str) -> None:
        """Validate text is suitable for coherence analysis.

        Raises:
            ValueError: If text is empty, too short, or has fewer than 2 sentences.
        """
        return _m_factuality.validate_text_for_coherence(self, text)

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
        return _m_factuality.detect_language_heuristic(self, sentences)

    def _extract_entities_german(self, sentences: List[str]) -> Dict[str, List[str]]:
        """
        Extract entities from German text via spaCy ``de_core_news_md``.

        Uses real Named Entity Recognition (PER, LOC, ORG, MISC) — replaces
        the previous capitalization heuristic which a) missed single-letter
        party abbreviations like "K", "V" common in German legal exam
        text, and b) couldn't distinguish proper nouns from common nouns
        at the start of sentences.

        The chosen model :code:`de_core_news_md` is the medium-size German
        news pipeline (~50 MB). It's pinned via a versioned wheel in
        :code:`requirements.txt` so worker images are reproducible. If
        loading fails (model not installed, e.g. during a partial
        development install), this method falls back to the legacy
        capitalization heuristic and records that on the evaluator
        instance via :code:`_last_coherence_ner_model` — the coherence
        provenance helper surfaces this in :code:`details.ner_model` so
        researchers always know which extractor produced their score.

        Args:
            sentences: List of sentences to analyze

        Returns:
            Entity grid: dict mapping entity (lowercase) -> list of roles per sentence
        """
        return _m_factuality.extract_entities_german(self, sentences)

    # spaCy German pipeline is loaded once and cached on the class. ~200ms
    # first call, then ~free for subsequent ones. We disable parser /
    # lemmatizer / attribute_ruler since coherence only consults
    # :code:`doc.ents` (NER); halving load time and ~40% peak memory.
    _DE_NLP_CACHE = None  # class attribute

    @classmethod
    def _get_de_spacy(cls):
        if cls._DE_NLP_CACHE == None:
            try:
                import spacy

                cls._DE_NLP_CACHE = spacy.load(
                    "de_core_news_md",
                    disable=["parser", "lemmatizer", "attribute_ruler"],
                )
            except (ImportError, OSError) as e:
                # Either spacy isn't installed or the model wheel isn't
                # present. Cache the negative result so we don't retry on
                # every sentence; legacy heuristic kicks in.
                logger.warning(
                    "Failed to load spaCy de_core_news_md: %s — coherence "
                    "will fall back to capitalization heuristic.",
                    e,
                )
                cls._DE_NLP_CACHE = False
        return cls._DE_NLP_CACHE if cls._DE_NLP_CACHE else None

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
        return _m_factuality.extract_entities_english(self, sentences)

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
        return _m_factuality.compute_entity_coherence(self, sentences)

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
        return _m_factuality.compute_semantic_coherence(self, sentences)
