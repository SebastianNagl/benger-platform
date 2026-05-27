"""Worker-side tests for the annotator-scope filter (issue #69).

Two layers of coverage, both DB-free:

1. Signature contract: `run_evaluation` accepts `annotator_user_ids` as a
   keyword argument with a None default. The kwarg name matches what the
   API dispatch threads in via
   `celery_app.send_task(..., kwargs={'annotator_user_ids': ...})`.

2. Source contract: the annotation-load query path in `tasks.py` actually
   composes a `.filter(Annotation.completed_by.in_(annotator_user_ids))`
   when the kwarg is set, and the import switches to the shared classifier
   from `services/shared/eval_field_classification.py`. Inspecting the
   source rather than running a full Celery dispatch keeps the test fast
   and avoids the heavyweight worker fixtures.
"""

import inspect
import re


# ---------------------------------------------------------------------------
# Layer 1: signature contract
# ---------------------------------------------------------------------------


def test_run_evaluation_accepts_annotator_user_ids():
    """Celery dispatch passes `annotator_user_ids` by keyword (D1 migrated
    to kwargs). The worker function must accept that keyword with a None
    default for backward-compat with non-scoped dispatches."""
    from tasks import run_evaluation

    fn = getattr(
        run_evaluation,
        "__wrapped__",
        run_evaluation.run if hasattr(run_evaluation, "run") else run_evaluation,
    )
    params = inspect.signature(fn).parameters
    assert "annotator_user_ids" in params, f"signature: {list(params.keys())}"
    assert params["annotator_user_ids"].default == None
    annot = params["annotator_user_ids"].annotation
    annot_str = str(annot)
    assert "None" in annot_str or "Optional" in annot_str, (
        f"expected Optional/None-aware annotation, got: {annot_str}"
    )


def test_run_evaluation_accepts_existing_scope_kwargs():
    """Sanity check that my new param sits alongside the existing scope
    kwargs, all with None defaults. Catches an accidental positional-arg
    change that would break the API's keyword dispatch."""
    from tasks import run_evaluation

    fn = getattr(
        run_evaluation,
        "__wrapped__",
        run_evaluation.run if hasattr(run_evaluation, "run") else run_evaluation,
    )
    params = inspect.signature(fn).parameters
    for kw in ("task_ids", "model_ids", "annotator_user_ids"):
        assert kw in params, f"missing {kw}"
        assert params[kw].default == None, f"{kw} default should be None"


# ---------------------------------------------------------------------------
# Layer 2: source contract
# ---------------------------------------------------------------------------


def test_worker_imports_shared_classifier():
    """The worker delegates field classification to the shared module
    (B1+B2). If the worker inlines its own classifier again, the cost
    endpoint will silently drift away from the worker. This pins the
    imported name."""
    import tasks
    src = inspect.getsource(tasks)
    assert "from eval_field_classification import classify_pred_fields" in src, (
        "worker must import classify_pred_fields from the shared module"
    )


def test_worker_filters_annotations_by_completed_by():
    """The annotation-load query path must filter by
    `Annotation.completed_by.in_(annotator_user_ids)` when the kwarg is
    set. Pin the filter call shape — a typo'd column would silently
    return all annotations and the bug would only surface in production."""
    import tasks
    src = inspect.getsource(tasks)
    # The filter line and its guarding conditional, allowed to be
    # separated by other statements (e.g. the pre-count for logging).
    assert "if annotator_user_ids:" in src, (
        "worker must guard the annotator filter with an if-check"
    )
    assert re.search(
        r"\.filter\(\s*Annotation\.completed_by\.in_\(\s*annotator_user_ids\s*\)\s*\)",
        src,
    ), "worker must apply the Annotation.completed_by filter"


def test_worker_logs_scope_filters_at_run_start():
    """E3 observability: scope-filter activity is logged once at function
    entry. The exact message can change but the log call must reference
    `evaluation_id` and at least one of the scope kwargs by name."""
    import tasks
    src = inspect.getsource(tasks)
    assert re.search(
        r"logger\.info\([^)]*evaluation_id[^)]*"
        r"(task_ids|model_ids|annotator_user_ids)",
        src,
    ), "expected a logger.info that names evaluation_id and scope kwargs"
