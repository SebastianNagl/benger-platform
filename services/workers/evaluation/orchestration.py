"""Single-sample / immediate evaluation orchestration (worker).

Extracted from ``services/workers/tasks.py`` as part of the structural
decomposition of that module. Behavior-preserving move: the function body is
byte-identical to the original, except that references to ``tasks``-module
globals (``SessionLocal``, ``logger``, monkeypatched helpers, etc.) are
resolved through the ``tasks`` module at call time so that test monkeypatches
like ``patch("tasks.SessionLocal")`` continue to apply.

``run_single_sample_evaluation`` stays in ``tasks.py`` (its nested
``_get_or_create_judge_run_for_config`` is pinned by a source-contract test);
its parallel per-config worker, ``_run_immediate_config_job``, lives here and
is invoked via the ``tasks._run_immediate_config_job`` wrapper.
"""

from typing import Any, Dict, Optional

import tasks


def _run_immediate_config_job_impl(
    *,
    job: Dict[str, Any],
    dispatch_eval_id: str,
    project_id: str,
    task_id: str,
    annotation_id: Optional[str],
    organization_id: Optional[str],
    user_id: Optional[str],
    task_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute + persist a single immediate-eval config in its OWN DB session.

    Run on a worker thread by ``run_single_sample_evaluation`` so multiple
    (I/O-bound) LLM-judge configs evaluate concurrently — wall-clock ≈ the
    slowest config, not the sum. Each thread owns its session (SQLAlchemy
    sessions are not thread-safe); the shared ``EvaluationRun`` +
    ``EvaluationJudgeRun`` rows were committed by the caller before fan-out,
    so the FKs resolve. ALWAYS returns a result dict (never raises) so one
    failing config can't poison its siblings or leave the run stuck.
    """
    import inspect as _inspect

    from models import TaskEvaluation

    metric_type = job["metric_type"]
    metric_params = job["metric_params"]
    field_name = job["field_name"]
    prediction_value = job["prediction_value"]
    reference_value = job["reference_value"]
    judge_run_id = job["judge_run_id"]
    evaluation_config_id = job.get("evaluation_config_id")
    record_id = job["record_id"]

    db = tasks.SessionLocal()
    try:
        if metric_type == "llm_judge_falloesung":
            # Phase 5: delegate to the extended-registered Falllösung compute.
            # Community edition (no benger_extended) raises an informative
            # error rather than crashing.
            try:
                from benger_extended.workers import get_falloesung_compute_fn
            except ImportError as exc:
                raise RuntimeError(
                    "Metric 'llm_judge_falloesung' requires the benger_extended "
                    "package; it is not installed in this worker. Configure the "
                    "project to use a different LLM-judge metric or load the "
                    "extended edition."
                ) from exc
            falloesung_fn = get_falloesung_compute_fn()
            # Older extended packages may not accept judge_run_id /
            # evaluation_config_id; introspect and pass only what's supported.
            fn_params = set(_inspect.signature(falloesung_fn).parameters.keys())
            extra: Dict[str, Any] = {}
            if "judge_run_id" in fn_params:
                extra["judge_run_id"] = judge_run_id
            if "evaluation_config_id" in fn_params:
                extra["evaluation_config_id"] = evaluation_config_id
            return falloesung_fn(
                db=db,
                record_id=record_id,
                immediate_eval_id=dispatch_eval_id,
                project_id=project_id,
                task_id=task_id,
                annotation_id=annotation_id,
                user_id=user_id,
                field_name=field_name,
                prediction=str(prediction_value),
                task_data=task_data,
                metric_params=metric_params,
                organization_id=organization_id,
                **extra,
            )

        elif metric_type.startswith("llm_judge_"):
            # Other LLM judge metrics — LLMJudgeEvaluator persists its own row.
            return tasks._evaluate_llm_judge_single(
                db=db,
                record_id=record_id,
                immediate_eval_id=dispatch_eval_id,
                judge_run_id=judge_run_id,
                project_id=project_id,
                task_id=task_id,
                annotation_id=annotation_id,
                user_id=user_id,
                field_name=field_name,
                metric_type=metric_type,
                prediction=str(prediction_value),
                reference=str(reference_value) if reference_value else "",
                metric_params=metric_params,
                organization_id=organization_id,
                evaluation_config_id=evaluation_config_id,
            )

        else:
            # Deterministic metrics — SampleEvaluator with real implementations.
            from ml_evaluation.sample_evaluator import SampleEvaluator
            from ml_evaluation import extract_value

            field_configs = {field_name: {"type": "text"}}
            param_configs = (
                {field_name: {metric_type: metric_params}} if metric_params else {}
            )
            evaluator = SampleEvaluator(record_id, field_configs, param_configs)
            metric_result = evaluator._compute_metric_with_details(
                metric_name=metric_type,
                ground_truth=reference_value,
                prediction=prediction_value,
                answer_type="text",
                parameters=metric_params or None,
            )
            score_value = extract_value(metric_result) or 0.0

            eval_record = TaskEvaluation(
                id=record_id,
                evaluation_id=dispatch_eval_id,
                # This config's own judge_run (judge_model_id=None for
                # deterministic metrics) — distinct per config so the
                # per-row uq_task_evaluations_cell doesn't collide.
                judge_run_id=judge_run_id,
                task_id=task_id,
                annotation_id=annotation_id,
                generation_id=None,
                field_name=field_name,
                # Issue #111 / migration 057: discrete carrier of the config id.
                evaluation_config_id=evaluation_config_id,
                answer_type="text",
                ground_truth=str(reference_value) if reference_value else "",
                prediction=str(prediction_value) if prediction_value else "",
                metrics={
                    metric_type: metric_result,  # Full {value, method, details}
                    "raw_score": float(score_value),
                },
                passed=float(score_value) >= 0.5,
            )
            db.add(eval_record)
            db.commit()
            return {
                "status": "completed",
                "record_id": record_id,
                "metric": metric_type,
                "score": float(score_value),
                "details": metric_result.get("details")
                if isinstance(metric_result, dict)
                else None,
            }

    except Exception as e:
        tasks.logger.error(f"[SingleSampleEval] {metric_type} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        # Persist an error TaskEvaluation row for EVERY metric type so the
        # method shows as failed in the modal and the run still reaches a
        # terminal state (every expected config ends with a row). judge_run_id
        # is REQUIRED — the column is NOT NULL (migration 043), so omitting it
        # used to raise an IntegrityError that escaped and left the whole run
        # stuck "running". Falllösung routes through the extended helper (it
        # owns the canonical row shape); everything else writes a minimal row.
        if metric_type == "llm_judge_falloesung":
            try:
                from benger_extended.workers.falloesung_tasks import (
                    _persist_falloesung_eval_error,
                )
                err_params = set(
                    _inspect.signature(_persist_falloesung_eval_error).parameters.keys()
                )
                err_kwargs: Dict[str, Any] = {
                    "eval_run_id": dispatch_eval_id,
                    "judge_run_id": judge_run_id,
                }
                if "evaluation_config_id" in err_params:
                    err_kwargs["evaluation_config_id"] = evaluation_config_id
                _persist_falloesung_eval_error(
                    db, record_id, project_id, task_id,
                    annotation_id, user_id or "system", field_name,
                    str(reference_value) if reference_value else "",
                    str(prediction_value) if prediction_value else "",
                    str(e),
                    **err_kwargs,
                )
            except ImportError:
                tasks.logger.warning(
                    "Falllösung error persistence skipped; benger_extended not installed"
                )
            except Exception as persist_err:
                tasks.logger.error(
                    "[SingleSampleEval] failed to persist falloesung error row: %s",
                    persist_err,
                )
        else:
            try:
                from models import TaskEvaluation
                db.add(
                    TaskEvaluation(
                        id=record_id,
                        evaluation_id=dispatch_eval_id,
                        judge_run_id=judge_run_id,
                        evaluation_config_id=evaluation_config_id,
                        task_id=task_id,
                        annotation_id=annotation_id,
                        generation_id=None,
                        field_name=field_name,
                        answer_type="text",
                        ground_truth=str(reference_value) if reference_value else "",
                        prediction=str(prediction_value) if prediction_value else "",
                        metrics={
                            metric_type: {
                                "value": None,
                                "method": metric_type,
                                "details": {},
                                "error": str(e),
                            }
                        },
                        error_message=str(e),
                        passed=False,
                    )
                )
                db.commit()
            except Exception as persist_err:
                tasks.logger.error(
                    "[SingleSampleEval] failed to persist error row for %s: %s",
                    metric_type,
                    persist_err,
                )
                try:
                    db.rollback()
                except Exception:
                    pass
        return {
            "status": "error",
            "record_id": record_id,
            "metric": metric_type,
            "error": str(e),
        }
    finally:
        db.close()
