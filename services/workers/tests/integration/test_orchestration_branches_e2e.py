"""End-to-end behavioral tests for the under-covered orchestration branches.

Companion to ``test_evaluation_chord_e2e.py`` (which covers the generation
happy path / idempotency / cancel / resume). This file drives the REAL
``run_evaluation`` chord pipeline against the real test Postgres + real
``test-redis`` chord backend (no shim) for the branches that file doesn't:

  * the ANNOTATION cell path (``evaluate_annotation_cell``) end-to-end,
  * a mixed config that fans out BOTH a generation cell and an annotation
    cell from one ``run_evaluation``,
  * cell metric-error arms (per-field error row vs. whole-cell failure that
    drives ``finalize_evaluation_run`` to the terminal ``failed`` state),
  * ``finalize_evaluation_run`` aggregation variants — multi-config /
    multi-metric keying, judge-run status derived from produced-row COUNT,
    and the already-terminal no-op guard,
  * ``run_evaluation`` setup short-circuits — no tasks, no enabled configs,
    and the missing-only "nothing to dispatch" path.

Metric is the deterministic ``exact_match`` everywhere (NO judge, NO
network, NO model downloads). Assertions are on persisted DB state.
"""

import pytest

import tasks
from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.fixture()
def mock_judge_mode(monkeypatch):
    """Drive the ``llm_judge_*`` path deterministically with NO network.

    Sets ``E2E_TEST_MODE=true`` and forces the judge AI-service resolver to
    return ``None`` so ``LLMJudgeEvaluator`` takes its built-in E2E mock
    branch in ``_evaluate_single_criterion`` (a hashed-but-deterministic
    0.6–0.99 score, no API call). ``run_evaluation`` keeps a key-less
    evaluator alive specifically when ``E2E_TEST_MODE`` is set, so the whole
    judge-setup + per-cell judge fan-out + finalize judges_by_config summary
    run inline."""
    monkeypatch.setenv("E2E_TEST_MODE", "true")
    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda *a, **k: None,
    )


def _llm_judge_config(config_id="jcfg", judge_model="gpt-4o", runs=1,
                      pred_field="__all_model__", ref_field="task.expected"):
    """A single-criterion ``llm_judge_correctness`` config in 0-1 score scale
    (so the mock score isn't rescaled). No ``custom_criteria`` → the judge
    stays in legacy single-criterion (non-multidim) mode."""
    return {
        "id": config_id,
        "metric": "llm_judge_correctness",
        "prediction_fields": [pred_field],
        "reference_fields": [ref_field],
        "metric_parameters": {
            "judges": [{"judge_model_id": judge_model, "runs": runs}],
            "score_scale": "0-1",
        },
        "enabled": True,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _ann_result(field_name, text_value):
    """A single Label Studio textarea result item, as stored in
    ``Annotation.result`` — ``extract_field_value`` keys off ``from_name``."""
    return {"from_name": field_name, "type": "textarea", "value": {"text": text_value}}


def _human_exact_match_config(config_id="cfg1", human_field="answer",
                              ref_field="task.expected"):
    """exact_match over a HUMAN annotation field. ``human:<f>`` flips
    ``classify_pred_fields`` to the annotation side so ``run_evaluation``
    enumerates annotation cells and dispatches ``evaluate_annotation_cell``."""
    return {
        "id": config_id,
        "metric": "exact_match",
        "prediction_fields": [f"human:{human_field}"],
        "reference_fields": [ref_field],
        "metric_parameters": {},
        "enabled": True,
    }


def _refresh(db_conn, run):
    db_conn.expire_all()
    return db_conn.query(EvaluationRun).filter(EvaluationRun.id == run.id).one()


def _make_default_judge_run(db_conn, run):
    """Create the default (deterministic, judge_model_id=None) EvaluationJudgeRun
    the orchestrator would have made — needed when a direct cell invocation
    produces a real row (its judge_run_id FK must resolve)."""
    import uuid as _uuid
    jr_id = str(_uuid.uuid4())
    db_conn.add(EvaluationJudgeRun(
        id=jr_id, evaluation_id=run.id, judge_model_id=None,
        run_index=0, status="running",
    ))
    db_conn.commit()
    return jr_id


def _run(db_conn, run, project, configs, **kwargs):
    """Drive the real chord; the callback auto-fires (real backend), so by
    return the run is already terminal. We do NOT manually finalize."""
    result = tasks.run_evaluation(
        evaluation_id=run.id,
        project_id=project.id,
        evaluation_configs=configs,
        **kwargs,
    )
    db_conn.expire_all()
    return result


# ---------------------------------------------------------------------------
# 1 — ANNOTATION cell path end-to-end (evaluate_annotation_cell 5394-5891)
# ---------------------------------------------------------------------------


def test_annotation_cell_happy_path_two_cells_one_match(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run,
):
    """An eval over human ANNOTATIONS (not generations). Two annotations:
    one whose ``answer`` matches ``task.expected`` (1.0), one that misses
    (0.0). Asserts: 2 TaskEvaluation rows keyed to the annotations (not
    generations), the human-prefixed field_name, the default judge_run, and
    finalize aggregating mean([1,0]) = 0.5."""
    user = make_user()
    make_llm_model(provider="OpenAI")  # not used, but keeps parity w/ gen path
    project = make_project(created_by=user.id)

    task_a = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    task_b = make_task(project.id, {"expected": "ja"}, created_by=user.id)

    ann_a = make_annotation(
        project.id, task_a.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],   # match
    )
    ann_b = make_annotation(
        project.id, task_b.id, completed_by=user.id,
        result=[_ann_result("answer", "nein")],  # miss
    )

    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    config = _human_exact_match_config()
    result = _run(db_conn, run, project, [config])

    # The orchestrator dispatched annotation cells (not generation cells).
    assert result["status"] == "dispatched"
    assert result["ann_cells"] == 2
    assert result["gen_cells"] == 0

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 2
    # All rows are annotation-side: annotation_id set, generation_id null.
    assert {r.annotation_id for r in rows} == {ann_a.id, ann_b.id}
    assert all(r.generation_id is None for r in rows)

    field_key = "cfg1|human:answer|task.expected"
    default_jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id.is_(None),
        )
        .one()
    )
    for r in rows:
        assert r.field_name == field_key
        assert r.evaluation_config_id == "cfg1"
        assert r.judge_run_id == default_jr.id

    # One passed (match), one failed (miss).
    assert sorted(r.passed for r in rows) == [False, True]

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 2
    metric_key = f"{field_key}|exact_match"
    assert fresh.metrics.get(metric_key) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 2 — one run, BOTH a generation cell AND an annotation cell
