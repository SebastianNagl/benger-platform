"""
Shared serialization functions for export paths.

Both the data export (GET /export, POST /tasks/bulk-export) and the full project
export (POST /bulk-export-full) use these functions to serialize ORM objects to dicts.

The `mode` parameter controls which fields are included:
- "data": Denormalized convenience fields for analysis (evaluated_model, judge_model,
  nested questionnaire_response). Used by data export endpoints.
- "full": Raw FK columns for flat re-import (task_id, project_id, generation_id,
  evaluation_id). Used by full project export/import.
"""

from typing import Any, Dict, List, Optional, Tuple


def _isoformat(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def serialize_task(task, *, mode: str = "data", total_generations: int = 0) -> dict:
    d = {
        "id": task.id,
        "inner_id": task.inner_id,
        "data": task.data,
        "meta": task.meta,
        "is_labeled": task.is_labeled,
        "created_at": _isoformat(task.created_at),
        "updated_at": _isoformat(task.updated_at),
    }
    if mode == "full":
        d.update({
            "project_id": task.project_id,
            "created_by": task.created_by,
            "updated_by": task.updated_by,
            "total_annotations": task.total_annotations,
            "cancelled_annotations": task.cancelled_annotations,
            "total_generations": total_generations,
            "comment_count": task.comment_count,
            "unresolved_comment_count": task.unresolved_comment_count,
            "last_comment_updated_at": _isoformat(task.last_comment_updated_at),
            "comment_authors": task.comment_authors,
            "file_upload_id": task.file_upload_id,
        })
    return d


def serialize_annotation(
    ann, *, mode: str = "data", questionnaire_response=None
) -> dict:
    d = {
        "id": ann.id,
        "result": ann.result,
        "completed_by": ann.completed_by,
        "created_at": _isoformat(ann.created_at),
        "updated_at": _isoformat(ann.updated_at),
        "was_cancelled": ann.was_cancelled,
        "ground_truth": ann.ground_truth,
        "lead_time": ann.lead_time,
        "active_duration_ms": ann.active_duration_ms,
        "focused_duration_ms": ann.focused_duration_ms,
        "tab_switches": ann.tab_switches,
    }
    if mode == "data":
        qr = questionnaire_response
        d["questionnaire_response"] = {
            "result": qr.result,
            "created_at": _isoformat(qr.created_at),
        } if qr else None
    elif mode == "full":
        d.update({
            "task_id": ann.task_id,
            "project_id": ann.project_id,
            "draft": ann.draft,
            "prediction_scores": ann.prediction_scores,
        })
    return d


def serialize_generation(
    gen, *, mode: str = "data", evaluations: Optional[List[dict]] = None
) -> dict:
    d = {
        "id": gen.id,
        "model_id": gen.model_id,
        "response_content": gen.response_content,
        "case_data": gen.case_data,
        "created_at": _isoformat(gen.created_at),
        "response_metadata": gen.response_metadata,
    }
    if mode == "data":
        d["evaluations"] = evaluations if evaluations is not None else []
    elif mode == "full":
        d.update({
            "generation_id": gen.generation_id,
            "task_id": gen.task_id,
            "usage_stats": gen.usage_stats,
            "status": gen.status,
            "error_message": gen.error_message,
        })
    return d


def serialize_task_evaluation(
    te,
    *,
    mode: str = "data",
    eval_run=None,
    judge_model_lookup: Optional[dict] = None,
) -> dict:
    d = {
        "id": te.id,
        "annotation_id": te.annotation_id,
        "field_name": te.field_name,
        "answer_type": te.answer_type,
        "ground_truth": te.ground_truth,
        "prediction": te.prediction,
        "metrics": te.metrics,
        "passed": te.passed,
        "confidence_score": te.confidence_score,
        "error_message": te.error_message,
        "processing_time_ms": te.processing_time_ms,
        "created_at": _isoformat(te.created_at),
    }
    if mode == "data":
        config_id = (
            te.field_name.split("|")[0]
            if te.field_name and "|" in te.field_name
            else te.field_name.split(":")[0]  # Backward compat
            if te.field_name and ":" in te.field_name
            else None
        )
        d.update({
            "evaluation_run_id": te.evaluation_id,
            "evaluated_model": eval_run.model_id if eval_run else None,
            "judge_model": (
                judge_model_lookup.get((te.evaluation_id, config_id))
                if judge_model_lookup and config_id
                else None
            ),
        })
    elif mode == "full":
        d.update({
            "evaluation_id": te.evaluation_id,
            "task_id": te.task_id,
            "generation_id": te.generation_id,
        })
    return d


def serialize_evaluation_run(er, *, mode: str = "data") -> dict:
    d = {
        "id": er.id,
        "model_id": er.model_id,
        "evaluation_type_ids": er.evaluation_type_ids,
        "metrics": er.metrics,
        "status": er.status,
        "samples_evaluated": er.samples_evaluated,
        "created_at": _isoformat(er.created_at),
        "completed_at": _isoformat(er.completed_at),
    }
    if mode == "data":
        d.update({
            "eval_metadata": er.eval_metadata,
            "error_message": er.error_message,
            "has_sample_results": er.has_sample_results,
            "created_by": er.created_by,
        })
    elif mode == "full":
        d.update({
            "project_id": er.project_id,
            "task_id": er.task_id,
            "eval_metadata": er.eval_metadata,
            "error_message": er.error_message,
            "created_by": er.created_by,
        })
    return d


def build_judge_model_lookup(evaluation_runs) -> Dict[Tuple[str, str], str]:
    """Build lookup: (evaluation_run_id, config_id) -> judge_model.

    Checks both new format (eval_metadata.judge_models) and old format
    (evaluation_configs[].metric_parameters.judge_model).
    """
    lookup: Dict[Tuple[str, str], str] = {}
    for er in evaluation_runs:
        meta = er.eval_metadata or {}
        # New format: top-level judge_models dict (set by worker on completion)
        if "judge_models" in meta:
            for config_id, model in meta["judge_models"].items():
                lookup[(er.id, config_id)] = model
        # Old format: dig into evaluation_configs
        for cfg in meta.get("evaluation_configs", []):
            cid = cfg.get("id", "")
            jm = (cfg.get("metric_parameters") or {}).get("judge_model")
            if jm and (er.id, cid) not in lookup:
                lookup[(er.id, cid)] = jm
    return lookup


def build_evaluation_indexes(
    task_evaluations,
) -> Tuple[Dict[str, list], Dict[str, list]]:
    """Build lookup dicts for evaluation nesting.

    Returns (te_by_task, te_by_generation) where:
    - te_by_task: task_id -> list of TaskEvaluation records
    - te_by_generation: generation_id -> list of TaskEvaluation records (only those with generation_id)
    """
    te_by_task: Dict[str, list] = {}
    te_by_generation: Dict[str, list] = {}
    for te in task_evaluations:
        te_by_task.setdefault(te.task_id, []).append(te)
        if te.generation_id is not None:
            te_by_generation.setdefault(te.generation_id, []).append(te)
    return te_by_task, te_by_generation
