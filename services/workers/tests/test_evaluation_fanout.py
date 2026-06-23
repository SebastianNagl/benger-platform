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


def _cell_source() -> str:
    """Source of the cell-evaluation bodies. They were extracted from tasks.py
    into ``evaluation/cell_evaluator.py`` (thin @app.task wrappers stay in
    tasks.py; the ~1100-line bodies live here as ``*_impl``). Pins on cell-body
    decisions read this; pins on the orchestrator/helpers/decorators still read
    ``_tasks_source()`` (those stayed in tasks.py)."""
    from evaluation import cell_evaluator
    return inspect.getsource(cell_evaluator)


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
    # The sub-tasks must unpack and use the three-tuple return. The cell bodies
    # live in cell_evaluator now (the helper itself stays in tasks.py).
    assert "n_inserted, n_passed, n_failed = _bulk_upsert_task_evaluations" in _cell_source(), (
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
    src = _cell_source()
    import ast
    tree = ast.parse(src)
    # The cell bodies are the `*_impl` functions in cell_evaluator.py (thin
    # wrappers in tasks.py just delegate).
    for fn_name in ("evaluate_generation_cell_impl", "evaluate_annotation_cell_impl"):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == fn_name:
                body_src = ast.get_source_segment(src, node) or ""
                assert "parent_status" in body_src and (
                    '"cancelled"' in body_src or "'cancelled'" in body_src
                ), (
                    f"{fn_name} must read EvaluationRun.status at entry and "
                    "short-circuit on cancelled/terminal to avoid burning "
                    "LLM quota on already-cancelled evals"
                )
                break
        else:
            raise AssertionError(f"function {fn_name} not found in cell_evaluator.py")


def test_cell_sub_tasks_have_poison_cell_guard():
    """A cell that deterministically OOMs would be redelivered
    indefinitely under `reject_on_worker_lost=True` (broker-level
    redeliveries don't decrement `max_retries`). The Redis-backed
    `_record_cell_attempt` counter caps redeliveries and short-circuits
    after `_CELL_ATTEMPT_LIMIT` so the chord still completes."""
    src = _tasks_source()
    assert "_record_cell_attempt" in src, "missing poison-cell counter helper"
    assert "_CELL_ATTEMPT_LIMIT" in src, "missing poison-cell limit constant"
    # Both sub-tasks invoke the guard near entry and short-circuit past the
    # limit. The call sites live in the cell bodies (cell_evaluator); the helper
    # + limit constant stay in tasks.py (asserted above).
    assert _cell_source().count("_record_cell_attempt(evaluation_id, ") >= 2, (
        "both cell sub-tasks must call _record_cell_attempt to share the cap"
    )
    # The skip path must TAG the failure at BOTH cell bodies. Assert it in
    # cell_evaluator (the real tagging sites) — NOT in tasks.py, where the tag
    # only appears once as the `_FAILURE_REASON_BUCKETS` allowlist constant, so
    # both tagging calls could be deleted and a tasks-source check would stay
    # green (a pin satisfiable by broken production code).
    assert _cell_source().count("poison_cell_max_attempts") >= 2, (
        "both cell sub-tasks' poison-skip paths must tag the failure_reason "
        "'poison_cell_max_attempts' so the UI can surface 'N cells went poison'"
    )


def test_bulk_upsert_groups_mixed_row_shapes_per_keyset():
    """The cell sub-task's `sample_results` mixes rows from
    `SampleEvaluator.evaluate_sample()` (full payloads with
    `confidence_score`, `processing_time_ms`) with hand-built error
    dicts that omit those keys. Two Postgres failure modes if we pass
    mixed shapes to one multi-row INSERT:
      1. SQLAlchemy uses the first row's keyset and rejects later
         rows that drop columns ("explicitly rendered as a bound
         parameter" error).
      2. If we union-fill missing keys with None to satisfy (1), we
         override Postgres' server defaults on NOT NULL columns
         (`truncated`/`refusal` have `server_default=false`) and the
         insert fails the NOT NULL constraint.

    Pin: helper must group by keyset and emit one INSERT per group,
    so each group has a consistent column list AND server defaults
    still apply to columns NO row in the group provides.

    Both failure modes hit on prod ZJS Fälle (2026-05-15):
      - First retrigger (PR #94 worker): mode 1, ~70% of cells errored
      - Second retrigger (post-hotfix #97 union-fill): mode 2, ~100%
        of LLM-judge cells errored on `truncated`/`refusal` NOT NULL
    """
    from unittest.mock import MagicMock
    from tasks import _bulk_upsert_task_evaluations

    executed_stmts = []

    def fake_execute(stmt):
        executed_stmts.append(stmt)
        r = MagicMock()
        r.fetchall.return_value = []
        return r

    fake_db = MagicMock()
    fake_db.execute.side_effect = fake_execute

    rows = [
        # Success-shape row (SampleEvaluator output): has `confidence_score`.
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "evaluation_id": "22222222-2222-2222-2222-222222222222",
            "judge_run_id": "33333333-3333-3333-3333-333333333333",
            "task_id": "44444444-4444-4444-4444-444444444444",
            "generation_id": "55555555-5555-5555-5555-555555555555",
            "field_name": "rouge|p|r",
            "answer_type": "text",
            "ground_truth": "x", "prediction": "y",
            "metrics": {"rouge": 0.5},
            "passed": True,
            "confidence_score": 0.8,
            "processing_time_ms": 42,
        },
        # Another success-shape row, same keyset (should batch with row 1).
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "evaluation_id": "22222222-2222-2222-2222-222222222222",
            "judge_run_id": "33333333-3333-3333-3333-333333333333",
            "task_id": "44444444-4444-4444-4444-444444444444",
            "generation_id": "55555555-5555-5555-5555-555555555555",
            "field_name": "meteor|p|r",
            "answer_type": "text",
            "ground_truth": "x", "prediction": "y",
            "metrics": {"meteor": 0.3},
            "passed": False,
            "confidence_score": 0.4,
            "processing_time_ms": 7,
        },
        # Error-shape row: missing `confidence_score`/`processing_time_ms`,
        # has `error_message` instead.
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "evaluation_id": "22222222-2222-2222-2222-222222222222",
            "judge_run_id": "33333333-3333-3333-3333-333333333333",
            "task_id": "44444444-4444-4444-4444-444444444444",
            "generation_id": "55555555-5555-5555-5555-555555555555",
            "field_name": "bleu|p|r",
            "answer_type": "text",
            "ground_truth": "x", "prediction": "y",
            "metrics": {},
            "passed": False,
            "error_message": "boom",
        },
    ]
    _bulk_upsert_task_evaluations(fake_db, rows)

    # Should produce exactly 2 INSERT statements, one per distinct
    # keyset (2 success-shape rows in one, 1 error-shape row in the other).
    assert len(executed_stmts) == 2, (
        f"expected 2 INSERTs (one per keyset); got {len(executed_stmts)}"
    )


