"""Evaluation run dispatch endpoint (POST /run)."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)
# ``_stdjson`` is underscore-prefixed so the ``import *`` above skips it;
# the idempotency dispatch_hash in run_evaluation needs it explicitly.
from ._common import _stdjson  # noqa: F401
from models import User as DBUser


def _translate_annotator_model_ids(db, project_id, model_ids, annotator_user_ids):
    """Translate synthetic ``annotator:<display>`` model ids into annotator_user_ids.

    Results grids identify human-annotator cells with a synthetic
    ``annotator:<display>`` model id (see results/by_task_model.py); the per-cell
    "Neuevaluierung" button forwards that id in ``model_ids``. Those aren't LLM
    models, so the caller's model_ids scope check would 400 them. Resolve each
    display back to the annotator's user id the same way the grid builds it
    (pseudonym when ``use_pseudonym``, else name/username), fold them into
    ``annotator_user_ids``, and strip them from ``model_ids``. Returns the
    ``(model_ids, annotator_user_ids)`` pair (each ``None`` when it empties out).

    Raises 400 if a supplied display matches no annotator on the project — better
    a clear error than a silent unscoped re-eval of the whole project.
    """
    annotator_model_ids = [
        m for m in (model_ids or []) if m.startswith("annotator:")
    ]
    if not annotator_model_ids:
        return model_ids, annotator_user_ids

    wanted_displays = {m.split(":", 1)[1] for m in annotator_model_ids}
    annotator_rows = (
        db.query(
            DBUser.id,
            DBUser.username,
            DBUser.name,
            DBUser.pseudonym,
            DBUser.use_pseudonym,
        )
        .join(Annotation, Annotation.completed_by == DBUser.id)
        .join(Task, Annotation.task_id == Task.id)
        .filter(
            Task.project_id == project_id,
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .distinct()
    )
    resolved_ids = {
        r.id
        for r in annotator_rows
        if (
            r.pseudonym if (r.use_pseudonym and r.pseudonym) else (r.name or r.username)
        )
        in wanted_displays
    }
    if not resolved_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "annotator display(s) not found on this project: "
                f"{sorted(wanted_displays)}"
            ),
        )

    new_annotator_ids = list({*(annotator_user_ids or []), *resolved_ids}) or None
    new_model_ids = [m for m in model_ids if not m.startswith("annotator:")] or None
    return new_model_ids, new_annotator_ids


@router.post("/run", response_model=EvaluationRunResponse)
async def run_evaluation(
    http_request: Request,
    request: EvaluationRunRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Run evaluation with N:M field mapping support.

    Supports multiple prediction fields evaluated against multiple reference fields
    with different metrics per combination.
    """
    try:
        # Verify project exists
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{request.project_id}' not found",
            )

        # Extract organization context for API key resolution (Issue #1180)
        organization_id = resolve_user_org_for_project(current_user, project, db)

        # Check access permissions
        org_context = get_org_context_from_request(http_request)
        if not auth_service.check_project_access(
            current_user, project, Permission.PROJECT_VIEW, db, org_context=org_context
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to run evaluations on this project",
            )

        # Timed access window: the access group can only run evaluations while
        # the window is open (editors exempt). PROJECT_VIEW above admits
        # non-editors, so this gate is load-bearing here. No-op without a window.
        enforce_project_write_window(db, current_user, project)

        # Validate evaluation configs
        if not request.evaluation_configs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No evaluation configurations provided",
            )

        enabled_configs = [c for c in request.evaluation_configs if c.enabled]
        if not enabled_configs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No enabled evaluation configurations",
            )

        # The results grid forwards synthetic `annotator:<display>` model ids from
        # the per-cell "Neuevaluierung" button; translate them into
        # annotator_user_ids so the scope check below doesn't 400 them as unknown
        # LLM models.
        request.model_ids, request.annotator_user_ids = _translate_annotator_model_ids(
            db, request.project_id, request.model_ids, request.annotator_user_ids
        )

        # Scope-filter validation (issue #69). Reject silent no-ops where the
        # user supplies ids that don't correspond to anything on this project
        # — a silent zero-result run is worse than a 400 because it looks
        # like the worker hung. Same treatment for model_ids (existing gap).
        if request.annotator_user_ids:
            valid_annotator_ids = {
                uid for (uid,) in db.query(Annotation.completed_by)
                .join(Task, Annotation.task_id == Task.id)
                .filter(
                    Task.project_id == request.project_id,
                    Annotation.was_cancelled == False,  # noqa: E712
                )
                .distinct()
            }
            invalid_annotators = [
                uid for uid in request.annotator_user_ids if uid not in valid_annotator_ids
            ]
            if invalid_annotators:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "annotator_user_ids contains ids without annotations on "
                        f"this project: {invalid_annotators}"
                    ),
                )

        if request.model_ids:
            valid_model_ids = {
                mid for (mid,) in db.query(DBLLMResponse.model_id)
                .join(
                    DBResponseGeneration,
                    DBLLMResponse.generation_id == DBResponseGeneration.id,
                )
                .filter(DBResponseGeneration.project_id == request.project_id)
                .distinct()
            }
            invalid_models = [
                mid for mid in request.model_ids if mid not in valid_model_ids
            ]
            if invalid_models:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "model_ids contains ids without generations on "
                        f"this project: {invalid_models}"
                    ),
                )

        # Split configs into human-graded vs LLM-driven. Human-graded
        # metrics (e.g. korrektur_falloesung) have no worker; each writes
        # into a singleton ongoing EvaluationRun per (project, metric).
        # See services.evaluation.human_eval_runs.
        human_configs = [c for c in enabled_configs if is_human_graded_metric(c.metric)]
        llm_configs = [c for c in enabled_configs if not is_human_graded_metric(c.metric)]

        # Ensure the singleton run exists for every distinct human metric in
        # the request. Idempotent — re-clicking Run returns the same row.
        human_run_ids: List[str] = []
        for metric in {c.metric for c in human_configs}:
            human_run = get_or_create_human_eval_run(
                db, request.project_id, metric, current_user.id
            )
            human_run_ids.append(human_run.id)
        if human_run_ids:
            db.commit()

        # All-human request: nothing to dispatch to Celery. Return the
        # singleton's id as the evaluation_id so the frontend can navigate
        # straight to the ongoing human run.
        if not llm_configs:
            primary_human_id = human_run_ids[0]
            return EvaluationRunResponse(
                evaluation_id=primary_human_id,
                project_id=request.project_id,
                status="ongoing",
                message=(
                    "Human grading queue is ongoing "
                    f"({len(human_configs)} human-graded metric(s))"
                ),
                evaluation_configs_count=len(enabled_configs),
                task_id=None,
                started_at=datetime.now(),
                human_eval_run_ids=human_run_ids,
            )

        # Create evaluation record
        # Extract unique metrics from enabled configs as evaluation_type_ids
        evaluation_type_ids = list(set(c.metric for c in llm_configs))

        # Determine the actual model_id from generations in this project
        # Query the most common model_id from generations for this project
        # Join through ResponseGeneration which has direct project_id
        generation_model_query = (
            db.query(DBLLMResponse.model_id, func.count(DBLLMResponse.id).label("count"))
            .join(
                DBResponseGeneration,
                DBLLMResponse.generation_id == DBResponseGeneration.id,
            )
            .filter(DBResponseGeneration.project_id == request.project_id)
            .filter(DBLLMResponse.parse_status == "success")
            .group_by(DBLLMResponse.model_id)
            .order_by(func.count(DBLLMResponse.id).desc())
            .first()
        )

        # Use the most common model_id, or fallback to "unknown" if no generations exist
        evaluated_model_id = generation_model_query[0] if generation_model_query else "unknown"

        # (H) Top-level seed propagation: when the request carries a
        # top-level seed and a config doesn't already pin its own seed in
        # metric_parameters, inject the run-level seed there. Per-config
        # `metric_parameters.seed` wins for backward-compat (override of
        # override). This keeps the worker's _resolve_param tier list
        # unchanged while letting the trigger thread one seed across all
        # judges in the run.
        def _with_run_seed(cfg_dict: dict) -> dict:
            if request.seed == None:  # noqa: E711
                return cfg_dict
            params = dict(cfg_dict.get("metric_parameters") or {})
            if "seed" not in params:
                params["seed"] = request.seed
                cfg_dict = {**cfg_dict, "metric_parameters": params}
            return cfg_dict

        dispatched_configs = [_with_run_seed(c.dict()) for c in llm_configs]

        # Idempotency guard: if the same user just dispatched an
        # evaluation against this project with the SAME config payload
        # that's still in-flight, return that run's id instead of
        # spawning a duplicate. Without this, a double-click on the
        # "Run" button dispatched two chord-fan-outs that processed
        # every cell twice — at ZJS Fälle scale that silently doubled
        # the LLM bill. 30s window covers the accidental-double-click
        # case without blocking legitimate sequential re-triggers.
        #
        # Hash includes the config payload + scope filters so two
        # legitimate distinct evals on the same project (e.g. BLEU on
        # tasks 1-10 then ROUGE on tasks 11-20) don't collapse into
        # one. Uses sha1 over a stable JSON serialization; hash lands
        # in `eval_metadata.dispatch_hash` for lookup.
        from datetime import timedelta as _td
        dispatch_payload = {
            "configs": dispatched_configs,
            "task_ids": request.task_ids or [],
            "model_ids": request.model_ids or [],
            "annotator_user_ids": request.annotator_user_ids or [],
            "force_rerun": request.force_rerun,
        }
        dispatch_hash = hashlib.sha1(
            _stdjson.dumps(dispatch_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        # `datetime.now(timezone.utc)` matches the timezone-aware
        # `created_at` column (`DateTime(timezone=True)`); a naive
        # `datetime.now()` would compare local-clock-as-if-UTC and
        # silently break the 30s window on any non-UTC host.
        # Filter the hash match in Python rather than SQL: the column
        # is mapped as the generic `JSON` type (not `JSONB`), so the
        # SQLAlchemy `.astext` accessor isn't available. The 30s window
        # bounds the candidate set to a handful of rows per user/project,
        # so a Python-side scan is cheaper than adding a JSON index +
        # custom dialect SQL just for this lookup.
        recent_candidates = (
            db.query(DBEvaluationRun)
            .filter(
                DBEvaluationRun.project_id == request.project_id,
                DBEvaluationRun.created_by == current_user.id,
                DBEvaluationRun.status.in_(("pending", "running")),
                DBEvaluationRun.created_at >= datetime.now(timezone.utc) - _td(seconds=30),
            )
            .order_by(DBEvaluationRun.created_at.desc())
            .all()
        )
        recent_inflight = next(
            (
                r for r in recent_candidates
                if (r.eval_metadata or {}).get("dispatch_hash") == dispatch_hash
            ),
            None,
        )
        if recent_inflight is not None:
            return EvaluationRunResponse(
                evaluation_id=recent_inflight.id,
                project_id=request.project_id,
                status="already_running",
                message=(
                    "An evaluation by this user is already in flight on "
                    f"this project (id {recent_inflight.id}, status "
                    f"{recent_inflight.status}); returning that run instead "
                    "of dispatching a duplicate."
                ),
                evaluation_configs_count=len(enabled_configs),
                task_id=None,
                started_at=recent_inflight.created_at,
                human_eval_run_ids=human_run_ids,
            )

        evaluation = DBEvaluationRun(
            id=str(uuid.uuid4()),
            project_id=request.project_id,
            model_id=evaluated_model_id,
            evaluation_type_ids=evaluation_type_ids,
            metrics={},
            status="pending",
            created_at=datetime.now(timezone.utc),
            created_by=current_user.id,
            samples_evaluated=0,
            eval_metadata={
                "evaluation_type": "evaluation",
                "triggered_by": current_user.id,
                # Stable hash of the dispatch payload — used by the
                # idempotency lookup to distinguish two legitimately
                # different in-flight evals from a double-click on the
                # same one.
                "dispatch_hash": dispatch_hash,
                "evaluation_configs": dispatched_configs,
                "batch_size": request.batch_size,
                "label_config_version": request.label_config_version,
                "evaluated_model_id": evaluated_model_id,  # Track model in metadata
                "force_rerun": request.force_rerun,
                "organization_id": organization_id,
                "task_ids": request.task_ids,
                "model_ids": request.model_ids,
                "annotator_user_ids": request.annotator_user_ids,
                # (H) Run-level seed snapshotted on eval_metadata even when
                # it's None, for unambiguous post-hoc reproducibility.
                "_top_level_seed": request.seed,
                # Side-effect: human-graded singletons that were ensured for
                # this request, for traceability from the LLM run back to
                # the parallel ongoing human runs.
                "human_eval_run_ids": human_run_ids,
            },
        )

        db.add(evaluation)
        db.commit()

        # Dispatch Celery task. Using `kwargs=` instead of `args=` keeps the
        # call site robust to future parameter additions on
        # `tasks.run_evaluation`: a positional list silently mis-binds when
        # the worker signature is reordered, whereas kwargs are matched by
        # name. (D1: previously this was a 10-element positional list.)
        try:
            task = celery_app.send_task(
                "tasks.run_evaluation",
                kwargs={
                    "evaluation_id": evaluation.id,
                    "project_id": request.project_id,
                    "evaluation_configs": dispatched_configs,
                    "batch_size": request.batch_size,
                    "label_config_version": request.label_config_version,
                    "evaluate_missing_only": not request.force_rerun,
                    "organization_id": organization_id,
                    "task_ids": request.task_ids,
                    "model_ids": request.model_ids,
                    "annotator_user_ids": request.annotator_user_ids,
                },
                queue="evaluation",
            )

            # Update evaluation with task ID
            evaluation.eval_metadata["celery_task_id"] = task.id
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(evaluation, "eval_metadata")
            db.commit()

            logger.info(
                f"Dispatched evaluation task {task.id} for project {request.project_id}"
            )

        except Exception as e:
            logger.error(f"Failed to dispatch evaluation task: {str(e)}")
            evaluation.status = "failed"
            evaluation.error_message = f"Failed to dispatch task: {str(e)}"
            db.commit()
            raise

        return EvaluationRunResponse(
            evaluation_id=evaluation.id,
            project_id=request.project_id,
            status="started",
            message=f"Evaluation started with {len(enabled_configs)} configurations",
            evaluation_configs_count=len(enabled_configs),
            task_id=task.id if "task" in locals() else None,
            started_at=evaluation.created_at,
            human_eval_run_ids=human_run_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start evaluation: {str(e)}",
        )

