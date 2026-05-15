"""Worker-side tests for the per-cell evaluation fan-out refactor.

Mirrors `test_run_evaluation_annotator_scope.py` style: signature
contracts (Layer 1) + source contracts (Layer 2). DB-free, fast,
catches architectural regressions without spinning up Celery or Postgres.

What's being pinned:
- The new sub-task signatures so the orchestrator's `chord(...)`
  dispatch keyword arguments stay in lockstep with what the sub-tasks
  accept. A drift here silently breaks dispatch at runtime.
- The orchestrator actually uses Celery `chord` (no longer iterates
  in-process) and dispatches sub-tasks to `queue="evaluation"`.
- Sub-tasks use the bulk-upsert helper with `ON CONFLICT DO NOTHING`
  (idempotent retries; defense-in-depth against concurrent triggers).
- The atomic counter-bump SQL pattern is in place (not read-modify-write).
- The finalizer has the idempotency guard against chord redelivery.
- Sub-tasks never call `_create_judge_run` — that race-prone helper
  remains orchestrator-only.

The end-to-end "100 cells × 3 metrics through real chord" test belongs
in `tests/integration/` and is intentionally out of scope here so this
file stays runnable in the fast unit pass.
"""

import inspect
import re


# ---------------------------------------------------------------------------
# Layer 1: signature contracts
#
# `chord(group(sub_sigs))(finalize_sig)` passes kwargs by name through
# Celery — a positional-arg shuffle in any of these three functions
# breaks dispatch silently. The asserts below catch that.
# ---------------------------------------------------------------------------


def _unwrap(task):
    """Get the plain Python callable behind an `@app.task` decorator."""
    return getattr(task, "__wrapped__", task.run if hasattr(task, "run") else task)


def test_evaluate_generation_cell_signature():
    from tasks import evaluate_generation_cell

    fn = _unwrap(evaluate_generation_cell)
    params = inspect.signature(fn).parameters
    expected = {
        "evaluation_id",
        "task_id",
        "generation_id",
        "project_id",
        "configs_for_cell",
        "judge_run_ids_by_config",
        "default_judge_run_id",
        "organization_id",
        "triggered_by_user_id",
        "label_config_version",
    }
    missing = expected - set(params.keys())
    assert not missing, f"evaluate_generation_cell missing kwargs: {missing}"


def test_evaluate_annotation_cell_signature():
    from tasks import evaluate_annotation_cell

    fn = _unwrap(evaluate_annotation_cell)
    params = inspect.signature(fn).parameters
    expected = {
        "evaluation_id",
        "task_id",
        "annotation_id",
        "project_id",
        "configs_for_cell",
        "judge_run_ids_by_config",
        "default_judge_run_id",
        "organization_id",
        "triggered_by_user_id",
    }
    missing = expected - set(params.keys())
    assert not missing, f"evaluate_annotation_cell missing kwargs: {missing}"


def test_finalize_evaluation_run_signature():
    """Celery chord callback convention: header sub-task return values are
    injected as the first positional arg. Pin that the first parameter is
    `_sub_task_results` (consumed only as a chord-protocol placeholder —
    finalizer reads state from DB) and `evaluation_id` is the keyword arg
    the orchestrator passes."""
    from tasks import finalize_evaluation_run

    fn = _unwrap(finalize_evaluation_run)
    params = list(inspect.signature(fn).parameters.items())
    # First param is `self` (bind=True) or `_sub_task_results` (bind=False).
    # Celery's bind=True prepends `self` so the chord-injected list lands
    # at index 1; without bind it lands at index 0. Accept either to keep
    # this test independent of whether we toggle `bind=`.
    names = [n for n, _ in params]
    assert (
        names[0] in ("self", "_sub_task_results")
        and "_sub_task_results" in names
        and "evaluation_id" in names
    ), f"finalize_evaluation_run param order looks wrong: {names}"


# ---------------------------------------------------------------------------
# Layer 2: source contracts
#
# Pin the architectural decisions in the source string. Each `assert`
# names the specific decision so failures point at what regressed.
# ---------------------------------------------------------------------------


def _tasks_source() -> str:
    import tasks
    return inspect.getsource(tasks)


def test_orchestrator_uses_celery_chord_dispatch():
    """The orchestrator must dispatch sub-tasks via a Celery chord. If
    someone reintroduces an in-process loop here, the chord callback
    won't fire and the parent EvaluationRun hangs in `running` forever."""
    src = _tasks_source()
    assert "from celery import chord" in src, (
        "orchestrator must import chord from celery"
    )
    assert re.search(r"chord\([^)]*header_sigs[^)]*\)\(", src) or re.search(
        r"chord\(\s*header_sigs\s*\)\(", src
    ), "expected `chord(header_sigs)(callback_sig)` dispatch shape"


