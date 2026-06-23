"""Shared streaming helpers for project JSON exports.

Used by both `GET /api/projects/{project_id}/export?format=json` and
`POST /api/projects/{project_id}/tasks/bulk-export?format=json`. Past
revisions of the GET handler loaded the entire project (tasks, annotations,
generations, task_evaluations, korrektur_comments, human-eval blocks) into
one nested Python dict and then `json.dumps(..., indent=2)`-ed it — that
peaked at ~3x the row-set's RAM and OOMKilled the API pod on 2026-05-31
when the Benchathon project (~8k task_evaluations / 400 MB of JSON) was
exported.

The generators below stream the same JSON tree out chunk-by-chunk. Two
things keep peak memory bounded by BATCH_SIZE regardless of project size:
`yield_per` bounds how many rows the DBAPI cursor buffers, and an explicit
`Session.expunge` of each batch's ORM rows keeps the Session identity map
from growing. The expunge is the load-bearing half — `yield_per` alone does
NOT release rows: every Task / Annotation / Generation / TaskEvaluation
object stays strongly referenced by the identity map for the life of the
Session, so without detaching them peak memory scales with the whole
project, not BATCH_SIZE. That gap OOMKilled the API pod again on the
581-task ZJS export (2026-05-31) even though this path "already streamed".

The existing POST /tasks/bulk-export uses the same `build_batch_objs`
helper (commits 7c61a79, 0ae2be0); this module extracts it so the
single-project GET can share the row-fetching, batching, detaching, and
JSON-splicing logic without duplication.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from itertools import chain
from typing import Callable, Iterable, Iterator, List, Optional

from sqlalchemy.orm import Session

from models import (
    EvaluationJudgeRun,
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
# serializers relocated to /shared alongside this module (issue #158) so the
# worker can import it; /shared is first on sys.path in both containers.
from serializers import (
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

# Shared, behavior-preserving extract of the row->dict serializers, batch
# helpers, and query builders this module previously duplicated inline (and
# across its two comprehensive generators). See stream_io/__init__.py for why
# the package is named stream_io and not io.
from stream_io.batch_utils import drain_expunge, fetch_batch_children
from stream_io.query_builders import (
    build_eval_run_ids,
    build_gen_counts,
    build_task_id_subquery,
)
from stream_io.serialization import (
    build_project_export_data,
    empty_export_stats,
    serialize_evaluation_judge_run_row,
    serialize_evaluation_metric_row,
    serialize_human_evaluation_config_row,
    serialize_human_evaluation_result_row,
    serialize_human_evaluation_session_row,
    serialize_likert_scale_evaluation_row,
    serialize_post_annotation_response_row,
    serialize_preference_ranking_row,
    serialize_project_member_row,
    serialize_response_generation_row,
    serialize_task_assignment_row,
    serialize_user_row,
)

BATCH_SIZE = 50

# Cap a batch by how many task_evaluations it pulls, not just how many tasks.
# `build_batch_objs` loads a batch's entire task_evaluation set as ORM rows AND
# materializes their serialized dicts at the same time, so peak RAM scales with
# evals-per-batch, not task count. On eval-dense projects (the Benchathon export
# is 15 tasks but ~10.5k task_evaluations — ~700/task — each carrying large
# legal-text metrics JSON) a 50-task batch is a single batch that peaks ~1.7 GB
# and OOMKills the 3Gi API pod mid-stream, severing the download (surfaced to
# the client as TruncatedExportError). Bounding by eval volume keeps the peak
# flat regardless of how evals are distributed across tasks. ~1000 evals/batch
# measured at ~0.5 GB peak; eval-light projects still form full BATCH_SIZE
# batches, preserving the batched-IN-query round-trip savings.
MAX_BATCH_TASK_EVALS = 1000


def iter_eval_bounded_batches(
    db: Session,
    task_q,
    eval_run_ids,
) -> Iterator[list]:
    """Yield task batches bounded by BOTH BATCH_SIZE tasks and
    MAX_BATCH_TASK_EVALS task_evaluations.

    A cheap GROUP BY prepass counts each task's evaluations (over the same
    `evaluation_id IN (...)` filter `build_batch_objs` applies), then tasks are
    accumulated until either cap is hit. A single task whose eval count already
    exceeds the cap still gets its own batch so the stream always makes
    progress. When `eval_run_ids` is empty the eval cap is inert and batching
    falls back to pure BATCH_SIZE behaviour.
    """
    eval_counts: dict = {}
    if eval_run_ids:
        for tid, n in (
            db.query(TaskEvaluation.task_id, sa_func.count(TaskEvaluation.id))
            .filter(TaskEvaluation.evaluation_id.in_(eval_run_ids))
            .group_by(TaskEvaluation.task_id)
            .all()
        ):
            eval_counts[tid] = n

    batch: list = []
    batch_evals = 0
    for task in task_q.yield_per(BATCH_SIZE):
        t_evals = eval_counts.get(task.id, 0)
        if batch and (
            len(batch) >= BATCH_SIZE
            or batch_evals + t_evals > MAX_BATCH_TASK_EVALS
        ):
            yield batch
            batch = []
            batch_evals = 0
        batch.append(task)
        batch_evals += t_evals
    if batch:
        yield batch


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

    (
        anns_all, qrs_all, gens_all, te_all,
        anns_by_task, qr_by_annotation, gens_by_task,
    ) = fetch_batch_children(
        db, batch_ids, list(eval_run_by_id.keys()) if eval_run_by_id else []
    )
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

    # Detach every ORM row this batch pulled in so the Session identity map
    # doesn't grow across batches — `out` holds only plain dicts now, so the
    # rows are dead weight. Without this, peak RAM scales with the whole
    # project (the TaskEvaluation rows carry large legal-text metrics JSON)
    # rather than BATCH_SIZE, which OOMKilled the API pod on large exports.
    # The caller's eval_run / judge_model_lookup objects are intentionally
    # left attached — they're reused on every batch.
    for obj in chain(batch, anns_all, qrs_all, gens_all, te_all):
        db.expunge(obj)
    return out


def stream_export_json(
    db: Session,
    project_id: str,
    task_ids: Optional[Iterable[str]],
    header_fields: dict,
    progress_cb: Optional[Callable[[int, int], None]] = None,
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

    `progress_cb`, when supplied, is called once per streamed task batch with
    `(tasks_streamed_so_far, total_tasks)` so the async worker can persist
    incremental progress. It is best-effort: any exception it raises is
    swallowed so a progress hiccup can never sever the export stream. The
    tasks block dominates the export, so task count is a faithful progress
    signal; the trailing korrektur/human-eval blocks finish near 100%.
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

    # Only pay for the count when a caller actually wants progress. `.count()`
    # issues its own statement and is fully drained before the streaming
    # cursor opens, so it doesn't disturb the `yield_per` iteration below.
    total_tasks = task_q.count() if progress_cb is not None else 0

    streamed_task_ids: list = []
    eval_run_ids = list(eval_run_by_id.keys())
    for batch in iter_eval_bounded_batches(db, task_q, eval_run_ids):
        streamed_task_ids.extend(t.id for t in batch)
        for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
            yield ("" if first else ",") + json.dumps(obj)
            first = False
        if progress_cb is not None:
            try:
                progress_cb(len(streamed_task_ids), total_tasks)
            except Exception:
                # Progress is best-effort; never let it break the export.
                pass

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
        db.expunge(kc)
    # `export_complete` is a completeness sentinel, not data. A multi-GB export
    # that gets cut mid-stream by a proxy/connection drop can be saved by the
    # browser as a "successful" but truncated file whose tail (a task object's
    # `"evaluations": []}`) is indistinguishable from a clean end (`]}`). The
    # download client only treats a file as complete when this trailing marker
    # is present, so a severed stream is surfaced as an error instead of a
    # silently-corrupt download. Keep it the LAST thing emitted.
    yield '], "export_complete": true}'


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
    sub-entity. Uses the same batched IN-queries and eval-bounded batching
    (`iter_eval_bounded_batches`) as the JSON stream so peak memory stays
    bounded regardless of project size or eval density.
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
    eval_run_ids = list(eval_run_by_id.keys())
    for batch in iter_eval_bounded_batches(db, task_q, eval_run_ids):
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
        (
            anns_all, qrs_all, gens_all, te_all,
            anns_by_task, qr_by_annotation, gens_by_task,
        ) = fetch_batch_children(
            db, batch_ids, list(eval_run_by_id.keys()) if eval_run_by_id else []
        )
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

        # Detach this batch's rows — `out` is plain JSON strings now, so the
        # ORM rows would otherwise pile up in the identity map and defeat the
        # small-batch memory bound this exporter relies on.
        for obj in chain(task_batch, anns_all, qrs_all, gens_all, te_all):
            db.expunge(obj)
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
    eval_run_ids = list(eval_run_by_id.keys())
    for batch in iter_eval_bounded_batches(db, task_q, eval_run_ids):
        for obj in build_batch_objs(db, batch, eval_run_by_id, judge_model_lookup):
            yield _format_task_txt(obj)


def stream_comprehensive_project_data_json(
    db: Session,
    project_id: str,
) -> Iterator[str]:
    """Stream the comprehensive (clone-format) project export as JSON chunks.

    Yields the same JSON shape the old dict-building
    `get_comprehensive_project_data` helper returned (removed in issue #106;
    this generator is the only producer now) — same top-level keys, same
    per-row field structure — but in chunks, so the full clone payload never
    lives in RAM simultaneously. Used by POST /bulk-export-full to keep the
    per-project peak bounded — Benchathon-sized projects (~11k task_evaluations
    in `mode='full'`) would otherwise OOMKill the API pod the moment the
    helper finished building its dict.

    Heavy sections (tasks / annotations / generations / task_evaluations) are
    iterated through `_drain`, which pairs `yield_per` (bounds the cursor
    buffer) with a per-row `Session.expunge` (bounds the identity map). Both
    halves are required: `yield_per` alone keeps every row alive in the
    identity map, so peak RAM would scale with the set, not one row. Small
    sections (configs, sessions, members, etc.) load with `.all()` and
    serialize once — they're tiny in practice. `users` is computed at the end
    from refs collected during the stream, and `statistics` is the running
    counters.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id!r} not found")

    org_row = (
        db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .first()
    )
    project_data = build_project_export_data(
        project, org_row[0] if org_row else None
    )

    user_ids: set[str] = set()
    if project.created_by:
        user_ids.add(project.created_by)
    stats: dict[str, int] = empty_export_stats()

    # Per-task generation counts for serialize_task(mode="full", total_generations=...).
    # task_id_subq is a SELECT used inside IN() filters across this function.
    task_id_subq = build_task_id_subquery(project_id)
    gen_counts: dict[str, int] = build_gen_counts(db, task_id_subq)

    def _drain(query, batch_size: int = BATCH_SIZE):
        return drain_expunge(db, query, batch_size)

    yield '{"format_version": "1.0.0",'
    yield '"exported_at": ' + json.dumps(datetime.utcnow().isoformat()) + ','
    yield '"exported_by": ' + json.dumps(project.created_by) + ','
    yield '"project": ' + json.dumps(project_data, ensure_ascii=False) + ','

    # --- tasks (heavy) ---
    yield '"tasks": ['
    first = True
    task_q = db.query(Task).filter(Task.project_id == project_id)
    for task in _drain(task_q):
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
    for ann in _drain(ann_q):
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
    for gen in _drain(gen_q):
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
    for rg in _drain(rg_q):
        yield ("" if first else ",") + json.dumps(
            serialize_response_generation_row(rg), ensure_ascii=False
        )
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
        yield ("" if first else ",") + json.dumps(
            serialize_project_member_row(member), ensure_ascii=False
        )
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
        yield ("" if first else ",") + json.dumps(
            serialize_task_assignment_row(a), ensure_ascii=False
        )
        first = False
        stats["total_assignments"] += 1
    yield "],"

    # --- evaluations (small: eval_runs themselves) ---
    eval_runs, eval_run_ids = build_eval_run_ids(db, project_id)
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
        for m in _drain(em_q):
            yield ("" if first else ",") + json.dumps(
                serialize_evaluation_metric_row(m), ensure_ascii=False
            )
            first = False
            stats["total_evaluation_metrics"] += 1
    yield "],"

    # --- evaluation_judge_runs (small: one per judge model x run_index) ---
    # Must precede task_evaluations: TaskEvaluation.judge_run_id is NOT NULL
    # (migration 043) and FK-references these rows, so the importer needs the
    # old->new judge-run id map built before it inserts task_evaluations.
    yield '"evaluation_judge_runs": ['
    first = True
    if eval_run_ids:
        jr_q = db.query(EvaluationJudgeRun).filter(
            EvaluationJudgeRun.evaluation_id.in_(eval_run_ids)
        )
        for jr in _drain(jr_q):
            yield ("" if first else ",") + json.dumps(
                serialize_evaluation_judge_run_row(jr), ensure_ascii=False
            )
            first = False
            stats["total_evaluation_judge_runs"] += 1
    yield "],"

    # --- task_evaluations (very heavy: thousands of rows) ---
    yield '"task_evaluations": ['
    first = True
    if eval_run_ids:
        te_q = db.query(TaskEvaluation).filter(
            TaskEvaluation.evaluation_id.in_(eval_run_ids)
        )
        for te in _drain(te_q):
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
    for c in _drain(hec_q):
        hec_ids.append(c.id)
        yield ("" if first else ",") + json.dumps(
            serialize_human_evaluation_config_row(c), ensure_ascii=False
        )
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
    for s in _drain(hes_q):
        hes_ids.append(s.id)
        yield ("" if first else ",") + json.dumps(
            serialize_human_evaluation_session_row(s), ensure_ascii=False
        )
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
        for r in _drain(her_q):
            yield ("" if first else ",") + json.dumps(
                serialize_human_evaluation_result_row(r), ensure_ascii=False
            )
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
        for p in _drain(pr_q):
            yield ("" if first else ",") + json.dumps(
                serialize_preference_ranking_row(p), ensure_ascii=False
            )
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
        for lk in _drain(ls_q):
            yield ("" if first else ",") + json.dumps(
                serialize_likert_scale_evaluation_row(lk), ensure_ascii=False
            )
            first = False
            stats["total_likert_scale_evaluations"] += 1
    yield "],"

    # --- korrektur_comments (medium) ---
    yield '"korrektur_comments": ['
    first = True
    kc_q = db.query(KorrekturComment).filter(KorrekturComment.project_id == project_id)
    for kc in _drain(kc_q):
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
    for r in _drain(par_q):
        if r.user_id:
            user_ids.add(r.user_id)
        yield ("" if first else ",") + json.dumps(
            serialize_post_annotation_response_row(r), ensure_ascii=False
        )
        first = False
        stats["total_post_annotation_responses"] += 1
    yield "],"

    # --- users (computed at end from refs collected during the stream) ---
    yield '"users": ['
    first = True
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            yield ("" if first else ",") + json.dumps(
                serialize_user_row(u), ensure_ascii=False
            )
            first = False
    yield "],"

    yield '"statistics": ' + json.dumps(stats) + "}"


