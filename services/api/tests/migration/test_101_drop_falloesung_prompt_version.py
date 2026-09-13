"""Data tests for migration 101: strip the dead `prompt_version` config key.

The Falllösung judge prompt is no longer versioned, so
`metric_parameters.prompt_version` selects nothing. It is live config, though:
without this migration it would survive every export, import and deep merge and
keep reappearing in the eval-config UI.

The pure `_strip` helper carries the semantics (what is removed, what is left
alone) and is tested directly; `upgrade()` is then run against the real DB to
prove it rewrites a seeded project, leaves the rest of the document intact, and
is a no-op the second time.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager

import sqlalchemy as sa

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "101_drop_falloesung_prompt_version.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_101", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


mig = _load_migration()


class TestStripSemantics:
    def test_it_removes_only_the_one_key(self):
        out = mig._strip(
            {
                "grade_scale": {"preset": "uebungsklausur"},
                "evaluation_configs": [
                    {
                        "metric": "llm_judge_falloesung",
                        "metric_parameters": {
                            "judge_model": "gpt-5-mini",
                            "prompt_version": "v2",
                        },
                    }
                ],
            }
        )
        entry = out["evaluation_configs"][0]
        assert entry["metric_parameters"] == {"judge_model": "gpt-5-mini"}
        # Everything else survives — the key sits next to the Notenschlüssel
        # and its audit trail, which must not be disturbed.
        assert out["grade_scale"] == {"preset": "uebungsklausur"}
        assert entry["metric"] == "llm_judge_falloesung"

    def test_a_document_without_the_key_is_reported_unchanged(self):
        assert (
            mig._strip(
                {
                    "evaluation_configs": [
                        {"metric_parameters": {"judge_model": "gpt-5-mini"}}
                    ]
                }
            )
            is None
        )

    def test_the_legacy_list_key_is_covered_too(self):
        out = mig._strip(
            {
                "multi_field_evaluations": [
                    {"metric_parameters": {"prompt_version": "v1"}}
                ]
            }
        )
        assert out["multi_field_evaluations"][0]["metric_parameters"] == {}

    def test_malformed_documents_are_left_alone(self):
        assert mig._strip(None) is None
        assert mig._strip("not a dict") is None
        assert mig._strip({"evaluation_configs": "not a list"}) is None
        # A non-dict entry in an otherwise fine list must not raise.
        assert mig._strip({"evaluation_configs": ["junk"]}) is None


class TestAgainstTheDatabase:
    def _seed(self, db, owner_id, config):
        """A real Project row — the ORM fills the NOT NULL defaults raw SQL
        would miss."""
        from project_models import Project

        project = Project(
            id=str(uuid.uuid4()),
            title="mig101",
            created_by=owner_id,
            evaluation_config=config,
        )
        db.add(project)
        db.commit()
        return project.id

    def _read(self, db, project_id):
        raw = db.execute(
            sa.text("SELECT evaluation_config FROM projects WHERE id = :id"),
            {"id": project_id},
        ).scalar()
        return _loads(raw)

    def test_upgrade_strips_and_is_idempotent(self, test_db, test_user):
        project_id = self._seed(
            test_db,
            test_user.id,
            {
                "grade_scale": {"preset": "standard"},
                "evaluation_configs": [
                    {
                        "id": "free",
                        "metric": "llm_judge_falloesung",
                        "metric_parameters": {
                            "judge_model": "gpt-5-mini",
                            "prompt_version": "v2",
                        },
                    },
                    {
                        "id": "rubric",
                        "metric": "llm_judge_rubric",
                        "metric_parameters": {"judge_model": "gpt-5.4-mini"},
                    },
                ],
            },
        )
        try:
            with _bound(test_db):
                mig.upgrade()
            doc = self._read(test_db, project_id)
            assert doc["evaluation_configs"][0]["metric_parameters"] == {
                "judge_model": "gpt-5-mini"
            }
            assert doc["evaluation_configs"][1]["metric_parameters"] == {
                "judge_model": "gpt-5.4-mini"
            }
            assert doc["grade_scale"] == {"preset": "standard"}

            # Second run finds nothing to do and changes nothing.
            with _bound(test_db):
                mig.upgrade()
            assert self._read(test_db, project_id) == doc
        finally:
            test_db.execute(
                sa.text("DELETE FROM projects WHERE id = :id"), {"id": project_id}
            )
            test_db.commit()


# --- helpers ---------------------------------------------------------------


def _dumps(config):
    return json.dumps(config)


def _loads(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def _config_type(db):
    from sqlalchemy import inspect as sa_inspect

    for column in sa_inspect(db.get_bind()).get_columns("projects"):
        if column["name"] == "evaluation_config":
            return "jsonb" if "JSONB" in str(column["type"]).upper() else "json"
    return "json"


@contextmanager
def _bound(db):
    """Run the migration's `upgrade()` on the test session's connection.

    `upgrade()` only ever asks alembic for the bind, so pointing that at the
    open test transaction is enough — and keeps the rows the test seeded
    visible to it.
    """
    original = mig.op.get_bind
    mig.op.get_bind = lambda: db.connection()  # type: ignore[assignment]
    try:
        yield
    finally:
        mig.op.get_bind = original  # type: ignore[assignment]