def test_bulk_upsert_does_not_null_fill_to_preserve_server_defaults():
    """Critical sub-property of the per-keyset grouping fix: each
    group's INSERT must only include columns the rows in that group
    have, so columns no row provides (e.g. `truncated`/`refusal` on
    a row that's not from the LLM-judge path) fall back to Postgres'
    server defaults. Union-filling with None overrides those defaults
    and fails the NOT NULL constraint."""
    import inspect
    from tasks import _bulk_upsert_task_evaluations

    src = inspect.getsource(_bulk_upsert_task_evaluations)
    # The helper must NOT carry the union-fill pattern that overrides
    # server defaults. Search for the broken pattern explicitly.
    assert "set().union(*(r.keys()" not in src, (
        "helper must not union-fill missing keys with None — that "
        "overrides server defaults on NOT NULL columns like "
        "truncated/refusal and fails the insert"
    )
    # Positive: must group by keyset.
    assert "defaultdict" in src, "helper must group rows by keyset via defaultdict"
    assert "sorted(r.keys())" in src or "tuple(sorted" in src, (
        "helper must key the per-keyset grouping on a stable tuple "
        "(sorted column names)"
    )


def test_bulk_upsert_emits_on_conflict_do_nothing_returning_passed():
    """Real check on the SQL that `_bulk_upsert_task_evaluations`
    generates. Source-grep tests catch deleted call sites but miss
    a refactor that e.g. swaps `.on_conflict_do_nothing()` for
    `.on_conflict_do_update(...)` or drops the RETURNING clause —
    both would silently break the redelivery-safe counter math.

    Compiles the actual SQLAlchemy statement with literal binds and
    asserts the dialect-rendered SQL contains the two clauses we
    depend on (`ON CONFLICT DO NOTHING` and `RETURNING ...passed`).
    """
    from unittest.mock import MagicMock
    from sqlalchemy.dialects import postgresql

    # Stub the import of `tasks` enough that `_bulk_upsert_task_evaluations`
    # is callable. The function constructs and executes a stmt — patch
    # `db.execute` to capture the stmt, then compile it ourselves.
    from tasks import _bulk_upsert_task_evaluations

    captured = {}

    def fake_execute(stmt):
        captured["stmt"] = stmt
        # Empty result set so the function returns (0, 0, 0) cleanly.
        result = MagicMock()
        result.fetchall.return_value = []
        return result

    fake_db = MagicMock()
    fake_db.execute.side_effect = fake_execute

    rows = [{
        "id": "11111111-1111-1111-1111-111111111111",
        "evaluation_id": "22222222-2222-2222-2222-222222222222",
        "judge_run_id": "33333333-3333-3333-3333-333333333333",
        "task_id": "44444444-4444-4444-4444-444444444444",
        "generation_id": "55555555-5555-5555-5555-555555555555",
        "annotation_id": None,
        "field_name": "cfg|p|r",
        "answer_type": "text",
        "ground_truth": "x",
        "prediction": "y",
        "metrics": {},
        "passed": False,
    }]
    result = _bulk_upsert_task_evaluations(fake_db, rows)

    # Function contract: empty fetchall → (0, 0, 0) regardless of input size.
    assert result == (0, 0, 0)
    # Captured stmt compiles with the postgresql dialect and contains
    # the two clauses we care about.
    compiled = str(
        captured["stmt"].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).upper()
    assert "ON CONFLICT DO NOTHING" in compiled, (
        "_bulk_upsert_task_evaluations must emit ON CONFLICT DO NOTHING "
        "so redelivered cells silently skip-insert instead of erroring"
    )
    assert "RETURNING" in compiled, (
        "_bulk_upsert_task_evaluations must use RETURNING so caller can "
        "bump parent counter by actual inserted count, not requested count"
    )
    assert "PASSED" in compiled, (
        "RETURNING clause must include `passed` so the helper can split "
        "(n_inserted, n_passed, n_failed)"
    )


