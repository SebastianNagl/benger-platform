"""Batch iteration / memory-bounding helpers shared by the import and export
stream drivers.

Both drivers stream multi-GB row sets and rely on the same two-part memory
bound: ``yield_per`` (export) / ``ijson`` element streaming (import) bounds the
buffer, and an explicit ``Session.expunge`` keeps the SQLAlchemy identity map
from growing for the life of the session. The helpers below are the exact loops
that were previously inlined / duplicated across the two modules. They are pure
move/extract — the flush/expunge cadence and ordering are unchanged.
"""
from typing import Any, Iterator

from models import Generation, TaskEvaluation
from project_models import Annotation, PostAnnotationResponse


def drain_expunge(db, query, batch_size: int) -> Iterator[Any]:
    """Yield rows under ``yield_per(batch_size)``, detaching each once consumed.

    ``yield_per`` bounds the cursor buffer; the per-row ``expunge`` bounds the
    identity map. Both halves are required — ``yield_per`` alone keeps every row
    strongly referenced by the identity map for the life of the Session, so peak
    RAM would scale with the whole row set rather than one row (the trap that
    OOMKilled the API pod on large exports). Extracted from the two identical
    ``_drain`` closures in ``export_stream.py``.
    """
    for row in query.yield_per(batch_size):
        yield row
        db.expunge(row)


def fetch_batch_children(db, batch_ids, eval_run_ids):
    """Fetch + group a task batch's child rows with batched ``IN()`` queries.

    Runs the 4 per-batch queries (annotations, questionnaire responses,
    generations, and — when ``eval_run_ids`` is non-empty — task_evaluations
    scoped to those runs) that the JSON/CSV and Label-Studio export batch
    builders both ran identically, and returns:

        (anns_all, qrs_all, gens_all, te_all,
         anns_by_task, qr_by_annotation, gens_by_task)

    The raw ``*_all`` lists are returned alongside the grouping dicts so the
    caller can ``expunge`` them after building its output (the memory bound this
    batching exists for). TaskEvaluation *indexing* is deliberately left to the
    caller: the JSON exporter splits task- vs generation-level via
    ``build_evaluation_indexes``, while the Label-Studio exporter groups all
    evals by task — so only the shared fetch + 3 common grouping dicts are
    extracted here. Behavior is identical to the previous inline preludes (same
    queries, same filters, same grouping).
    """
    anns_all = db.query(Annotation).filter(Annotation.task_id.in_(batch_ids)).all()
    qrs_all = db.query(PostAnnotationResponse).filter(
        PostAnnotationResponse.task_id.in_(batch_ids)
    ).all()
    gens_all = db.query(Generation).filter(Generation.task_id.in_(batch_ids)).all()
    if eval_run_ids:
        te_all = db.query(TaskEvaluation).filter(
            TaskEvaluation.task_id.in_(batch_ids),
            TaskEvaluation.evaluation_id.in_(eval_run_ids),
        ).all()
    else:
        te_all = []

    anns_by_task: dict = {}
    for a in anns_all:
        anns_by_task.setdefault(a.task_id, []).append(a)
    qr_by_annotation = {qr.annotation_id: qr for qr in qrs_all}
    gens_by_task: dict = {}
    for g in gens_all:
        gens_by_task.setdefault(g.task_id, []).append(g)

    return (
        anns_all, qrs_all, gens_all, te_all,
        anns_by_task, qr_by_annotation, gens_by_task,
    )


def stream_array_rows(db, iter_array_fn, spooled, path: str, batch: int) -> Iterator[Any]:
    """Yield each element of a top-level JSON array one at a time, flushing +
    expunging the session every ``batch`` rows.

    ``iter_array_fn(spooled, path)`` is the ijson element iterator (passed in so
    this helper stays free of any ijson import and matches whatever array reader
    the caller uses). Flushing *before* expunging is load-bearing: it guarantees
    rows still pending from an earlier entity loop are INSERTed (rather than
    silently dropped by ``expunge_all``) before a later loop's children
    FK-reference them. Cross-references travel via string id maps, never live ORM
    objects, so detaching the just-inserted rows is safe. Extracted from
    ``import_stream._stream_rows`` (behavior identical).
    """
    n = 0
    for row in iter_array_fn(spooled, path):
        yield row
        n += 1
        flush_every(db, n, batch)


def flush_every(db, count: int, batch: int) -> None:
    """Flush + expunge the whole session every ``batch`` items.

    Call once per successfully-processed item with the running ``count``. On
    each ``batch``-th item this flushes pending rows to the DB and detaches the
    identity map, bounding peak heap to O(batch) instead of O(file).

    Flushing *before* expunging is load-bearing: it INSERTs rows still pending
    from an earlier entity loop before a later loop's children FK-reference them
    (``expunge_all`` would otherwise silently drop the un-flushed rows).
    Cross-references travel via string id maps, never live ORM objects, so
    detaching the just-inserted rows is safe. This is the exact cadence
    previously inlined at the NDJSON and task-array insert loops in
    ``import_stream`` (and the per-row variant in ``stream_array_rows`` above).
    """
    if count % batch == 0:
        db.flush()
        db.expunge_all()
