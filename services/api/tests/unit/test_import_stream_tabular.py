"""Unit tests for the tabular import driver (cloud imports).

``run_tabular_import`` turns a plain CSV/TSV/TXT file into tasks in an
existing project — the cloud-import flow's tabular arm. These tests pin the
row → ``Task.data`` semantics (headers as keys, short rows padded with
``""``), the txt one-task-per-non-blank-line mode, the BOM / quoted-field /
gzip handling, the 422s for empty/headerless input, and the
``_IMPORT_BATCH`` flush/expunge cadence with the single end commit.

DB-free: a capture session records ``add``/``flush``/``expunge_all``/
``commit`` calls, matching how the driver only ever uses those four session
methods on the insert path.
"""

import gzip
import io
import sys
import os

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from routers.projects._import_stream import (  # noqa: E402
    _IMPORT_BATCH,
    ImportValidationError,
    run_tabular_import,
)


class _CaptureSession:
    """Records the four session calls the tabular driver makes."""

    def __init__(self):
        self.added = []
        self.flushes = 0
        self.expunges = 0
        self.commits = 0
        self.calls = []  # ordered call log for cadence assertions

    def add(self, obj):
        self.added.append(obj)
        self.calls.append("add")

    def flush(self):
        self.flushes += 1
        self.calls.append("flush")

    def expunge_all(self):
        self.expunges += 1
        self.calls.append("expunge_all")

    def commit(self):
        self.commits += 1
        self.calls.append("commit")

    # report_service's best-effort post-import update probes the session; any
    # attribute access beyond the four above raises and is swallowed by the
    # driver's try/except — emulate that by not defining query().


def _run(content: bytes, fmt: str, db=None, **kwargs):
    db = db if db is not None else _CaptureSession()
    result = run_tabular_import(db, "proj-1", io.BytesIO(content), "user-1", fmt, **kwargs)
    return result, db


class TestCsv:
    def test_basic_rows(self):
        result, db = _run(b"name,points\nAlice,10\nBob,7\n", "csv")
        assert result["created_tasks"] == 2
        assert result["format"] == "csv"
        assert [t.data for t in db.added] == [
            {"name": "Alice", "points": "10"},
            {"name": "Bob", "points": "7"},
        ]
        assert [t.inner_id for t in db.added] == [1, 2]
        assert all(t.project_id == "proj-1" for t in db.added)
        # uuid4 string ids, unique per task.
        assert len({t.id for t in db.added}) == 2
        assert all(isinstance(t.id, str) and len(t.id) == 36 for t in db.added)
        assert db.commits == 1

    def test_headers_trimmed(self):
        result, db = _run(b"  name , points \nA,1\n", "csv")
        assert db.added[0].data == {"name": "A", "points": "1"}

    def test_bom_consumed(self):
        result, db = _run("﻿name,points\nA,1\n".encode("utf-8"), "csv")
        assert db.added[0].data == {"name": "A", "points": "1"}

    def test_quoted_fields_with_embedded_delimiters_and_newlines(self):
        content = b'name,text\nA,"hello, world"\nB,"line1\nline2"\n'
        result, db = _run(content, "csv")
        assert result["created_tasks"] == 2
        assert db.added[0].data == {"name": "A", "text": "hello, world"}
        assert db.added[1].data == {"name": "B", "text": "line1\nline2"}

    def test_short_rows_padded_and_blank_rows_skipped(self):
        content = b"a,b,c\n1,2\n\n , , \n4,5,6,EXTRA\n"
        result, db = _run(content, "csv")
        assert result["created_tasks"] == 2
        assert db.added[0].data == {"a": "1", "b": "2", "c": ""}
        # Cells beyond the header width are dropped.
        assert db.added[1].data == {"a": "4", "b": "5", "c": "6"}

    def test_empty_file_422(self):
        with pytest.raises(ImportValidationError) as exc_info:
            _run(b"", "csv")
        assert exc_info.value.status_code == 422

    def test_headerless_422(self):
        # A first row of only blank cells has no usable column names.
        with pytest.raises(ImportValidationError) as exc_info:
            _run(b" , , \n1,2,3\n", "csv")
        assert exc_info.value.status_code == 422

    def test_header_only_file_creates_nothing(self):
        result, db = _run(b"a,b\n", "csv")
        assert result["created_tasks"] == 0
        assert db.added == []
        assert db.commits == 1

    def test_invalid_utf8_422(self):
        with pytest.raises(ImportValidationError) as exc_info:
            _run(b"a,b\n\xff\xfe,broken\n", "csv")
        assert exc_info.value.status_code == 422

    def test_gzip_transparent(self):
        content = gzip.compress(b"name\nA\nB\n")
        result, db = _run(content, "csv")
        assert result["created_tasks"] == 2

    def test_unknown_format_422(self):
        with pytest.raises(ImportValidationError):
            _run(b"a,b\n1,2\n", "xlsx")


class TestTsv:
    def test_tab_delimited(self):
        result, db = _run(b"name\tpoints\nAlice\t10\n", "tsv")
        assert db.added[0].data == {"name": "Alice", "points": "10"}

    def test_commas_are_data_in_tsv(self):
        result, db = _run(b"name\ttext\nA\thello, world\n", "tsv")
        assert db.added[0].data == {"name": "A", "text": "hello, world"}


class TestTxt:
    def test_one_task_per_non_blank_line(self):
        result, db = _run(b"first line\n\n   \nsecond line\n", "txt")
        assert result["created_tasks"] == 2
        assert [t.data for t in db.added] == [
            {"text": "first line"},
            {"text": "second line"},
        ]
        assert [t.inner_id for t in db.added] == [1, 2]

    def test_interior_whitespace_kept(self):
        result, db = _run(b"  indented line  \n", "txt")
        # Only the trailing newline is stripped; the line body is kept.
        assert db.added[0].data == {"text": "  indented line  "}

    def test_blank_only_file_422(self):
        with pytest.raises(ImportValidationError) as exc_info:
            _run(b"\n \n\t\n", "txt")
        assert exc_info.value.status_code == 422


class TestBatching:
    def test_flush_expunge_cadence_and_single_commit(self):
        n_rows = _IMPORT_BATCH * 2 + 1
        body = "h\n" + "\n".join(f"v{i}" for i in range(n_rows)) + "\n"
        result, db = _run(body.encode("utf-8"), "csv")
        assert result["created_tasks"] == n_rows
        # One flush+expunge per full batch; the tail rides the end commit.
        assert db.flushes == 2
        assert db.expunges == 2
        assert db.commits == 1
        # flush precedes expunge_all each time (FK-safety invariant), and the
        # commit is the last session call of the insert path.
        flush_idx = [i for i, c in enumerate(db.calls) if c == "flush"]
        expunge_idx = [i for i, c in enumerate(db.calls) if c == "expunge_all"]
        assert all(e == f + 1 for f, e in zip(flush_idx, expunge_idx))
        assert db.calls[-1] == "commit"

    def test_progress_cb_fires_per_batch_and_at_end(self):
        n_rows = _IMPORT_BATCH * 2 + 1
        body = "h\n" + "\n".join(f"v{i}" for i in range(n_rows)) + "\n"
        seen = []
        _run(body.encode("utf-8"), "csv", progress_cb=seen.append)
        assert seen == [_IMPORT_BATCH, _IMPORT_BATCH * 2, n_rows]
