"""Single-sample LLM-judge evaluation implementation (worker).

Extracted from ``services/workers/tasks.py`` as part of the structural
decomposition of that module. Behavior-preserving move: the function bodies
are byte-identical to the originals, except that references to ``tasks``-module
globals (``SessionLocal``, ``logger``, monkeypatched helpers, etc.) are
resolved through the ``tasks`` module at call time so that test monkeypatches
like ``patch("tasks.SessionLocal")`` continue to apply.

The public, decorated Celery task wrappers (with their original names, task
names, and decorator args) remain in ``tasks.py`` and delegate here.
"""

import tasks
from typing import Any, Dict, Optional

def _evaluate_llm_judge_single_impl(
    db, record_id, immediate_eval_id, project_id, task_id,
    annotation_id, user_id, field_name, metric_type, prediction,
    reference, metric_params, organization_id,
    judge_run_id: Optional[str] = None,
    evaluation_config_id: Optional[str] = None,
):
    """Run generic LLM judge evaluation for a single sample.

    Args:
        judge_run_id: EvaluationJudgeRun id this row belongs to (migration 042).
            Optional for backwards compatibility with any caller that hasn't
            been updated; passing None leaves the column NULL until the
            judge_run_id NOT NULL migration lands.
        evaluation_config_id: Issue #111 / migration 057 — the evaluation
            config id this row belongs to, persisted discretely so
            downstream readers don't parse ``field_name``. Optional for
            backward compatibility; older callers leave it NULL.
    """
    from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user
    from models import TaskEvaluation

    params = metric_params or {}
    judge_model = params.get("judge_model", "gpt-4o")
    provider = tasks._get_provider_from_model(judge_model)

    # Tiered parameter resolution for the judge call (mode='evaluation').
    # Same precedence as generation but with metric_parameters as the
    # user_per_model tier. Catalog `recommended_parameters` becomes the
    # third tier so a judge call honors provider-recommended defaults
    # whenever metric_parameters doesn't pin a value.
    judge_model_obj = (
        db.query(tasks.DBLLMModel).filter(tasks.DBLLMModel.id == judge_model).first()
    )
    judge_recommended = (
        getattr(judge_model_obj, "recommended_parameters", None) or None
    )

    def _resolve_judge(key: str, fallback_default: Any = None):
        value, _source, _rec = tasks._resolve_param(
            key=key,
            mode="evaluation",
            model_recommended=judge_recommended,
            project_cfg=None,
            per_model_cfg=params,
        )
        return value if value is not None else fallback_default

    # Apply per-model temperature constraint (e.g. Opus 4.7 → 1.0, GPT-5
    # → 1.0, DeepSeek-R1 min 0.6). Mirror of the generation-side clamp.
    judge_constraints = (
        getattr(judge_model_obj, "parameter_constraints", None) or None
    )
    _judge_temp, _ = tasks._clamp_temperature_to_constraint(
        _resolve_judge("temperature", 0.0), judge_constraints
    )

    llm_judge = create_llm_judge_for_user(
        db=db,
        user_id=user_id,
        provider=provider,
        judge_model=judge_model,
        temperature=_judge_temp,
        max_tokens=_resolve_judge("max_tokens", 500),
        criteria=params.get("dimensions"),
        custom_criteria=params.get("custom_criteria"),
        custom_prompt_template=params.get("custom_prompt_template"),
        answer_type=params.get("answer_type"),
        field_mappings=params.get("field_mappings"),
        score_scale=params.get("score_scale", "1-5"),
        organization_id=organization_id,
        seed=_resolve_judge("seed", 42),
    )

    if not llm_judge.ai_service:
        raise RuntimeError(f"No AI service available for LLM judge ({provider})")

    # Multi-dim single-call mode: when custom_criteria carries max_score on
    # any dimension, the user's prompt is expected to score every dimension
    # in one LLM call (Grundprinzipien-style 4-dim rubric). Skip the
    # per-criterion fan-out and persist per-dim scores under
    # metrics[<metric>].details.scores.
    if llm_judge.is_multidim_mode():
        from project_models import Task as ProjectTask, Annotation
        from annotation_utils import extract_all_field_values
        task_row = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
        task_data = (task_row.data if task_row else {}) or {}

        # Flatten the model/annotation output so the prompt can reference
        # individual fields by name (e.g. {{kurzantwort}}, {{begruendung}})
        # without forcing the user to write field_mappings for every one.
        # Branches by whichever target the eval is grading.
        field_outputs: Dict[str, Any] = {}
        if annotation_id:
            ann_row = db.query(Annotation).filter(Annotation.id == annotation_id).first()
            if ann_row and ann_row.result:
                field_outputs = extract_all_field_values(ann_row.result)
        # Generation case: parsed_annotation lives on the generation row
        # already in label-studio shape, so the same flattener works.
        gen_id_from_meta = (metric_params or {}).get("generation_id")
        if not field_outputs and gen_id_from_meta:
            gen_row = db.query(tasks.DBLLMResponse).filter(tasks.DBLLMResponse.id == gen_id_from_meta).first()
            parsed = getattr(gen_row, "parsed_annotation", None) if gen_row else None
            if parsed:
                field_outputs = extract_all_field_values(parsed)

        multidim = llm_judge._evaluate_multidim_single_call(
            context="",
            ground_truth=reference,
            prediction=prediction,
            task_data=task_data,
            field_outputs=field_outputs,
        )
        if multidim is None or multidim.get("error") or "scores" not in multidim:
            err_msg = (
                (multidim or {}).get("error_message") or "multi-dim LLM judge produced no scores"
            )
            raise RuntimeError(err_msg)

        total = float(multidim.get("total_score") or 0.0)
        total_max = float(multidim.get("total_max") or 0.0)
        normalized = total / total_max if total_max > 0 else 0.0
        eval_record = TaskEvaluation(
            id=record_id,
            evaluation_id=immediate_eval_id,
            judge_run_id=judge_run_id,
            task_id=task_id,
            annotation_id=annotation_id,
            generation_id=None,
            field_name=field_name,
            # Issue #111 / migration 057: discrete carrier of the config id.
            evaluation_config_id=evaluation_config_id,
            answer_type="text",
            ground_truth=reference,
            prediction=prediction,
            metrics={
                metric_type: {
                    "value": float(normalized),
                    "method": metric_type,
                    "details": {
                        "scores": multidim["scores"],
                        "total_score": total,
                        "total_max": total_max,
                        "overall_assessment": multidim.get("overall_assessment", ""),
                        "call_metadata": multidim.get("_call_metadata", {}),
                        "raw_output": multidim.get("_raw_output", ""),
                    },
                    "error": None,
                },
                "raw_score": float(normalized),
            },
            judge_prompts_used=multidim.get("_judge_prompts_used"),
            passed=float(normalized) >= 0.5,
        )
        db.add(eval_record)
        db.commit()
        return {
            "status": "completed",
            "record_id": record_id,
            "metric": metric_type,
            "score": float(normalized),
            "total_score": total,
            "total_max": total_max,
        }

    # Derive the per-criterion key from the metric name. `llm_judge_helpfulness`
    # → criterion `helpfulness`. `llm_judge_classic` / `llm_judge_custom`
    # don't carry a single criterion in the name; fall back to the first
    # configured criterion on the evaluator.
    criterion = (
        metric_type.replace("llm_judge_", "")
        if metric_type.startswith("llm_judge_") and metric_type != "llm_judge_classic"
        and metric_type != "llm_judge_custom"
        else (llm_judge.criteria[0] if llm_judge.criteria else "helpfulness")
    )

    # Use the per-criterion path directly: this is the same call evaluate()
    # makes internally per (sample, criterion). The previous code called
    # llm_judge.evaluate_single(...) which never existed on LLMJudgeEvaluator
    # and would crash any non-Falllösung llm_judge metric in immediate-eval.
    raw = llm_judge._evaluate_single_criterion(
        context="",
        ground_truth=reference,
        prediction=prediction,
        criterion=criterion,
        task_data={},
    )
    if raw is None or raw.get("error") or "score" not in raw:
        err_msg = (
            (raw or {}).get("error_message") or f"LLM judge produced no score for {criterion}"
        )
        raise RuntimeError(err_msg)

    raw_score = float(raw["score"])
    # Normalize to 0..1 the same way evaluate() does for the bulk path.
    score = raw_score if llm_judge.score_scale == "0-1" else (raw_score - 1) / 4
    eval_record = TaskEvaluation(
        id=record_id,
        evaluation_id=immediate_eval_id,
        judge_run_id=judge_run_id,
        task_id=task_id,
        annotation_id=annotation_id,
        generation_id=None,
        field_name=field_name,
        # Issue #111 / migration 057: discrete carrier of the config id.
        evaluation_config_id=evaluation_config_id,
        answer_type="text",
        ground_truth=reference,
        prediction=prediction,
        metrics={
            metric_type: float(score),
            f"{metric_type}_details": raw,
            "raw_score": float(score),
        },
        passed=float(score) >= 0.5,
    )
    db.add(eval_record)
    db.commit()

    return {
        "status": "completed",
        "record_id": record_id,
        "metric": metric_type,
        "score": float(score),
    }