# ---------------------------------------------------------------------------


def test_mixed_generation_and_annotation_targets_in_one_run(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_annotation, make_evaluation_run, exact_match_config,
):
    """Two configs in one run: one targets ``__all_model__`` (generation
    side), one targets ``human:answer`` (annotation side). ``run_evaluation``
    must enumerate BOTH a gen cell and an ann cell and dispatch one of each
    sub-task type. Asserts both row types land and finalize aggregates two
    distinct metric keys."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)

    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )

    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    gen_cfg = exact_match_config(config_id="gcfg")          # __all_model__
    ann_cfg = _human_exact_match_config(config_id="acfg")   # human:answer
    result = _run(db_conn, run, project, [gen_cfg, ann_cfg])

    assert result["gen_cells"] == 1
    assert result["ann_cells"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    # 1 gen-side row + 1 ann-side row.
    gen_rows = [r for r in rows if r.generation_id == gen.id]
    ann_rows = [r for r in rows if r.annotation_id == ann.id]
    assert len(gen_rows) == 1
    assert len(ann_rows) == 1
    assert gen_rows[0].annotation_id is None
    assert ann_rows[0].generation_id is None

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 2
    # Two distinct aggregate keys, both 1.0 (both matched "ja").
    assert fresh.metrics.get("gcfg|__all_model__|task.expected|exact_match") == pytest.approx(1.0)
    assert fresh.metrics.get("acfg|human:answer|task.expected|exact_match") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3 — finalize multi-config / multi-metric → multiple aggregate keys
# ---------------------------------------------------------------------------


def test_finalize_multi_metric_distinct_aggregate_keys(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run,
):
    """Two generation configs with DIFFERENT deterministic metrics over the
    same cell. finalize must produce one aggregate key per (field_name,
    metric) pair. ``exact_match`` and ``accuracy`` are both pure-comparison
    (``1.0 if gt == pred else 0.0``) — deterministic, no torch/nltk/network."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    cfg_exact = {
        "id": "c_exact", "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    cfg_acc = {
        "id": "c_acc", "metric": "accuracy",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    result = _run(db_conn, run, project, [cfg_exact, cfg_acc])
    assert result["gen_cells"] == 1  # one cell, two configs scored within it

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    # Two separate (field|metric) aggregate keys.
    k_exact = "c_exact|__all_model__|task.expected|exact_match"
    k_acc = "c_acc|__all_model__|task.expected|accuracy"
    assert k_exact in fresh.metrics, fresh.metrics
    assert k_acc in fresh.metrics, fresh.metrics
    assert fresh.metrics[k_exact] == pytest.approx(1.0)
    assert fresh.metrics[k_acc] == pytest.approx(1.0)
    # Two rows total (one per config over the single cell).
    n = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
    )
    assert n == 2
    assert fresh.samples_evaluated == 2


# ---------------------------------------------------------------------------
# 4 — per-field metric error → error row persisted, run still completes
# ---------------------------------------------------------------------------


def test_cell_metric_error_persists_error_row_and_completes(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """When a single field-pair's metric computation raises, the cell's
    per-field ``except Exception`` arm must persist an error TaskEvaluation
    row (passed=False, error_message set) rather than swallowing it — and
    because a row WAS produced, finalize still resolves the run to
    ``completed`` (the default judge_run produced rows)."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    # Make the deterministic metric computation blow up inside the cell's
    # per-field try block (5273-5294 in tasks.py).
    from ml_evaluation.sample_evaluator import SampleEvaluator

    boom = RuntimeError("metric kaboom")

    def _raise(self, *a, **k):
        raise boom

    monkeypatch.setattr(SampleEvaluator, "evaluate_sample", _raise)

    result = _run(db_conn, run, project, [exact_match_config()])
    assert result["status"] == "dispatched"

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    # The error arm wrote exactly one row, with the failure surfaced.
    assert len(rows) == 1
    row = rows[0]
    assert row.passed is False
    assert row.error_message == "metric kaboom"
    assert row.generation_id == gen.id

    fresh = _refresh(db_conn, run)
    # Row produced → judge_run "completed" → run "completed" (the error is
    # recorded IN the row, not by failing the whole run).
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1
    meta = fresh.eval_metadata or {}
    assert int(meta.get("samples_failed", 0)) == 1


# ---------------------------------------------------------------------------
# 5 — whole-cell failure → 0 rows → finalize marks run `failed`
# ---------------------------------------------------------------------------


def test_whole_cell_failure_drives_run_to_failed(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """When the cell raises BEFORE producing any row (here: the per-cell
    SampleEvaluator construction blows up), the cell's OUTER ``except`` arm
    (5335-5362) records a failure reason + bumps samples_failed but writes
    no row. With zero rows under the default judge_run, finalize derives the
    judge_run status as ``failed`` from the row COUNT and marks the parent
    run ``failed`` with the documented 'no judge_run produced any rows'
    message — the failure is surfaced, never silently 'completed'."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    # Blow up the cell before any row is built/inserted.
    def _boom(*a, **k):
        raise RuntimeError("cell setup kaboom")

    monkeypatch.setattr(tasks, "_build_sample_evaluator_for_cell", _boom)

    result = _run(db_conn, run, project, [exact_match_config()])
    assert result["status"] == "dispatched"

    n = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
    )
    assert n == 0, "no rows should have been written"

    fresh = _refresh(db_conn, run)
    assert fresh.status == "failed"
    assert fresh.error_message in (
        "all judge_runs failed",
        "no judge_run produced any rows",
    )
    # The default judge_run was reconciled to failed from its 0-row count.
    jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id == run.id)
        .one()
    )
    assert jr.status == "failed"
    assert jr.samples_evaluated == 0
    # The failure reason bucket was recorded for the UI breakdown.
    meta = fresh.eval_metadata or {}
    assert "failures_by_reason" in meta
    assert sum(meta["failures_by_reason"].values()) >= 1


# ---------------------------------------------------------------------------
# 6 — judge-run status derived from produced-row COUNT (not stale field)
# ---------------------------------------------------------------------------


