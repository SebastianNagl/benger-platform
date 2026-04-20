"""
ML Evaluation Module for BenGER

This module provides ML model evaluation via the SampleEvaluator (deterministic metrics)
and LLMJudgeEvaluator (LLM-as-Judge assessment).

Issue #483: Added LLM-as-Judge evaluator for research-grade assessment
"""

from .base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult
from .llm_judge_evaluator import LLMJudgeEvaluator, create_llm_judge_for_user
from .registry import EvaluatorRegistry

# Global registry instance
evaluator_registry = EvaluatorRegistry()

# Register LLM-as-Judge evaluator
evaluator_registry.register("llm_judge", LLMJudgeEvaluator)

# Load extended evaluators if available
_CORE_API_VERSION = "1.0"  # Must match extensions.py CORE_API_VERSION

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
]