def stream_export_ndjson(
    db: Session,
    project_id: str,
) -> Iterator[str]:
    """Yield an NDJSON typed-record comprehensive export, one JSON object per line.

    Frames the SAME comprehensive data as ``stream_comprehensive_project_data_json``
    but as newline-delimited typed records consumable by ``run_ndjson_import`` in
    a single forward pass: a leading ``{"_type":"meta",...,"project":{...}}``
    record, then flat entity records in FK-dependency order (users → tasks →
    annotations → … → post_annotation_responses), then a trailing
    ``{"_type":"end","statistics":{...},"export_complete":true}`` record. That
    ``end`` record is the structural completeness marker that replaces the legacy
    byte-tail ``export_complete`` sentinel.

    Two deliberate ordering differences from the comprehensive generator make the
    stream single-pass-importable:

    - ``users`` lead the stream (the comprehensive JSON emits them last, computed
      from refs). The importer builds its old→new user map from these records
      before any FK-bearing row arrives, so they must come first. The same user
      set is gathered up front via cheap column-only queries.
    - ``korrektur_comments`` are emitted roots-first, then replies, so a reply's
      ``parent_id`` always remaps against an already-seen parent.

    Per-entity record bodies mirror ``stream_comprehensive_project_data_json``
    exactly (same ``serialize_*`` calls / inline shapes) so the dicts the
    importer's ``_insert_<entity>`` helpers consume are identical whether they
    arrive as a JSON array element (legacy multi-pass) or an NDJSON line. Heavy
    sections stream through ``_drain`` (``yield_per`` + per-row ``expunge``) so
    peak memory stays O(batch) regardless of project size.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id!r} not found")

    org_row = (
        db.query(ProjectOrganization.organization_id)
        .filter(ProjectOrganization.project_id == project.id)
        .first()
    )
    project_data = build_project_export_data(
        project, org_row[0] if org_row else None
    )

    stats: dict[str, int] = empty_export_stats()

    def _emit(record_type: str, payload: dict) -> str:
        return json.dumps({"_type": record_type, **payload}, ensure_ascii=False) + "\n"

    def _drain(query, batch_size: int = BATCH_SIZE):
        return drain_expunge(db, query, batch_size)

    # Per-task generation counts for serialize_task(mode="full", total_generations=...).
    task_id_subq = build_task_id_subquery(project_id)
    gen_counts: dict[str, int] = build_gen_counts(db, task_id_subq)

    # --- meta (project header + version) ---
    yield _emit("meta", {
        "format_version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "exported_by": project.created_by,
        "project": project_data,
    })

    # --- users (lead the stream; same id set the comprehensive generator
    # collects as a side effect, gathered here up front via column-only queries
    # so the importer has the user map before FK-bearing rows arrive) ---
    user_ids: set[str] = set()
    if project.created_by:
        user_ids.add(project.created_by)
    for cb, ub in (
        db.query(Task.created_by, Task.updated_by)
        .filter(Task.project_id == project_id)
    ):
        if cb:
            user_ids.add(cb)
        if ub:
            user_ids.add(ub)
    for (cb,) in (
        db.query(Annotation.completed_by)
        .filter(Annotation.project_id == project_id)
    ):
        if cb:
            user_ids.add(cb)
    for (uid,) in (
        db.query(ProjectMember.user_id)
        .filter(ProjectMember.project_id == project_id)
    ):
        if uid:
            user_ids.add(uid)
    for uid, ab in (
        db.query(TaskAssignment.user_id, TaskAssignment.assigned_by)
        .join(Task)
        .filter(Task.project_id == project_id)
    ):
        if uid:
            user_ids.add(uid)
        if ab:
            user_ids.add(ab)
    for (uid,) in (
        db.query(PostAnnotationResponse.user_id)
        .filter(PostAnnotationResponse.project_id == project_id)
    ):
        if uid:
            user_ids.add(uid)

    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            yield _emit("user", serialize_user_row(u))

    # --- tasks (heavy) ---
    for task in _drain(db.query(Task).filter(Task.project_id == project_id)):
        yield _emit("task", serialize_task(
            task, mode="full", total_generations=gen_counts.get(task.id, 0),
        ))
        stats["total_tasks"] += 1

    # --- annotations (heavy) ---
    for ann in _drain(db.query(Annotation).filter(Annotation.project_id == project_id)):
        yield _emit("annotation", serialize_annotation(ann, mode="full"))
        stats["total_annotations"] += 1

    # --- response_generations (medium) ---
    for rg in _drain(
        db.query(ResponseGeneration).filter(ResponseGeneration.task_id.in_(task_id_subq))
    ):
        yield _emit("response_generation", serialize_response_generation_row(rg))

    # --- generations (very heavy: response_content) ---
    for gen in _drain(db.query(Generation).filter(Generation.task_id.in_(task_id_subq))):
        yield _emit("generation", serialize_generation(gen, mode="full"))
        stats["total_generations"] += 1

    # --- evaluations (small: eval_runs themselves) ---
    eval_runs, eval_run_ids = build_eval_run_ids(db, project_id)
    for er in eval_runs:
        yield _emit("evaluation", serialize_evaluation_run(er, mode="full"))
        stats["total_evaluations"] += 1

    # --- evaluation_metrics (medium) ---
    if eval_run_ids:
        for m in _drain(
            db.query(EvaluationRunMetric).filter(
                EvaluationRunMetric.evaluation_id.in_(eval_run_ids)
            )
        ):
            yield _emit("evaluation_metric", serialize_evaluation_metric_row(m))
            stats["total_evaluation_metrics"] += 1

    # --- evaluation_judge_runs (small) ---
    # Emitted before task_evaluations so the single-pass importer has the
    # old->new judge-run id map ready when it inserts task_evaluations
    # (TaskEvaluation.judge_run_id is NOT NULL, migration 043).
    if eval_run_ids:
        for jr in _drain(
            db.query(EvaluationJudgeRun).filter(
                EvaluationJudgeRun.evaluation_id.in_(eval_run_ids)
            )
        ):
            yield _emit("evaluation_judge_run", serialize_evaluation_judge_run_row(jr))
            stats["total_evaluation_judge_runs"] += 1

    # --- task_evaluations (very heavy: thousands of rows) ---
    if eval_run_ids:
        for te in _drain(
            db.query(TaskEvaluation).filter(
                TaskEvaluation.evaluation_id.in_(eval_run_ids)
            )
        ):
            yield _emit("task_evaluation", serialize_task_evaluation(te, mode="full"))
            stats["total_task_evaluations"] += 1

    # --- human_evaluation_configs (small) ---
    hec_ids: list[str] = []
    for c in _drain(
        db.query(HumanEvaluationConfig).filter(
            HumanEvaluationConfig.task_id.in_(task_id_subq)
        )
    ):
        hec_ids.append(c.id)
        yield _emit("human_evaluation_config", serialize_human_evaluation_config_row(c))
        stats["total_human_evaluation_configs"] += 1

    # --- human_evaluation_sessions (small) ---
    hes_ids: list[str] = []
    for s in _drain(
        db.query(HumanEvaluationSession).filter(
            HumanEvaluationSession.project_id == project_id
        )
    ):
        hes_ids.append(s.id)
        yield _emit("human_evaluation_session", serialize_human_evaluation_session_row(s))
        stats["total_human_evaluation_sessions"] += 1

    # --- human_evaluation_results (medium) ---
    if hec_ids:
        for r in _drain(
            db.query(HumanEvaluationResult).filter(
                HumanEvaluationResult.config_id.in_(hec_ids)
            )
        ):
            yield _emit("human_evaluation_result", serialize_human_evaluation_result_row(r))
            stats["total_human_evaluation_results"] += 1

    # --- preference_rankings (medium) ---
    if hes_ids:
        for p in _drain(
            db.query(PreferenceRanking).filter(
                PreferenceRanking.session_id.in_(hes_ids)
            )
        ):
            yield _emit("preference_ranking", serialize_preference_ranking_row(p))
            stats["total_preference_rankings"] += 1

    # --- likert_scale_evaluations (medium) ---
    if hes_ids:
        for lk in _drain(
            db.query(LikertScaleEvaluation).filter(
                LikertScaleEvaluation.session_id.in_(hes_ids)
            )
        ):
            yield _emit("likert_scale_evaluation", serialize_likert_scale_evaluation_row(lk))
            stats["total_likert_scale_evaluations"] += 1

    # --- korrektur_comments (roots first, then replies, for single-pass import) ---
    kc_base = db.query(KorrekturComment).filter(
        KorrekturComment.project_id == project_id
    )
    for kc in _drain(kc_base.filter(KorrekturComment.parent_id.is_(None))):
        yield _emit("korrektur_comment", serialize_korrektur_comment(kc))
    for kc in _drain(kc_base.filter(KorrekturComment.parent_id.isnot(None))):
        yield _emit("korrektur_comment", serialize_korrektur_comment(kc))

    # --- project_members (small) ---
    for member in (
        db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    ):
        yield _emit("project_member", serialize_project_member_row(member))
        stats["total_members"] += 1

    # --- task_assignments (medium; join through Task) ---
    for a in (
        db.query(TaskAssignment).join(Task).filter(Task.project_id == project_id).all()
    ):
        yield _emit("task_assignment", serialize_task_assignment_row(a))
        stats["total_assignments"] += 1

    # --- post_annotation_responses (medium) ---
    for r in _drain(
        db.query(PostAnnotationResponse).filter(
            PostAnnotationResponse.project_id == project_id
        )
    ):
        yield _emit("post_annotation_response", serialize_post_annotation_response_row(r))
        stats["total_post_annotation_responses"] += 1

    # --- end (structural completeness marker; replaces the byte-tail sentinel) ---
    yield _emit("end", {"statistics": stats, "export_complete": True})


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


# Maps an export format to (media_type, file_extension). The async download
# endpoint reads this to set Content-Type / Content-Disposition; the worker
# stores the blob opaquely, so it only needs the format string itself.
EXPORT_FORMAT_MEDIA_TYPES: dict[str, tuple[str, str]] = {
    "json": ("application/json", "json"),
    "csv": ("text/csv", "csv"),
    "tsv": ("text/tab-separated-values", "tsv"),
    "label_studio": ("application/json", "json"),
    "txt": ("text/plain", "txt"),
    "comprehensive": ("application/json", "json"),
    "ndjson": ("application/x-ndjson", "ndjson"),
    # gzip-compressed NDJSON. Stored as an opaque .gz blob (NOT served with
    # Content-Encoding: gzip — see plan Phase 3b) so the byte stream the client
    # downloads is exactly what the importer's gzip-magic detection decompresses.
    "ndjson_gz": ("application/gzip", "ndjson.gz"),
}

# Formats whose generator emits plain text that the worker must gzip-compress
# before storing. The generator itself stays format-agnostic (it yields the same
# NDJSON for "ndjson" and "ndjson_gz"); compression is a transport concern owned
# by the worker's multipart upload loop.
GZIPPED_EXPORT_FORMATS: frozenset[str] = frozenset({"ndjson_gz"})


def export_format_is_gzipped(fmt: str) -> bool:
    """True when the worker should gzip the generator output for ``fmt``."""
    return fmt in GZIPPED_EXPORT_FORMATS


def build_json_export_header_fields(db: Session, project) -> dict:
    """Build the top-level ``{"project": {...}}`` header for a JSON export.

    Extracted from ``GET /{project_id}/export?format=json`` so the worker's
    async export task produces a byte-identical header. The count queries pass
    whole-model classes (not column attributes) so they stay mockable in unit
    tests and issue cheap ``COUNT(*)`` round-trips; Task / EvaluationRun rows
    are loaded because their IDs feed the ``in_()`` filters.
    """
    project_id = project.id
    project_tasks_for_counts = (
        db.query(Task).filter(Task.project_id == project_id).all()
    )
    task_id_list = [t.id for t in project_tasks_for_counts]
    evaluation_runs_for_counts = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.project_id == project_id)
        .all()
    )
    eval_run_ids_for_counts = [er.id for er in evaluation_runs_for_counts]

    task_count = len(project_tasks_for_counts)
    annotation_count = (
        db.query(Annotation).filter(Annotation.project_id == project_id).count()
    )
    generation_count = (
        db.query(Generation).filter(Generation.task_id.in_(task_id_list)).count()
        if task_id_list
        else 0
    )
    task_evaluation_count = (
        db.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id.in_(eval_run_ids_for_counts))
        .count()
        if eval_run_ids_for_counts
        else 0
    )

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "created_at": (
                project.created_at.isoformat() if project.created_at else None
            ),
            "task_count": task_count,
            "annotation_count": annotation_count,
            "generation_count": generation_count,
            "evaluation_run_count": len(eval_run_ids_for_counts),
            "task_evaluation_count": task_evaluation_count,
            "label_config": project.label_config,
        },
    }


def select_export_generator(
    db: Session,
    project,
    fmt: str,
    task_ids: Optional[List[str]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Iterator[str]:
    """Return the chunk-yielding generator for ``fmt`` against ``project``.

    Single dispatch point shared by the async worker task so a given format
    always emits the same bytes. ``project`` is a loaded ``Project`` row (the
    json/txt generators read its title / description / metadata).

    ``task_ids`` restricts the export to a task subset (selected/filtered
    export). It is only supported for the ``json`` format — the other formats
    have no subset path — so a non-empty ``task_ids`` with any other format
    raises ``ValueError``. Raises ``ValueError`` for an unknown format too.

    ``progress_cb`` is only wired into the ``json`` generator (the path the UI
    Download uses); other formats stream without a progress signal, so their
    callers keep an indeterminate bar.
    """
    project_id = project.id
    if task_ids and fmt != "json":
        raise ValueError(
            f"Subset export (task_ids) is only supported for the json format, not {fmt!r}"
        )
    if fmt == "json":
        header_fields = build_json_export_header_fields(db, project)
        return stream_export_json(
            db,
            project_id,
            task_ids=task_ids,
            header_fields=header_fields,
            progress_cb=progress_cb,
        )
    if fmt in ("csv", "tsv"):
        delimiter = "," if fmt == "csv" else "\t"
        return stream_export_flat_csv(db, project_id, delimiter=delimiter)
    if fmt == "label_studio":
        return stream_export_label_studio(db, project_id)
    if fmt == "txt":
        return stream_export_txt(db, project_id, project.title, project.description)
    if fmt == "comprehensive":
        return stream_comprehensive_project_data_json(db, project_id)
    if fmt in ("ndjson", "ndjson_gz"):
        # Same text stream for both; the worker compresses when fmt is gzipped.
        return stream_export_ndjson(db, project_id)
    raise ValueError(f"Unsupported export format: {fmt!r}")
