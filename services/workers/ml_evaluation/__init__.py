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

# Load the extension packages' evaluators and metric handlers. The registry
# (/shared/extension_registry.py, same module the API's extensions.py uses)
# imports every package named in BENGER_EXTENSIONS in order, runs the
# COMPATIBLE_CORE_VERSIONS handshake and the REQUIRES_EXTENSIONS check, and
# raises for a required package that fails (BENGER_REQUIRE_EXTENSIONS, or the
# legacy BENGER_REQUIRE_EXTENDED). Registrations run under the package's
# owner so a replaced evaluator or handler is logged with both names.
import extension_registry as _extension_registry  # noqa: E402

for _ext in _extension_registry.load_all():
    # A package without a workers module is an API-only overlay; an import
    # error inside the module is a broken overlay and propagates.
    _workers = _extension_registry.worker_module(_ext.name, strict=True)
    if _workers is None:
        continue
    with _extension_registry.owner(_ext.name):
        _register_evaluators = getattr(_workers, "register_evaluators", None)
        if _register_evaluators is not None:
            _register_evaluators(evaluator_registry)
        # Extended metric handlers (e.g. the Falllösung LLM judge). A package
        # that predates the hook simply does not export it.
        _register_metric_handlers = getattr(_workers, "register_metric_handlers", None)
        if _register_metric_handlers is not None:
            _register_metric_handlers(metric_registry)

# Master flags ``extension.<EXTENSION_ID>`` of the loaded packages (core
# 2.42): the worker evaluates them per task (extension_activation), so the
# definitions (default state) must exist in this process too.
import extension_activation as _extension_activation  # noqa: E402

_extension_activation.register_master_flags(_extension_registry.loaded())

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
