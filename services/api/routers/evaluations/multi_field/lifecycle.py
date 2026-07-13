"""Evaluation run lifecycle endpoints: pause / resume / retry (issue #198).

Evaluation parity with the generation lifecycle shipped in migration 063.
Semantics (all state flips are race-safe ``UPDATE … WHERE status IN (…)
RETURNING`` so a concurrent finalizer/cancel wins cleanly):

- **pause**  (``pending``/``running`` → ``paused``): flips status and stamps
  ``paused_at``. Cell sub-tasks check the parent status at entry and skip
  while paused; the chord finalizer no-ops on a paused parent, so partial
  ``task_evaluations`` survive exactly like cancel. Granularity is between
  cells — a cell already holding an LLM call finishes it (its row is kept).
- **resume** (``paused``/``cancelled`` → ``pending``): re-dispatches
  ``tasks.run_evaluation`` from the dispatch snapshot in ``eval_metadata``
  with ``evaluate_missing_only=True`` — the orchestrator preload reuses every
  completed cell, so only missing work re-runs. Resuming a cancelled run
  formalizes the manual "flip the SAME run id to pending + re-dispatch"
  operator procedure.
- **retry**  (``failed`` → ``pending``): same re-dispatch, increments
  ``retry_count``. Missing-only as well: rows that survived the failed
  attempt are reused.

Dispatch goes straight through ``celery_app.send_task`` — deliberately NOT
through the ``POST /run`` HTTP handler, whose per-user in-flight idempotency
guard would eat the re-dispatch.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)

from sqlalchemy import text as _sql_text
from sqlalchemy.orm.attributes import flag_modified


def _get_run_and_authorize(
    db: Session,
    http_request: Request,
    evaluation_id: str,
    current_user: User,
    action: str,
) -> DBEvaluationRun:
    """404/403 guard stack shared by all three lifecycle handlers.

    Permission mirrors single-run cancel: the user who triggered the run,
    OR anyone with project EDIT. See cancel.py for why PROJECT_VIEW is too
    permissive and EDIT-only too strict.
    """
    evaluation = (
        db.query(DBEvaluationRun)
        .filter(DBEvaluationRun.id == evaluation_id)
        .first()
    )
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation '{evaluation_id}' not found",
        )
    project = db.query(Project).filter(Project.id == evaluation.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent project '{evaluation.project_id}' not found",
        )
    org_context = get_org_context_from_request(http_request)
    is_owner = evaluation.created_by == current_user.id
    has_edit = auth_service.check_project_access(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    )
    if not (is_owner or has_edit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You don't have permission to {action} this evaluation. "
                "Only the user who triggered the run or a user with project "
                f"edit permission can {action}."
            ),
        )
    return evaluation


def _dispatch_snapshot_kwargs(evaluation: DBEvaluationRun) -> Dict[str, Any]:
    """Rebuild the ``tasks.run_evaluation`` kwargs from the dispatch snapshot
    ``POST /run`` stores in ``eval_metadata`` (configs, batch size, scope
    filters). Raises 409 when the run predates snapshotting — those runs
    can't be re-dispatched faithfully; the user re-triggers a fresh run.
    """
    meta = evaluation.eval_metadata or {}
    configs = meta.get("evaluation_configs")
    if not configs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This run has no dispatch snapshot (it predates config "
                "snapshotting), so it cannot be re-dispatched. Trigger a "
                "fresh evaluation instead — missing-only mode will reuse "
                "its completed cells."
            ),
        )
    return {
        "evaluation_id": evaluation.id,
        "project_id": evaluation.project_id,
        "evaluation_configs": configs,
        "batch_size": meta.get("batch_size") or 100,
        "label_config_version": meta.get("label_config_version"),
        # Always missing-only on resume/retry: reuse every completed cell.
        "evaluate_missing_only": True,
        "organization_id": meta.get("organization_id"),
        "task_ids": meta.get("task_ids"),
        "model_ids": meta.get("model_ids"),
        "annotator_user_ids": meta.get("annotator_user_ids"),
    }


def _redispatch(db: Session, evaluation: DBEvaluationRun, action: str) -> str:
    """Send ``tasks.run_evaluation`` for the (already pending-flipped) run and
    persist the new celery task id. On broker failure, mark the run failed
    (mirror of the ``POST /run`` dispatch except-branch) and re-raise.
    """
    kwargs = _dispatch_snapshot_kwargs(evaluation)
    try:
        task = celery_app.send_task(
            "tasks.run_evaluation", kwargs=kwargs, queue="evaluation"
        )
    except Exception as e:  # pragma: no cover - broker down
        logger.error(f"Failed to dispatch evaluation {action}: {e}")
        evaluation.status = "failed"
        evaluation.error_message = f"Failed to dispatch {action}: {e}"
        db.commit()
        raise
    meta = dict(evaluation.eval_metadata or {})
    meta["celery_task_id"] = task.id
    meta[f"{action}d_at"] = datetime.now(timezone.utc).isoformat()
    evaluation.eval_metadata = meta
    flag_modified(evaluation, "eval_metadata")
    db.commit()
    logger.info(
        f"Evaluation {evaluation.id}: {action} dispatched celery task {task.id}"
    )
    return task.id


@router.post(
    "/run/{evaluation_id}/pause",
    response_model=EvaluationLifecycleResponse,
)
async def pause_evaluation_run(
    http_request: Request,
    evaluation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Pause an in-flight evaluation run. Partial scores survive; resume
    continues missing-only."""
    evaluation = _get_run_and_authorize(
        db, http_request, evaluation_id, current_user, "pause"
    )
    previous = evaluation.status
    row = db.execute(
        _sql_text(
            """
            UPDATE evaluation_runs
               SET status = 'paused', paused_at = NOW()
             WHERE id = :id AND status IN ('pending', 'running')
            RETURNING id
            """
        ),
        {"id": evaluation_id},
    ).fetchone()
    db.commit()
    if not row:
        db.refresh(evaluation)
        return EvaluationLifecycleResponse(
            evaluation_id=evaluation_id,
            action="pause",
            changed=False,
            previous_status=evaluation.status,
            status=evaluation.status,
            retry_count=evaluation.retry_count,
            message=(
                f"Run is '{evaluation.status}' — only pending/running runs "
                "can be paused."
            ),
        )
    db.refresh(evaluation)
    return EvaluationLifecycleResponse(
        evaluation_id=evaluation_id,
        action="pause",
        changed=True,
        previous_status=previous,
        status="paused",
        retry_count=evaluation.retry_count,
        message=(
            "Run paused. In-flight cells drain without new judge calls; "
            "completed scores are preserved. Resume to continue "
            "missing-only."
        ),
    )


