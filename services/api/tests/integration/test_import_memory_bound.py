"""Constrained-heap memory regression tests for streaming import/export (issue #158).

Issue #158's acceptance text requires the memory bound be *verified by a
regression test*, not inferred from functional batch tests: "verify with a
constrained-heap regression test, not just functional tests" / "API pod
resident memory stays roughly flat (not proportional to dataset)". The
batch-boundary tests (test_import_streaming_batch.py) prove row-level
correctness across flush+expunge boundaries; these tests enforce the bound.

The heap constraint is enforced with ``tracemalloc`` rather than a kernel
``resource.setrlimit(RLIMIT_AS)``: an address-space rlimit sits on top of a
~hundreds-of-MB interpreter/SQLAlchemy baseline that varies by platform and
allocator, which makes a kernel limit tight enough to catch a whole-file parse
inherently flaky, and a subprocess with its own rlimit cannot share the
SAVEPOINT-isolated ``test_db`` session. ``tracemalloc`` tracks exactly the
allocation class the streaming rewrite removed — Python objects materialized
from the payload (``json.load`` dict trees) — deterministically and in-process.

Assertion shape: each driver is measured on a small body and on a body 8x
bigger, and the big run's peak must stay within 2x the small run's. Measured
behaviour on the streaming drivers is a flat ~6.5 MB peak regardless of body
size (dominated by one flush batch plus statement-rendering transients), so
the ratio sits near 1.0; an O(file) parse ties peak to body size and pushes
the ratio toward the 8x spread. An absolute cap (peak < body size) backs the
ratio up so a uniformly huge allocation in both runs can't slip through.
"""

import io
import json
import os
import tempfile
import tracemalloc
import uuid

import pytest

from project_models import Project, ProjectOrganization, Task
from routers.projects._export_stream import stream_export_ndjson
from routers.projects._import_stream import (
    run_full_project_import,
    run_nested_import,
)
from routers.projects.import_export import _IMPORT_BATCH

# One shared filler string keeps the fixture build cheap; every imported row
# still parses its own fresh copy out of the serialized bytes, which is what
# the measurement cares about.
_FILLER = "lorem ipsum dolor sit amet consectetur adipiscing elit " * 90  # ~5 KB

_SMALL_ROWS = 2 * _IMPORT_BATCH
_LARGE_ROWS = 16 * _IMPORT_BATCH  # 8x the small body

