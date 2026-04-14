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

__all__ = [
    "BaseEvaluator",
    "EvaluationConfig",
    "EvaluationResult",
    "EvaluatorRegistry",
    "evaluator_registry",
    "LLMJudgeEvaluator",
    "create_llm_judge_for_user",
]
