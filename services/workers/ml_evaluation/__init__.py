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

# Load extended evaluators if available. The handshake constant comes from
# /shared/core_version.py (single source of truth, same module the API's
# extensions.py imports — /shared is on sys.path in the worker container and
# in workers/tests/conftest.py).
from core_version import CORE_API_VERSION as _CORE_API_VERSION  # noqa: E402
from core_version import extended_required as _extended_required  # noqa: E402

try:
    import benger_extended

    _compatible = True
    if hasattr(benger_extended, "COMPATIBLE_CORE_VERSIONS"):
        if _CORE_API_VERSION not in benger_extended.COMPATIBLE_CORE_VERSIONS:
            import logging

            _msg = (
                "Extended package incompatible with workers "
                f"(needs {benger_extended.COMPATIBLE_CORE_VERSIONS}, "
                f"core is {_CORE_API_VERSION})"
            )
            if _extended_required():
                raise RuntimeError(
                    f"{_msg}. BENGER_REQUIRE_EXTENDED is set — refusing to "
                    "start with extended evaluators disabled."
                )
            logging.getLogger(__name__).warning(_msg)
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
except ImportError as _ext_import_error:
    if _extended_required():
        raise RuntimeError(
            "BENGER_REQUIRE_EXTENDED is set but the benger_extended package "
            f"failed to import in the worker: {_ext_import_error}. Refusing "
            "to start as community edition."
        ) from _ext_import_error

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