def test_sub_tasks_dispatch_to_evaluation_queue():
    """Both cell sub-tasks and the finalizer must be dispatched to the
    dedicated `evaluation` queue so they don't compete with generation
    on the shared `celery`/`default` pool (the contention that prompted
    this refactor in the first place)."""
    src = _tasks_source()
    # The orchestrator dispatches three signatures; each must set the queue.
    assert src.count('queue="evaluation"') >= 3, (
        "orchestrator must dispatch all three sub-task signatures to "
        "queue=\"evaluation\""
    )


def test_bulk_upsert_uses_on_conflict_do_nothing():
    """Sub-tasks must use `ON CONFLICT DO NOTHING` against the partial
    unique index from migration 048. Without this, concurrent retries
    or chord redeliveries duplicate-write TaskEvaluation rows and
    pollute the metric aggregates."""
    src = _tasks_source()
    assert "on_conflict_do_nothing" in src, (
        "sub-tasks must use postgresql.insert(...).on_conflict_do_nothing()"
    )
    assert "_bulk_upsert_task_evaluations" in src, (
        "expected the shared bulk-upsert helper to be defined and used"
    )


def test_bulk_upsert_returns_actual_inserts_for_redelivery_safety():
    """`_bulk_upsert_task_evaluations` must use `RETURNING` and return
    the count of rows that ACTUALLY landed (after `ON CONFLICT DO
    NOTHING` skipped duplicates). Sub-tasks must bump the parent
    counter by this returned count, NOT by the requested count.

    Why: with `acks_late=True`, a worker crashing between task
    completion and ack triggers Celery to redeliver. The redelivered
    task re-runs, all its inserts conflict (returning 0 rows), and the
    counter bump must be 0 — otherwise `samples_evaluated` over-counts
    and `samples_passed`/`samples_failed` drift from reality."""
    src = _tasks_source()
    assert ".returning(" in src, (
        "_bulk_upsert_task_evaluations must use RETURNING so callers "
        "can bump by the actually-inserted count, not the requested count"
    )
    # The sub-tasks must unpack and use the three-tuple return.
    assert "n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations" in src, (
        "sub-tasks must derive counter-bump values from the helper's "
        "RETURNING-derived tuple, not from local in-loop tallies"
    )


def test_sub_tasks_use_acks_late_for_chord_completeness():
    """Cell sub-tasks must have `acks_late=True` + `reject_on_worker_lost=True`.

    Without `acks_late`, a worker SIGKILL/OOM mid-cell loses the
    message; the chord barrier never sees that header's result, and
    the chord callback (`finalize_evaluation_run`) never fires. The
    parent EvaluationRun then sits in `running` forever. At ~6940 cells
    per real eval, lost cells are essentially guaranteed.

    `reject_on_worker_lost=True` ensures the message goes back to the
    broker when the worker dies, instead of disappearing."""
    src = _tasks_source()
    # Both sub-tasks + the finalizer get the same treatment.
    for tag in (
        "tasks.evaluate_generation_cell",
        "tasks.evaluate_annotation_cell",
        "tasks.finalize_evaluation_run",
    ):
        # Find the decorator block for this task. Anchor on `)\s*\ndef `
        # rather than the lazy `.*?)` — the lazy form stops at the FIRST
        # `)` it sees, which is fragile if a future kwarg value contains
        # parens (e.g. `retry_backoff_max=timedelta(seconds=30)`). The
        # `\)\s*\ndef ` anchor guarantees we capture through the actual
        # decorator close.
        m = re.search(
            r'@app\.task\(\s*name="' + re.escape(tag) + r'".*?\)\s*\ndef ',
            src, re.DOTALL,
        )
        assert m, f"could not locate decorator for {tag}"
        deco = m.group(0)
        # Anchor on the actual kwarg (whitespace-tolerant) so a stray
        # `acks_late=True` inside a docstring or comment block doesn't
        # falsely satisfy the assertion.
        assert re.search(r"\backs_late\s*=\s*True\b", deco), (
            f"{tag} must set acks_late=True so worker death triggers redelivery"
        )
        assert re.search(r"\breject_on_worker_lost\s*=\s*True\b", deco), (
            f"{tag} must set reject_on_worker_lost=True for redelivery on SIGKILL"
        )


