"""Overlay-provided LLM judges that bypass the generic judge parser.

The generic ``LLMJudgeEvaluator`` path needs a parseable score; a judge
whose result is something else (e.g. the extended edition's feedback-only
``llm_judge_feedback``, which returns written feedback and no score) plugs
in here instead. An overlay exposes::

    <package>.workers.get_inline_judge(metric) -> InlineJudge | None

(looked up through ``extension_registry``, gating class gated, so it only
answers while the package is active for the task; while the package that
answers for a metric is off for the task, the cell records the
``feature_disabled`` result instead of running the generic judge, see
:func:`inactive_inline_judge_owner`)

where an ``InlineJudge`` provides

* ``compute(*, ai_service, judge_model, temperature, max_tokens,
  thinking_budget, reasoning_effort, task_data, prediction,
  metric_params) -> dict`` — the judge call. Returns the result dict, or an
  error wrapper ``{"error": True, "error_message": ...}``. A
  ``_judge_prompts_used`` key is moved to the row's audit column, a
  ``_raw_reasoning`` key (the judge model's reasoning text, e.g. the
  service response's ``reasoning``) to the row's ``raw_reasoning`` column.
* ``build_row(*, result, error_message) -> dict`` — the metric-specific
  ``TaskEvaluation`` kwargs (``metrics``, ``passed`` and the discrete
  call-metadata columns).
* ``evaluate_single(**kwargs) -> dict`` — the immediate-evaluation lane:
  same keyword arguments as the Falllösung single-sample helper; persists
  its own row and returns the run-result dict.

A config of a metric registered with
``task_rubric_resolution.register_sheet_judge_metric`` whose
``metric_parameters`` say ``use_task_rubric: true`` (see
``task_rubric_resolution.is_rubric_judge``) is a sheet judge: the platform
resolves the task's usable ``task_rubrics`` row and hands it to ``compute``
and ``evaluate_single`` as ``task_rubric`` (core 2.81). Without a usable
sheet the cell gets the platform's ``rubric_missing`` error row and the judge
is not called; the immediate dispatch holds such a grading until the sheet is
ready. A judge whose functions take no ``task_rubric`` keyword never
receives it.

The platform owns everything around it: judge construction and key
resolution, the row context (ids, fields, prediction), bulk upsert and the
run counters. ``llm_judge_falloesung`` keeps its older dedicated hooks.
"""

import inspect
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


def inactive_inline_judge_owner(metric: str) -> Optional[str]:
    """The package whose inline judge answers for ``metric`` while that
    package is switched off for the task, or None.

    :func:`resolve_inline_judge` returns None both when no package judges the
    metric (it takes the generic judge path) and when the package that does
    is inactive. In the second case the generic path would make a paid judge
    call with a prompt the metric was never meant for and store a junk score;
    the caller records ``feature_disabled_result(owner)`` instead, as the
    registered metric handlers do.
    """
    if not metric or metric == "llm_judge_falloesung":
        return None
    import extension_registry

    for package, get_inline_judge in extension_registry.inactive_worker_attrs(
        "get_inline_judge"
    ):
        try:
            if get_inline_judge(metric) is not None:
                return package
        except Exception:  # pragma: no cover - a broken overlay must not stop grading
            import logging

            logging.getLogger(__name__).exception(
                "inline judge lookup failed for %s", metric
            )
    return None


def feature_disabled_metrics(metric: str, package: str) -> Dict[str, Any]:
    """The ``metrics`` of the row a cell writes for ``metric`` while its
    owning ``package`` is inactive for the task."""
    import extension_activation

    result = extension_activation.feature_disabled_result(package)
    result["method"] = metric
    return {metric: result}


def feature_disabled_row(
    row: Dict[str, Any], metric: str, package: str
) -> Dict[str, Any]:
    """The full ``TaskEvaluation`` row dict of a bulk cell for ``metric``
    while its owning ``package`` is inactive (``row`` carries the context)."""
    import extension_activation

    return {
        **row,
        "metrics": feature_disabled_metrics(metric, package),
        "passed": False,
        "error_message": str(extension_activation.ExtensionInactive(package)),
    }


def accepts_keyword(fn: Any, name: str) -> bool:
    """Whether ``fn`` takes the keyword ``name`` (or ``**kwargs``)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def inline_judge_row(
    judge: Any,
    *,
    evaluator: Any,
    task_data: Optional[Dict[str, Any]],
    prediction: Any,
    metric_params: Optional[Dict[str, Any]],
    row: Dict[str, Any],
    task_rubric: Any = None,
) -> Dict[str, Any]:
    """Run ``judge`` with the bulk-cell evaluator's model settings and return
    the full ``TaskEvaluation`` row dict (``row`` carries the context).
    ``task_rubric`` is the sheet a sheet judge grades along (see the module
    doc); it reaches ``compute`` only when ``compute`` takes it."""
    extra: Dict[str, Any] = {}
    if task_rubric is not None and accepts_keyword(judge.compute, "task_rubric"):
        extra["task_rubric"] = task_rubric
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
        **extra,
    )
    judge_prompts = result.pop("_judge_prompts_used", None) if result else None
    import tasks

    judge_reasoning = tasks._pop_judge_reasoning(result)
    error_msg = None
    if not result or result.get("error"):
        error_msg = (result or {}).get("error_message") or "LLM judge evaluation failed"
    return {
        **row,
        "error_message": error_msg,
        "judge_prompts_used": judge_prompts,
        "raw_reasoning": judge_reasoning,
        **judge.build_row(result=result, error_message=error_msg),
    }
