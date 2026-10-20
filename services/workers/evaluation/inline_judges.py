"""Overlay-provided LLM judges that bypass the generic judge parser.

The generic ``LLMJudgeEvaluator`` path needs a parseable score; a judge
whose result is something else (e.g. the extended edition's feedback-only
``llm_judge_feedback``, which returns written feedback and no score) plugs
in here instead. An overlay exposes::

    <package>.workers.get_inline_judge(metric) -> InlineJudge | None

(looked up through ``extension_registry``, gating class gated, so it only
answers while the package is active for the task)

where an ``InlineJudge`` provides

* ``compute(*, ai_service, judge_model, temperature, max_tokens,
  thinking_budget, reasoning_effort, task_data, prediction,
  metric_params) -> dict`` — the judge call. Returns the result dict, or an
  error wrapper ``{"error": True, "error_message": ...}``. A
  ``_judge_prompts_used`` key is moved to the row's audit column.
* ``build_row(*, result, error_message) -> dict`` — the metric-specific
  ``TaskEvaluation`` kwargs (``metrics``, ``passed`` and the discrete
  call-metadata columns).
* ``evaluate_single(**kwargs) -> dict`` — the immediate-evaluation lane:
  same keyword arguments as the Falllösung single-sample helper; persists
  its own row and returns the run-result dict.

The platform owns everything around it: judge construction and key
resolution, the row context (ids, fields, prediction), bulk upsert and the
run counters. ``llm_judge_falloesung`` keeps its older dedicated hooks.
"""

from typing import Any, Dict, Optional


def resolve_inline_judge(metric: str) -> Optional[Any]:
    """The overlay's inline judge for ``metric``, or None (generic path)."""
    if not metric or metric == "llm_judge_falloesung":
        return None
    import extension_registry

    # Through the registry so the judge follows the package's runtime switch
    # (WORKER_ATTR_GATING: gated): while the owning package is off for the
    # task, the metric falls back to the generic path.
    get_inline_judge = extension_registry.first_worker_attr("get_inline_judge")
    if get_inline_judge is None:
        return None
    try:
        return get_inline_judge(metric)
    except Exception:  # pragma: no cover - a broken overlay must not stop grading
        import logging

        logging.getLogger(__name__).exception(
            "inline judge lookup failed for %s", metric
        )
        return None


def inline_judge_row(
    judge: Any,
    *,
    evaluator: Any,
    task_data: Optional[Dict[str, Any]],
    prediction: Any,
    metric_params: Optional[Dict[str, Any]],
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Run ``judge`` with the bulk-cell evaluator's model settings and return
    the full ``TaskEvaluation`` row dict (``row`` carries the context)."""
    result = judge.compute(
        ai_service=evaluator.ai_service,
        judge_model=evaluator.judge_model,
        temperature=evaluator.temperature,
        max_tokens=evaluator.max_tokens,
        thinking_budget=evaluator.thinking_budget,
        reasoning_effort=evaluator.reasoning_effort,
        task_data=task_data or {},
        prediction=str(prediction) if prediction else "",
        metric_params=metric_params or {},
    )
    judge_prompts = result.pop("_judge_prompts_used", None) if result else None
    error_msg = None
    if not result or result.get("error"):
        error_msg = (result or {}).get("error_message") or "LLM judge evaluation failed"
    return {
        **row,
        "error_message": error_msg,
        "judge_prompts_used": judge_prompts,
        **judge.build_row(result=result, error_message=error_msg),
    }