def test_cell_sub_tasks_short_circuit_on_parent_cancel():
    """Once chord dispatches ~6940 sub-tasks, cancelling the parent run
    only marks status='cancelled'; the sub-tasks themselves keep
    running and burn LLM quota unless they re-check parent status.

    Pin: both cell sub-tasks must read parent status at entry and skip
    when it's terminal. Cheap (one indexed SELECT)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for fn_name in ("evaluate_generation_cell", "evaluate_annotation_cell"):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                body_src = ast.get_source_segment(src, node) or ""
                assert "parent_status" in body_src and (
                    '"cancelled"' in body_src or "'cancelled'" in body_src
                ), (
                    f"{fn_name} must read EvaluationRun.status at entry and "
                    f"short-circuit on cancelled/terminal to avoid burning "
                    f"LLM quota on already-cancelled evals"
                )
                break
        else:
            raise AssertionError(f"function {fn_name} not found in tasks.py")


def test_counter_bump_skips_when_parent_terminal():
    """Defense in depth against the finalize TOCTOU race: even if a
    late sub-task bump lands between finalize's `db.refresh` and
    `db.commit`, the SQL UPDATE filter `status NOT IN
    ('completed','failed','cancelled')` makes it a no-op (rowcount=0).
    Without this, the late bump silently clobbers the finalized
    counters in `eval_metadata`."""
    src = _tasks_source()
    assert re.search(
        r"status\s+NOT\s+IN\s*\(\s*'completed'\s*,\s*'failed'\s*,\s*'cancelled'\s*\)",
        src,
    ), (
        "_bump_evaluation_counters UPDATE must include "
        "`AND status NOT IN ('completed','failed','cancelled')` so late "
        "bumps after finalize are no-ops"
    )


def test_counter_bump_uses_atomic_sql_increment():
    """`samples_evaluated` (and the JSON-blob counters
    `samples_passed`/`samples_failed`) must be bumped via SQL
    `col = col + :n` so concurrent sub-tasks don't lose updates. A
    Python-side `evaluation.samples_evaluated += local_n` would race."""
    src = _tasks_source()
    assert re.search(
        r"samples_evaluated\s*=\s*COALESCE\(samples_evaluated,\s*0\)\s*\+\s*:n",
        src,
    ), "expected atomic `samples_evaluated = COALESCE(...) + :n` SQL bump"
    assert "jsonb_set" in src, (
        "expected jsonb_set for atomic samples_passed/samples_failed bumps"
    )
    # Postgres 18 (the post-Broadcom Bitnami image content) enforces
    # FIPS-strict OpenSSL and refuses implicit json↔jsonb coercion. The
    # `eval_metadata` column is `json` (legacy), so the bump UPDATE must
    # cast explicitly: read as `::jsonb`, write back as `::json`.
    assert "eval_metadata::jsonb" in src, (
        "expected explicit ::jsonb cast on read side (Postgres 18 FIPS-strict)"
    )
    assert ")::json" in src, (
        "expected explicit ::json cast on write side (Postgres 18 FIPS-strict)"
    )


def test_finalizer_has_idempotency_guard():
    """The chord callback can be redelivered if the worker dies between
    `finalize_evaluation_run` completing its work and Celery ack'ing the
    result. The finalizer must short-circuit if the parent is already
    terminal (`completed`/`failed`/`cancelled`) so a redelivery doesn't
    e.g. re-fire the completion notification."""
    src = _tasks_source()
    assert re.search(
        r"evaluation\.status\s+in\s*\(\s*[\"']completed[\"']\s*,\s*[\"']failed[\"']",
        src,
    ), "finalize_evaluation_run must guard against re-entry on terminal status"


def test_sub_tasks_do_not_create_judge_runs():
    """`_create_judge_run` does a non-atomic SELECT-then-INSERT against
    the `uq_evaluation_judge_runs_eval_model_index` unique constraint.
    Under fan-out, concurrent sub-tasks would race here. The
    orchestrator must own judge_run creation; sub-tasks only consume IDs
    the orchestrator pre-populated."""
    src = _tasks_source()
    # Locate the two sub-task function bodies and assert _create_judge_run
    # is not referenced inside either.
    import ast
    tree = ast.parse(src)
    sub_task_names = {"evaluate_generation_cell", "evaluate_annotation_cell"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in sub_task_names:
            body_src = ast.get_source_segment(src, node) or ""
            assert "_create_judge_run" not in body_src, (
                f"{node.name} must not call _create_judge_run — orchestrator "
                f"pre-creates all judge_runs to avoid UQ races"
            )


def test_orchestrator_pre_creates_judge_runs_synchronously():
    """The orchestrator must call `_create_judge_run` synchronously
    BEFORE dispatching the chord. Otherwise sub-tasks would be the only
    callers and we'd hit the race condition that motivated the previous
    test."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_evaluation":
            body_src = ast.get_source_segment(src, node) or ""
            assert "_create_judge_run" in body_src, (
                "orchestrator must call _create_judge_run during setup phase"
            )
            assert "chord(" in body_src, (
                "orchestrator must dispatch the chord (no in-process loop)"
            )
            # Order: _create_judge_run calls come before the chord dispatch.
            idx_create = body_src.index("_create_judge_run")
            idx_chord = body_src.index("chord(")
            assert idx_create < idx_chord, (
                "_create_judge_run must run BEFORE chord dispatch"
            )
            return
    raise AssertionError("run_evaluation function not found")


