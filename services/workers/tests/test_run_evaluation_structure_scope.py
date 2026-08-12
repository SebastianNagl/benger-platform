"""Worker-side tests for the prompt-structure scope filter on evaluation runs.

Mirrors the two DB-free layers of `test_run_evaluation_annotator_scope.py`:

1. Signature contract: `run_evaluation` accepts `structure_keys` as a keyword
   argument with a None default, matching the API dispatch
   `celery_app.send_task(..., kwargs={'structure_keys': ...})`.

2. Source contract: the generation-cell enumeration composes a join on
   `ResponseGeneration` and filters
   `ResponseGeneration.structure_key.in_(structure_keys)` when the kwarg is
   set. SQL `IN` never matches NULL, so legacy generations without a
   structure_key are excluded from scoped runs by construction.
"""

import inspect
import re


# ---------------------------------------------------------------------------
# Layer 1: signature contract
# ---------------------------------------------------------------------------


def test_run_evaluation_accepts_structure_keys():
    """The API dispatch passes `structure_keys` by keyword. The worker must
    accept it with a None default so pre-deploy (unscoped) messages and
    resume/retry snapshots without the key keep today's behavior."""
    from tasks import run_evaluation

    fn = getattr(
        run_evaluation,
        "__wrapped__",
        run_evaluation.run if hasattr(run_evaluation, "run") else run_evaluation,
    )
    params = inspect.signature(fn).parameters
    assert "structure_keys" in params, f"signature: {list(params.keys())}"
    assert params["structure_keys"].default == None  # noqa: E711
    annot_str = str(params["structure_keys"].annotation)
    assert "None" in annot_str or "Optional" in annot_str, (
        f"expected Optional/None-aware annotation, got: {annot_str}"
    )


def test_run_evaluation_scope_kwargs_all_default_none():
    """structure_keys sits alongside the existing scope kwargs, all with
    None defaults. Catches an accidental positional-arg change that would
    break the API's keyword dispatch."""
    from tasks import run_evaluation

    fn = getattr(
        run_evaluation,
        "__wrapped__",
        run_evaluation.run if hasattr(run_evaluation, "run") else run_evaluation,
    )
    params = inspect.signature(fn).parameters
    for kw in ("task_ids", "model_ids", "annotator_user_ids", "structure_keys"):
        assert kw in params, f"missing {kw}"
        assert params[kw].default == None, f"{kw} default should be None"  # noqa: E711


# ---------------------------------------------------------------------------
# Layer 2: source contract
# ---------------------------------------------------------------------------


def test_worker_filters_generations_by_structure_key():
    """The generation enumeration must join ResponseGeneration and filter by
    `structure_key.in_(structure_keys)` when the kwarg is set. Pin the join
    + filter shape — a missing join or a filter on the wrong column would
    silently grade every structure's generations."""
    import tasks

    src = inspect.getsource(tasks)
    assert "if structure_keys:" in src, (
        "worker must guard the structure filter with an if-check"
    )
    assert re.search(
        r"\.join\(\s*ResponseGeneration,\s*"
        r"Generation\.generation_id\s*==\s*ResponseGeneration\.id,?\s*\)",
        src,
    ), "worker must join Generation -> ResponseGeneration for the structure filter"
    assert re.search(
        r"\.filter\(\s*ResponseGeneration\.structure_key\.in_\(\s*structure_keys\s*\)\s*\)",
        src,
    ), "worker must apply the ResponseGeneration.structure_key filter"


def test_worker_logs_structure_scope_at_run_start():
    """Scope-filter observability: the entry log line must mention
    structure_keys so 'why did this run only grade N cells' is answerable
    from the log alone. Pinned via the literal f-string fragments — a
    paren-bounded regex can't span the len(...) calls inside the message."""
    import tasks

    src = inspect.getsource(tasks)
    assert "if task_ids or model_ids or annotator_user_ids or structure_keys:" in src, (
        "the scope-log guard must include structure_keys"
    )
    assert "structure_keys={len(structure_keys) if structure_keys else 0}" in src, (
        "expected the scope logger.info to report the structure_keys count"
    )