def test_classify_cell_failure_is_whitelisted():
    """Unknown exception classes must NOT leak their class name into
    `failures_by_reason` keys — that would let a misbehaving SDK
    emitting one new exception per call grow the JSON object
    unboundedly inside the parent's `eval_metadata`."""
    from tasks import _FAILURE_REASON_BUCKETS, _classify_cell_failure

    class WeirdSDKException(Exception):
        pass

    # An exception class the classifier doesn't recognise must bucket
    # into the whitelist's catch-all, not leak the class name.
    assert _classify_cell_failure(WeirdSDKException("boom")) == "other"
    assert "WeirdSDKException" not in _FAILURE_REASON_BUCKETS


def test_classify_cell_failure_no_substring_false_positives():
    """The pre-fix classifier used `"rate" in exc.__class__.__name__.lower()`
    which incorrectly bucketed `EnumerateError`, `AggregateError`,
    `MigrateError` into `rate_limit`. Pin the fix: only classes whose
    name actually ends in the canonical suffix get bucketed."""
    from tasks import _classify_cell_failure

    class EnumerateError(Exception): pass
    class AggregateError(Exception): pass
    class MigrateError(Exception): pass
    class RateLimitError(Exception): pass

    assert _classify_cell_failure(EnumerateError("...")) == "other"
    assert _classify_cell_failure(AggregateError("...")) == "other"
    assert _classify_cell_failure(MigrateError("...")) == "other"
    # Real rate-limit class is still classified correctly.
    assert _classify_cell_failure(RateLimitError("...")) == "rate_limit"


