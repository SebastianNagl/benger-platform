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

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _isoformat(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_iso(value: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parse for re-import. Returns None on falsy/invalid input."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Python's fromisoformat handles "...+00:00"; trim trailing "Z" first.
            return datetime.fromisoformat(value.rstrip("Z"))
        except ValueError:
            return None
    return None


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
        "auto_submitted": ann.auto_submitted,
        "instruction_variant": ann.instruction_variant,
        "ai_assisted": ann.ai_assisted,
        "reviewed_by": ann.reviewed_by,
        "reviewed_at": _isoformat(ann.reviewed_at),
        "review_result": ann.review_result,
        "review_annotation": ann.review_annotation,
        "review_comment": ann.review_comment,
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
            "parse_status": gen.parse_status,
            "parse_error": gen.parse_error,
            "parsed_annotation": gen.parsed_annotation,
            "parse_metadata": gen.parse_metadata,
            "label_config_version": gen.label_config_version,
            "label_config_snapshot": gen.label_config_snapshot,
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
        "judge_prompts_used": te.judge_prompts_used,
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


def serialize_korrektur_comment(comment) -> dict:
    """Full export shape for KorrekturComment — used by both export sites."""
    return {
        "id": comment.id,
        "project_id": comment.project_id,
        "task_id": comment.task_id,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
        "parent_id": comment.parent_id,
        "text": comment.text,
        "highlight_start": comment.highlight_start,
        "highlight_end": comment.highlight_end,
        "highlight_text": comment.highlight_text,
        "highlight_label": comment.highlight_label,
        "is_resolved": comment.is_resolved,
        "resolved_at": _isoformat(comment.resolved_at),
        "resolved_by": comment.resolved_by,
        "created_by": comment.created_by,
        "created_at": _isoformat(comment.created_at),
        "updated_at": _isoformat(comment.updated_at),
    }


def serialize_human_evaluation_data(db, project_id: str, task_ids: List[str]) -> Dict[str, list]:
    """Bundle of human-evaluation tables for a project.

    Returns dict with keys: human_evaluation_configs, human_evaluation_sessions,
    human_evaluation_results, preference_rankings, likert_scale_evaluations.

    Used by both `GET /{project_id}/export` (data path) and
    `get_comprehensive_project_data` (clone path).
    """
    from models import (
        HumanEvaluationConfig,
        HumanEvaluationResult,
        HumanEvaluationSession,
        LikertScaleEvaluation,
        PreferenceRanking,
    )

    configs_data: List[dict] = []
    if task_ids:
        configs = (
            db.query(HumanEvaluationConfig)
            .filter(HumanEvaluationConfig.task_id.in_(task_ids))
            .all()
        )
        for c in configs:
            configs_data.append({
                "id": c.id,
                "task_id": c.task_id,
                "evaluation_project_id": c.evaluation_project_id,
                "evaluator_count": c.evaluator_count,
                "randomization_seed": c.randomization_seed,
                "blinding_enabled": c.blinding_enabled,
                "include_human_responses": c.include_human_responses,
                "status": c.status,
                "created_at": _isoformat(c.created_at),
                "updated_at": _isoformat(c.updated_at),
            })

    sessions = (
        db.query(HumanEvaluationSession)
        .filter(HumanEvaluationSession.project_id == project_id)
        .all()
    )
    sessions_data = [{
        "id": s.id,
        "project_id": s.project_id,
        "evaluator_id": s.evaluator_id,
        "session_type": s.session_type,
        "items_evaluated": s.items_evaluated,
        "total_items": s.total_items,
        "status": s.status,
        "session_config": s.session_config,
        "created_at": _isoformat(s.created_at),
        "updated_at": _isoformat(s.updated_at),
        "completed_at": _isoformat(s.completed_at),
    } for s in sessions]

    config_ids = [c["id"] for c in configs_data]
    results_data: List[dict] = []
    if config_ids:
        results = (
            db.query(HumanEvaluationResult)
            .filter(HumanEvaluationResult.config_id.in_(config_ids))
            .all()
        )
        for r in results:
            results_data.append({
                "id": r.id,
                "config_id": r.config_id,
                "task_id": r.task_id,
                "response_id": r.response_id,
                "evaluator_id": r.evaluator_id,
                "correctness_score": r.correctness_score,
                "completeness_score": r.completeness_score,
                "style_score": r.style_score,
                "usability_score": r.usability_score,
                "comments": r.comments,
                "evaluation_time_seconds": r.evaluation_time_seconds,
                "created_at": _isoformat(r.created_at),
            })

    session_ids = [s["id"] for s in sessions_data]
    rankings_data: List[dict] = []
    likert_data: List[dict] = []
    if session_ids:
        rankings = (
            db.query(PreferenceRanking)
            .filter(PreferenceRanking.session_id.in_(session_ids))
            .all()
        )
        for r in rankings:
            rankings_data.append({
                "id": r.id,
                "session_id": r.session_id,
                "task_id": r.task_id,
                "response_a_id": r.response_a_id,
                "response_b_id": r.response_b_id,
                "winner": r.winner,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "time_spent_seconds": r.time_spent_seconds,
                "created_at": _isoformat(r.created_at),
            })

        likerts = (
            db.query(LikertScaleEvaluation)
            .filter(LikertScaleEvaluation.session_id.in_(session_ids))
            .all()
        )
        for l in likerts:
            likert_data.append({
                "id": l.id,
                "session_id": l.session_id,
                "task_id": l.task_id,
                "response_id": l.response_id,
                "dimension": l.dimension,
                "rating": l.rating,
                "comment": l.comment,
                "time_spent_seconds": l.time_spent_seconds,
                "created_at": _isoformat(l.created_at),
            })

    return {
        "human_evaluation_configs": configs_data,
        "human_evaluation_sessions": sessions_data,
        "human_evaluation_results": results_data,
        "preference_rankings": rankings_data,
        "likert_scale_evaluations": likert_data,
    }