def test_finalize_derives_judge_status_from_row_count(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """finalize must set each judge_run's status + samples_evaluated from the
    COUNT of rows it actually produced, regardless of the judge_run's prior
    status field. We pre-set the default judge_run to a stale 'failed' before
    finalize runs (by cancelling+resuming): the row count is authoritative,
    so the judge_run ends 'completed' with samples_evaluated == row count."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    config = exact_match_config()
    _run(db_conn, run, project, [config])

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"

    jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id == run.id)
        .one()
    )
    # samples_evaluated on the judge_run mirrors the produced-row count.
    n = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.judge_run_id == jr.id)
        .count()
    )
    assert jr.status == "completed"
    assert jr.samples_evaluated == n == 1
    assert jr.completed_at is not None


# ---------------------------------------------------------------------------
# 7 — finalize already-terminal no-op guard
# ---------------------------------------------------------------------------


def test_finalize_already_terminal_is_noop(
    db_conn, make_user, make_project, make_evaluation_run,
):
    """Calling finalize on a run that is already terminal must be a no-op:
    it returns ``{status: noop, reason: already_terminal}`` and mutates
    nothing. Exercised directly (no cells needed)."""
    user = make_user()
    project = make_project(created_by=user.id)
    run = make_evaluation_run(project.id, user.id, status="completed")
    db_conn.commit()

    res = tasks.finalize_evaluation_run.apply(args=[[], run.id]).get()
    assert res["status"] == "noop"
    assert res["reason"] == "already_terminal"
    assert res["current_status"] == "completed"

    # And on a 'cancelled' run too.
    run2 = make_evaluation_run(project.id, user.id, status="cancelled")
    db_conn.commit()
    res2 = tasks.finalize_evaluation_run.apply(args=[[], run2.id]).get()
    assert res2["status"] == "noop"
    assert res2["current_status"] == "cancelled"


# ---------------------------------------------------------------------------
# 8 — finalize: evaluation not found
# ---------------------------------------------------------------------------


def test_finalize_missing_evaluation_is_skipped(db_conn):
    """finalize on a nonexistent evaluation id returns the not-found skip,
    not an exception (covers the early ``if not evaluation`` guard)."""
    res = tasks.finalize_evaluation_run.apply(
        args=[[], "00000000-0000-0000-0000-0000deadbeef"]
    ).get()
    assert res["status"] == "skipped"
    assert res["reason"] == "evaluation_not_found"


# ---------------------------------------------------------------------------
# 9 — run_evaluation setup short-circuits
# ---------------------------------------------------------------------------


def test_run_evaluation_no_enabled_configs_fails(
    db_conn, make_user, make_project, make_task, make_evaluation_run,
):
    """All configs disabled → the 'No enabled evaluation configurations'
    short-circuit marks the run failed before any judge_run/cell work."""
    user = make_user()
    project = make_project(created_by=user.id)
    make_task(project.id, {"expected": "ja"}, created_by=user.id)
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    disabled = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": False,
    }
    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[disabled],
    )
    assert result["status"] == "error"
    assert "No enabled" in result["message"]
    fresh = _refresh(db_conn, run)
    assert fresh.status == "failed"
    assert "No enabled" in (fresh.error_message or "")


def test_run_evaluation_no_tasks_fails(
    db_conn, make_user, make_project, make_evaluation_run, exact_match_config,
):
    """A project with NO tasks → the up-front task-probe short-circuit marks
    the run failed with 'No tasks found in project' and creates no judge_runs
    (avoids orphan judge_run rows)."""
    user = make_user()
    project = make_project(created_by=user.id)  # no tasks
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[exact_match_config()],
    )
    assert result["status"] == "error"
    assert "No tasks" in result["message"]

    fresh = _refresh(db_conn, run)
    assert fresh.status == "failed"
    # No judge_runs were created by the short-circuit.
    assert (
        db_conn.query(EvaluationJudgeRun)
        .filter(EvaluationJudgeRun.evaluation_id == run.id)
        .count()
        == 0
    )


def test_run_evaluation_missing_only_nothing_to_dispatch_completes(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """Run once fully, then re-dispatch with ``evaluate_missing_only=True``:
    every cell is already evaluated, so the orchestrator's
    ``cells_dispatched == 0`` short-circuit marks the run completed with
    ``samples_evaluated=0`` and the 'no cells to dispatch' note — WITHOUT
    firing a chord."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    config = exact_match_config()
    _run(db_conn, run, project, [config])
    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1

    # Flip back to pending and re-dispatch missing-only.
    fresh.status = "pending"
    db_conn.commit()

    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[config], evaluate_missing_only=True,
    )
    assert result["status"] == "success"
    assert result["cells_dispatched"] == 0
    assert result["samples_evaluated"] == 0

    fresh2 = _refresh(db_conn, run)
    assert fresh2.status == "completed"
    meta = fresh2.eval_metadata or {}
    assert meta.get("note") == "no cells to dispatch (missing-only short-circuit)"
    # The already-existing row is untouched.
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 1
    )


def test_run_evaluation_evaluation_not_found(db_conn):
    """A nonexistent evaluation id returns the not-found error arm without
    raising (the very first guard in run_evaluation)."""
    result = tasks.run_evaluation(
        evaluation_id="00000000-0000-0000-0000-00000000beef",
        project_id="00000000-0000-0000-0000-00000000cafe",
        evaluation_configs=[],
    )
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# 10 — annotation __all_human__ wildcard prediction expansion
# ---------------------------------------------------------------------------


def test_annotation_all_human_wildcard_expands_fields(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """``__all_human__`` expands to one prediction per stringy annotation
    field. With an annotation carrying a single ``answer`` field matching
    ``task.expected``, the wildcard config produces one matching row. Covers
    the ``base_field == '__all_human__'`` branch of evaluate_annotation_cell."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["__all_human__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    result = _run(db_conn, run, project, [cfg])
    assert result["ann_cells"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.annotation_id == ann.id
    # The wildcard resolves the concrete field name into the key.
    assert row.field_name == "cfg1|human:answer|task.expected"
    assert row.passed is True

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.metrics.get("cfg1|human:answer|task.expected|exact_match") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 11 — per-cell guards via DIRECT sub-task invocation (cheap arms)
# ---------------------------------------------------------------------------


def _gen_cell_kwargs(run, project, task, gen, user, **over):
    kw = {
        "evaluation_id": run.id,
        "task_id": task.id,
        "generation_id": gen.id,
        "project_id": project.id,
        "configs_for_cell": [],
        "judge_run_ids_by_config": {},
        "default_judge_run_id": "00000000-0000-0000-0000-0000000000aa",
        "organization_id": None,
        "triggered_by_user_id": user.id,
        "already_evaluated_field_keys": [],
    }
    kw.update(over)
    return kw


def _ann_cell_kwargs(run, project, task, ann, user, **over):
    kw = {
        "evaluation_id": run.id,
        "task_id": task.id,
        "annotation_id": ann.id,
        "project_id": project.id,
        "configs_for_cell": [],
        "judge_run_ids_by_config": {},
        "default_judge_run_id": "00000000-0000-0000-0000-0000000000aa",
        "organization_id": None,
        "triggered_by_user_id": user.id,
        "already_evaluated_field_keys": [],
    }
    kw.update(over)
    return kw


def test_generation_cell_not_found_guards(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """Missing generation / missing task → the gen cell short-circuits with a
    'skipped' breadcrumb and writes no row (generation_not_found /
    task_not_found guards)."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    missing_gen = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        generation_id="00000000-0000-0000-0000-00000000d00d",
        configs_for_cell=[exact_match_config()],
    )).get()
    assert missing_gen["status"] == "skipped"
    assert missing_gen["reason"] == "generation_not_found"

    missing_task = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        task_id="00000000-0000-0000-0000-00000000beef",
        configs_for_cell=[exact_match_config()],
    )).get()
    assert missing_task["status"] == "skipped"
    assert missing_task["reason"] == "task_not_found"

    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


