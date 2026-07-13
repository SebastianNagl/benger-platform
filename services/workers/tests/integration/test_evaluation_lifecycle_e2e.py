"""Behavioral tests for the evaluation pause lifecycle in the workers
(issue #198) plus the metric_parameters=None orchestrator crash fix.

Same harness as test_evaluation_chord_e2e.py: REAL `run_evaluation`
orchestrator / cell sub-tasks / `finalize_evaluation_run` against the real
test Postgres under eager Celery, deterministic `exact_match` metric.

What 'paused' must mean in the worker:
- orchestrator entry: a paused (or terminal) run is never flipped back to
  'running' by a queued/redelivered orchestrator message;
- cell sub-tasks: skip without evaluating while the parent is paused;
- chord finalizer: no-op on a paused parent — partial rows survive and the
  run STAYS 'paused' (marking it completed would silently end the pause);
- resume semantics: flipping the same run back to 'pending' and re-running
  the orchestrator missing-only reuses completed rows and finishes the run.
"""

import pytest

import tasks
from models import EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]

FIELD_KEY = "cfg1|__all_model__|task.expected"


def _build_scenario(db_conn, make_user, make_llm_model, make_project,
                    make_task, make_generation, make_evaluation_run,
                    status="pending"):
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task_a = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    task_b = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen_a = make_generation(
        project.id, task_a.id, model.id, user.id, response_content="ja"
    )
    _, gen_b = make_generation(
        project.id, task_b.id, model.id, user.id, response_content="nein"
    )
    run = make_evaluation_run(project.id, user.id, status=status)
    db_conn.flush()
    return user, project, run, task_a, task_b, gen_a, gen_b


class TestOrchestratorEntryGuard:
    def test_paused_run_is_not_flipped_to_running(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run, exact_match_config,
    ):
        """A pause landing while the orchestrator message sits in the queue
        must win: the orchestrator skips instead of stomping the pause."""
        _, project, run, *_ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run, status="paused",
        )
        result = tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[exact_match_config()],
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "status_paused"
        db_conn.expire_all()
        assert run.status == "paused"
        # Nothing evaluated.
        assert (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
            == 0
        )

    def test_completed_run_redelivery_is_noop(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run, exact_match_config,
    ):
        """Broker redelivery of the orchestrator after the run finished must
        not flip a terminal run back to 'running'."""
        _, project, run, *_ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run, status="completed",
        )
        result = tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[exact_match_config()],
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "status_completed"
        db_conn.expire_all()
        assert run.status == "completed"


class TestCellSkipOnPaused:
    def test_generation_cell_skips_while_parent_paused(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run, exact_match_config,
    ):
        user, project, run, task_a, _, gen_a, _ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run, status="paused",
        )
        result = tasks.evaluate_generation_cell(
            evaluation_id=run.id,
            task_id=task_a.id,
            generation_id=gen_a.id,
            project_id=project.id,
            configs_for_cell=[exact_match_config()],
            judge_run_ids_by_config={},
            default_judge_run_id=None,
            organization_id=None,
            triggered_by_user_id=user.id,
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "parent_paused"
        assert (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
            == 0
        )


class TestFinalizerPausedNoop:
    def test_finalizer_leaves_paused_run_paused(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run, exact_match_config,
    ):
        """Pause mid-run: in-flight cells drain, the chord callback fires —
        and must NOT mark the run completed off the partial rows."""
        _, project, run, *_ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run,
        )
        # Run to completion first to get real rows, then rewind the run to
        # 'paused' and re-fire the finalizer — equivalent to the callback
        # firing after a pause landed.
        tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[exact_match_config()],
        )
        db_conn.expire_all()
        rows_before = (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
        )
        assert rows_before > 0

        db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).update(
            {"status": "paused"}
        )
        db_conn.commit()

        result = tasks.finalize_evaluation_run.apply(args=[[], run.id]).get()
        assert result["status"] == "noop"
        assert result["reason"] == "paused"
        db_conn.expire_all()
        assert run.status == "paused"
        # Partial rows survive for the resume.
        assert (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
            == rows_before
        )


class TestResumeMissingOnly:
    def test_resume_after_pause_reuses_completed_cells(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run, exact_match_config,
    ):
        """The API resume flips paused→pending and re-dispatches with
        evaluate_missing_only=True; the orchestrator preload must reuse the
        rows the paused attempt produced (no duplicates) and finish the run.
        """
        _, project, run, *_ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run,
        )
        config = exact_match_config()
        # First attempt completes both cells (eager), then simulate the
        # operator pause + resume cycle on the same run id.
        tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[config],
        )
        db_conn.expire_all()
        assert (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
            == 2
        )

        db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).update(
            {"status": "pending"}
        )
        db_conn.commit()

        result = tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[config],
            evaluate_missing_only=True,
        )
        assert result["status"] in ("dispatched", "completed", "skipped") or (
            "cells_dispatched" in result
        )
        db_conn.expire_all()
        # Still exactly 2 rows — completed cells were reused, not re-graded.
        assert (
            db_conn.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == run.id)
            .count()
            == 2
        )
        assert run.status == "completed"


class TestMetricParametersNoneCrashFix:
    def test_llm_judge_config_with_null_metric_parameters_does_not_crash(
        self, db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    ):
        """EvaluationConfigItem.metric_parameters is Optional and serializes
        as None (key PRESENT with null). `config.get("metric_parameters", {})`
        returned that None and `_resolve_judges(None)` crashed the WHOLE
        orchestrator with AttributeError — every config in the run lost.
        After the `or {}` fix the run proceeds (the judge cells may still
        fail without an AI service, but per-cell, not orchestrator-fatal).
        """
        _, project, run, *_ = _build_scenario(
            db_conn, make_user, make_llm_model, make_project, make_task,
            make_generation, make_evaluation_run,
        )
        judge_config = {
            "id": "cfgjudge",
            "metric": "llm_judge_custom",
            "prediction_fields": ["__all_model__"],
            "reference_fields": ["task.expected"],
            "metric_parameters": None,  # the crash shape
            "enabled": True,
        }
        result = tasks.run_evaluation(
            evaluation_id=run.id,
            project_id=project.id,
            evaluation_configs=[judge_config],
        )
        # The historical failure mode: {'status': 'error', 'message':
        # "'NoneType' object has no attribute 'get'"}.
        assert "NoneType" not in str(result.get("message", "")), result
        db_conn.expire_all()
        assert "NoneType" not in str(run.error_message or "")
