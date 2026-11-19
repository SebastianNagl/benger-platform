"""Unit tests of ``shared/import_provenance.py``: payload hash, source
manifest, idempotency key and the declared-manifest check. The worker flow
(no-op re-import, changed payload, concurrent repeats) is covered end to end
in ``services/workers/tests/integration/test_import_provenance_e2e.py``."""

import hashlib
import io

import import_provenance as provenance
import pytest


def _manifest(**overrides):
    fields = {
        "payload_sha256": "a" * 64,
        "byte_size": 10,
        "object_key": "imports/2026/11/p1/20261119_120000_tasks.json",
        "source_connection_id": None,
        "target": provenance.project_target("p1"),
        "mode": "nested",
    }
    fields.update(overrides)
    return provenance.build_manifest(**fields)


class TestHashFileobj:
    def test_hash_and_size_of_the_whole_file_from_its_start(self):
        body = b"x" * (3 * 1024 * 1024 + 17)
        fileobj = io.BytesIO(body)
        fileobj.seek(100)

        digest, size = provenance.hash_fileobj(fileobj)

        assert digest == hashlib.sha256(body).hexdigest()
        assert size == len(body)
        assert fileobj.tell() == 0

    def test_empty_file(self):
        assert provenance.hash_fileobj(io.BytesIO(b"")) == (
            hashlib.sha256(b"").hexdigest(),
            0,
        )


class TestBuildManifest:
    def test_upload_into_a_project(self):
        manifest = _manifest(declared={"origin": "synthetic"})
        assert manifest == {
            "version": 1,
            "payload": {"sha256": "a" * 64, "byte_size": 10},
            "source": {
                "kind": "upload",
                "object_key": "imports/2026/11/p1/20261119_120000_tasks.json",
                "filename": "20261119_120000_tasks.json",
            },
            "target": {"kind": "project", "project_id": "p1"},
            "import": {"mode": "nested", "model_id_map": {}, "reimport": False},
            "declared": {"origin": "synthetic"},
        }

    def test_storage_connection_source(self):
        manifest = _manifest(
            object_key="in/rows.csv", source_connection_id="c1", mode="csv"
        )
        assert manifest["source"] == {
            "kind": "storage_connection",
            "object_key": "in/rows.csv",
            "filename": "rows.csv",
            "connection_id": "c1",
        }
        assert "declared" not in manifest

    def test_new_project_target(self):
        manifest = _manifest(
            target=provenance.new_project_target("u1", "o1", None),
            mode="comprehensive",
            model_id_map={"b": "y", "a": "x"},
        )
        assert manifest["target"] == {
            "kind": "new_project",
            "requested_by": "u1",
            "organization_id": "o1",
            "organization_group_id": None,
        }
        assert list(manifest["import"]["model_id_map"]) == ["a", "b"]

    def test_model_map_only_counts_where_it_applies(self):
        # The nested and tabular imports ignore the map, so it is not recorded
        # and cannot make two identical nested imports look different.
        assert _manifest(model_id_map={"a": "x"})["import"]["model_id_map"] == {}
        assert _manifest(mode="merge", model_id_map={"a": "x"})["import"][
            "model_id_map"
        ] == {"a": "x"}


class TestIdempotencyKey:
    def test_same_payload_target_and_options_give_the_same_key(self):
        assert provenance.idempotency_key(_manifest()) == provenance.idempotency_key(
            _manifest()
        )

    def test_changed_payload_gives_another_key(self):
        assert provenance.idempotency_key(
            _manifest(payload_sha256="b" * 64)
        ) != provenance.idempotency_key(_manifest())

    @pytest.mark.parametrize(
        "overrides",
        [
            {"target": provenance.project_target("p2")},
            {"mode": "merge"},
            {
                "target": provenance.new_project_target("u1", None, None),
                "mode": "comprehensive",
            },
        ],
    )
    def test_other_target_or_mode_gives_another_key(self, overrides):
        assert provenance.idempotency_key(_manifest(**overrides)) != (
            provenance.idempotency_key(_manifest())
        )

    def test_model_map_counts_for_a_merge(self):
        assert provenance.idempotency_key(
            _manifest(mode="merge", model_id_map={"a": "x"})
        ) != provenance.idempotency_key(_manifest(mode="merge"))

    def test_source_name_reimport_and_declared_do_not_count(self):
        # The same bytes uploaded again under another name, imported with
        # reimport or described differently are still the same import.
        assert provenance.idempotency_key(
            _manifest(
                object_key="imports/2026/11/p1/20261120_090000_copy.json",
                source_connection_id="c1",
                reimport=True,
                declared={"note": "second upload"},
            )
        ) == provenance.idempotency_key(_manifest())

    def test_merge_preview_has_no_key(self):
        assert provenance.idempotency_key(_manifest(mode="merge_preview")) is None

    def test_key_is_a_sha256_hex(self):
        key = provenance.idempotency_key(_manifest())
        assert len(key) == 64 and int(key, 16) >= 0


class TestValidateDeclaredManifest:
    def test_none_and_objects_pass(self):
        assert provenance.validate_declared_manifest(None) is None
        assert provenance.validate_declared_manifest({"a": [1, 2]}) == {"a": [1, 2]}

    @pytest.mark.parametrize("bad", [[1], "x", 3, True])
    def test_non_objects_are_refused(self, bad):
        with pytest.raises(ValueError, match="JSON object"):
            provenance.validate_declared_manifest(bad)

    def test_non_json_values_are_refused(self):
        with pytest.raises(ValueError, match="plain JSON"):
            provenance.validate_declared_manifest({"a": object()})

    def test_size_limit(self):
        limit = provenance.DECLARED_MANIFEST_MAX_BYTES
        # {"a":"..."} is 8 bytes of framing around the value.
        assert provenance.validate_declared_manifest({"a": "x" * (limit - 8)})
        with pytest.raises(ValueError, match="too large"):
            provenance.validate_declared_manifest({"a": "x" * (limit - 7)})


class TestNoOpResult:
    def test_points_at_the_earlier_job_and_keeps_its_project(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        prior = SimpleNamespace(
            id="job-1",
            project_id="p1",
            updated_at=datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc),
            result={
                "project_title": "Copy",
                "project_url": "/projects/p1",
                "statistics": {"imported_counts": {"tasks": 5}},
            },
        )
        assert provenance.no_op_result(prior, "a" * 64) == {
            "project_id": "p1",
            "no_op": True,
            "duplicate_of": {
                "job_id": "job-1",
                "completed_at": "2026-11-19T08:00:00+00:00",
                "payload_sha256": "a" * 64,
            },
            "project_title": "Copy",
            "project_url": "/projects/p1",
        }