@router.post(
    "/run/{evaluation_id}/resume",
    response_model=EvaluationLifecycleResponse,
)
async def resume_evaluation_run(
    http_request: Request,
    evaluation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Resume a paused (or continue a cancelled) run: same run id, re-dispatch
    missing-only so completed cells are reused."""
    evaluation = _get_run_and_authorize(
        db, http_request, evaluation_id, current_user, "resume"
    )
    previous = evaluation.status
    # Snapshot guard BEFORE flipping state so a snapshot-less run isn't
    # left stranded in 'pending' with nothing dispatched.
    _dispatch_snapshot_kwargs(evaluation)
    row = db.execute(
        _sql_text(
            """
            UPDATE evaluation_runs
               SET status = 'pending', paused_at = NULL,
                   completed_at = NULL, error_message = NULL
             WHERE id = :id AND status IN ('paused', 'cancelled')
            RETURNING id
            """
        ),
        {"id": evaluation_id},
    ).fetchone()
    db.commit()
    if not row:
        db.refresh(evaluation)
        return EvaluationLifecycleResponse(
            evaluation_id=evaluation_id,
            action="resume",
            changed=False,
            previous_status=evaluation.status,
            status=evaluation.status,
            retry_count=evaluation.retry_count,
            message=(
                f"Run is '{evaluation.status}' — only paused/cancelled runs "
                "can be resumed."
            ),
        )
    db.refresh(evaluation)
    task_id = _redispatch(db, evaluation, "resume")
    return EvaluationLifecycleResponse(
        evaluation_id=evaluation_id,
        action="resume",
        changed=True,
        previous_status=previous,
        status="pending",
        retry_count=evaluation.retry_count,
        celery_task_id=task_id,
        message=(
            "Run resumed (missing-only): completed cells are reused, only "
            "missing work re-runs."
        ),
    )


@router.post(
    "/run/{evaluation_id}/retry",
    response_model=EvaluationLifecycleResponse,
)
async def retry_evaluation_run(
    http_request: Request,
    evaluation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Retry a failed run: same run id, missing-only re-dispatch, bumps
    retry_count."""
    evaluation = _get_run_and_authorize(
        db, http_request, evaluation_id, current_user, "retry"
    )
    previous = evaluation.status
    _dispatch_snapshot_kwargs(evaluation)  # 409 before any state change
    row = db.execute(
        _sql_text(
            """
            UPDATE evaluation_runs
               SET status = 'pending', retry_count = retry_count + 1,
                   paused_at = NULL, completed_at = NULL, error_message = NULL
             WHERE id = :id AND status = 'failed'
            RETURNING retry_count
            """
        ),
        {"id": evaluation_id},
    ).fetchone()
    db.commit()
    if not row:
        db.refresh(evaluation)
        return EvaluationLifecycleResponse(
            evaluation_id=evaluation_id,
            action="retry",
            changed=False,
            previous_status=evaluation.status,
            status=evaluation.status,
            retry_count=evaluation.retry_count,
            message=(
                f"Run is '{evaluation.status}' — only failed runs can be "
                "retried."
            ),
        )
    db.refresh(evaluation)
    task_id = _redispatch(db, evaluation, "retry")
    return EvaluationLifecycleResponse(
        evaluation_id=evaluation_id,
        action="retry",
        changed=True,
        previous_status=previous,
        status="pending",
        retry_count=row[0],
        celery_task_id=task_id,
        message=(
            f"Retry #{row[0]} dispatched (missing-only): surviving cells are "
            "reused, failed/missing work re-runs."
        ),
    )