def test_cell_sub_tasks_record_failure_reasons():
    """When a cell sub-task hits a transient error and bumps
    `samples_failed=1` without writing a TaskEvaluation row, the user
    sees a pass-rate drop with no signal as to *why*. Both sub-tasks
    must classify the exception and increment
    `eval_metadata.failures_by_reason[<reason>]` so the InflightRunsBanner
    can display 'rate_limit: 139, timeout: 12' on the runs view."""
    src = _tasks_source()
    assert "_record_cell_failure_reason" in src, (
        "missing failure-reason tracker helper"
    )
    assert "_classify_cell_failure" in src, (
        "missing exception → reason classifier"
    )
    # Both cell sub-tasks should call the recorder in their outer except
    # block. The call sites live in the cell bodies (cell_evaluator); the
    # helper + classifier stay in tasks.py (asserted above).
    assert _cell_source().count("_record_cell_failure_reason(db, evaluation_id, ") >= 2, (
        "both cell sub-tasks must record the failure reason in the outer "
        "exception handler so the UI can surface a breakdown"
    )


def test_orchestrator_pre_chord_cancel_check():
    """Orchestrator setup (judge_run creation + work-unit enumeration +
    missing-only preload) takes ~25s on a ZJS-scale eval. If the user
    cancels DURING setup, we must skip the chord dispatch — otherwise
    we fan out 6940 sub-tasks that each immediately short-circuit on
    their own parent-status check (Celery message churn + worker CPU
    for no useful work)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_evaluation":
            body_src = ast.get_source_segment(src, node) or ""
            assert "cancelled_before_dispatch" in body_src, (
                "orchestrator must re-check EvaluationRun.status just before "
                "chord dispatch and bail (status 'cancelled_before_dispatch') "
                "rather than fan out useless sub-tasks"
            )
            return
    raise AssertionError("run_evaluation function not found")


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
    # The sub-task BODIES are the `*_impl` functions in cell_evaluator (the
    # tasks.py wrappers just delegate — walking those would be vacuous since a
    # 2-line wrapper can never contain `_create_judge_run`).
    src = _cell_source()
    import ast
    tree = ast.parse(src)
    sub_task_names = {"evaluate_generation_cell_impl", "evaluate_annotation_cell_impl"}
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in sub_task_names:
            seen.add(node.name)
            body_src = ast.get_source_segment(src, node) or ""
            assert "_create_judge_run" not in body_src, (
                f"{node.name} must not call _create_judge_run — orchestrator "
                "pre-creates all judge_runs to avoid UQ races"
            )
    assert seen == sub_task_names, (
        f"could not locate cell-body impls in cell_evaluator.py: missing "
        f"{sub_task_names - seen}"
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


def test_finalizer_judges_children_by_produced_rows_not_stale_status():
    """Regression: a missing-only resume into the SAME EvaluationRun (the
    supported way to continue a cancelled run) reuses the cancelled
    attempt's EvaluationJudgeRun — which the cancel left marked 'failed'
    ('Parent EvaluationRun cancelled') — and grades EVERY cell under that
    very row. The old finalizer did `if child.status == "failed": continue`,
    so it stranded that judge_run as failed without ever re-checking the
    rows it produced, set any_child_completed=False, and flipped the parent
    to 'failed'/'all judge_runs failed' despite a complete, valid grade.
    That forced a manual prod status flip (Grundprinzipien run 792a006e,
    every one of 6365 cells scored cleanly).

    Pin the fix: the finalizer's child loop must NOT branch on a child's
    (possibly stale) status field. It must count the TaskEvaluation rows
    each child actually produced and derive completed/failed from that count
    (rows>0 ⇒ completed; rows==0 ⇒ failed, which still covers the legitimate
    up-front 'no AI service' failure that writes no rows)."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef)
                and node.name == "finalize_evaluation_run"):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.For)
                        and isinstance(sub.target, ast.Name)
                        and sub.target.id == "child"
                        and isinstance(sub.iter, ast.Name)
                        and sub.iter.id == "child_runs"):
                    loop_src = ast.get_source_segment(src, sub) or ""
                    # The bug was a read of the child's stale status to decide
                    # the branch. The fix only *writes* child.status (from the
                    # row count) — it never *compares* it. Assert no comparison.
                    assert not re.search(r"child\.status\s*==", loop_src), (
                        "finalize_evaluation_run must not branch on a child's "
                        "stale status field — a reused-but-graded judge_run is "
                        "left 'failed' by the cancel, and an early skip here "
                        "flips the parent to failed despite valid grades"
                    )
                    assert (
                        "TaskEvaluation.judge_run_id == child.id" in loop_src
                    ), (
                        "finalizer must count each child's produced rows "
                        "(TaskEvaluation.judge_run_id == child.id)"
                    )
                    assert "if child_rows > 0:" in loop_src, (
                        "finalizer must derive completed/failed from the "
                        "produced-row count, not the stale status field"
                    )
                    return
            raise AssertionError(
                "`for child in child_runs:` loop not found in "
                "finalize_evaluation_run"
            )
    raise AssertionError("finalize_evaluation_run function not found")


