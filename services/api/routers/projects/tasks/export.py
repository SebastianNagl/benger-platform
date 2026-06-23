"""Bulk export endpoint (streaming JSON/CSV/TSV)."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


@router.post("/{project_id}/tasks/bulk-export")
def bulk_export_tasks(
    project_id: str,
    data: dict,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Bulk export tasks from a project.

    Streams the response chunk-by-chunk and uses `yield_per` on the heavy
    queries so peak memory stays bounded regardless of project size.
    Previously the handler loaded every task / annotation / generation /
    evaluation row into Python with `.all()`, built one nested dict, and
    `json.dumps(...)`-ed it with `indent=2` — that OOMKilled the API pod on
    2026-05-18 when a 581-task / 8k-generation / 57k-eval project was
    exported (1.5 GiB container limit).

    Also `def` (not `async def`) so FastAPI runs it in the threadpool — the
    sync DB iteration no longer blocks the event loop during the export.
    """
    task_ids = data.get("task_ids", [])
    format = data.get("format", "json")

    if format not in ("json", "csv", "tsv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # Project + access check up front (still uses the request-scoped session;
    # closes naturally when the threadpool worker returns).
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    # Capture scalars now — we'll reference them inside the generator after
    # the closure has been handed off to StreamingResponse.
    project_title = project.title
    exported_at_iso = datetime.now().isoformat()
    filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    from routers.projects._export_stream import (
        BATCH_SIZE as _BATCH_SIZE,
        build_batch_objs as _build_batch_objs_shared,
        stream_export_json,
    )
    from routers.projects.serializers import build_judge_model_lookup

    # Local closure over `db` so the CSV/TSV path below can keep its
    # existing 2-arg call signature.
    def _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
        return _build_batch_objs_shared(db, batch, eval_run_by_id, judge_model_lookup)

    # The streaming generators below capture the request-scoped `db` via
    # closure. FastAPI keeps the Depends(get_db) session open until the
    # response body is fully consumed (i.e. until the generator returns),
    # so iterating `yield_per` against it is safe. The per-iteration-session
    # pattern that fixes the WS/SSE leaks does NOT apply here: exports are
    # short-lived and continuously query the DB, not idle in transaction.

    def _json_stream():
        yield from stream_export_json(
            db,
            project_id,
            task_ids,
            header_fields={
                "project_id": project_id,
                "project_title": project_title,
                "exported_at": exported_at_iso,
            },
        )

    def _csv_or_tsv_stream(delimiter: str):
        """Stream CSV/TSV one task at a time. Each row is `task_id, task_data,
        is_labeled, annotation_count, generation_count, evaluation_count, created_at`
        (matches the legacy shape)."""
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter)
        writer.writerow([
            "task_id", "task_data", "is_labeled",
            "annotation_count", "generation_count", "evaluation_count",
            "created_at",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()

        eval_runs = db.query(EvaluationRun).filter(
            EvaluationRun.project_id == project_id
        ).all()
        eval_run_by_id = {er.id: er for er in eval_runs}
        judge_model_lookup = build_judge_model_lookup(eval_runs, db)

        task_q = db.query(Task).filter(
            Task.id.in_(task_ids), Task.project_id == project_id
        )

        def _write_obj(obj):
            writer.writerow([
                obj["id"],
                json.dumps(obj["data"]),
                obj["is_labeled"],
                len(obj["annotations"]),
                len(obj["generations"]),
                len(obj["evaluations"]),
                obj["created_at"],
            ])
            chunk = buf.getvalue()
            buf.seek(0)
            buf.truncate()
            return chunk

        batch: list = []
        for task in task_q.yield_per(_BATCH_SIZE):
            batch.append(task)
            if len(batch) >= _BATCH_SIZE:
                for obj in _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
                    yield _write_obj(obj)
                batch = []
        for obj in _build_batch_objs(batch, eval_run_by_id, judge_model_lookup):
            yield _write_obj(obj)

    from fastapi.responses import StreamingResponse

    if format == "json":
        gen, media_type, ext = _json_stream(), "application/json", "json"
    elif format == "csv":
        gen, media_type, ext = _csv_or_tsv_stream(","), "text/csv", "csv"
    else:  # tsv
        gen, media_type, ext = _csv_or_tsv_stream("\t"), "text/tab-separated-values", "tsv"

    filename = f"tasks_export_{project_id}_{filename_ts}.{ext}"
    return StreamingResponse(
        gen,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
