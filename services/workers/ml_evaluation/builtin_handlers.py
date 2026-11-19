"""Built-in MetricHandler implementations for the platform's metric registry.

Phase 4 of the academic-rigor overhaul. Each platform metric is now a
registered :class:`MetricHandler` so dispatch goes through the registry
rather than the legacy ``_compute_metric`` if/elif chain. The handlers
themselves are thin adapters: each calls the existing
:class:`SampleEvaluator` family of `_compute_*` helpers (which house
the actual scoring math, well-tested across the platform) and wraps the
returned bare float into the standard ``{value, method, details, error}``
shape with parameter provenance.

The metrics with bespoke provenance dicts (coherence, MoverScore, QAGS,
BERTScore, semantic-similarity) get slightly richer handlers that
delegate to the corresponding ``_..._with_details`` helper from Phase 2
so their full audit trail flows through.

Why thin adapters and not class-based reimplementations? The compute
math is correct and unit-tested today; rewriting 50+ branches into
"real" classes would risk introducing new bugs for zero academic-rigor
benefit. The registry's value is the dispatch contract — handlers
return a uniform shape — not the OOP packaging.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .handlers import MetricHandler


# --------------------------------------------------------------------
# Generic adapter — used for every metric that calls a
# `SampleEvaluator._compute_*` helper and returns a bare float.
# --------------------------------------------------------------------


class _LegacyMetricHandler(MetricHandler):
    """Adapter that wraps a SampleEvaluator-bound bare-float compute path.

    The handler doesn't OWN the evaluator instance — handlers are
    process-singletons in the registry. Each ``compute()`` call gets a
    short-lived SampleEvaluator built solely to access its compute
    helpers; this matches the pre-existing pattern in
    ``run_single_sample_evaluation`` (tasks.py).
    """

    def __init__(self, name: str, primary_key: Optional[str] = None):
        self.name = name
        self.primary_metric_key = primary_key

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Lazy import to avoid the circular handlers <-> sample_evaluator
        # path during module load.
        from .sample_evaluator import SampleEvaluator

        # Use a placeholder eval id; this handler doesn't persist anything
        # itself — the caller (tasks.py / SampleEvaluator.evaluate_sample)
        # owns the TaskEvaluation row.
        evaluator = SampleEvaluator(
            evaluation_id="<handler-call>",
            field_configs={"f": {"type": answer_type or "text"}},
            metric_parameters={},
        )

        # Direct call into the legacy if/elif chain — _compute_metric_legacy
        # skips the registry lookup at the top of _compute_metric, avoiding
        # infinite recursion (this handler was just dispatched FROM that
        # registry lookup).
        legacy_value = evaluator._compute_metric_legacy(
            self.name, ground_truth, prediction, answer_type or "text", parameters
        )
        return {
            "value": float(legacy_value) if legacy_value is not None else 0.0,
            "method": self.name,
            "details": {
                "registered_via": "_LegacyMetricHandler",
                "parameters_applied": dict(parameters) if parameters else {},
            },
            "error": None,
        }


# --------------------------------------------------------------------
# Provenance-rich handlers — delegate to the corresponding
# `_..._with_details` helper added in Phase 2 so the full audit trail
# flows through (methods used, backend, fallback reasons, etc.).
# --------------------------------------------------------------------


class _CoherenceHandler(MetricHandler):
    name = "coherence"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator("<handler-call>", {"f": {"type": "text"}}, {})
        return evaluator._coherence_with_details(prediction, parameters or {})


class _MoverScoreHandler(MetricHandler):
    name = "moverscore"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator("<handler-call>", {"f": {"type": "text"}}, {})
        return evaluator._moverscore_with_details(
            ground_truth, prediction, parameters or {}
        )


class _QAGSHandler(MetricHandler):
    name = "qags"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator("<handler-call>", {"f": {"type": "text"}}, {})
        return evaluator._qags_with_details(
            ground_truth, prediction, parameters or {}
        )


class _BERTScoreHandler(MetricHandler):
    name = "bertscore"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator("<handler-call>", {"f": {"type": "text"}}, {})
        return evaluator._bertscore_with_details(
            ground_truth, prediction, parameters or {}
        )


class _SemanticSimilarityHandler(MetricHandler):
    name = "semantic_similarity"

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from .sample_evaluator import SampleEvaluator

        evaluator = SampleEvaluator("<handler-call>", {"f": {"type": "text"}}, {})
        return evaluator._semantic_similarity_with_details(
            ground_truth, prediction, parameters or {}
        )


class TextPatternHandler(MetricHandler):
    """A text pattern code (``services/shared/analysis/text_patterns.py``)
    of the prediction as a metric.

    ``metric_parameters``: ``{"pattern_set": {...}, "code": "<code id>"}``.
    The value is the code of the prediction text: 1/0 for ``any`` and
    ``all`` codes, the match count for ``count`` codes, and for a ``first``
    code 1 when a rule matched (its value is in ``details.label``) and 0
    when the default applied. Task literals (``{{task.<path>}}``) read the
    task's data. The reference value is not read: a code needs no ground
    truth. A missing text or an unresolved literal gives no value and says
    why in ``error``; every code of the set is in ``details.codes``.
    """

    name = "text_pattern"
    #: Receive the prediction as stored (no lower-casing or stripping) and
    #: the task data (``task_data=``), see SampleEvaluator.
    wants_raw_values = True
    uses_task_data = True
    reference_free = True

    def __init__(self) -> None:
        self._compiled: Dict[str, Any] = {}

    def _compile(self, doc: Any):
        from analysis.canonical import json_hash
        from analysis.text_patterns import compile_pattern_set

        key = json_hash(doc)
        compiled = self._compiled.get(key)
        if compiled is None:
            if len(self._compiled) > 256:
                self._compiled.clear()
            compiled = compile_pattern_set(doc)
            self._compiled[key] = compiled
        return compiled

    def compute(
        self,
        ground_truth: Any,
        prediction: Any,
        answer_type: str,
        parameters: Optional[Dict[str, Any]] = None,
        task_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        import math

        from analysis.codes import text_of
        from analysis.text_patterns import PatternSetError

        params = parameters or {}
        try:
            compiled = self._compile(params.get("pattern_set"))
        except PatternSetError as exc:
            return {"value": None, "method": self.name, "details": {}, "error": f"invalid pattern set: {exc}"}
        code = params.get("code")
        codes = compiled.normalized["codes"]
        if code not in codes:
            return {
                "value": None,
                "method": self.name,
                "details": {"pattern_set": compiled.describe()},
                "error": f"the pattern set has no code {code!r}",
            }
        text = text_of(prediction)
        values = compiled.codes(text, task_data or {})
        clean = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in values.items()}
        details: Dict[str, Any] = {
            "pattern_set": compiled.describe(),
            "code": code,
            "mode": codes[code]["mode"],
            "codes": clean,
        }
        raw, status = compiled.evaluate(code, text, task_data or {})
        if status == "no_text":
            return {"value": None, "method": self.name, "details": details, "error": "the prediction has no text to code"}
        if status == "unresolved":
            return {
                "value": None,
                "method": self.name,
                "details": details,
                "error": "a task literal of the code does not resolve for this task",
            }
        if codes[code]["mode"] == "first":
            details["label"] = raw
            value = 1.0 if status == "matched" else 0.0
        else:
            value = raw
        return {"value": float(value), "method": self.name, "details": details, "error": None}


# --------------------------------------------------------------------
# Registration entry point
# --------------------------------------------------------------------


# Every platform metric in the legacy if/elif chain. Order doesn't
# matter — registration is a dict insertion. Each name MUST match the
# string the legacy chain dispatches on.
PLATFORM_METRIC_NAMES: list[str] = [
    # Lexical / classification
    "exact_match",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "cohen_kappa",
    "confusion_matrix",
    # Multi-label / set
    "jaccard",
    "hamming_loss",
    "subset_accuracy",
    "token_f1",
    # Regression
    "mae",
    "rmse",
    "mape",
    "r2",
    "correlation",
    # Ranking
    "weighted_kappa",
    "spearman_correlation",
    "kendall_tau",
    "ndcg",
    "map",
    # Lexical text similarity
    "bleu",
    "rouge",
    "edit_distance",
    "meteor",
    "chrf",
    # Factuality
    "factcc",
    # Structured data
    "json_accuracy",
    "schema_validation",
    "field_accuracy",
    # Span / sequence
    "span_exact_match",
    "iou",
    "partial_match",
    "boundary_accuracy",
    # Hierarchical
    "hierarchical_f1",
    "path_accuracy",
    "lca_accuracy",
]


def register_builtin_metric_handlers(registry) -> None:
    """Register every platform metric into the fine-grained MetricRegistry.

    Phase 4 of the academic-rigor overhaul. Called once at module load
    from ``ml_evaluation/__init__.py`` after the registry is instantiated.
    """
    # Provenance-rich handlers (Phase 2 audit trail flows through).
    registry.register(_CoherenceHandler())
    registry.register(_MoverScoreHandler())
    registry.register(_QAGSHandler())
    registry.register(_BERTScoreHandler())
    registry.register(_SemanticSimilarityHandler())
    registry.register(TextPatternHandler())

    # Generic adapters for every other platform metric.
    for name in PLATFORM_METRIC_NAMES:
        registry.register(_LegacyMetricHandler(name))


__all__ = ["register_builtin_metric_handlers", "PLATFORM_METRIC_NAMES"]
