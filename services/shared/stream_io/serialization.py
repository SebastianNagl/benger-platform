"""Row -> dict serializers shared by the comprehensive export drivers.

``export_stream.py`` had two comprehensive generators —
``stream_comprehensive_project_data_json`` (one nested JSON document) and
``stream_export_ndjson`` (one typed record per line) — that emitted the *same*
per-row dict shapes via copy-pasted inline literals. Every helper here is one of
those literals, extracted verbatim so the two generators (and any importer that
round-trips them) keep byte-identical field names, ordering, and defaults.

Scope note (what is and isn't here):

- The entity types with a real serializer in ``serializers.py``
  (``serialize_task`` / ``serialize_annotation`` / ``serialize_generation`` /
  ``serialize_task_evaluation`` / ``serialize_evaluation_run`` /
  ``serialize_korrektur_comment``) are NOT duplicated here — both generators
  already call those shared functions. This module only covers the rows that
  were still being hand-built inline in BOTH generators.
- The DICT -> ORM *decode* side (the importer's ``_insert_<entity>`` helpers)
  is deliberately NOT merged in. The encode dicts here and the decode helpers in
  ``import_stream.py`` are not symmetric: the importer remaps every FK through
  old->new id maps, applies different per-field defaults (e.g. likert ``rating``
  defaults to 0 on the nested path but 3 on the full path), and skips rows whose
  parents weren't imported. Folding encode+decode into one round-trip helper
  would have to encode those import-only policies, so the decode side stays put.
- The Label-Studio export object and the per-task JSON/CSV export object are
  built in their own generators and were NOT duplicated, so they stay in
  ``export_stream.py``.
"""


def _iso(dt):
    """``datetime -> isoformat`` or ``None`` — the exact inline idiom the
    generators used (``x.isoformat() if x else None``)."""
    return dt.isoformat() if dt else None


# Zero-initialized statistics counter, identical in both comprehensive
# generators. A fresh dict is returned per call so callers can mutate freely.
def empty_export_stats() -> dict:
    return {
        "total_tasks": 0,
        "total_annotations": 0,
        "total_generations": 0,
        "total_evaluations": 0,
        "total_evaluation_metrics": 0,
        "total_evaluation_judge_runs": 0,
        "total_task_evaluations": 0,
        "total_human_evaluation_configs": 0,
        "total_human_evaluation_sessions": 0,
        "total_human_evaluation_results": 0,
        "total_preference_rankings": 0,
        "total_likert_scale_evaluations": 0,
        "total_members": 0,
        "total_assignments": 0,
        "total_post_annotation_responses": 0,
    }


def build_project_export_data(project, organization_id) -> dict:
    """The top-level ``project`` payload, identical in both comprehensive
    generators (37 fields). ``organization_id`` is resolved by the caller from
    ``ProjectOrganization`` (left to the caller because the lookup query differs
    in trivial ways and is cheap)."""
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "label_config": project.label_config,
        "expert_instruction": project.expert_instruction,
        "show_instruction": project.show_instruction,
        "show_skip_button": project.show_skip_button,
        "enable_empty_annotation": project.enable_empty_annotation,
        "created_by": project.created_by,
        "organization_id": organization_id,
        "min_annotations_per_task": project.min_annotations_per_task,
        "is_published": project.is_published,
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
        "generation_config": project.generation_config,
        "evaluation_config": project.evaluation_config,
        "label_config_version": project.label_config_version,
        "label_config_history": project.label_config_history,
        "maximum_annotations": project.maximum_annotations,
        "assignment_mode": project.assignment_mode,
        "show_submit_button": project.show_submit_button,
        "require_comment_on_skip": project.require_comment_on_skip,
        "require_confirm_before_submit": project.require_confirm_before_submit,
        "is_archived": project.is_archived,
        "questionnaire_enabled": project.questionnaire_enabled,
        "questionnaire_config": project.questionnaire_config,
        "randomize_task_order": project.randomize_task_order,
        "instructions_always_visible": project.instructions_always_visible,
        "conditional_instructions": project.conditional_instructions,
        "review_enabled": project.review_enabled,
        "review_mode": project.review_mode,
        "allow_self_review": project.allow_self_review,
        "korrektur_enabled": project.korrektur_enabled,
        "korrektur_config": project.korrektur_config,
        # Timed access window (nullable timestamps) — survive export/import.
        "window_start_at": _iso(project.window_start_at),
        "window_end_at": _iso(project.window_end_at),
    }


