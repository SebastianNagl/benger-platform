"""End-to-end behavioral tests for the evaluation Celery chord pipeline.

Drives the REAL `run_evaluation` orchestrator → per-cell sub-tasks
(`evaluate_generation_cell`) → `finalize_evaluation_run` chord callback
against the real test Postgres, under eager Celery. Metric is the
deterministic `exact_match` (NO judge, NO network).

Scenario shape (shared across most tests): 2 tasks × 1 exact_match config.
- Task A: data.expected="ja", generation response_content="ja"  → match (1.0)
- Task B: data.expected="ja", generation response_content="nein" → miss (0.0)
So the aggregate `{field}|exact_match` metric is mean([1.0, 0.0]) = 0.5,
samples_evaluated == 2, one passed / one failed.
"""

import pytest

import tasks
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


# Field key the orchestrator builds: "{config_id}|{pred_field}|{ref_field}".
FIELD_KEY = "cfg1|__all_model__|task.expected"
METRIC_KEY = f"{FIELD_KEY}|exact_match"


def _build_scenario(db_conn, make_user, make_llm_model, make_project,
                    make_task, make_generation, make_evaluation_run):
    """Two tasks, two generations (one match, one miss), a pending run."""
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

    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.flush()
    return user, project, run, task_a, task_b, gen_a, gen_b


def _dispatch(run, project, config):
    """Run the orchestrator; force the chord callback if eager didn't.

    Under `task_always_eager` the chord callback usually fires inline, but
    we don't rely on it: if the parent isn't terminal after dispatch we
    invoke `finalize_evaluation_run` explicitly (its first positional arg
    `_sub_task_results` is ignored, so a placeholder is fine).
    """
    result = tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[config],
    )
    return result


def _finalize(run_id):
    return tasks.finalize_evaluation_run.apply(args=[[], run_id]).get()


def _ensure_finalized(db_conn, run):
    # Subtasks + finalize ran on their own sessions over the SAME shared
    # connection; expire_all() drops the test session's stale identity map
    # so subsequent queries re-read the rows those sessions committed.
    db_conn.expire_all()
    if run.status not in ("completed", "failed", "cancelled"):
        _finalize(run.id)
        db_conn.expire_all()


# ---------------------------------------------------------------------------
# Test 1 — happy path
# ---------------------------------------------------------------------------


def test_happy_path_two_cells_one_match(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    user, project, run, *_ = _build_scenario(
        db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    )
    config = exact_match_config()

    _dispatch(run, project, config)
    _ensure_finalized(db_conn, run)

    # Exactly 2 TaskEvaluation rows.
    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 2

    # The single default (deterministic, judge_model_id=None) judge_run.
    default_jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id.is_(None),
        )
        .one()
    )
    for r in rows:
        assert r.judge_run_id == default_jr.id
        assert r.field_name == FIELD_KEY
        assert r.evaluation_config_id == "cfg1"
        assert r.answer_type == "text"

    # One passed (match), one failed (miss).
    passed = sorted(r.passed for r in rows)
    assert passed == [False, True]

    db_conn.expire(run)
    assert run.status == "completed"
    assert run.samples_evaluated == 2
    assert run.has_sample_results is True

    # Aggregate metric = mean([1.0, 0.0]) = 0.5 under "{field}|exact_match".
    assert METRIC_KEY in run.metrics
    assert run.metrics[METRIC_KEY] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 2 — idempotent re-dispatch + double finalize is a no-op
# ---------------------------------------------------------------------------