def test_orchestrator_persists_judge_run_ids_for_finalizer():
    """The finalizer rebuilds the `judges_by_config` summary from
    `eval_metadata.judge_run_ids_by_config`. If the orchestrator stops
    persisting it, the frontend's Judges tab silently shows blank."""
    src = _tasks_source()
    assert '"judge_run_ids_by_config"' in src, (
        "orchestrator must persist judge_run_ids_by_config into eval_metadata"
    )


def test_orchestrator_preloads_missing_only_skip_sets():
    """Pre-filtering the chord header against the existing-evaluations
    skip set keeps Celery message count under control on retries (we
    don't fan out N×K cells just to ON-CONFLICT them away inside each
    sub-task)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_evaluation":
            body_src = ast.get_source_segment(src, node) or ""
            # Both skip sets get materialized in the orchestrator's pre-filter.
            assert "evaluated_by_gen" in body_src, (
                "orchestrator must build the gen-side missing-only skip set"
            )
            assert "evaluated_by_ann" in body_src, (
                "orchestrator must build the ann-side missing-only skip set"
            )
            assert "all_expected_field_keys.issubset" in body_src, (
                "orchestrator must skip fully-evaluated cells before dispatch"
            )
            # Status filter must include 'cancelled' so successful rows
            # under a cancelled parent run are still reused on re-trigger
            # in missing-only mode (e.g. an admin cancels mid-run and the
            # user re-triggers via the UI's "evaluate missing" path).
            assert body_src.count('"cancelled"') >= 2, (
                "preload status filter must include 'cancelled' at both "
                "gen-side and ann-side sites"
            )
            return
    raise AssertionError("run_evaluation function not found")


def test_finalizer_recomputes_metrics_from_db():
    """Per-sub-task aggregate state can't be shared safely under fan-out,
    so the finalizer recomputes from `TaskEvaluation` rows. Pin that the
    SELECT happens (not just reads back the parent's pre-existing
    `metrics` field)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "finalize_evaluation_run":
            body_src = ast.get_source_segment(src, node) or ""
            assert re.search(
                r"SELECT\s+field_name,\s*metrics\s+FROM\s+task_evaluations",
                body_src,
                re.IGNORECASE,
            ), "finalizer must SELECT field_name + metrics from task_evaluations"
            return
    raise AssertionError("finalize_evaluation_run function not found")


def test_sub_tasks_reconstruct_evaluators_per_process():
    """Each sub-task instantiates its own `LLMJudgeEvaluator` per worker
    process via the helper. The helper signature is the contract — if it
    drifts (e.g. starts requiring a shared cache), sub-tasks will fail
    silently when run under real Celery."""
    src = _tasks_source()
    assert "_reconstruct_judge_evaluators_for_cell" in src, (
        "expected the per-cell judge-evaluator reconstruction helper"
    )
    assert "create_llm_judge_for_user" in src, (
        "helper must call create_llm_judge_for_user (mirrors orchestrator init)"
    )


def test_orchestrator_short_circuits_on_zero_cells():
    """A `missing-only` run that finds nothing left to do should mark
    the EvaluationRun as `completed` immediately (not dispatch an empty
    chord, which would never invoke the finalizer)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_evaluation":
            body_src = ast.get_source_segment(src, node) or ""
            assert "cells_dispatched == 0" in body_src, (
                "orchestrator must short-circuit when no cells need dispatch"
            )
            return
    raise AssertionError("run_evaluation function not found")