def serialize_response_generation_row(rg) -> dict:
    return {
        "id": rg.id,
        "task_id": rg.task_id,
        "model_id": rg.model_id,
        "config_id": rg.config_id,
        "status": rg.status,
        "responses_generated": rg.responses_generated,
        "error_message": rg.error_message,
        "generation_metadata": rg.generation_metadata,
        "created_by": rg.created_by,
        "created_at": _iso(rg.created_at),
        "started_at": _iso(rg.started_at),
        "completed_at": _iso(rg.completed_at),
    }


def serialize_project_member_row(member) -> dict:
    return {
        "id": member.id,
        "project_id": member.project_id,
        "user_id": member.user_id,
        "role": member.role,
        "is_active": member.is_active,
        "created_at": _iso(member.created_at),
        "updated_at": _iso(member.updated_at),
    }


def serialize_task_assignment_row(a) -> dict:
    return {
        "id": a.id,
        "task_id": a.task_id,
        "user_id": a.user_id,
        "assigned_by": a.assigned_by,
        "status": a.status,
        "priority": a.priority,
        "due_date": _iso(a.due_date),
        "notes": a.notes,
        "assigned_at": _iso(a.assigned_at),
        "started_at": _iso(a.started_at),
        "completed_at": _iso(a.completed_at),
    }


def serialize_evaluation_metric_row(m) -> dict:
    return {
        "id": m.id,
        "evaluation_id": m.evaluation_id,
        "evaluation_type_id": m.evaluation_type_id,
        "value": m.value,
        "created_at": _iso(m.created_at),
    }


def serialize_evaluation_judge_run_row(jr) -> dict:
    return {
        "id": jr.id,
        "evaluation_id": jr.evaluation_id,
        "judge_model_id": jr.judge_model_id,
        "run_index": jr.run_index,
        "status": jr.status,
        "samples_evaluated": jr.samples_evaluated,
        "error_message": jr.error_message,
        "metric_parameters_snapshot": jr.metric_parameters_snapshot,
    }


def serialize_human_evaluation_config_row(c) -> dict:
    return {
        "id": c.id,
        "task_id": c.task_id,
        "evaluation_project_id": c.evaluation_project_id,
        "evaluator_count": c.evaluator_count,
        "randomization_seed": c.randomization_seed,
        "blinding_enabled": c.blinding_enabled,
        "include_human_responses": c.include_human_responses,
        "status": c.status,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def serialize_human_evaluation_session_row(s) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "evaluator_id": s.evaluator_id,
        "session_type": s.session_type,
        "items_evaluated": s.items_evaluated,
        "total_items": s.total_items,
        "status": s.status,
        "session_config": s.session_config,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
        "completed_at": _iso(s.completed_at),
    }


def serialize_human_evaluation_result_row(r) -> dict:
    return {
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
        "created_at": _iso(r.created_at),
    }


def serialize_preference_ranking_row(p) -> dict:
    return {
        "id": p.id,
        "session_id": p.session_id,
        "task_id": p.task_id,
        "response_a_id": p.response_a_id,
        "response_b_id": p.response_b_id,
        "winner": p.winner,
        "confidence": p.confidence,
        "reasoning": p.reasoning,
        "time_spent_seconds": p.time_spent_seconds,
        "created_at": _iso(p.created_at),
    }


def serialize_likert_scale_evaluation_row(lk) -> dict:
    return {
        "id": lk.id,
        "session_id": lk.session_id,
        "task_id": lk.task_id,
        "response_id": lk.response_id,
        "dimension": lk.dimension,
        "rating": lk.rating,
        "comment": lk.comment,
        "time_spent_seconds": lk.time_spent_seconds,
        "created_at": _iso(lk.created_at),
    }


def serialize_post_annotation_response_row(r) -> dict:
    return {
        "id": r.id,
        "annotation_id": r.annotation_id,
        "task_id": r.task_id,
        "project_id": r.project_id,
        "user_id": r.user_id,
        "result": r.result,
        "created_at": _iso(r.created_at),
    }


def serialize_user_row(u) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "name": u.name,
        "is_active": u.is_active,
        "is_superadmin": u.is_superadmin,
    }