def test_idempotent_redispatch_and_double_finalize(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    user, project, run, *_ = _build_scenario(
        db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    )
    config = exact_match_config()

    _dispatch(run, project, config)
    _ensure_finalized(db_conn, run)

    db_conn.expire(run)
    assert run.status == "completed"
    first_samples = run.samples_evaluated
    assert first_samples == 2

    rows_after_first = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
    )
    assert rows_after_first == 2

    # Re-dispatch into the SAME run: reset to pending and re-run. The bare
    # ON CONFLICT DO NOTHING against uq_task_evaluations_cell must keep the
    # row count at exactly 2 and not double-count samples_evaluated (the
    # counter bumps by the RETURNING count, which is 0 on full conflict).
    run.status = "pending"
    run.completed_at = None
    db_conn.flush()
    db_conn.commit()  # release savepoint so the re-run's session sees pending

    _dispatch(run, project, config)
    _ensure_finalized(db_conn, run)

    rows_after_second = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
    )
    assert rows_after_second == 2, "ON CONFLICT must prevent duplicate rows"

    db_conn.expire(run)
    assert run.status == "completed"
    assert run.samples_evaluated == 2, "samples must not be double-counted"

    # Double finalize: calling finalize again on a terminal run is a no-op
    # (the already_terminal guard) — returns noop and changes nothing.
    res = _finalize(run.id)
    assert res["status"] == "noop"
    assert res["reason"] == "already_terminal"
    assert res["current_status"] == "completed"

    db_conn.expire(run)
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 2
    )


# ---------------------------------------------------------------------------
# Test 3 — cancel before dispatch + per-cell guard
# ---------------------------------------------------------------------------


def test_orchestrator_short_circuit_on_midsetup_cancel(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """The orchestrator's final pre-chord cancel check (`cancelled_before_dispatch`).

    `run_evaluation` flips the run to 'running' at the very start, so a
    PRE-set 'cancelled' is overwritten and never seen — the real short-circuit
    only fires when a cancel lands DURING the ~25s setup window. We reproduce
    that deterministically: monkeypatch the cell-signature builder so that,
    while the orchestrator is assembling header_sigs (after the running-flip,
    before the pre-chord `db.refresh`), the run is flipped to 'cancelled' via a
    SEPARATE committed session. The orchestrator's refresh then observes the
    terminal status and returns `cancelled_before_dispatch` without dispatching.
    """
    user, project, run, task_a, task_b, gen_a, gen_b = _build_scenario(
        db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    )
    config = exact_match_config()

    real_sig = tasks.evaluate_generation_cell.signature
    flipped = {"done": False}

    def _sig_then_cancel(*args, **kwargs):
        if not flipped["done"]:
            flipped["done"] = True
            sess = tasks.SessionLocal()
            try:
                row = (
                    sess.query(EvaluationRun)
                    .filter(EvaluationRun.id == run.id)
                    .first()
                )
                row.status = "cancelled"
                sess.commit()
            finally:
                sess.close()
        return real_sig(*args, **kwargs)

    monkeypatch.setattr(
        tasks.evaluate_generation_cell, "signature", _sig_then_cancel
    )

    result = _dispatch(run, project, config)
    assert result["status"] == "cancelled_before_dispatch"
    assert result["current_status"] == "cancelled"

    # No cells dispatched → no partial rows.
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


def test_per_cell_guard_skips_cancelled_parent(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """The per-cell guard: a cell sub-task invoked against a cancelled parent
    short-circuits with reason 'parent_cancelled' and writes no row — this is
    how in-flight cells stop after an operator cancels. Partial rows already
    written by earlier cells are preserved (we seed one and assert it stays).
    """
    user, project, run, task_a, task_b, gen_a, gen_b = _build_scenario(
        db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    )
    config = exact_match_config()

    # Grade gen_a fully first (parent still pending), then cancel.
    _dispatch(run, project, config)
    _ensure_finalized(db_conn, run)
    db_conn.expire_all()
    seeded = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
    )
    assert seeded == 2

    run.status = "cancelled"
    db_conn.commit()

    # A fresh cell against the now-cancelled parent must skip + write nothing.
    cell_res = tasks.evaluate_generation_cell.apply(
        kwargs={
            "evaluation_id": run.id,
            "task_id": task_a.id,
            "generation_id": gen_a.id,
            "project_id": project.id,
            "configs_for_cell": [config],
            "judge_run_ids_by_config": {},
            "default_judge_run_id": "00000000-0000-0000-0000-0000000000aa",
            "organization_id": None,
            "triggered_by_user_id": user.id,
            "already_evaluated_field_keys": [],
        }
    ).get()
    assert cell_res["status"] == "skipped"
    assert cell_res["reason"] == "parent_cancelled"

    # Partial rows preserved (the guard writes nothing, deletes nothing).
    db_conn.expire_all()
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 2
    )


