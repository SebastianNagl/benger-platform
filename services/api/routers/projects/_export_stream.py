"""Shared streaming helpers for project JSON exports.

Used by both `GET /api/projects/{project_id}/export?format=json` and
`POST /api/projects/{project_id}/tasks/bulk-export?format=json`. Past
revisions of the GET handler loaded the entire project (tasks, annotations,
generations, task_evaluations, korrektur_comments, human-eval blocks) into
one nested Python dict and then `json.dumps(..., indent=2)`-ed it — that
peaked at ~3x the row-set's RAM and OOMKilled the API pod on 2026-05-31
when the Benchathon project (~8k task_evaluations / 400 MB of JSON) was
exported.

The generator below streams the same JSON tree out chunk-by-chunk and uses
`yield_per` + batched IN-queries so peak memory stays bounded by
BATCH_SIZE regardless of project size. The existing
POST /tasks/bulk-export already used this pattern (commits 7c61a79,
0ae2be0); this module extracts it so the single-project GET can share it
without duplicating the row-fetching, batching, and JSON-splicing logic.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Iterable, Iterator, Optional

from sqlalchemy.orm import Session

from models import (
    EvaluationRun,
    EvaluationRunMetric,
    Generation,
    HumanEvaluationConfig,
    HumanEvaluationResult,
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import (
    Annotation,
    KorrekturComment,
    PostAnnotationResponse,
    Project,
    ProjectMember,
    ProjectOrganization,
    Task,
    TaskAssignment,
)
from routers.projects.serializers import (
    build_evaluation_indexes,
    build_judge_model_lookup,
    serialize_annotation,
    serialize_evaluation_run,
    serialize_generation,
    serialize_human_evaluation_data,
    serialize_korrektur_comment,
    serialize_task,
    serialize_task_evaluation,
)
from sqlalchemy import func as sa_func
from sqlalchemy import select

BATCH_SIZE = 50


def build_batch_objs(
    db: Session,
    batch: list,
    eval_run_by_id: dict,
    judge_model_lookup: dict,
) -> list[dict]:
    """Build per-task export dicts for a batch with 4 batched IN-queries
    (annotations, questionnaire responses, generations, task_evaluations)
    instead of 4 queries per task. For a 581-task project this collapses
    ~2,300 round-trips to ~48.
    """
    if not batch:
        return []
    batch_ids = [t.id for t in batch]

    anns_all = db.query(Annotation).filter(Annotation.task_id.in_(batch_ids)).all()
    qrs_all = db.query(PostAnnotationResponse).filter(
        PostAnnotationResponse.task_id.in_(batch_ids)
    ).all()
    gens_all = db.query(Generation).filter(Generation.task_id.in_(batch_ids)).all()
    if eval_run_by_id:
        te_all = db.query(TaskEvaluation).filter(
            TaskEvaluation.task_id.in_(batch_ids),
            TaskEvaluation.evaluation_id.in_(eval_run_by_id.keys()),
        ).all()
    else:
        te_all = []

    anns_by_task: dict = {}
    for a in anns_all:
        anns_by_task.setdefault(a.task_id, []).append(a)
    qr_by_annotation = {qr.annotation_id: qr for qr in qrs_all}
    gens_by_task: dict = {}
    for g in gens_all:
        gens_by_task.setdefault(g.task_id, []).append(g)
    te_by_task_id, te_by_gen_id = build_evaluation_indexes(te_all)

    out = []
    for task in batch:
        task_data = serialize_task(task, mode="data")
        task_data["annotations"] = [
            serialize_annotation(
                ann, mode="data", questionnaire_response=qr_by_annotation.get(ann.id)
            )
            for ann in anns_by_task.get(task.id, [])
        ]
        task_data["generations"] = []
        for gen in gens_by_task.get(task.id, []):
            gen_evals = te_by_gen_id.get(gen.id, [])
            eval_dicts = [
                serialize_task_evaluation(
                    te, mode="data",
                    eval_run=eval_run_by_id.get(te.evaluation_id),
                    judge_model_lookup=judge_model_lookup,
                )
                for te in gen_evals
            ]
            task_data["generations"].append(
                serialize_generation(gen, mode="data", evaluations=eval_dicts)
            )

        task_data["evaluations"] = []
        for te in te_by_task_id.get(task.id, []):
            if te.generation_id is not None:
                continue
            task_data["evaluations"].append(
                serialize_task_evaluation(
                    te, mode="data",
                    eval_run=eval_run_by_id.get(te.evaluation_id),
                    judge_model_lookup=judge_model_lookup,
                )
            )
        out.append(task_data)
    return out


def stream_export_json(
    db: Session,
    project_id: str,
    task_ids: Optional[Iterable[str]],
    header_fields: dict,
) -> Iterator[str]:
    """Yield a complete JSON export as string chunks.

    `header_fields` becomes the top-level keys preceding the streamed
    blocks. The bulk-export endpoint passes a flat
    {project_id, project_title, exported_at} dict; the single-project GET
    passes the richer {"project": {...metadata...}} shape its existing
    consumers expect — both round-trip because we splice via string
    surgery (`json.dumps(header)[:-1]` drops the closing `}` so we can
    append more keys).

    Passing `task_ids=None` exports every task in the project; otherwise
    only the specified subset is included. The eval_runs / korrektur
    blocks are always project-wide; human-eval is filtered to the same
    task set we end up streaming.
    """
    eval_runs = db.query(EvaluationRun).filter(
        EvaluationRun.project_id == project_id
    ).all()
    eval_run_by_id = {er.id: er for er in eval_runs}
    judge_model_lookup = build_judge_model_lookup(eval_runs, db)

    header = dict(header_fields)
    header["evaluation_runs"] = [
        serialize_evaluation_run(er, mode="data") for er in eval_runs
    ]
    yield json.dumps(header)[:-1] + ', "tasks": ['

    first = True
    task_q = db.query(Task).filter(Task.project_id == project_id)
    if task_ids is not None:
        task_q = task_q.filter(Task.id.in_(list(task_ids)))

    batch: list = []
    streamed_task_ids: list = []
    for task in task_q.yield_per(BATCH_SIZE):
        batch.append(task)
        streamed_task_ids.append(task.id)
        if len(batch) >= BATCH_SIZE:
            for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
                yield ("" if first else ",") + json.dumps(obj)
                first = False
            batch = []
    for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
        yield ("" if first else ",") + json.dumps(obj)
        first = False

    yield "], "

    human_eval = serialize_human_evaluation_data(db, project_id, streamed_task_ids) or {}
    items = list(human_eval.items())
    for idx, (k, v) in enumerate(items):
        yield json.dumps(k) + ":" + json.dumps(v)
        if idx < len(items) - 1:
            yield ","
    if items:
        yield ","

    yield '"korrektur_comments": ['
    first = True
    kc_q = db.query(KorrekturComment).filter(KorrekturComment.project_id == project_id)
    for kc in kc_q.yield_per(100):
        yield ("" if first else ",") + json.dumps(serialize_korrektur_comment(kc))
        first = False
    yield "]}"


# Per-row column layout used by GET /{project_id}/export?format=csv|tsv.
# Each task fans out to max(annotations, generations, evaluations, 1) rows,
# matching the legacy in-memory CSV builder's shape so existing test
# assertions (`task_id`, `annotation_id`, `generation_id` in header) and any
# downstream parsers keep working.
EXPORT_FLAT_CSV_COLUMNS: list[str] = [
    "task_id",
    "task_data",
    "annotation_id",
    "annotation_result",
    "annotation_completed_by",
    "annotation_created_at",
    "questionnaire_response",
    "generation_id",
    "generation_model",
    "generation_content",
    "generation_created_at",
    "evaluation_field",
    "evaluation_metrics",
    "evaluation_passed",
]


def stream_export_flat_csv(
    db: Session,
    project_id: str,
    delimiter: str,
) -> Iterator[str]:
    """Yield a flat per-row CSV/TSV export as string chunks.

    Mirrors the legacy `GET /{project_id}/export?format=csv|tsv` shape:
    one header row, then max(N_anns, N_gens, N_evals, 1) rows per task,
    columns lined up positionally so each row carries at most one of each
    sub-entity. Uses the same batched IN-queries as the JSON stream so
    peak memory stays bounded by BATCH_SIZE regardless of project size.
    """
    eval_runs = db.query(EvaluationRun).filter(
        EvaluationRun.project_id == project_id
    ).all()
    eval_run_by_id = {er.id: er for er in eval_runs}
    judge_model_lookup = build_judge_model_lookup(eval_runs, db)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter)
    writer.writerow(EXPORT_FLAT_CSV_COLUMNS)
    yield buf.getvalue()
    buf.seek(0); buf.truncate()

    def _emit_rows(task_obj: dict) -> str:
        anns = task_obj.get("annotations") or []
        gens = task_obj.get("generations") or []
        evals = task_obj.get("evaluations") or []
        max_items = max(len(anns), len(gens), len(evals), 1)
        for i in range(max_items):
            ann = anns[i] if i < len(anns) else None
            gen = gens[i] if i < len(gens) else None
            ev = evals[i] if i < len(evals) else None
            writer.writerow([
                task_obj["id"],
                json.dumps(task_obj.get("data")),
                ann["id"] if ann else "",
                json.dumps(ann["result"]) if ann else "",
                ann["completed_by"] if ann else "",
                ann["created_at"] if ann else "",
                (
                    json.dumps(ann["questionnaire_response"])
                    if ann and ann.get("questionnaire_response")
                    else ""
                ),
                gen["id"] if gen else "",
                gen.get("model_id") if gen else "",
                gen.get("response_content") if gen else "",
                gen.get("created_at") if gen else "",
                ev["field_name"] if ev else "",
                json.dumps(ev["metrics"]) if ev else "",
                ev["passed"] if ev else "",
            ])
        chunk = buf.getvalue()
        buf.seek(0); buf.truncate()
        return chunk

    task_q = db.query(Task).filter(Task.project_id == project_id)
    batch: list = []
    for task in task_q.yield_per(BATCH_SIZE):
        batch.append(task)
        if len(batch) >= BATCH_SIZE:
            for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
                yield _emit_rows(obj)
            batch = []
    for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
        yield _emit_rows(obj)


def stream_export_label_studio(
    db: Session,
    project_id: str,
) -> Iterator[str]:
    """Yield a Label Studio JSON array as string chunks, one task per element.

    Schema matches what the legacy in-memory branch emitted: Label Studio's
    task object (id, data, annotations[], predictions[], meta, created/updated,
    is_labeled, project) plus BenGER extensions `generations` and
    `evaluations`. Span-typed annotation results go through
    `convert_to_label_studio_format` so the spans round-trip back into
    Label Studio's UI.

    Uses a smaller `LS_BATCH_SIZE` than the JSON/CSV paths because each LS
    batch's IN-query against TaskEvaluation pulls every eval for every task
    in the batch, with no opportunity to filter further (legacy callers
    expect both task-level and gen-level evals on the LS task object). For
    Benchathon-sized projects, a 50-task batch would yank ~40k eval rows in
    one shot and OOMKilled the API pod; 5-task batches keep peak well under
    the container limit.
    """
    from routers.projects.import_export import convert_to_label_studio_format

    LS_BATCH_SIZE = 5

    eval_runs = db.query(EvaluationRun).filter(
        EvaluationRun.project_id == project_id
    ).all()
    eval_run_by_id = {er.id: er for er in eval_runs}

    yield "["
    first = True

    task_q = db.query(Task).filter(Task.project_id == project_id)
    batch: list = []

    def _build_ls_objs(task_batch: list) -> list[str]:
        if not task_batch:
            return []
        batch_ids = [t.id for t in task_batch]
        anns_all = db.query(Annotation).filter(
            Annotation.task_id.in_(batch_ids)
        ).all()
        qrs_all = db.query(PostAnnotationResponse).filter(
            PostAnnotationResponse.task_id.in_(batch_ids)
        ).all()
        gens_all = db.query(Generation).filter(
            Generation.task_id.in_(batch_ids)
        ).all()
        if eval_run_by_id:
            te_all = db.query(TaskEvaluation).filter(
                TaskEvaluation.task_id.in_(batch_ids),
                TaskEvaluation.evaluation_id.in_(eval_run_by_id.keys()),
            ).all()
        else:
            te_all = []

        anns_by_task: dict = {}
        for a in anns_all:
            anns_by_task.setdefault(a.task_id, []).append(a)
        qr_by_annotation = {qr.annotation_id: qr for qr in qrs_all}
        gens_by_task: dict = {}
        for g in gens_all:
            gens_by_task.setdefault(g.task_id, []).append(g)
        # Legacy LS export emits every task_evaluation (both task- and
        # gen-level) into the task's `evaluations` array; mirror that here.
        te_by_task: dict = {}
        for te in te_all:
            te_by_task.setdefault(te.task_id, []).append(te)

        out: list[str] = []
        for task in task_batch:
            ls_task = {
                "id": task.inner_id or task.id,
                "data": task.data,
                "annotations": [],
                "predictions": [],
                "meta": task.meta or {},
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "is_labeled": task.is_labeled,
                "project": project_id,
            }
            for ann in anns_by_task.get(task.id, []):
                converted_result = convert_to_label_studio_format(ann.result)
                ls_ann = {
                    "id": ann.id,
                    "completed_by": ann.completed_by,
                    "result": converted_result,
                    "was_cancelled": ann.was_cancelled,
                    "ground_truth": ann.ground_truth,
                    "created_at": ann.created_at.isoformat() if ann.created_at else None,
                    "updated_at": ann.updated_at.isoformat() if ann.updated_at else None,
                    "lead_time": ann.lead_time,
                    "task": task.inner_id or task.id,
                    "project": project_id,
                }
                if ann.draft:
                    ls_ann["draft"] = ann.draft
                if ann.prediction_scores:
                    ls_ann["prediction"] = ann.prediction_scores
                qr = qr_by_annotation.get(ann.id)
                if qr:
                    ls_ann["questionnaire_response"] = {
                        "result": qr.result,
                        "created_at": qr.created_at.isoformat() if qr.created_at else None,
                    }
                ls_task["annotations"].append(ls_ann)

            task_gens = gens_by_task.get(task.id, [])
            if task_gens:
                ls_task["generations"] = [
                    {
                        "id": gen.id,
                        "model_id": gen.model_id,
                        "response_content": gen.response_content,
                        "case_data": gen.case_data,
                        "created_at": (
                            gen.created_at.isoformat() if gen.created_at else None
                        ),
                        "response_metadata": gen.response_metadata,
                    }
                    for gen in task_gens
                ]
            task_evals_list = te_by_task.get(task.id, [])
            if task_evals_list:
                ls_task["evaluations"] = [
                    {
                        "id": te.id,
                        "evaluation_id": te.evaluation_id,
                        "generation_id": te.generation_id,
                        "field_name": te.field_name,
                        "answer_type": te.answer_type,
                        "ground_truth": te.ground_truth,
                        "prediction": te.prediction,
                        "metrics": te.metrics,
                        "passed": te.passed,
                        "confidence_score": te.confidence_score,
                        "created_at": (
                            te.created_at.isoformat() if te.created_at else None
                        ),
                    }
                    for te in task_evals_list
                ]
            out.append(json.dumps(ls_task, ensure_ascii=False))
        return out

    for task in task_q.yield_per(LS_BATCH_SIZE):
        batch.append(task)
        if len(batch) >= LS_BATCH_SIZE:
            for chunk in _build_ls_objs(batch):
                yield ("" if first else ",") + chunk
                first = False
            batch = []
    for chunk in _build_ls_objs(batch):
        yield ("" if first else ",") + chunk
        first = False

    yield "]"


def stream_export_txt(
    db: Session,
    project_id: str,
    project_title: str,
    project_description: Optional[str],
) -> Iterator[str]:
    """Yield the legacy plain-text export summary as string chunks.

    Header carries project metadata and totals; each task contributes a
    short section listing its data dict, annotations (with optional
    questionnaire result), and evaluations. The totals match what
    `.count()` reports, not what the per-batch stream sees — those are
    identical for the project-wide export but kept explicit so the txt
    summary doesn't drift if the helper later gains a task subset.
    """
    eval_runs = db.query(EvaluationRun).filter(
        EvaluationRun.project_id == project_id
    ).all()
    eval_run_by_id = {er.id: er for er in eval_runs}
    judge_model_lookup = build_judge_model_lookup(eval_runs, db)

    task_count = db.query(Task).filter(Task.project_id == project_id).count()
    annotation_count = (
        db.query(Annotation).filter(Annotation.project_id == project_id).count()
    )

    yield f"Project: {project_title}\n"
    yield f"Description: {project_description or 'None'}\n"
    yield f"Total Tasks: {task_count}\n"
    yield f"Total Annotations: {annotation_count}\n"
    yield "-" * 50 + "\n"

    task_q = db.query(Task).filter(Task.project_id == project_id)
    batch: list = []
    for task in task_q.yield_per(BATCH_SIZE):
        batch.append(task)
        if len(batch) >= BATCH_SIZE:
            for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
                yield _format_task_txt(obj)
            batch = []
    for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
        yield _format_task_txt(obj)


def stream_comprehensive_project_data_json(
    db: Session,
    project_id: str,
) -> Iterator[str]:
    """Streaming sibling of `routers.projects.helpers.get_comprehensive_project_data`.

    Yields the same JSON shape the helper returns (same top-level keys, same
    per-row field structure) but in chunks, so the full clone payload never
    lives in RAM simultaneously. Used by POST /bulk-export-full to keep the
    per-project peak bounded — Benchathon-sized projects (~11k task_evaluations
    in `mode='full'`) would otherwise OOMKill the API pod the moment the
    helper finished building its dict.

    Heavy sections (tasks / annotations / generations / task_evaluations) use
    `yield_per` + per-row `json.dumps` so peak RAM scales with one row, not the
    set. Small sections (configs, sessions, members, etc.) load with `.all()`
    and serialize once — they're tiny in practice. `users` is computed at the
    end from refs collected during the stream, and `statistics` is the
    running counters.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id!r} not found")

    org_row = (
        db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .first()
    )
    project_data = {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "label_config": project.label_config,
        "expert_instruction": project.expert_instruction,
        "show_instruction": project.show_instruction,
        "show_skip_button": project.show_skip_button,
        "enable_empty_annotation": project.enable_empty_annotation,
        "created_by": project.created_by,
        "organization_id": org_row[0] if org_row else None,
        "min_annotations_per_task": project.min_annotations_per_task,
        "is_published": project.is_published,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
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
    }

    user_ids: set[str] = set()
    if project.created_by:
        user_ids.add(project.created_by)
    stats: dict[str, int] = {
        "total_tasks": 0,
        "total_annotations": 0,
        "total_generations": 0,
        "total_evaluations": 0,
        "total_evaluation_metrics": 0,
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

    # Per-task generation counts for serialize_task(mode="full", total_generations=...).
    # task_id_subq is a SELECT used inside IN() filters across this function.
    gen_counts: dict[str, int] = {}
    task_id_subq = select(Task.id).where(Task.project_id == project_id)
    gen_count_rows = (
        db.query(Generation.task_id, sa_func.count(Generation.id))
        .filter(Generation.task_id.in_(task_id_subq))
        .group_by(Generation.task_id)
        .all()
    )
    for tid, n in gen_count_rows:
        gen_counts[tid] = n

    yield '{"format_version": "1.0.0",'
    yield '"exported_at": ' + json.dumps(datetime.utcnow().isoformat()) + ','
    yield '"exported_by": ' + json.dumps(project.created_by) + ','
    yield '"project": ' + json.dumps(project_data, ensure_ascii=False) + ','

    # --- tasks (heavy) ---
    yield '"tasks": ['
    first = True
    task_q = db.query(Task).filter(Task.project_id == project_id)
    for task in task_q.yield_per(BATCH_SIZE):
        if task.created_by:
            user_ids.add(task.created_by)
        if task.updated_by:
            user_ids.add(task.updated_by)
        td = serialize_task(
            task, mode="full", total_generations=gen_counts.get(task.id, 0),
        )
        yield ("" if first else ",") + json.dumps(td, ensure_ascii=False)
        first = False
        stats["total_tasks"] += 1
    yield "],"

    # --- annotations (heavy) ---
    yield '"annotations": ['
    first = True
    ann_q = db.query(Annotation).filter(Annotation.project_id == project_id)
    for ann in ann_q.yield_per(BATCH_SIZE):
        if ann.completed_by:
            user_ids.add(ann.completed_by)
        yield ("" if first else ",") + json.dumps(
            serialize_annotation(ann, mode="full"), ensure_ascii=False
        )
        first = False
        stats["total_annotations"] += 1
    yield "],"

    # --- predictions (deprecated table; always empty) ---
    yield '"predictions": [],'

    # --- generations (very heavy: response_content) ---
    yield '"generations": ['
    first = True
    gen_q = db.query(Generation).filter(Generation.task_id.in_(task_id_subq))
    for gen in gen_q.yield_per(BATCH_SIZE):
        yield ("" if first else ",") + json.dumps(
            serialize_generation(gen, mode="full"), ensure_ascii=False
        )
        first = False
        stats["total_generations"] += 1
    yield "],"

    # --- response_generations (medium) ---
    yield '"response_generations": ['
    first = True
    rg_q = db.query(ResponseGeneration).filter(
        ResponseGeneration.task_id.in_(task_id_subq)
    )
    for rg in rg_q.yield_per(BATCH_SIZE):
        rg_data = {
            "id": rg.id,
            "task_id": rg.task_id,
            "model_id": rg.model_id,
            "config_id": rg.config_id,
            "status": rg.status,
            "responses_generated": rg.responses_generated,
            "error_message": rg.error_message,
            "generation_metadata": rg.generation_metadata,
            "created_by": rg.created_by,
            "created_at": rg.created_at.isoformat() if rg.created_at else None,
            "started_at": rg.started_at.isoformat() if rg.started_at else None,
            "completed_at": rg.completed_at.isoformat() if rg.completed_at else None,
        }
        yield ("" if first else ",") + json.dumps(rg_data, ensure_ascii=False)
        first = False
    yield "],"

    # --- project_members (small) ---
    members = (
        db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    )
    yield '"project_members": ['
    first = True
    for member in members:
        if member.user_id:
            user_ids.add(member.user_id)
        m_data = {
            "id": member.id,
            "project_id": member.project_id,
            "user_id": member.user_id,
            "role": member.role,
            "is_active": member.is_active,
            "created_at": member.created_at.isoformat() if member.created_at else None,
            "updated_at": member.updated_at.isoformat() if member.updated_at else None,
        }
        yield ("" if first else ",") + json.dumps(m_data, ensure_ascii=False)
        first = False
        stats["total_members"] += 1
    yield "],"

    # --- task_assignments (medium; join through Task) ---
    assignments = (
        db.query(TaskAssignment).join(Task).filter(Task.project_id == project_id).all()
    )
    yield '"task_assignments": ['
    first = True
    for a in assignments:
        if a.user_id:
            user_ids.add(a.user_id)
        if a.assigned_by:
            user_ids.add(a.assigned_by)
        a_data = {
            "id": a.id,
            "task_id": a.task_id,
            "user_id": a.user_id,
            "assigned_by": a.assigned_by,
            "status": a.status,
            "priority": a.priority,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "notes": a.notes,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        yield ("" if first else ",") + json.dumps(a_data, ensure_ascii=False)
        first = False
        stats["total_assignments"] += 1
    yield "],"

    # --- evaluations (small: eval_runs themselves) ---
    eval_runs = (
        db.query(EvaluationRun).filter(EvaluationRun.project_id == project_id).all()
    )
    eval_run_ids = [er.id for er in eval_runs]
    yield '"evaluations": ['
    first = True
    for er in eval_runs:
        yield ("" if first else ",") + json.dumps(
            serialize_evaluation_run(er, mode="full"), ensure_ascii=False
        )
        first = False
        stats["total_evaluations"] += 1
    yield "],"

    # --- evaluation_metrics (medium) ---
    yield '"evaluation_metrics": ['
    first = True
    if eval_run_ids:
        em_q = db.query(EvaluationRunMetric).filter(
            EvaluationRunMetric.evaluation_id.in_(eval_run_ids)
        )
        for m in em_q.yield_per(BATCH_SIZE):
            m_data = {
                "id": m.id,
                "evaluation_id": m.evaluation_id,
                "evaluation_type_id": m.evaluation_type_id,
                "value": m.value,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            yield ("" if first else ",") + json.dumps(m_data, ensure_ascii=False)
            first = False
            stats["total_evaluation_metrics"] += 1
    yield "],"

    # --- task_evaluations (very heavy: thousands of rows) ---
    yield '"task_evaluations": ['
    first = True
    if eval_run_ids:
        te_q = db.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id.in_(eval_run_ids)
        )
        for te in te_q.yield_per(BATCH_SIZE):
            yield ("" if first else ",") + json.dumps(
                serialize_task_evaluation(te, mode="full"), ensure_ascii=False
            )
            first = False
            stats["total_task_evaluations"] += 1
    yield "],"

    # --- human_evaluation_configs (small) ---
    hec_ids: list[str] = []
    yield '"human_evaluation_configs": ['
    first = True
    hec_q = db.query(HumanEvaluationConfig).filter(
        HumanEvaluationConfig.task_id.in_(task_id_subq)
    )
    for c in hec_q.yield_per(BATCH_SIZE):
        hec_ids.append(c.id)
        c_data = {
            "id": c.id,
            "task_id": c.task_id,
            "evaluation_project_id": c.evaluation_project_id,
            "evaluator_count": c.evaluator_count,
            "randomization_seed": c.randomization_seed,
            "blinding_enabled": c.blinding_enabled,
            "include_human_responses": c.include_human_responses,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        yield ("" if first else ",") + json.dumps(c_data, ensure_ascii=False)
        first = False
        stats["total_human_evaluation_configs"] += 1
    yield "],"

    # --- human_evaluation_sessions (small) ---
    hes_ids: list[str] = []
    yield '"human_evaluation_sessions": ['
    first = True
    hes_q = db.query(HumanEvaluationSession).filter(
        HumanEvaluationSession.project_id == project_id
    )
    for s in hes_q.yield_per(BATCH_SIZE):
        hes_ids.append(s.id)
        s_data = {
            "id": s.id,
            "project_id": s.project_id,
            "evaluator_id": s.evaluator_id,
            "session_type": s.session_type,
            "items_evaluated": s.items_evaluated,
            "total_items": s.total_items,
            "status": s.status,
            "session_config": s.session_config,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        yield ("" if first else ",") + json.dumps(s_data, ensure_ascii=False)
        first = False
        stats["total_human_evaluation_sessions"] += 1
    yield "],"

    # --- human_evaluation_results (medium) ---
    yield '"human_evaluation_results": ['
    first = True
    if hec_ids:
        her_q = db.query(HumanEvaluationResult).filter(
            HumanEvaluationResult.config_id.in_(hec_ids)
        )
        for r in her_q.yield_per(BATCH_SIZE):
            r_data = {
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
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            yield ("" if first else ",") + json.dumps(r_data, ensure_ascii=False)
            first = False
            stats["total_human_evaluation_results"] += 1
    yield "],"

    # --- preference_rankings (medium) ---
    yield '"preference_rankings": ['
    first = True
    if hes_ids:
        pr_q = db.query(PreferenceRanking).filter(
            PreferenceRanking.session_id.in_(hes_ids)
        )
        for p in pr_q.yield_per(BATCH_SIZE):
            p_data = {
                "id": p.id,
                "session_id": p.session_id,
                "task_id": p.task_id,
                "response_a_id": p.response_a_id,
                "response_b_id": p.response_b_id,
                "winner": p.winner,
                "confidence": p.confidence,
                "reasoning": p.reasoning,
                "time_spent_seconds": p.time_spent_seconds,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            yield ("" if first else ",") + json.dumps(p_data, ensure_ascii=False)
            first = False
            stats["total_preference_rankings"] += 1
    yield "],"

    # --- likert_scale_evaluations (medium) ---
    yield '"likert_scale_evaluations": ['
    first = True
    if hes_ids:
        ls_q = db.query(LikertScaleEvaluation).filter(
            LikertScaleEvaluation.session_id.in_(hes_ids)
        )
        for lk in ls_q.yield_per(BATCH_SIZE):
            lk_data = {
                "id": lk.id,
                "session_id": lk.session_id,
                "task_id": lk.task_id,
                "response_id": lk.response_id,
                "dimension": lk.dimension,
                "rating": lk.rating,
                "comment": lk.comment,
                "time_spent_seconds": lk.time_spent_seconds,
                "created_at": lk.created_at.isoformat() if lk.created_at else None,
            }
            yield ("" if first else ",") + json.dumps(lk_data, ensure_ascii=False)
            first = False
            stats["total_likert_scale_evaluations"] += 1
    yield "],"

    # --- korrektur_comments (medium) ---
    yield '"korrektur_comments": ['
    first = True
    kc_q = db.query(KorrekturComment).filter(KorrekturComment.project_id == project_id)
    for kc in kc_q.yield_per(BATCH_SIZE):
        yield ("" if first else ",") + json.dumps(
            serialize_korrektur_comment(kc), ensure_ascii=False
        )
        first = False
    yield "],"

    # --- post_annotation_responses (medium) ---
    yield '"post_annotation_responses": ['
    first = True
    par_q = db.query(PostAnnotationResponse).filter(
        PostAnnotationResponse.project_id == project_id
    )
    for r in par_q.yield_per(BATCH_SIZE):
        if r.user_id:
            user_ids.add(r.user_id)
        r_data = {
            "id": r.id,
            "annotation_id": r.annotation_id,
            "task_id": r.task_id,
            "project_id": r.project_id,
            "user_id": r.user_id,
            "result": r.result,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        yield ("" if first else ",") + json.dumps(r_data, ensure_ascii=False)
        first = False
        stats["total_post_annotation_responses"] += 1
    yield "],"

    # --- users (computed at end from refs collected during the stream) ---
    yield '"users": ['
    first = True
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            u_data = {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "name": u.name,
                "is_active": u.is_active,
                "is_superadmin": u.is_superadmin,
            }
            yield ("" if first else ",") + json.dumps(u_data, ensure_ascii=False)
            first = False
    yield "],"

    yield '"statistics": ' + json.dumps(stats) + "}"


def _format_task_txt(task_obj: dict) -> str:
    lines: list[str] = []
    lines.append(f"\nTask {task_obj['id']}:")
    lines.append(f"Data: {json.dumps(task_obj.get('data'))}")
    anns = task_obj.get("annotations") or []
    if anns:
        lines.append(f"Annotations ({len(anns)}):")
        for ann in anns:
            lines.append(f"  - {ann['id']}: {json.dumps(ann['result'])}")
            qr = ann.get("questionnaire_response")
            if qr:
                lines.append(f"    Questionnaire: {json.dumps(qr['result'])}")
    else:
        lines.append("No annotations")
    evals = task_obj.get("evaluations") or []
    if evals:
        lines.append(f"Evaluations ({len(evals)}):")
        for ev in evals:
            lines.append(
                f"  - {ev['field_name']}: passed={ev['passed']} metrics={json.dumps(ev['metrics'])}"
            )
    return "\n".join(lines) + "\n"