def test_judge_run_reuse_revives_terminal_rows_for_resume():
    """Root-cause companion to the finalizer fix. When a missing-only resume
    reuses an EvaluationJudgeRun a prior cancel left terminal
    ('failed'/'cancelled'), the reuse helpers must revive it to 'running'
    (clear error_message/completed_at, reset started_at) so the in-progress
    regrade isn't represented by a stale terminal row mid-run. Both judge_run
    reuse sites must do this, since a resume can dispatch through either:
      - `_create_judge_run` — the orchestrator (run_evaluation) path
      - `_get_or_create_judge_run_for_config` — the single-sample /
        immediate-eval dispatch path
    Without the revival, the finalizer's row-count reconciliation still
    rescues the run, but the judge_run sits 'failed' for the whole regrade
    and the Judges tab / inflight banner misreport it as failed."""
    src = _tasks_source()
    import ast
    tree = ast.parse(src)
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef) and node.name in (
                "_create_judge_run", "_get_or_create_judge_run_for_config")):
            body_src = ast.get_source_segment(src, node) or ""
            assert re.search(
                r"existing\.status\s+in\s*\(\s*['\"]failed['\"]\s*,\s*"
                r"['\"]cancelled['\"]\s*\)",
                body_src,
            ), (
                f"{node.name} must detect a reused terminal judge_run "
                "(status in failed/cancelled) left behind by a prior cancel"
            )
            assert re.search(
                r"existing\.status\s*=\s*['\"]running['\"]", body_src
            ), (
                f"{node.name} must revive a reused terminal judge_run to "
                "'running' so it reflects the in-progress regrade"
            )
            found.add(node.name)
    missing = {
        "_create_judge_run", "_get_or_create_judge_run_for_config"
    } - found
    assert not missing, f"judge_run reuse helper(s) not found: {missing}"
