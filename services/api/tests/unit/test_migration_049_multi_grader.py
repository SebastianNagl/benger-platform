"""Source-contract tests for migration 049 (per-grader unique index fix).

Migration 048 keyed the partial unique index on
  (evaluation_id, judge_run_id, gen, ann, field_name)
which collapsed multi-grader human korrektur rows. Confirmed prod
incident on Benchathon 2026-05-15: a 0.72 grade by Ann-Kristin and a
later 0.0 by Aleyna on the same annotation were treated as duplicates
by 048's pre-dedup, and the older row was deleted.

Migration 049 drops the index and recreates it with `created_by` in
the key tuple, so multi-grader rows coexist by design (needed for
inter-rater-agreement scoring) while LLM-redelivery dedup still works
(redelivered LLM cells have the same NULL/system `created_by` and
still trigger ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import importlib.util
import os


MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "049_unique_task_evaluation_cell_per_grader.py",
    )
)


def _load_module():
    spec = importlib.util.spec_from_file_location("m049", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_049_revision_chain():
    """049 must follow 048 in the alembic chain — otherwise upgrade
    skips it and the cross-grader bug stays in prod."""
    m = _load_module()
    assert m.revision == "049_unique_task_evaluation_cell_per_grader"
    assert m.down_revision == "048_unique_task_evaluation_cell"


def test_migration_049_upgrade_adds_created_by_to_index():
    """The whole point of this migration: the new index must include
    `created_by` as a key column so two graders on the same annotation
    don't collide."""
    src = open(MIGRATION_PATH).read()
    # The CREATE INDEX must list created_by inside the column tuple.
    assert "COALESCE(created_by" in src, (
        "migration must include `COALESCE(created_by, sentinel)` in the "
        "unique index key — otherwise multi-grader korrektur rows still "
        "collide and one grader's score is deleted on dedup"
    )
    # The OLD (3-coalesce, 5-column) shape must be DROPPED first.
    assert "DROP INDEX" in src, (
        "migration must DROP the existing index before recreating with "
        "the new key shape"
    )


def test_migration_049_downgrade_restores_048_shape():
    """Downgrade must put 048's index shape back (no created_by). The
    docstring notes that the operator may need to manually re-run 048's
    pre-dedup if multi-grader rows have accumulated."""
    m = _load_module()
    # The downgrade function body should mention restoring the index
    # without created_by — we check that the source has both the drop
    # and a non-created_by recreate.
    import inspect

    src = inspect.getsource(m.downgrade)
    assert "DROP INDEX" in src
    assert src.index("DROP INDEX") < src.index("CREATE UNIQUE INDEX")
    # The downgrade's CREATE INDEX should NOT include created_by.
    create_idx = src[src.index("CREATE UNIQUE INDEX"):]
    assert "COALESCE(generation_id" in create_idx
    assert "COALESCE(annotation_id" in create_idx
    assert "COALESCE(created_by" not in create_idx, (
        "downgrade must restore 048's shape, which had no created_by in "
        "the index key"
    )


def test_migration_049_does_not_run_pre_dedup_delete():
    """Migration 048's pre-dedup DELETE is exactly the buggy operation
    that lost the Ann-Kristin / Aleyna row. Migration 049 must NOT
    repeat it — under the new index shape, multi-grader rows coexist,
    and any rows that currently violate the OLD index shape but match
    the NEW one are intentional cross-grader scores that the operator
    backfilled. Deleting them would re-introduce the original bug."""
    src = open(MIGRATION_PATH).read()
    assert "DELETE FROM task_evaluations" not in src.upper().replace(
        "DELETE FROM TASK_EVALUATIONS", "DELETE FROM TASK_EVALUATIONS"
    ), (
        "migration 049 must NOT run a pre-dedup DELETE on task_evaluations — "
        "that would re-introduce the multi-grader data loss"
    )
