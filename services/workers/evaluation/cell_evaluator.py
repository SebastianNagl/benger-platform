"""Cell-level evaluation task bodies (worker).

Extracted from ``services/workers/tasks.py`` as part of the structural
decomposition of that module. Behaviour-preserving move: each function body is
byte-identical to the original; references to ``tasks``-module globals
(``SessionLocal``, ``logger``, the per-cell helpers) are re-bound at
the top of each ``_impl`` from the ``tasks`` module **at call time**, so test
monkeypatches like ``patch("tasks.SessionLocal")`` keep applying and the import
graph stays one-way (``tasks`` imports this module; this module imports
``tasks`` only lazily inside the functions).

The ``@app.task`` wrappers (and every per-cell helper they call) stay in
``tasks.py`` — only the ~1100-line bodies live here. The registered task names
(``tasks.evaluate_generation_cell`` / ``tasks.evaluate_annotation_cell``) are
unchanged.
"""
from typing import Any, Dict, List, Optional  # noqa: F401  (used by the bodies)


def evaluate_generation_cell_impl(
    self,
    evaluation_id: str,
    task_id: str,
    generation_id: str,
    project_id: str,
    configs_for_cell: List[Dict[str, Any]],
    judge_run_ids_by_config: Dict[str, List[Dict[str, Any]]],
    default_judge_run_id: str,
    organization_id: Optional[str],
    triggered_by_user_id: str,
    label_config_version: Optional[str] = None,
    already_evaluated_field_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Per-(task, generation) sub-task dispatched by the eval orchestrator.

    Loads the generation, task (and ground-truth annotation when needed),
    reconstructs its own LLM judge evaluators per process, runs all
    `configs_for_cell` × field_pairs × judges, and writes the resulting
    TaskEvaluation rows via `ON CONFLICT DO NOTHING` so retries are
    idempotent. At the end, atomically bumps the parent EvaluationRun's
    `samples_evaluated`/`samples_passed`/`samples_failed` counters.

    Returns a small breadcrumb dict for the chord header; the finalizer
    doesn't consume the return value — it reads from the DB.
    """
    # Resolve tasks-module globals at call time: keeps the import one-way
    # (tasks -> cell_evaluator, never back) and preserves test monkeypatches
    # like patch("tasks.SessionLocal") / patch("tasks._record_cell_attempt").
    import tasks

    SessionLocal = tasks.SessionLocal
    logger = tasks.logger
    _CELL_ATTEMPT_LIMIT = tasks._CELL_ATTEMPT_LIMIT
    _build_multidim_judge_row_metrics = tasks._build_multidim_judge_row_metrics
    _build_sample_evaluator_for_cell = tasks._build_sample_evaluator_for_cell
    _bulk_upsert_task_evaluations = tasks._bulk_upsert_task_evaluations
    _bump_evaluation_counters = tasks._bump_evaluation_counters
    _classify_cell_failure = tasks._classify_cell_failure
    _extract_field_value_from_annotation = tasks._extract_field_value_from_annotation
    _extract_field_value_from_parsed_annotation = tasks._extract_field_value_from_parsed_annotation
    _get_insensitive = tasks._get_insensitive
    _llm_judge_columns_from_result = tasks._llm_judge_columns_from_result
    _normalize_field_key = tasks._normalize_field_key
    _publish_progress = tasks._publish_progress
    _reconstruct_judge_evaluators_for_cell = tasks._reconstruct_judge_evaluators_for_cell
    _record_cell_attempt = tasks._record_cell_attempt
    _record_cell_failure_reason = tasks._record_cell_failure_reason

    import uuid as _gen_uuid

    db = SessionLocal()
    try:
        from models import EvaluationRun, Generation
        from project_models import Annotation, Task

        # Parent-status short-circuit. The legacy bundled task checked
        # `EvaluationRun.status` at the top of each iteration and bailed
        # if the user/admin cancelled mid-run; with chord fan-out, the
        # ~6940 cells are already in-flight when cancel happens, so each
        # sub-task must re-check itself or the cancellation does nothing
        # but mark the parent terminal. Avoid burning LLM quota on
        # cancelled work.
        parent_status = db.query(EvaluationRun.status).filter(
            EvaluationRun.id == evaluation_id
        ).scalar()
        # 'paused' (issue #198) skips like the terminal states: cells drain
        # without burning judge quota, the chord finalizer no-ops on paused,
        # and resume re-dispatches whatever is still missing.
        if parent_status in ("cancelled", "failed", "completed", "paused"):
            return {"status": "skipped", "reason": f"parent_{parent_status}",
                    "evaluation_id": evaluation_id, "generation_id": generation_id}

        # Poison-cell guard: cap broker-level redeliveries via Redis
        # counter so a deterministic-OOM cell doesn't loop forever.
        attempts = _record_cell_attempt(evaluation_id, f"gen:{generation_id}")
        if attempts > _CELL_ATTEMPT_LIMIT:
            logger.error(
                f"evaluate_generation_cell: poison cell — gen {generation_id} "
                f"hit attempt #{attempts} for eval {evaluation_id}; bailing"
            )
            _record_cell_failure_reason(db, evaluation_id, "poison_cell_max_attempts")
            _bump_evaluation_counters(
                db, evaluation_id=evaluation_id,
                samples_evaluated=0, samples_passed=0, samples_failed=1,
            )
            db.commit()
            return {"status": "poisoned", "evaluation_id": evaluation_id,
                    "generation_id": generation_id, "attempts": attempts}

        gen = db.query(Generation).filter(Generation.id == generation_id).first()
        if not gen:
            logger.warning(
                f"evaluate_generation_cell: generation {generation_id} not found; "
                f"skipping (eval {evaluation_id})"
            )
            return {"status": "skipped", "reason": "generation_not_found",
                    "evaluation_id": evaluation_id, "generation_id": generation_id}
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning(
                f"evaluate_generation_cell: task {task_id} not found; skipping"
            )
            return {"status": "skipped", "reason": "task_not_found",
                    "evaluation_id": evaluation_id, "task_id": task_id}

        uses_annotation_fields = any(
            any(not ref.startswith("task.") for ref in c.get("reference_fields", []))
            for c in configs_for_cell
        )
        ground_truth_annotation = None
        if uses_annotation_fields:
            ann = (
                db.query(Annotation)
                .filter(Annotation.task_id == task_id, Annotation.was_cancelled == False)  # noqa: E712
                .first()
            )
            ground_truth_annotation = ann

        # Reconstruct evaluators + sample_evaluator scoped to this cell's configs.
        judge_runs_by_config, llm_judge_evaluators = _reconstruct_judge_evaluators_for_cell(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id,
            db=db,
        )
        sample_evaluator = _build_sample_evaluator_for_cell(evaluation_id, configs_for_cell)

        # Pre-normalize the orchestrator-supplied "already done" set so the
        # per-field-pair skip check below is a cheap set membership lookup
        # instead of re-normalizing each iteration. Skipping here avoids the
        # wasted LLM-judge call that would otherwise happen (the ON CONFLICT
        # DO NOTHING insert would drop the row, but the LLM call already
        # happened — burning quota). Mirror of the legacy skip at
        # ex-`tasks.py:2906-2909`.
        _already_done_normalized = {
            _normalize_field_key(fk, is_annotation=False)
            for fk in (already_evaluated_field_keys or [])
        }

        # Local accumulators (returned to caller via counter bump at end).
        sample_results: List[Dict[str, Any]] = []
        local_samples_evaluated = 0
        local_samples_passed = 0
        local_samples_failed = 0

        # Inner loop — lifted from orchestrator's per-generation block at
        # ex-`tasks.py` ~lines 2882-3355. Logic preserved as-is except for:
        #   * `evaluation_id` is a closure capture (not orchestrator-local)
        #   * `evaluation.samples_evaluated = ...` per-batch commits removed
        #     (counter bump happens atomically at end via _bump_evaluation_counters)
        #   * Sample rows are accumulated and bulk-upserted at end
        for config in configs_for_cell:
            config_id = config.get("id", "unknown")
            metric = config.get("metric", "")
            prediction_fields = config.get("prediction_fields", [])
            reference_fields = config.get("reference_fields", [])

            if metric.startswith("korrektur_"):
                continue

            for pred_field in prediction_fields:
                if pred_field.startswith("human:") or pred_field == "__all_human__":
                    continue

                for ref_field in reference_fields:
                    field_key = f"{config_id}|{pred_field}|{ref_field}"

                    # Per-field-pair skip when this cell already has a row
                    # for this (config, pred, ref). Lifted from legacy
                    # ex-`tasks.py:2906-2909`. Without this, partial-cell
                    # retries would re-call the LLM judge for already-done
                    # field_keys (ON CONFLICT only stops the INSERT, not
                    # the upstream LLM call).
                    if _normalize_field_key(field_key, is_annotation=False) in _already_done_normalized:
                        continue

                    # Ground truth extraction.
                    if ref_field.startswith("task."):
                        data_field = ref_field[5:]
                        ground_truth = task.data.get(data_field) if task.data else None
                    elif ground_truth_annotation:
                        ground_truth = _extract_field_value_from_annotation(
                            ground_truth_annotation.result or [], ref_field
                        )
                        if ground_truth is None and task.data and ref_field in task.data:
                            ground_truth = task.data.get(ref_field)
                    else:
                        ground_truth = task.data.get(ref_field) if task.data else None
                    if ground_truth is None:
                        logger.warning(
                            f"Evaluation skip: reference field '{ref_field}' not found "
                            f"for task {task.id} (config {config_id})"
                        )
                        continue

                    # Prediction extraction.
                    base_field = pred_field
                    if pred_field.startswith("model:"):
                        base_field = pred_field[6:]
                    if pred_field == "__all_model__":
                        prediction = gen.response_content
                    else:
                        prediction = _extract_field_value_from_parsed_annotation(
                            gen.parsed_annotation, base_field
                        )
                        if prediction is None and gen.response_content:
                            prediction = gen.response_content
                    if prediction is None:
                        logger.warning(
                            f"Evaluation skip: prediction field '{pred_field}' not found "
                            f"for task {task.id}, model {gen.model_id} (config {config_id})"
                        )
                        continue

                    allow_unparsed = pred_field == "__all_model__"
                    try:
                        # Terminal-error row when an llm_judge_* config has no init'd evaluator.
                        if metric.startswith("llm_judge_") and config_id not in llm_judge_evaluators:
                            sample_results.append({
                                "id": str(_gen_uuid.uuid4()),
                                "evaluation_id": evaluation_id,
                                "judge_run_id": default_judge_run_id,
                                "task_id": task.id,
                                "generation_id": gen.id,
                                "field_name": field_key,
                                "evaluation_config_id": config_id,
                                "answer_type": "text",
                                "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                "prediction": str(prediction)[:1000] if prediction else "",
                                "metrics": {
                                    metric: {
                                        "value": None,
                                        "method": metric,
                                        "error": (
                                            "LLM judge evaluator not initialized for config "
                                            f"{config_id} — likely missing API key for the "
                                            "triggering user/org. Run skipped this metric."
                                        ),
                                        "details": {},
                                    },
                                },
                                "passed": False,
                                "error_message": (
                                    f"LLM judge evaluator not initialized for config {config_id}"
                                ),
                            })
                            local_samples_evaluated += 1
                            local_samples_failed += 1
                            continue

                        if metric.startswith("llm_judge_") and config_id in llm_judge_evaluators:
                            # ── Multi-judge / multi-run fan-out (intra-cell) ──
                            per_judge_results: List[Dict[str, Any]] = []
                            context = (
                                _get_insensitive(task.data, "text")
                                or _get_insensitive(task.data, "input")
                                or _get_insensitive(task.data, "sachverhalt")
                                or ""
                            )
                            eval_ground_truth = str(ground_truth) if ground_truth else ""
                            if metric == "llm_judge_falloesung" and task.data:
                                muster = (
                                    _get_insensitive(task.data, "musterloesung")
                                    or _get_insensitive(task.data, "musterlösung")
                                )
                                if muster:
                                    eval_ground_truth = str(muster)

                            criterion = metric.replace("llm_judge_", "")
                            if criterion in ("custom", "overall"):
                                criterion = "correctness"

                            for jr_entry in judge_runs_by_config.get(config_id, []):
                                jr_evaluator = jr_entry["evaluator"]
                                jr_id = jr_entry["judge_run_id"]
                                jr_judge_model = jr_entry["judge_model_id"]
                                jr_run_index = jr_entry["run_index"]

                                if jr_evaluator is None:
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": {
                                            metric: {
                                                "value": None,
                                                "method": metric,
                                                "error": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                                "details": {},
                                            },
                                        },
                                        "passed": False,
                                        "error_message": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                    })
                                    continue

                                multidim_mode = (
                                    metric != "llm_judge_falloesung"
                                    and getattr(jr_evaluator, "is_multidim_mode", lambda: False)()
                                )

                                if metric == "llm_judge_falloesung":
                                    try:
                                        from benger_extended.workers import (
                                            get_falloesung_bulk_compute_fn,
                                        )
                                    except ImportError as exc:
                                        raise RuntimeError(
                                            "Metric 'llm_judge_falloesung' requires the "
                                            "benger_extended package; it is not installed."
                                        ) from exc
                                    falloesung_bulk_fn = get_falloesung_bulk_compute_fn()
                                    sachverhalt = (
                                        _get_insensitive(task.data, "sachverhalt")
                                        if task.data
                                        else ""
                                    )
                                    result = falloesung_bulk_fn(
                                        ai_service=jr_evaluator.ai_service,
                                        judge_model=jr_evaluator.judge_model,
                                        temperature=jr_evaluator.temperature,
                                        max_tokens=jr_evaluator.max_tokens,
                                        sachverhalt=str(sachverhalt) if sachverhalt else "",
                                        musterloesung=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        thinking_budget=getattr(jr_evaluator, "thinking_budget", None),
                                        reasoning_effort=getattr(jr_evaluator, "reasoning_effort", None),
                                    )
                                elif multidim_mode:
                                    # Flatten the model's per-field output
                                    # (parsed_annotation is in label-studio
                                    # shape) so the user's prompt can
                                    # reference {{kurzantwort}} /
                                    # {{begruendung}} directly without
                                    # field_mappings.
                                    from annotation_utils import extract_all_field_values
                                    gen_field_outputs = (
                                        extract_all_field_values(gen.parsed_annotation)
                                        if getattr(gen, "parsed_annotation", None)
                                        else {}
                                    )
                                    result = jr_evaluator._evaluate_multidim_single_call(
                                        context=context,
                                        ground_truth=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        task_data=task.data,
                                        field_outputs=gen_field_outputs,
                                    )
                                else:
                                    result = jr_evaluator._evaluate_single_criterion(
                                        context=context,
                                        ground_truth=eval_ground_truth,
                                        prediction=str(prediction) if prediction else "",
                                        criterion=criterion,
                                        task_data=task.data,
                                    )

                                judge_prompts = (
                                    result.pop("_judge_prompts_used", None)
                                    if result
                                    else None
                                )

                                if multidim_mode:
                                    error_msg = (
                                        result.get("error_message")
                                        if result and result.get("error")
                                        else None
                                    )
                                    metrics_dict, normalized = _build_multidim_judge_row_metrics(
                                        result, metric, error_msg,
                                    )
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": metrics_dict,
                                        "passed": (normalized or 0.0) >= 0.5,
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **_llm_judge_columns_from_result(result),
                                    })
                                    continue

                                raw_score = result.get("score") if result is not None else None
                                error_msg = None
                                if raw_score is not None:
                                    if jr_evaluator.score_scale == "0-1":
                                        score = raw_score
                                    elif jr_evaluator.score_scale == "0-100":
                                        score = raw_score / 100.0
                                    else:
                                        score = (raw_score - 1) / 4
                                else:
                                    score = None
                                    error_msg = (
                                        (result.get("error_message") if result else None)
                                        or "LLM judge evaluation failed"
                                    )
                                    logger.warning(
                                        f"LLM judge {jr_judge_model} run {jr_run_index} returned None "
                                        f"for task {task.id}, field {field_key}"
                                    )

                                if metric == "llm_judge_falloesung":
                                    from benger_extended.workers.falloesung_tasks import (
                                        build_falloesung_row_dict,
                                    )
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "annotation_id": None,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **build_falloesung_row_dict(result=result, error_message=error_msg),
                                    })
                                else:
                                    per_judge_results.append({
                                        "id": str(_gen_uuid.uuid4()),
                                        "evaluation_id": evaluation_id,
                                        "judge_run_id": jr_id,
                                        "task_id": task.id,
                                        "generation_id": gen.id,
                                        "field_name": field_key,
                                        "evaluation_config_id": config_id,
                                        "answer_type": "text",
                                        "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                        "prediction": str(prediction)[:1000] if prediction else "",
                                        "metrics": {
                                            metric: score,
                                            "raw_score": raw_score,
                                            f"{metric}_response": result,
                                            **(
                                                {f"{metric}_grade_points": result["grade_points"]}
                                                if result and result.get("grade_points") is not None
                                                else {}
                                            ),
                                            **(
                                                {f"{metric}_passed": 1.0 if result["passed"] else 0.0}
                                                if result and "passed" in result
                                                else {}
                                            ),
                                        },
                                        "passed": (
                                            result.get("passed", score > 0.5)
                                            if result and "passed" in result
                                            else (score > 0.5 if score is not None else False)
                                        ),
                                        "error_message": error_msg,
                                        "judge_prompts_used": judge_prompts,
                                        **_llm_judge_columns_from_result(result),
                                    })

                            for sr in per_judge_results:
                                sample_results.append(sr)
                                local_samples_evaluated += 1
                                if sr["passed"]:
                                    local_samples_passed += 1
                                else:
                                    local_samples_failed += 1
                            continue

                        # Deterministic metric (BLEU/ROUGE/METEOR/etc.) — SampleEvaluator path.
                        sample_result = sample_evaluator.evaluate_sample(
                            task_id=task.id,
                            field_name=field_key,
                            ground_truth=ground_truth,
                            prediction=prediction,
                            metrics_to_compute=[metric],
                            generation_id=gen.id,
                            parse_status=gen.parse_status,
                            allow_unparsed=allow_unparsed,
                        )
                        if isinstance(sample_result, dict):
                            sample_result["judge_run_id"] = default_judge_run_id
                            # Issue #111 / migration 057: discrete config-id carrier.
                            sample_result["evaluation_config_id"] = config_id

                        sample_results.append(sample_result)
                        local_samples_evaluated += 1
                        if sample_result.get("passed"):
                            local_samples_passed += 1
                        else:
                            local_samples_failed += 1

                    except ValueError as e:
                        logger.warning(f"Skipping sample: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Error evaluating sample: {e}")
                        sample_results.append({
                            "id": str(_gen_uuid.uuid4()),
                            "evaluation_id": evaluation_id,
                            "judge_run_id": default_judge_run_id,
                            "task_id": task.id,
                            "generation_id": gen.id,
                            "field_name": field_key,
                            "evaluation_config_id": config_id,
                            "answer_type": "text",
                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                            "prediction": str(prediction)[:1000] if prediction else "",
                            "metrics": {},
                            "passed": False,
                            "error_message": str(e),
                        })
                        local_samples_evaluated += 1
                        local_samples_failed += 1

        # Bulk upsert + atomic counter bump. One commit per sub-task.
        # Bump by the *actually inserted* row count (from RETURNING),
        # not by the locally-tallied counts. On Celery message
        # redelivery, all rows conflict and `n_inserted == 0`, so the
        # redelivered task contributes nothing to the parent counters
        # — defense against the `acks_late=True` double-bump path.
        n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations(db, sample_results)
        _bump_evaluation_counters(
            db,
            evaluation_id=evaluation_id,
            samples_evaluated=n_inserted,
            samples_passed=n_passed,
            samples_failed=n_failed,
        )
        db.commit()
        # Tell the API WS handler this cell landed so it can push a
        # `tick` to connected EvaluationResults clients. The handler
        # subscribes to `evaluation:progress:{project_id}` and re-fetches
        # the task-model view on each tick.
        if n_inserted > 0:
            _publish_progress(
                f"evaluation:progress:{project_id}",
                {
                    "type": "cell_complete",
                    "evaluation_id": evaluation_id,
                    "task_id": task_id,
                    "generation_id": generation_id,
                    "samples_added": n_inserted,
                },
            )
        return {
            "status": "ok",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "generation_id": generation_id,
            "samples_added": n_inserted,
            "samples_passed": n_passed,
            "samples_failed": n_failed,
        }
    except Exception as e:
        logger.error(
            f"evaluate_generation_cell failed (eval {evaluation_id}, gen {generation_id}): {e}",
            exc_info=True,
        )
        db.rollback()
        # Don't propagate — the chord finalizer must still fire. Best-effort
        # increment of `samples_failed` and record the failure reason so
        # the UI can surface *why* the cell silently produced no row.
        try:
            _record_cell_failure_reason(db, evaluation_id, _classify_cell_failure(e))
            _bump_evaluation_counters(
                db,
                evaluation_id=evaluation_id,
                samples_evaluated=0,
                samples_passed=0,
                samples_failed=1,
            )
            db.commit()
        except Exception as bump_err:
            logger.error(f"Failed to bump failed counter: {bump_err}")
        return {
            "status": "error",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "generation_id": generation_id,
            "error": str(e),
        }
    finally:
        db.close()

def evaluate_annotation_cell_impl(
    self,
    evaluation_id: str,
    task_id: str,
    annotation_id: str,
    project_id: str,
    configs_for_cell: List[Dict[str, Any]],
    judge_run_ids_by_config: Dict[str, List[Dict[str, Any]]],
    default_judge_run_id: str,
    organization_id: Optional[str],
    triggered_by_user_id: str,
    already_evaluated_field_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Per-(task, annotation) sub-task dispatched by the eval orchestrator.

    Mirror of `evaluate_generation_cell` for the human-annotation
    evaluation path (configs whose `prediction_fields` contain
    `human:<field>` or `__all_human__`). Same structure: load + reconstruct
    + run inner block + bulk upsert + atomic counter bump.
    """
    # Resolve tasks-module globals at call time: keeps the import one-way
    # (tasks -> cell_evaluator, never back) and preserves test monkeypatches
    # like patch("tasks.SessionLocal") / patch("tasks._record_cell_attempt").
    import tasks

    SessionLocal = tasks.SessionLocal
    logger = tasks.logger
    _CELL_ATTEMPT_LIMIT = tasks._CELL_ATTEMPT_LIMIT
    _build_multidim_judge_row_metrics = tasks._build_multidim_judge_row_metrics
    _build_sample_evaluator_for_cell = tasks._build_sample_evaluator_for_cell
    _bulk_upsert_task_evaluations = tasks._bulk_upsert_task_evaluations
    _bump_evaluation_counters = tasks._bump_evaluation_counters
    _classify_cell_failure = tasks._classify_cell_failure
    _extract_field_value_from_annotation = tasks._extract_field_value_from_annotation
    _get_insensitive = tasks._get_insensitive
    _llm_judge_columns_from_result = tasks._llm_judge_columns_from_result
    _normalize_field_key = tasks._normalize_field_key
    _publish_progress = tasks._publish_progress
    _reconstruct_judge_evaluators_for_cell = tasks._reconstruct_judge_evaluators_for_cell
    _record_cell_attempt = tasks._record_cell_attempt
    _record_cell_failure_reason = tasks._record_cell_failure_reason

    import uuid as _ann_uuid

    db = SessionLocal()
    try:
        from models import EvaluationRun
        from project_models import Annotation, Task
        from annotation_utils import extract_all_field_values as _extract_all_fields
        from eval_field_classification import classify_pred_fields

        # Parent-status short-circuit — mirror of evaluate_generation_cell
        # (incl. 'paused', issue #198).
        parent_status = db.query(EvaluationRun.status).filter(
            EvaluationRun.id == evaluation_id
        ).scalar()
        if parent_status in ("cancelled", "failed", "completed", "paused"):
            return {"status": "skipped", "reason": f"parent_{parent_status}",
                    "evaluation_id": evaluation_id, "annotation_id": annotation_id}

        # Poison-cell guard — mirror of evaluate_generation_cell.
        attempts = _record_cell_attempt(evaluation_id, f"ann:{annotation_id}")
        if attempts > _CELL_ATTEMPT_LIMIT:
            logger.error(
                f"evaluate_annotation_cell: poison cell — ann {annotation_id} "
                f"hit attempt #{attempts} for eval {evaluation_id}; bailing"
            )
            _record_cell_failure_reason(db, evaluation_id, "poison_cell_max_attempts")
            _bump_evaluation_counters(
                db, evaluation_id=evaluation_id,
                samples_evaluated=0, samples_passed=0, samples_failed=1,
            )
            db.commit()
            return {"status": "poisoned", "evaluation_id": evaluation_id,
                    "annotation_id": annotation_id, "attempts": attempts}

        annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
        if not annotation:
            logger.warning(
                f"evaluate_annotation_cell: annotation {annotation_id} not found; skipping"
            )
            return {"status": "skipped", "reason": "annotation_not_found",
                    "evaluation_id": evaluation_id, "annotation_id": annotation_id}
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning(f"evaluate_annotation_cell: task {task_id} not found; skipping")
            return {"status": "skipped", "reason": "task_not_found",
                    "evaluation_id": evaluation_id, "task_id": task_id}

        judge_runs_by_config, llm_judge_evaluators = _reconstruct_judge_evaluators_for_cell(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id,
            db=db,
        )
        sample_evaluator = _build_sample_evaluator_for_cell(evaluation_id, configs_for_cell)

        # Pre-normalize per-cell already-done set (annotation-side mirror of
        # the generation-side skip). Same rationale — avoid the wasted
        # LLM-judge call on partial-cell retries.
        _already_done_normalized = {
            _normalize_field_key(fk, is_annotation=True)
            for fk in (already_evaluated_field_keys or [])
        }

        sample_results: List[Dict[str, Any]] = []
        local_samples_evaluated = 0
        local_samples_passed = 0
        local_samples_failed = 0
        gt_cache: Dict[tuple, Any] = {}

        for config in configs_for_cell:
            config_id = config.get("id", "unknown")
            metric = config.get("metric", "")
            prediction_fields = config.get("prediction_fields", [])
            reference_fields = config.get("reference_fields", [])

            if metric.startswith("korrektur_"):
                continue

            human_fields_raw, _llm_fields = classify_pred_fields(metric, prediction_fields)
            human_pred_fields = []
            for pf in human_fields_raw:
                if pf == "__all_human__":
                    human_pred_fields.append(("__all_human__", "__all_human__"))
                elif pf.startswith("human:"):
                    human_pred_fields.append((pf, pf[6:]))
                else:
                    human_pred_fields.append((f"human:{pf}", pf))

            if not human_pred_fields:
                continue

            for pred_field_prefixed, base_field in human_pred_fields:
                # Extract prediction from THIS annotation.
                if base_field == "__all_human__":
                    all_values = _extract_all_fields(annotation.result or [])
                    field_predictions = [
                        (f"human:{fn}", v) for fn, v in all_values.items()
                        if isinstance(v, str)
                    ]
                else:
                    value = _extract_field_value_from_annotation(
                        annotation.result or [], base_field
                    )
                    field_predictions = [(pred_field_prefixed, value)] if value else []

                for actual_pred_field, prediction in field_predictions:
                    for ref_field in reference_fields:
                        field_key = f"{config_id}|{actual_pred_field}|{ref_field}"

                        # Per-field-pair skip — mirror of legacy
                        # ex-`tasks.py:3485-3488`. Same wasted-LLM-call
                        # rationale as the gen-side sub-task.
                        if _normalize_field_key(field_key, is_annotation=True) in _already_done_normalized:
                            continue

                        gt_key = (task.id, ref_field)
                        if gt_key not in gt_cache:
                            if ref_field.startswith("task."):
                                data_field = ref_field[5:]
                                gt_cache[gt_key] = task.data.get(data_field) if task.data else None
                            else:
                                gt_cache[gt_key] = task.data.get(ref_field) if task.data else None
                        ground_truth = gt_cache[gt_key]
                        if ground_truth is None:
                            continue

                        try:
                            if metric.startswith("llm_judge_") and config_id not in llm_judge_evaluators:
                                sample_results.append({
                                    "id": str(_ann_uuid.uuid4()),
                                    "evaluation_id": evaluation_id,
                                    "judge_run_id": default_judge_run_id,
                                    "task_id": task.id,
                                    "generation_id": None,
                                    "annotation_id": annotation.id,
                                    "field_name": field_key,
                                    "evaluation_config_id": config_id,
                                    "answer_type": "text",
                                    "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                    "prediction": str(prediction)[:1000] if prediction else "",
                                    "metrics": {
                                        metric: {
                                            "value": None,
                                            "method": metric,
                                            "error": (
                                                "LLM judge evaluator not initialized for config "
                                                f"{config_id}"
                                            ),
                                            "details": {},
                                        },
                                    },
                                    "passed": False,
                                    "error_message": (
                                        f"LLM judge evaluator not initialized for config {config_id}"
                                    ),
                                })
                                local_samples_evaluated += 1
                                local_samples_failed += 1
                                continue

                            if metric.startswith("llm_judge_") and config_id in llm_judge_evaluators:
                                context = (
                                    _get_insensitive(task.data, "text")
                                    or _get_insensitive(task.data, "input")
                                    or _get_insensitive(task.data, "sachverhalt")
                                    or ""
                                ) if task.data else ""
                                eval_ground_truth = str(ground_truth) if ground_truth else ""
                                if metric == "llm_judge_falloesung" and task.data:
                                    muster = (
                                        _get_insensitive(task.data, "musterloesung")
                                        or _get_insensitive(task.data, "musterlösung")
                                    )
                                    if muster:
                                        eval_ground_truth = str(muster)
                                criterion = metric.replace("llm_judge_", "")
                                if criterion in ("custom", "overall"):
                                    criterion = "correctness"

                                per_judge_results: List[Dict[str, Any]] = []
                                for jr_entry in judge_runs_by_config.get(config_id, []):
                                    jr_evaluator = jr_entry["evaluator"]
                                    jr_id = jr_entry["judge_run_id"]
                                    jr_judge_model = jr_entry["judge_model_id"]
                                    jr_run_index = jr_entry["run_index"]

                                    if jr_evaluator is None:
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": {
                                                metric: {
                                                    "value": None,
                                                    "method": metric,
                                                    "error": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                                    "details": {},
                                                },
                                            },
                                            "passed": False,
                                            "error_message": f"judge {jr_judge_model} run {jr_run_index} not initialized",
                                        })
                                        continue

                                    multidim_mode = (
                                        metric != "llm_judge_falloesung"
                                        and getattr(jr_evaluator, "is_multidim_mode", lambda: False)()
                                    )

                                    if metric == "llm_judge_falloesung":
                                        try:
                                            from benger_extended.workers import (
                                                get_falloesung_bulk_compute_fn,
                                            )
                                        except ImportError as exc:
                                            raise RuntimeError(
                                                "Metric 'llm_judge_falloesung' requires the "
                                                "benger_extended package; it is not installed."
                                            ) from exc
                                        falloesung_bulk_fn = get_falloesung_bulk_compute_fn()
                                        sachverhalt = (
                                            _get_insensitive(task.data, "sachverhalt")
                                            if task.data
                                            else ""
                                        )
                                        result = falloesung_bulk_fn(
                                            ai_service=jr_evaluator.ai_service,
                                            judge_model=jr_evaluator.judge_model,
                                            temperature=jr_evaluator.temperature,
                                            max_tokens=jr_evaluator.max_tokens,
                                            sachverhalt=str(sachverhalt) if sachverhalt else "",
                                            musterloesung=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            thinking_budget=getattr(jr_evaluator, "thinking_budget", None),
                                            reasoning_effort=getattr(jr_evaluator, "reasoning_effort", None),
                                        )
                                    elif multidim_mode:
                                        # Same as the gen-cell side: flatten
                                        # the human annotator's per-field
                                        # outputs so the user's prompt can
                                        # reference {{kurzantwort}} /
                                        # {{begruendung}} directly.
                                        from annotation_utils import extract_all_field_values
                                        ann_field_outputs = (
                                            extract_all_field_values(annotation.result)
                                            if getattr(annotation, "result", None)
                                            else {}
                                        )
                                        result = jr_evaluator._evaluate_multidim_single_call(
                                            context=context,
                                            ground_truth=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            task_data=task.data,
                                            field_outputs=ann_field_outputs,
                                        )
                                    else:
                                        result = jr_evaluator._evaluate_single_criterion(
                                            context=context,
                                            ground_truth=eval_ground_truth,
                                            prediction=str(prediction) if prediction else "",
                                            criterion=criterion,
                                            task_data=task.data,
                                        )

                                    judge_prompts = (
                                        result.pop("_judge_prompts_used", None)
                                        if result
                                        else None
                                    )

                                    if multidim_mode:
                                        error_msg = (
                                            result.get("error_message")
                                            if result and result.get("error")
                                            else None
                                        )
                                        metrics_dict, normalized = _build_multidim_judge_row_metrics(
                                            result, metric, error_msg,
                                        )
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": metrics_dict,
                                            "passed": (normalized or 0.0) >= 0.5,
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **_llm_judge_columns_from_result(result),
                                        })
                                        continue

                                    raw_score = result.get("score") if result is not None else None
                                    error_msg = None
                                    if raw_score is not None:
                                        if jr_evaluator.score_scale == "0-1":
                                            score = raw_score
                                        elif jr_evaluator.score_scale == "0-100":
                                            score = raw_score / 100.0
                                        else:
                                            score = (raw_score - 1) / 4
                                    else:
                                        score = None
                                        error_msg = (
                                            (result.get("error_message") if result else None)
                                            or "LLM judge evaluation failed"
                                        )

                                    if metric == "llm_judge_falloesung":
                                        from benger_extended.workers.falloesung_tasks import (
                                            build_falloesung_row_dict,
                                        )
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **build_falloesung_row_dict(result=result, error_message=error_msg),
                                        })
                                    else:
                                        per_judge_results.append({
                                            "id": str(_ann_uuid.uuid4()),
                                            "evaluation_id": evaluation_id,
                                            "judge_run_id": jr_id,
                                            "task_id": task.id,
                                            "generation_id": None,
                                            "annotation_id": annotation.id,
                                            "field_name": field_key,
                                            "evaluation_config_id": config_id,
                                            "answer_type": "text",
                                            "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                            "prediction": str(prediction)[:1000] if prediction else "",
                                            "metrics": {
                                                metric: score,
                                                "raw_score": raw_score,
                                                f"{metric}_response": result,
                                                **(
                                                    {f"{metric}_grade_points": result["grade_points"]}
                                                    if result and result.get("grade_points") is not None
                                                    else {}
                                                ),
                                                **(
                                                    {f"{metric}_passed": 1.0 if result["passed"] else 0.0}
                                                    if result and "passed" in result
                                                    else {}
                                                ),
                                            },
                                            "passed": (
                                                result.get("passed", score > 0.5)
                                                if result and "passed" in result
                                                else (score > 0.5 if score is not None else False)
                                            ),
                                            "error_message": error_msg,
                                            "judge_prompts_used": judge_prompts,
                                            **_llm_judge_columns_from_result(result),
                                        })

                                for sr in per_judge_results:
                                    sample_results.append(sr)
                                    local_samples_evaluated += 1
                                    if sr["passed"]:
                                        local_samples_passed += 1
                                    else:
                                        local_samples_failed += 1
                                continue

                            # Deterministic annotation metric.
                            annotation_result = sample_evaluator.evaluate_sample(
                                task_id=task.id,
                                field_name=field_key,
                                ground_truth=ground_truth,
                                prediction=prediction,
                                metrics_to_compute=[metric],
                                annotation_id=annotation.id,
                            )
                            annotation_result["annotation_id"] = annotation.id
                            annotation_result["generation_id"] = None
                            if isinstance(annotation_result, dict):
                                annotation_result["judge_run_id"] = default_judge_run_id
                                # Issue #111 / migration 057: discrete config-id carrier.
                                annotation_result["evaluation_config_id"] = config_id

                            sample_results.append(annotation_result)
                            local_samples_evaluated += 1
                            if annotation_result.get("passed"):
                                local_samples_passed += 1
                            else:
                                local_samples_failed += 1

                        except ValueError as e:
                            logger.warning(f"Skipping annotation sample: {e}")
                            continue
                        except Exception as e:
                            logger.warning(
                                f"Annotation eval failed for annotation {annotation.id}: {e}"
                            )
                            sample_results.append({
                                "id": str(_ann_uuid.uuid4()),
                                "evaluation_id": evaluation_id,
                                "judge_run_id": default_judge_run_id,
                                "task_id": task.id,
                                "generation_id": None,
                                "annotation_id": annotation.id,
                                "field_name": field_key,
                                "evaluation_config_id": config_id,
                                "answer_type": "text",
                                "ground_truth": str(ground_truth)[:1000] if ground_truth else "",
                                "prediction": str(prediction)[:1000] if prediction else "",
                                "metrics": {},
                                "passed": False,
                                "error_message": str(e),
                            })
                            local_samples_evaluated += 1
                            local_samples_failed += 1

        # Bump by RETURNING-derived counts — see gen sub-task for rationale.
        n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations(db, sample_results)
        _bump_evaluation_counters(
            db,
            evaluation_id=evaluation_id,
            samples_evaluated=n_inserted,
            samples_passed=n_passed,
            samples_failed=n_failed,
        )
        db.commit()
        # Same as the gen cell — broadcast so the API WS pushes a tick.
        if n_inserted > 0:
            _publish_progress(
                f"evaluation:progress:{project_id}",
                {
                    "type": "cell_complete",
                    "evaluation_id": evaluation_id,
                    "task_id": task_id,
                    "annotation_id": annotation_id,
                    "samples_added": n_inserted,
                },
            )
        return {
            "status": "ok",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "annotation_id": annotation_id,
            "samples_added": n_inserted,
            "samples_passed": n_passed,
            "samples_failed": n_failed,
        }
    except Exception as e:
        logger.error(
            f"evaluate_annotation_cell failed (eval {evaluation_id}, ann {annotation_id}): {e}",
            exc_info=True,
        )
        db.rollback()
        try:
            _record_cell_failure_reason(db, evaluation_id, _classify_cell_failure(e))
            _bump_evaluation_counters(
                db,
                evaluation_id=evaluation_id,
                samples_evaluated=0,
                samples_passed=0,
                samples_failed=1,
            )
            db.commit()
        except Exception as bump_err:
            logger.error(f"Failed to bump failed counter: {bump_err}")
        return {
            "status": "error",
            "evaluation_id": evaluation_id,
            "task_id": task_id,
            "annotation_id": annotation_id,
            "error": str(e),
        }
    finally:
        db.close()