# The big body must dwarf one flush batch or the ratio assertion stops meaning
# anything; guarded below, not just assumed here.
_MIN_LARGE_BYTES = 12 * 1024 * 1024


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, admin, org, title):
    project = Project(
        id=_uid(),
        title=title,
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    db.add(ProjectOrganization(
        id=_uid(), project_id=project.id,
        organization_id=org.id, assigned_by=admin.id,
    ))
    db.flush()
    return project


def _seed_tasks(db, project_id, admin_id, count):
    """Insert ``count`` bulky tasks in flush+expunge chunks so the fixture
    build itself is bounded and the session enters measured phases empty."""
    for start in range(0, count, _IMPORT_BATCH):
        for i in range(start, min(start + _IMPORT_BATCH, count)):
            db.add(Task(
                id=_uid(),
                project_id=project_id,
                inner_id=i + 1,
                data={"text": f"{i:06d} {_FILLER}"},
                created_by=admin_id,
            ))
        db.flush()
        db.expunge_all()
    db.commit()


def _nested_body(row_count) -> bytes:
    return json.dumps({
        "data": [
            {"data": {"text": f"{i:06d} {_FILLER}"}}
            for i in range(row_count)
        ]
    }).encode("utf-8")


def _traced_peak(fn):
    """Run ``fn`` under tracemalloc and return (result, peak_bytes)."""
    tracemalloc.start()
    try:
        result = fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


def _assert_flat(label, small_peak, large_peak, large_size):
    assert large_peak < 2 * small_peak, (
        f"{label} peak heap scales with body size: {small_peak / 1e6:.1f} MB on "
        f"the small body but {large_peak / 1e6:.1f} MB on the 8x body — an "
        "O(file) parse or a dropped per-batch expunge crept back in"
    )
    assert large_peak < large_size, (
        f"{label} peak heap {large_peak / 1e6:.1f} MB exceeds the "
        f"{large_size / 1e6:.1f} MB body itself — the streaming bound is broken "
        "even if it broke equally at both sizes"
    )


@pytest.mark.integration
class TestNestedImportMemoryBound:
    """run_nested_import peak heap stays flat as the legacy JSON body grows 8x."""

    def test_peak_heap_does_not_scale_with_body(
        self, test_db, test_users, test_org
    ):
        admin = test_users[0]
        admin_id = admin.id
        # Plain-string ids only past this point: the import drivers
        # expunge_all() internally, so ORM fixture instances detach mid-test.
        warm_id = _make_project(test_db, admin, test_org, "Nested Warm-up").id
        small_id = _make_project(test_db, admin, test_org, "Nested Small").id
        large_id = _make_project(test_db, admin, test_org, "Nested Large").id
        test_db.commit()

        # First pass through the driver pays one-time costs (lazy module
        # imports, SQLAlchemy statement compilation, notification machinery);
        # absorb them so the small measurement isn't inflated, which would
        # make the ratio assertion lenient.
        run_nested_import(
            test_db, warm_id,
            io.BytesIO(json.dumps(
                {"data": [{"data": {"text": "warm-up"}}]}
            ).encode("utf-8")),
            admin_id,
        )

        small_body = _nested_body(_SMALL_ROWS)
        large_body = _nested_body(_LARGE_ROWS)
        assert len(large_body) > _MIN_LARGE_BYTES, (
            f"large fixture shrank to {len(large_body)} bytes; grow "
            "_LARGE_ROWS or _FILLER"
        )

        small_stream = io.BytesIO(small_body)
        small_result, small_peak = _traced_peak(lambda: run_nested_import(
            test_db, small_id, small_stream, admin_id
        ))
        large_stream = io.BytesIO(large_body)
        large_result, large_peak = _traced_peak(lambda: run_nested_import(
            test_db, large_id, large_stream, admin_id
        ))

        # The runs must have actually imported everything — a driver that
        # silently skips rows would pass any memory bound.
        assert small_result["created_tasks"] == _SMALL_ROWS
        assert large_result["created_tasks"] == _LARGE_ROWS
        assert test_db.query(Task).filter(
            Task.project_id == large_id
        ).count() == _LARGE_ROWS

        _assert_flat("nested import", small_peak, large_peak, len(large_body))


@pytest.mark.integration
class TestNdjsonRoundTripMemoryBound:
    """stream_export_ndjson and the NDJSON single-pass import stay flat as the
    project grows 8x."""

    def test_export_and_import_peaks_do_not_scale(
        self, test_db, test_users, test_org
    ):
        admin = test_users[0]
        admin_id = admin.id
        # Plain-string ids only past this point: the import drivers
        # expunge_all() internally, so ORM fixture instances detach mid-test.
        small_id = _make_project(test_db, admin, test_org, "NDJSON Small").id
        large_id = _make_project(test_db, admin, test_org, "NDJSON Large").id

        # Warm up both measured drivers with a 2-task round-trip (same
        # rationale as the nested test's warm-up pass).
        warm_id = _make_project(test_db, admin, test_org, "NDJSON Warm-up").id
        _seed_tasks(test_db, warm_id, admin_id, 2)
        warm_stream = "".join(stream_export_ndjson(test_db, warm_id))
        run_full_project_import(
            test_db, io.BytesIO(warm_stream.encode("utf-8")), admin_id
        )

        _seed_tasks(test_db, small_id, admin_id, _SMALL_ROWS)
        _seed_tasks(test_db, large_id, admin_id, _LARGE_ROWS)

        peaks = {}
        sizes = {}
        results = {}
        for label, project_id in (("small", small_id), ("large", large_id)):
            spool = tempfile.NamedTemporaryFile(
                prefix="benger-test-ndjson-", suffix=".ndjson", delete=False
            )
            spool.close()
            try:
                def _export():
                    with open(spool.name, "w", encoding="utf-8") as out:
                        for chunk in stream_export_ndjson(test_db, project_id):
                            out.write(chunk)

                _, peaks[f"export_{label}"] = _traced_peak(_export)
                sizes[label] = os.path.getsize(spool.name)

                with open(spool.name, "rb") as body:
                    results[label], peaks[f"import_{label}"] = _traced_peak(
                        lambda: run_full_project_import(test_db, body, admin_id)
                    )
            finally:
                os.unlink(spool.name)

        assert sizes["large"] > _MIN_LARGE_BYTES, (
            f"large NDJSON fixture shrank to {sizes['large']} bytes; grow "
            "_LARGE_ROWS or _FILLER"
        )

        for label, expected in (("small", _SMALL_ROWS), ("large", _LARGE_ROWS)):
            counts = results[label]["statistics"]["imported_counts"]
            assert counts["tasks"] == expected
            assert test_db.query(Task).filter(
                Task.project_id == results[label]["project_id"]
            ).count() == expected

        _assert_flat(
            "NDJSON export",
            peaks["export_small"], peaks["export_large"], sizes["large"],
        )
        _assert_flat(
            "NDJSON import",
            peaks["import_small"], peaks["import_large"], sizes["large"],
        )
