"""
ML Evaluation Module for BenGER

This module provides ML model evaluation via the SampleEvaluator (deterministic metrics)
and LLMJudgeEvaluator (LLM-as-Judge assessment).

Issue #483: Added LLM-as-Judge evaluator for research-grade assessment
"""

from .base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult
from .handlers import MetricHandler, MetricRegistry, extract_value
from .llm_judge_evaluator import LLMJudgeEvaluator, create_llm_judge_for_user
from .registry import EvaluatorRegistry

# Coarse-grained registry: task-type -> evaluator class. Pre-existing.
evaluator_registry = EvaluatorRegistry()
evaluator_registry.register("llm_judge", LLMJudgeEvaluator)

# Fine-grained registry: metric name -> handler instance. Introduced in
# Phase 1 of the academic-rigor plan. Phase 4 migrates the legacy if/elif
# branches into handlers; Phase 5 lets the extended package register
# Falllösung-style metrics through `register_metric_handlers`.
metric_registry = MetricRegistry()

# Phase 4: register every platform metric as a class-based handler so
# dispatch goes through the registry. Provenance-rich helpers from
# Phase 2 (coherence/MoverScore/QAGS/BERTScore/semantic-similarity)
# are registered with their dedicated handlers; the rest use a thin
# adapter that wraps the existing _compute_* compute paths.
from .builtin_handlers import register_builtin_metric_handlers  # noqa: E402

register_builtin_metric_handlers(metric_registry)

# Load extended evaluators if available
_CORE_API_VERSION = "2.1"  # Must match extensions.py CORE_API_VERSION

try:
    import benger_extended

    _compatible = True
    if hasattr(benger_extended, "COMPATIBLE_CORE_VERSIONS"):
        if _CORE_API_VERSION not in benger_extended.COMPATIBLE_CORE_VERSIONS:
            import logging

            logging.getLogger(__name__).warning(
                f"Extended package incompatible with workers "
                f"(needs {benger_extended.COMPATIBLE_CORE_VERSIONS}, "
                f"core is {_CORE_API_VERSION})"
            )
            _compatible = False

    if _compatible:
        from benger_extended.workers import register_evaluators

        register_evaluators(evaluator_registry)

        # Phase 5 hook: extended metric handlers (e.g. Falllösung LLM judge).
        # Importing inside the version-checked block so a community-edition
        # install (no benger_extended) is a clean no-op via the outer except.
        try:
            from benger_extended.workers import register_metric_handlers

            register_metric_handlers(metric_registry)
        except ImportError:
            # Extended package present but does not yet export the new hook
            # (older extended version that predates Phase 5). Treat as a
            # legitimate no-op rather than an error — the platform-side
            # registry just stays unpopulated for extended metrics.
            pass
except ImportError:
    pass

__all__ = [
    "BaseEvaluator",
    "EvaluationConfig",
    "EvaluationResult",
    "EvaluatorRegistry",
    "evaluator_registry",
    "LLMJudgeEvaluator",
    "create_llm_judge_for_user",
    # Phase 1 additions: fine-grained metric registry
    "MetricHandler",
    "MetricRegistry",
    "metric_registry",
    "extract_value",
]
