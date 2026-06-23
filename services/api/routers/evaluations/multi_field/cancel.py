"""Evaluation cancellation endpoints (single + bulk) and the shared
`_cancel_runs` helper.

`_cancel_runs` lives here (not in `_common`) because both cancel handlers
call it; co-locating means `patch("routers.evaluations.multi_field.cancel.<name>")`
reaches both the handler and the helper's own internal references.
"""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


# ============= Cancellation =============
#
# Cancel sets `EvaluationRun.status='cancelled'` and `completed_at=now()`,
# and fails any child `EvaluationJudgeRun` still in `running`. It
# DELIBERATELY does NOT delete `task_evaluations` rows — partial results
# are preserved so a subsequent `force_rerun=False` (missing-only) trigger
# can reuse them. The new orchestrator's preload status filter includes
# `'cancelled'` so this works without extra wiring (see PR #94).
#
# The worker side is already plumbed for cancel: each cell sub-task does
# a parent-status check at entry and short-circuits if terminal; the
# `_bump_evaluation_counters` UPDATE filters out terminal parents so any
# late counter bump no-ops. So flipping status is enough — in-flight
# cells will drain within the duration of the LLM call they're holding.


def _cancel_runs(
    db: Session,
    *,
    run_ids: List[str],
    reason: str,
) -> CancelEvaluationResponse:
    """Cancel-runs helper used by both single and bulk endpoints. SQL
    mirrors the Phase-0 prod cleanup we did pre-deploy (see PR #94
    deploy plan). Uses raw text() so the `json::jsonb` cast survives
    under Postgres 18's FIPS-strict type coercion (eval_metadata is
    typed `json`, not `jsonb`)."""
    from sqlalchemy import text as _text

    if not run_ids:
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message="No runs to cancel.",
        )

    cancelled = db.execute(
        _text(
            """
            UPDATE evaluation_runs
               SET status = 'cancelled',
                   completed_at = NOW(),
                   error_message = COALESCE(error_message, :reason),
                   eval_metadata = (
                     jsonb_set(
                       jsonb_set(COALESCE(eval_metadata::jsonb, '{}'::jsonb),
                                 '{cancelled_via_api}', 'true'::jsonb),
                       '{cancel_reason}', to_jsonb(CAST(:reason AS text))
                     )
                   )::json
             WHERE id = ANY(:ids)
               AND status IN ('pending', 'running')
            RETURNING id
            """
        ),
        {"ids": run_ids, "reason": reason},
    )
    actually_cancelled = [row[0] for row in cancelled.fetchall()]

    if not actually_cancelled:
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message="No runs in pending/running state to cancel.",
        )

    failed_judge_runs = db.execute(
        _text(
            """
            UPDATE evaluation_judge_runs
               SET status = 'failed',
                   completed_at = NOW(),
                   error_message = COALESCE(error_message, :reason)
             WHERE evaluation_id = ANY(:ids) AND status = 'running'
            """
        ),
        {"ids": actually_cancelled, "reason": "Parent EvaluationRun cancelled"},
    ).rowcount

    preserved = db.execute(
        _text(
            "SELECT count(*) FROM task_evaluations WHERE evaluation_id = ANY(:ids)"
        ),
        {"ids": actually_cancelled},
    ).scalar()

    db.commit()

    return CancelEvaluationResponse(
        cancelled_run_ids=actually_cancelled,
        failed_child_judge_run_count=failed_judge_runs or 0,
        preserved_task_evaluation_count=preserved or 0,
        message=(
            f"Cancelled {len(actually_cancelled)} run(s); "
            f"{failed_judge_runs or 0} in-flight judge_run(s) marked failed; "
            f"{preserved or 0} task_evaluation row(s) preserved for "
            "missing-only re-trigger."
        ),
    )


@router.post(
    "/run/{evaluation_id}/cancel",
    response_model=CancelEvaluationResponse,
)
async def cancel_evaluation_run(
    http_request: Request,
    evaluation_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cancel a single in-flight evaluation run. Partial scores survive."""
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
    # Single-run cancel: allow the user who triggered the run to cancel
    # it, OR anyone with project EDIT permission. PROJECT_VIEW is too
    # permissive here (an annotator could cancel an admin's 6940-cell
    # eval); PROJECT_EDIT-only would block the user-cancels-own-run
    # case. The disjunction matches the symmetry users expect: "I can
    # cancel what I started."
    is_owner = evaluation.created_by == current_user.id
    has_edit = auth_service.check_project_access(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    )
    if not (is_owner or has_edit):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have permission to cancel this evaluation. "
                "Only the user who triggered the run or a user with project "
                "edit permission can cancel."
            ),
        )

    if evaluation.status in ("completed", "failed", "cancelled"):
        return CancelEvaluationResponse(
            cancelled_run_ids=[],
            failed_child_judge_run_count=0,
            preserved_task_evaluation_count=0,
            message=f"Evaluation is already terminal (status='{evaluation.status}'); nothing to cancel.",
        )

    reason = f"Cancelled via API by user {current_user.id}"
    return _cancel_runs(db, run_ids=[evaluation_id], reason=reason)


@router.post(
    "/projects/{project_id}/runs/cancel-all",
    response_model=CancelEvaluationResponse,
)
async def cancel_all_project_evaluations(
    http_request: Request,
    project_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cancel every in-flight (pending or running) evaluation on a project.

    Useful when an operator wants to stop a runaway re-trigger or
    multiple stuck runs at once. Per-run rows are preserved for
    missing-only re-trigger downstream.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    org_context = get_org_context_from_request(http_request)
    # Bulk cancel is strictly PROJECT_EDIT — it nukes every in-flight
    # run on the project regardless of who triggered them, so a
    # read-only viewer must not be able to fire it.
    if not auth_service.check_project_access(
        current_user, project, Permission.PROJECT_EDIT, db, org_context=org_context
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You don't have permission to bulk-cancel evaluations on "
                "this project (requires project edit permission)."
            ),
        )

    in_flight = (
        db.query(DBEvaluationRun.id)
        .filter(
            DBEvaluationRun.project_id == project_id,
            DBEvaluationRun.status.in_(("pending", "running")),
        )
        .all()
    )
    run_ids = [row[0] for row in in_flight]
    reason = (
        f"Bulk-cancelled via API by user {current_user.id} "
        f"(project {project_id})"
    )
    return _cancel_runs(db, run_ids=run_ids, reason=reason)

