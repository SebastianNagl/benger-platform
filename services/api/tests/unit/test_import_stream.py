"""Unit tests for the streaming-import helpers (issue #158).

`routers/projects/_import_stream.py` replaced whole-file ``json.load`` in the
import handlers so a multi-GB export no longer balloons to O(file) resident.
These tests pin the two invariants that make that work:

  * ``read_top_object`` materializes only a whitelist of small keys and records
    the opening event of *every* top-level key, while parsing-through (not
    building) the big arrays.
  * ``iter_array`` yields one array element at a time and is re-seekable for
    multiple independent passes.

Plus two regressions the integration suite already caught the hard way:
  * numbers must come back as ``float`` (``use_float=True``), not
    ``decimal.Decimal`` — psycopg2 can't serialize Decimal into a JSON column.
  * consuming a large array must stay O(element), not O(file) — proven against
    ``json.load`` under ``tracemalloc``.
"""

import io
import json
import os
import sys
import tracemalloc
from decimal import Decimal

import ijson
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from routers.projects._import_stream import (  # noqa: E402
    iter_array,
    read_top_object,
)


def _bytesio(obj) -> io.BytesIO:
    return io.BytesIO(json.dumps(obj).encode("utf-8"))


class TestReadTopObject:
    def test_builds_only_whitelisted_keys(self):
        doc = {
            "meta": {"format": "ls", "n": 2},
            "project": {"id": "p1"},
            "data": [{"x": 1}, {"x": 2}, {"x": 3}],
        }
        values, kinds = read_top_object(_bytesio(doc), {"meta", "project"})

        assert values["meta"] == {"format": "ls", "n": 2}
        assert values["project"] == {"id": "p1"}
        # The big array is parse-through-and-discarded — never materialized.
        assert "data" not in values

    def test_kinds_records_every_top_level_key(self):
        doc = {
            "meta": {"a": 1},
            "data": [1, 2],
            "format_version": "1.0.0",
            "count": 5,
            "flag": True,
            "nothing": None,
        }
        _values, kinds = read_top_object(_bytesio(doc), {"meta"})

        # kinds is reported for *all* top-level keys, not just whitelisted ones.
        assert kinds["meta"] == "start_map"
        assert kinds["data"] == "start_array"
        assert kinds["format_version"] == "string"
        assert kinds["count"] == "number"
        assert kinds["flag"] == "boolean"
        assert kinds["nothing"] == "null"

    def test_missing_key_absent_from_values(self):
        doc = {"project": {"id": "p1"}}
        values, kinds = read_top_object(_bytesio(doc), {"meta", "project"})
        assert "meta" not in values
        assert values["project"] == {"id": "p1"}

    def test_numbers_are_float_not_decimal(self):
        # Regression: ijson defaults to Decimal; the helper passes use_float=True
        # so values land in JSON/JSONB columns without a serialization error.
        doc = {"meta": {"score": 0.9, "nested": {"v": 1.5}, "ints": [1, 2]}}
        values, _kinds = read_top_object(_bytesio(doc), {"meta"})

        assert type(values["meta"]["score"]) is float
        assert not isinstance(values["meta"]["score"], Decimal)
        assert type(values["meta"]["nested"]["v"]) is float

    def test_malformed_json_raises_jsonerror(self):
        bad = io.BytesIO(b'{"meta": {"a": 1}, "data": [')  # truncated
        with pytest.raises(ijson.JSONError):
            read_top_object(bad, {"meta"})

    def test_bare_array_top_level_yields_empty(self):
        # A non-object top level has no top-level keys to build.
        values, kinds = read_top_object(io.BytesIO(b"[1, 2, 3]"), {"meta"})
        assert values == {}
        assert kinds == {}

    def test_reseeks_to_start(self):
        # Helper must seek(0) itself so a pre-positioned file still parses.
        buf = _bytesio({"meta": {"a": 1}, "data": [1, 2]})
        buf.seek(10)
        values, _kinds = read_top_object(buf, {"meta"})
        assert values["meta"] == {"a": 1}


class TestIterArray:
    def test_yields_each_element(self):
        doc = {"data": [{"x": 1}, {"x": 2}, {"x": 3}]}
        items = list(iter_array(_bytesio(doc), "data.item"))
        assert items == [{"x": 1}, {"x": 2}, {"x": 3}]

    def test_absent_path_yields_nothing(self):
        doc = {"data": [{"x": 1}]}
        # No 'tasks' array present → empty iteration, not an error.
        assert list(iter_array(_bytesio(doc), "tasks.item")) == []

    def test_reseekable_multiple_passes(self):
        # The import handlers stream the same spool twice (user-id pre-pass then
        # the main insert pass); each iter_array call must re-seek to 0.
        buf = _bytesio({"data": [{"x": 1}, {"x": 2}]})
        first = list(iter_array(buf, "data.item"))
        second = list(iter_array(buf, "data.item"))
        assert first == second == [{"x": 1}, {"x": 2}]

    def test_numbers_are_float_not_decimal(self):
        doc = {"data": [{"score": 0.75, "n": 3}]}
        (item,) = list(iter_array(_bytesio(doc), "data.item"))
        assert type(item["score"]) is float
        assert not isinstance(item["score"], Decimal)

    def test_lazy_one_at_a_time(self):
        # The generator must not pre-read the whole array: consuming one element
        # leaves the rest unconsumed.
        doc = {"data": [{"x": i} for i in range(5)]}
        gen = iter_array(_bytesio(doc), "data.item")
        assert next(gen) == {"x": 0}
        assert next(gen) == {"x": 1}
        # remaining still streamable
        assert [r["x"] for r in gen] == [2, 3, 4]


class TestMemoryBounded:
    """The whole point of #158: O(element) streaming, not O(file)."""

    def _write_large_array(self, n=20_000, pad=400):
        """A JSON object whose `data` array dominates the file size."""
        buf = io.BytesIO()
        buf.write(b'{"meta": {"k": 1}, "data": [')
        blob = "x" * pad
        for i in range(n):
            if i:
                buf.write(b",")
            buf.write(json.dumps({"id": i, "blob": blob, "score": 0.5}).encode())
        buf.write(b"]}")
        buf.seek(0)
        return buf, len(buf.getvalue())

    def test_iter_array_peak_far_below_json_load(self):
        buf, file_size = self._write_large_array()
        # File must be large enough that O(file) materialization is obvious.
        assert file_size > 5 * 1024 * 1024  # > 5MB

        # Streaming pass: never hold more than one element.
        buf.seek(0)
        tracemalloc.start()
        count = 0
        for item in iter_array(buf, "data.item"):
            count += 1
            del item
        _, stream_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert count == 20_000

        # Materializing pass: json.load holds every element at once.
        buf.seek(0)
        tracemalloc.start()
        whole = json.load(buf)
        _, load_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert len(whole["data"]) == 20_000

        # Streaming peak must be a small fraction of full materialization, and
        # well under the file size (json.load is >= file size here).
        assert stream_peak < load_peak / 4
        assert stream_peak < file_size / 4

    def test_read_top_object_does_not_materialize_big_array(self):
        # read_top_object parses *through* the big `data` array (building only
        # `meta`) — its peak must also stay well below json.load.
        buf, file_size = self._write_large_array()

        buf.seek(0)
        tracemalloc.start()
        values, kinds = read_top_object(buf, {"meta"})
        _, top_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert values["meta"] == {"k": 1}
        assert kinds["data"] == "start_array"
        assert "data" not in values
        assert top_peak < file_size / 4