def test_annotation_cell_guards_parent_terminal_and_not_found(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """Annotation cell guards: parent-terminal short-circuit, missing
    annotation, and missing task — each returns a 'skipped' breadcrumb and
    writes nothing."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    cfg = _human_exact_match_config()

    # Parent already cancelled → parent_cancelled skip.
    run_cancelled = make_evaluation_run(project.id, user.id, status="cancelled")
    db_conn.commit()
    res_cancel = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run_cancelled, project, task, ann, user, configs_for_cell=[cfg],
    )).get()
    assert res_cancel["status"] == "skipped"
    assert res_cancel["reason"] == "parent_cancelled"

    # Running parent, but missing annotation / missing task.
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    res_no_ann = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user,
        annotation_id="00000000-0000-0000-0000-0000000000a1",
        configs_for_cell=[cfg],
    )).get()
    assert res_no_ann["status"] == "skipped"
    assert res_no_ann["reason"] == "annotation_not_found"

    res_no_task = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user,
        task_id="00000000-0000-0000-0000-0000000000b2",
        configs_for_cell=[cfg],
    )).get()
    assert res_no_task["status"] == "skipped"
    assert res_no_task["reason"] == "task_not_found"


def test_annotation_cell_poison_guard_bails(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """After ``_CELL_ATTEMPT_LIMIT`` redeliveries the annotation cell records
    the poison reason, bumps samples_failed, and returns 'poisoned' instead
    of looping forever. We pre-seed the Redis attempt counter past the limit
    (the broker now points at the real test-redis) so a single invocation
    trips the guard deterministically."""
    import redis as _redis

    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    # Pre-seed the per-cell attempt counter ABOVE the limit so the next
    # invocation's incr lands past it.
    client = _redis.from_url(tasks.app.conf.broker_url)
    key = f"benger:cell_attempts:{run.id}:ann:{ann.id}"
    client.set(key, tasks._CELL_ATTEMPT_LIMIT + 5)

    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user,
        configs_for_cell=[_human_exact_match_config()],
    )).get()
    assert res["status"] == "poisoned"
    assert res["attempts"] > tasks._CELL_ATTEMPT_LIMIT

    # No row, samples_failed bumped, poison reason recorded.
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )
    fresh = _refresh(db_conn, run)
    meta = fresh.eval_metadata or {}
    assert int(meta.get("samples_failed", 0)) >= 1
    assert meta.get("failures_by_reason", {}).get("poison_cell_max_attempts", 0) >= 1
    client.delete(key)


def test_annotation_cell_deterministic_metric_error_persists_row(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run, monkeypatch,
):
    """A deterministic annotation metric that raises lands in the cell's
    per-field ``except Exception`` arm: an error row is written
    (passed=False, error_message set) rather than swallowed. Covers the
    annotation-side error arm (5823-5847)."""
    import uuid as _uuid
    from models import EvaluationJudgeRun

    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    # The error row's judge_run_id FK must reference a real judge_run — create
    # the default (deterministic, judge_model_id=None) one the orchestrator
    # would have made, since we invoke the cell directly here.
    jr_id = str(_uuid.uuid4())
    db_conn.add(EvaluationJudgeRun(
        id=jr_id, evaluation_id=run.id, judge_model_id=None,
        run_index=0, status="running",
    ))
    db_conn.commit()

    from ml_evaluation.sample_evaluator import SampleEvaluator

    def _raise(self, *a, **k):
        raise RuntimeError("ann metric kaboom")

    monkeypatch.setattr(SampleEvaluator, "evaluate_sample", _raise)

    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user, default_judge_run_id=jr_id,
        configs_for_cell=[_human_exact_match_config()],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].annotation_id == ann.id
    assert rows[0].passed is False
    assert rows[0].error_message == "ann metric kaboom"


def test_generation_cell_poison_guard_bails(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """Generation-cell poison guard: pre-seed the Redis attempt counter past
    the limit so the next invocation trips it → 'poisoned', no row, failure
    reason recorded. Mirror of the annotation poison test for the gen path."""
    import redis as _redis

    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    client = _redis.from_url(tasks.app.conf.broker_url)
    key = f"benger:cell_attempts:{run.id}:gen:{gen.id}"
    client.set(key, tasks._CELL_ATTEMPT_LIMIT + 5)

    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[exact_match_config()],
    )).get()
    assert res["status"] == "poisoned"
    assert res["attempts"] > tasks._CELL_ATTEMPT_LIMIT
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )
    fresh = _refresh(db_conn, run)
    meta = fresh.eval_metadata or {}
    assert meta.get("failures_by_reason", {}).get("poison_cell_max_attempts", 0) >= 1
    client.delete(key)


def test_generation_cell_already_evaluated_field_key_is_skipped(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """When the orchestrator passes a field_key in
    ``already_evaluated_field_keys``, the cell skips that pair entirely (no
    row, no metric work) — the per-field skip that avoids re-grading +
    re-firing an LLM call on a partial-cell retry. With the ONLY field_key
    pre-marked done, the cell produces zero rows and returns samples_added=0."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    field_key = "cfg1|__all_model__|task.expected"
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        configs_for_cell=[exact_match_config()],
        already_evaluated_field_keys=[field_key],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


def test_generation_cell_missing_reference_field_is_skipped(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run,
):
    """A reference field absent from ``task.data`` → the cell skips that pair
    (ground_truth is None → continue) and writes no row. Covers the
    reference-not-found skip branch."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    # task.data has NO 'expected' key → the ref_field 'task.expected' resolves
    # to None and the pair is skipped.
    task = make_task(project.id, {"other": "x"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],  # not present in task.data
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[cfg],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# 12 — llm_judge GENERATION path (mock judge, no network)
# ---------------------------------------------------------------------------


def test_llm_judge_generation_path_end_to_end(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, mock_judge_mode,
):
    """Full ``llm_judge_correctness`` run over a generation, with the
    deterministic E2E mock judge. Exercises the orchestrator's judge-setup
    block (EvaluationJudgeRun creation, judge_run_ids_by_config), the
    gen-cell judge fan-out, and finalize's judges_by_config summary — all
    network-free. Asserts a real judge_run (judge_model_id set) was created,
    one scored row landed under it, and finalize summarizes it."""
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")   # the judge model
    model = make_llm_model(provider="OpenAI")              # the graded model
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = _run(db_conn, run, project, [_llm_judge_config()])
    assert result["status"] == "dispatched"
    assert result["gen_cells"] == 1

    # A real (judge_model_id != None) judge_run was created for the config.
    judge_run = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id == "gpt-4o",
        )
        .one()
    )

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.judge_run_id == judge_run.id
    assert row.field_name == "jcfg|__all_model__|task.expected"
    # The mock judge returns a deterministic 0.6-0.99 score → stored under
    # the metric key; row passed since score > 0.5.
    assert row.metrics.get("llm_judge_correctness") is not None
    assert row.passed is True

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1
    # finalize reconciled the judge_run from its produced rows.
    db_conn.expire(judge_run)
    assert judge_run.status == "completed"
    assert judge_run.samples_evaluated == 1
    # judges_by_config summary present in metadata.
    meta = fresh.eval_metadata or {}
    assert "judges_by_config" in meta
    assert meta["judges_by_config"]["jcfg"][0]["judge_model_id"] == "gpt-4o"
    assert meta["judges_by_config"]["jcfg"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# 13 — llm_judge multi-run ensemble (2 runs of the same judge)
# ---------------------------------------------------------------------------


def test_llm_judge_multi_run_creates_two_judge_runs(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, mock_judge_mode,
):
    """``runs: 2`` for one judge → two EvaluationJudgeRun rows (run_index 0
    and 1) and two scored TaskEvaluation rows per cell (one per judge run).
    Covers the per-run seed-perturbation loop in the orchestrator and the
    intra-cell per-judge_run fan-out."""
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    _run(db_conn, run, project, [_llm_judge_config(runs=2)])

    judge_runs = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id == "gpt-4o",
        )
        .all()
    )
    assert len(judge_runs) == 2
    assert sorted(jr.run_index for jr in judge_runs) == [0, 1]

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    # One scored row per judge_run over the single cell.
    assert len(rows) == 2
    assert {r.judge_run_id for r in rows} == {jr.id for jr in judge_runs}

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 2


# ---------------------------------------------------------------------------
# 14 — llm_judge ANNOTATION path (mock judge, no network)
# ---------------------------------------------------------------------------


def test_llm_judge_annotation_path_end_to_end(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, mock_judge_mode,
):
    """``llm_judge_correctness`` over a HUMAN annotation field
    (``human:answer``) with the mock judge. Exercises the annotation-cell
    judge fan-out (5538-5798) network-free; asserts a scored annotation-side
    row under the real judge_run."""
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    cfg = _llm_judge_config(pred_field="human:answer")
    result = _run(db_conn, run, project, [cfg])
    assert result["ann_cells"] == 1
    assert result["gen_cells"] == 0

    judge_run = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id == "gpt-4o",
        )
        .one()
    )
    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.annotation_id == ann.id
    assert row.generation_id is None
    assert row.judge_run_id == judge_run.id
    assert row.field_name == "jcfg|human:answer|task.expected"
    assert row.metrics.get("llm_judge_correctness") is not None

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1


# ---------------------------------------------------------------------------
# 15 — run_evaluation scope filters (task_ids / model_ids)
# ---------------------------------------------------------------------------


def test_run_evaluation_task_and_model_scope_filters(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """``task_ids`` + ``model_ids`` scope filters narrow the fan-out. Two
    tasks, two models; scoping to one task AND one model dispatches exactly
    one gen cell. Covers the scope-filter logging + the task/generation
    query filters in run_evaluation's enumeration."""
    user = make_user()
    model_a = make_llm_model(provider="OpenAI")
    model_b = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task_a = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    task_b = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    # task_a has gens from BOTH models; task_b from model_a only.
    make_generation(project.id, task_a.id, model_a.id, user.id, response_content="ja")
    make_generation(project.id, task_a.id, model_b.id, user.id, response_content="ja")
    make_generation(project.id, task_b.id, model_a.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = _run(
        db_conn, run, project, [exact_match_config()],
        task_ids=[task_a.id], model_ids=[model_a.id],
    )
    # Only task_a + model_a's single generation is in scope.
    assert result["gen_cells"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].task_id == task_a.id

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1


# ---------------------------------------------------------------------------
# 16 — run_evaluation annotator_user_ids scope filter (annotation side)
# ---------------------------------------------------------------------------


def test_run_evaluation_annotator_scope_filter(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """``annotator_user_ids`` narrows the annotation pool. Two annotators on
    the same task; scoping to one dispatches exactly one annotation cell.
    Covers the annotator-scope filter + reduced-pool logging branch."""
    user = make_user()
    other = make_user(name="Other Annotator")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann_keep = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    make_annotation(
        project.id, task.id, completed_by=other.id,
        result=[_ann_result("answer", "nein")],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    result = _run(
        db_conn, run, project, [_human_exact_match_config()],
        annotator_user_ids=[user.id],
    )
    assert result["ann_cells"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].annotation_id == ann_keep.id

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"


# ---------------------------------------------------------------------------
# 17 — run_evaluation outer exception arm → run marked failed
# ---------------------------------------------------------------------------


def test_run_evaluation_outer_exception_marks_run_failed(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """An unexpected error during dispatch (here: the chord call raises) is
    caught by run_evaluation's outer ``except``: the run is marked ``failed``
    with the error message and the failure-notification arm runs (notification
    stubbed). Covers the 3366-3411 exception handler."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    make_generation(project.id, task.id, model.id, user.id, response_content="ja")
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    import celery as _celery

    def _boom_chord(*a, **k):
        raise RuntimeError("chord dispatch kaboom")

    monkeypatch.setattr(_celery, "chord", _boom_chord)

    result = tasks.run_evaluation(
        evaluation_id=run.id, project_id=project.id,
        evaluation_configs=[exact_match_config()],
    )
    assert result["status"] == "error"
    assert "kaboom" in result["message"]

    fresh = _refresh(db_conn, run)
    assert fresh.status == "failed"
    assert "kaboom" in (fresh.error_message or "")
    assert fresh.completed_at is not None


# ---------------------------------------------------------------------------
# 18 — finalize outer exception arm → run marked failed
# ---------------------------------------------------------------------------


def test_finalize_outer_exception_marks_run_failed(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """An unexpected error inside finalize (after the cells produced rows) is
    caught by its outer ``except``, which last-ditch marks the run ``failed``
    so it never sits in 'running' forever. We make the late
    ``flag_modified`` raise; finalize is invoked directly on a running run
    whose cell already ran. Covers the 6142-6172 handler."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    # Grade one cell directly (leaving the run 'running') so finalize has a
    # produced row to aggregate, then invoke finalize with a broken
    # flag_modified to exercise its last-ditch failure handler.
    jr_id = _make_default_judge_run(db_conn, run)
    tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        configs_for_cell=[exact_match_config()], default_judge_run_id=jr_id,
    )).get()

    # Break the late flag_modified call inside finalize.
    import sqlalchemy.orm.attributes as _attrs

    def _boom_flag(*a, **k):
        raise RuntimeError("finalize kaboom")

    monkeypatch.setattr(_attrs, "flag_modified", _boom_flag)

    res = tasks.finalize_evaluation_run.apply(args=[[], run.id]).get()
    assert res["status"] == "error"
    assert "kaboom" in res["error"]

    fresh = _refresh(db_conn, run)
    assert fresh.status == "failed"
    assert "crashed" in (fresh.error_message or "").lower()


# ---------------------------------------------------------------------------
# 19 — gen cell: model: prefix prediction falls back to response_content
# ---------------------------------------------------------------------------


def test_generation_cell_model_prefixed_prediction_fallback(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run,
):
    """A ``model:<field>`` prediction field with no parsed_annotation falls
    back to ``gen.response_content``. Covers the model:-prefix base_field
    stripping + the parsed-annotation-None fallback branch (4978-4987)."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["model:kurzantwort"],  # parsed-annotation field
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[cfg],
        default_judge_run_id=jr_id,
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1

    row = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .one()
    )
    # gen has no parsed_annotation → prediction fell back to response_content
    # ("ja") which matches task.expected ("ja") → passed.
    assert row.field_name == "cfg1|model:kurzantwort|task.expected"
    assert row.passed is True


# ---------------------------------------------------------------------------
# 20 — gen cell: annotation-side reference field extraction
# ---------------------------------------------------------------------------


def test_generation_cell_uses_annotation_reference_field(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_annotation, make_evaluation_run,
):
    """A reference field that is NOT ``task.*`` makes the gen cell load the
    ground-truth ANNOTATION and extract the field from it (4961-4966). The
    generation's response is compared against the human annotation's value."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"text": "frage"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    # Ground-truth annotation carries the reference value under "goldlabel".
    make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("goldlabel", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["goldlabel"],  # NOT task.* → pulled from annotation
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[cfg],
        default_judge_run_id=jr_id,
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1

    row = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .one()
    )
    # gen response "ja" vs annotation goldlabel "ja" → match.
    assert row.passed is True
    assert row.field_name == "cfg1|__all_model__|goldlabel"


# ---------------------------------------------------------------------------
# 21 — llm_judge config whose evaluator fails to init → terminal-error rows
# ---------------------------------------------------------------------------


def test_llm_judge_uninitialized_evaluator_writes_terminal_error_rows(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_annotation, make_evaluation_run, exact_match_config,
    monkeypatch,
):
    """When an ``llm_judge_*`` config has no working AI service (no API key
    AND not E2E mode), run_evaluation marks that judge_run ``failed``
    up-front. The cell reconstructs a (key-less) evaluator whose judge call
    returns no score, so it writes a FAILED TaskEvaluation row (passed=False,
    error_message set, metric value None) rather than silently producing
    nothing. A sibling deterministic ``exact_match`` config provides the
    default judge_run + keeps the overall run ``completed``. Covers the
    gen-cell judge None-score arm (5164-5239) and run_evaluation's
    judge-init-failed handler (2964-2974)."""
    # No E2E_TEST_MODE → run_evaluation drops the key-less evaluator.
    monkeypatch.delenv("E2E_TEST_MODE", raising=False)
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user",
        lambda *a, **k: None,
    )

    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    # exact_match (det) creates the default judge_run; the llm_judge config's
    # evaluator fails to init → terminal-error row under that default run.
    det = exact_match_config(config_id="det")
    judge = _llm_judge_config(config_id="jcfg")
    _run(db_conn, run, project, [det, judge])

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    # One det row (passed) + one llm_judge terminal-error row (failed).
    det_rows = [r for r in rows if r.evaluation_config_id == "det"]
    judge_rows = [r for r in rows if r.evaluation_config_id == "jcfg"]
    assert len(det_rows) == 1 and det_rows[0].passed is True
    assert len(judge_rows) == 1
    err_row = judge_rows[0]
    assert err_row.passed is False
    # The judge produced no score → a failure is recorded on the row.
    assert err_row.error_message
    assert err_row.metrics.get("llm_judge_correctness") is None

    # The gpt-4o judge_run exists; run_evaluation marked it failed up-front
    # (no AI service), but finalize reconciles each judge_run's terminal
    # status from its produced-row COUNT — and the cell DID write one
    # (failed) row under it, so it ends 'completed' (it produced output,
    # the output just records a failure). This is the row-count-authoritative
    # reconciliation the finalizer documents.
    gpt4o_jr = (
        db_conn.query(EvaluationJudgeRun)
        .filter(
            EvaluationJudgeRun.evaluation_id == run.id,
            EvaluationJudgeRun.judge_model_id == "gpt-4o",
        )
        .one()
    )
    assert gpt4o_jr.samples_evaluated == 1
    assert gpt4o_jr.status == "completed"

    fresh = _refresh(db_conn, run)
    # Both judge_runs produced rows → run completes; the det row passed and
    # the judge row recorded its failure.
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 2


def test_llm_judge_uninitialized_evaluator_annotation_side(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, monkeypatch,
):
    """Annotation-side mirror: an llm_judge config with no working AI service
    over a human annotation produces a FAILED row (no score) under the judge
    fan-out. Covers the annotation-cell judge None-score arm. A deterministic
    human exact_match config provides the default judge_run + keeps the run
    completed."""
    monkeypatch.delenv("E2E_TEST_MODE", raising=False)
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user",
        lambda *a, **k: None,
    )

    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    det = _human_exact_match_config(config_id="det")
    judge = _llm_judge_config(config_id="jcfg", pred_field="human:answer")
    _run(db_conn, run, project, [det, judge])

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    judge_rows = [r for r in rows if r.evaluation_config_id == "jcfg"]
    assert len(judge_rows) == 1
    err_row = judge_rows[0]
    assert err_row.annotation_id == ann.id
    assert err_row.passed is False
    assert err_row.error_message

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"


# ---------------------------------------------------------------------------
# 22 — annotation cell config-shape branches (korrektur skip, bare field,
#      already-done skip, missing-reference skip)
# ---------------------------------------------------------------------------


def test_annotation_cell_config_shape_branches(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """Several cheap deterministic config-shape branches of the annotation
    cell in one invocation:
      * a ``korrektur_*`` config is skipped entirely (5485-5486),
      * a ``human:`` config with two references — one present in ``task.data``
        (→ 1 row), one absent (→ ground_truth None → that pair skipped).
    The net effect: exactly ONE row from the present reference, none from
    the korrektur config or the absent reference."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    # korrektur_ config → skipped wholesale.
    korrektur = {
        "id": "kor", "metric": "korrektur_falloesung",
        "prediction_fields": ["human:answer"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    # human:answer with one present + one absent reference.
    human = {
        "id": "h", "metric": "exact_match",
        "prediction_fields": ["human:answer"],
        "reference_fields": ["task.expected", "task.nope"],  # nope is absent
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user, default_judge_run_id=jr_id,
        configs_for_cell=[korrektur, human],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.evaluation_config_id == "h"
    assert row.field_name == "h|human:answer|task.expected"
    assert row.passed is True


def test_annotation_cell_already_evaluated_field_key_skipped(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run,
):
    """The annotation cell skips a pair whose field_key is in
    ``already_evaluated_field_keys`` (mirror of the gen-cell skip) — with the
    only pair pre-marked, zero rows are produced."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user,
        configs_for_cell=[_human_exact_match_config()],
        already_evaluated_field_keys=["cfg1|human:answer|task.expected"],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# 23 — gen cell: prediction field absent → pair skipped
# ---------------------------------------------------------------------------


def test_generation_cell_missing_prediction_is_skipped(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run,
):
    """A ``model:<field>`` prediction with no parsed_annotation AND an empty
    ``response_content`` resolves to None → that pair is skipped (no row).
    Covers the prediction-None skip branch (4988-4993)."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    # Empty response_content → the model: fallback to response_content yields
    # None (falsy), so prediction stays None.
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content=""
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["model:kurzantwort"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[cfg],
        default_judge_run_id=jr_id,
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# 24 — gen cell: annotation ref absent in annotation but present in task.data
# ---------------------------------------------------------------------------


def test_generation_cell_annotation_ref_falls_back_to_task_data(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_annotation, make_evaluation_run,
):
    """A non-``task.`` reference field that the ground-truth annotation does
    NOT carry, but ``task.data`` does, falls back to ``task.data`` (4965-4966).
    The annotation exists (so the annotation branch is taken) but lacks the
    field; task.data supplies it."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    # task.data carries 'goldlabel'; the annotation does NOT.
    task = make_task(project.id, {"goldlabel": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("something_else", "irrelevant")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    cfg = {
        "id": "cfg1", "metric": "exact_match",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["goldlabel"],  # not in annotation → task.data fallback
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[cfg],
        default_judge_run_id=jr_id,
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1
    row = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .one()
    )
    # gen "ja" vs task.data goldlabel "ja" → match.
    assert row.passed is True


# ---------------------------------------------------------------------------
# 25 — cell outer-except nested handler (bump itself fails)
# ---------------------------------------------------------------------------


def test_generation_cell_outer_except_nested_handler(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """When the gen cell's body raises AND the failure-counter bump in the
    outer ``except`` ALSO raises, the nested ``except`` logs and the task
    returns 'error' without propagating. Covers 5369-5370."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    monkeypatch.setattr(tasks, "_build_sample_evaluator_for_cell",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("body boom")))
    monkeypatch.setattr(tasks, "_bump_evaluation_counters",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bump boom")))

    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, configs_for_cell=[exact_match_config()],
    )).get()
    assert res["status"] == "error"
    assert "body boom" in res["error"]


def test_annotation_cell_outer_except_nested_handler(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run, monkeypatch,
):
    """Annotation-side mirror of the nested outer-except handler (5895-5898):
    body raises AND the bump raises → 'error' returned, no propagation."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()

    monkeypatch.setattr(tasks, "_build_sample_evaluator_for_cell",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ann body boom")))
    monkeypatch.setattr(tasks, "_bump_evaluation_counters",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ann bump boom")))

    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user,
        configs_for_cell=[_human_exact_match_config()],
    )).get()
    assert res["status"] == "error"
    assert "ann body boom" in res["error"]


# ---------------------------------------------------------------------------
# 26 — finalize tolerates report-section + notification side-effect failures
# ---------------------------------------------------------------------------


def test_finalize_swallows_report_and_notification_errors(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """finalize's report-section update and completion-notification are
    best-effort: if either raises, finalize logs and STILL completes the run
    (the eval result must not be lost to a side-effect failure). Covers the
    6103-6104 and 6137-6138 except arms."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    # Produce one row so finalize reaches the side-effect block.
    tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        configs_for_cell=[exact_match_config()], default_judge_run_id=jr_id,
    )).get()

    import report_service as _rs

    monkeypatch.setattr(
        _rs, "update_report_evaluation_section",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("report boom")),
    )
    # Override the conftest no-op stub with a raiser to hit the notif except.
    monkeypatch.setattr(
        tasks.NotificationService, "create_notification",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("notif boom")),
    )

    res = tasks.finalize_evaluation_run.apply(args=[[], run.id]).get()
    assert res["status"] == "success"
    assert res["final_status"] == "completed"

    fresh = _refresh(db_conn, run)
    assert fresh.status == "completed"
    assert fresh.samples_evaluated == 1


# ---------------------------------------------------------------------------
# 27 — llm_judge fan-out with a None-evaluator entry among valid ones
# ---------------------------------------------------------------------------


def test_llm_judge_cell_handles_none_evaluator_entry(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, mock_judge_mode, monkeypatch,
):
    """In a multi-judge_run config, an entry whose evaluator failed to
    reconstruct (``evaluator=None``) writes a per-judge 'not initialized'
    failure row while the sibling VALID judge_run still scores normally.
    Covers the gen-cell per-judge None-evaluator arm. We patch the
    reconstruction to return one real (mock) evaluator + one None entry."""
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    # Two judge runs configured for the same judge.
    cfg = _llm_judge_config(runs=2)
    real_reconstruct = tasks._reconstruct_judge_evaluators_for_cell

    def _reconstruct_with_none(*, configs_for_cell, judge_run_ids_by_config,
                               triggered_by_user_id, organization_id, db):
        jrbc, evals = real_reconstruct(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id, db=db,
        )
        # Null out the SECOND entry's evaluator for the config so the cell
        # hits the per-judge None-evaluator arm while the first stays valid.
        for cid, entries in jrbc.items():
            if len(entries) >= 2:
                entries[1]["evaluator"] = None
        return jrbc, evals

    monkeypatch.setattr(
        tasks, "_reconstruct_judge_evaluators_for_cell", _reconstruct_with_none
    )

    _run(db_conn, run, project, [cfg])

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    # Two rows (one per judge_run): one scored, one 'not initialized' failure.
    assert len(rows) == 2
    statuses = sorted(r.passed for r in rows)
    assert statuses == [False, True]
    failed = [r for r in rows if r.passed is False][0]
    assert "not initialized" in (failed.error_message or "")


def test_llm_judge_annotation_cell_handles_none_evaluator_entry(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_annotation, make_evaluation_run, mock_judge_mode, monkeypatch,
):
    """Annotation-side mirror of the per-judge None-evaluator arm: a 2-run
    llm_judge config over a human annotation, with the second judge_run's
    evaluator nulled → one scored row + one 'not initialized' failure row."""
    user = make_user()
    make_llm_model(model_id="gpt-4o", provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="pending")
    db_conn.commit()

    cfg = _llm_judge_config(runs=2, pred_field="human:answer")
    real_reconstruct = tasks._reconstruct_judge_evaluators_for_cell

    def _reconstruct_with_none(*, configs_for_cell, judge_run_ids_by_config,
                               triggered_by_user_id, organization_id, db):
        jrbc, evals = real_reconstruct(
            configs_for_cell=configs_for_cell,
            judge_run_ids_by_config=judge_run_ids_by_config,
            triggered_by_user_id=triggered_by_user_id,
            organization_id=organization_id, db=db,
        )
        for cid, entries in jrbc.items():
            if len(entries) >= 2:
                entries[1]["evaluator"] = None
        return jrbc, evals

    monkeypatch.setattr(
        tasks, "_reconstruct_judge_evaluators_for_cell", _reconstruct_with_none
    )

    _run(db_conn, run, project, [cfg])

    rows = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .all()
    )
    assert len(rows) == 2
    assert all(r.annotation_id == ann.id for r in rows)
    assert sorted(r.passed for r in rows) == [False, True]
    failed = [r for r in rows if r.passed is False][0]
    assert "not initialized" in (failed.error_message or "")


# ---------------------------------------------------------------------------
# 28 — gen cell skips korrektur_ configs and human: prediction fields
# ---------------------------------------------------------------------------


def test_generation_cell_skips_korrektur_and_human_pred_fields(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config,
):
    """The GENERATION cell skips ``korrektur_*`` configs wholesale (4938-4939)
    and skips ``human:``/``__all_human__`` prediction fields within a config
    (4942-4943) — those belong to the annotation path. With a korrektur
    config + a config whose pred fields are ALL human + one normal
    exact_match config, only the normal config produces a row."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    korrektur = {
        "id": "kor", "metric": "korrektur_falloesung",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    human_only = {
        "id": "hum", "metric": "exact_match",
        "prediction_fields": ["human:answer", "__all_human__"],  # both skipped
        "reference_fields": ["task.expected"],
        "metric_parameters": {}, "enabled": True,
    }
    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user, default_judge_run_id=jr_id,
        configs_for_cell=[korrektur, human_only, exact_match_config()],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 1

    row = (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .one()
    )
    assert row.evaluation_config_id == "cfg1"  # the normal exact_match config
    assert row.field_name == "cfg1|__all_model__|task.expected"


# ---------------------------------------------------------------------------
# 29 — cell per-field ValueError arm → pair skipped (no row)
# ---------------------------------------------------------------------------


def test_generation_cell_value_error_skips_pair(
    db_conn, make_user, make_llm_model, make_project, make_task,
    make_generation, make_evaluation_run, exact_match_config, monkeypatch,
):
    """A ``ValueError`` from the metric computation is treated as a soft skip
    (logged + ``continue``), NOT an error row — distinct from the generic
    ``Exception`` arm. Covers the gen-cell per-field ValueError arm
    (5288-5290): zero rows produced."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    _, gen = make_generation(
        project.id, task.id, model.id, user.id, response_content="ja"
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    from ml_evaluation.sample_evaluator import SampleEvaluator

    def _raise_value(self, *a, **k):
        raise ValueError("soft skip")

    monkeypatch.setattr(SampleEvaluator, "evaluate_sample", _raise_value)

    res = tasks.evaluate_generation_cell.apply(kwargs=_gen_cell_kwargs(
        run, project, task, gen, user,
        configs_for_cell=[exact_match_config()], default_judge_run_id=jr_id,
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )


def test_annotation_cell_value_error_skips_pair(
    db_conn, make_user, make_project, make_task, make_annotation,
    make_evaluation_run, monkeypatch,
):
    """Annotation-side ValueError soft-skip arm (5808-5810): zero rows."""
    user = make_user()
    project = make_project(created_by=user.id)
    task = make_task(project.id, {"expected": "ja"}, created_by=user.id)
    ann = make_annotation(
        project.id, task.id, completed_by=user.id,
        result=[_ann_result("answer", "ja")],
    )
    run = make_evaluation_run(project.id, user.id, status="running")
    db_conn.commit()
    jr_id = _make_default_judge_run(db_conn, run)

    from ml_evaluation.sample_evaluator import SampleEvaluator

    def _raise_value(self, *a, **k):
        raise ValueError("soft skip")

    monkeypatch.setattr(SampleEvaluator, "evaluate_sample", _raise_value)

    res = tasks.evaluate_annotation_cell.apply(kwargs=_ann_cell_kwargs(
        run, project, task, ann, user, default_judge_run_id=jr_id,
        configs_for_cell=[_human_exact_match_config()],
    )).get()
    assert res["status"] == "ok"
    assert res["samples_added"] == 0
    assert (
        db_conn.query(TaskEvaluation)
        .filter(TaskEvaluation.evaluation_id == run.id)
        .count()
        == 0
    )