# ---------------------------------------------------------------------------
# Test 4 — resume: one cell graded, one not; missing-only re-dispatch
# ---------------------------------------------------------------------------


def test_resume_missing_only_revives_judge_run(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """Highest-value: a cancelled run with one cell graded and one not.
    Flip cancelled→pending and re-dispatch missing-only → only the missing
    cell gets a new row (skip-already-done), the judge_run revives, the
    parent ends completed, samples_evaluated is not double-counted.
    """
    user, project, run, task_a, task_b, gen_a, gen_b = _build_scenario(
        db_conn, make_user, make_llm_model, make_project, make_task,
        make_generation, make_evaluation_run,
    )
    config = exact_match_config()

    # First full run → 2 rows, completed.
    _dispatch(run, project, config)
    _ensure_finalized(db_conn, run)
    db_conn.expire(run)
    assert run.status == "completed"
    assert run.samples_evaluated == 2

    # Simulate a partial state: delete the row for gen_b (the "miss"),
    # leaving gen_a graded. Mark the run cancelled + the judge_run terminal,
    # mirroring a cancel that landed mid-flight after one cell finished.
    gen_b_rows = (
        db_conn.query(TaskEvaluation)
        .filter(
            TaskEvaluation.evaluation_id == run.id,
            TaskEvaluation.generation_id == gen_b.id,
        )
        .all()
    )
    assert len(gen_b_rows) == 1
    for r in gen_b_rows:
        db_conn.delete(r)
    db_conn.flush()

    default_jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id == run.id)
        .one()
    )
    default_jr.status = "cancelled"
    default_jr.completed_at = None
    run.status = "cancelled"
    run.completed_at = None
    db_conn.flush()
    db_conn.commit()

    remaining = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].generation_id == gen_a.id

    # The parent's samples_evaluated counter is a CUMULATIVE total bumped per
    # inserted row across every dispatch into the run (finalize never resets
    # it — it reads the accumulated counter). After the first full run it's 2.
    # Deleting a row does NOT decrement it. Capture it so we can assert the
    # resume adds exactly ONE (the single missing cell), not the whole set.
    db_conn.expire(run)
    counter_before_resume = run.samples_evaluated
    assert counter_before_resume == 2

    # Resume: flip cancelled→pending and re-dispatch with missing-only.
    run.status = "pending"
    db_conn.commit()

    tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=[config],
        evaluate_missing_only=True,
    )
    _ensure_finalized(db_conn, run)

    # Exactly 2 rows again (the missing gen_b cell got a NEW row; gen_a's
    # existing row was NOT re-created — skip-already-done + ON CONFLICT).
    db_conn.expire_all()
    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 2
    gen_ids = {r.generation_id for r in rows}
    assert gen_ids == {gen_a.id, gen_b.id}

    # Judge_run revived to completed (finalize reconciles from row count).
    db_conn.expire(default_jr)
    assert default_jr.status == "completed"

    db_conn.expire(run)
    assert run.status == "completed"
    # The resume inserted exactly ONE new cell (the missing one) — the
    # cumulative counter advances by 1, NOT by the whole set. gen_a's cell was
    # skipped (skip-already-done), so it contributed zero new inserts.
    assert run.samples_evaluated == counter_before_resume + 1, (
        "resume must count only the single newly inserted (missing) cell"
    )

    # Aggregate metric still computed over BOTH stored rows → 0.5.
    assert run.metrics.get(METRIC_KEY) == pytest.approx(0.5)
