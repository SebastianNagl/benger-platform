"""Shape tests for migration 145: compliance assessments, suite runs, findings.

The shared test DB already carries the three tables (built from the models),
so ``upgrade()`` must be a no-op through its guards, twice. ``downgrade()``
removes them and a re-run ``upgrade()`` rebuilds them with the columns,
indexes, keys and checks of the models. Values in double precision survive
exactly, and a finding cannot name a suite run of another assessment.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "145_compliance_findings"
TABLES = ("compliance_assessments", "compliance_suite_runs", "compliance_findings")


def _load():
    spec = importlib.util.spec_from_file_location(
        f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py")
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _models():
    from models import ComplianceAssessment, ComplianceFinding, ComplianceSuiteRun

    return {
        "compliance_assessments": ComplianceAssessment,
        "compliance_suite_runs": ComplianceSuiteRun,
        "compliance_findings": ComplianceFinding,
    }


def _assert_shape(conn):
    insp = inspect(conn)
    for table, model in _models().items():
        columns = {c["name"]: c for c in insp.get_columns(table)}
        assert set(columns) == {c.name for c in model.__table__.columns}, table
        for column in model.__table__.columns:
            assert columns[column.name]["nullable"] == column.nullable, (table, column.name)
        model_indexes = {i.name: [c.name for c in i.columns] for i in model.__table__.indexes}
        db_indexes = {i["name"]: i["column_names"] for i in insp.get_indexes(table)}
        for name, cols in model_indexes.items():
            assert db_indexes.get(name) == cols, (table, name)
        model_checks = {
            c.name for c in model.__table__.constraints if c.__class__.__name__ == "CheckConstraint"
        }
        assert model_checks <= {c["name"] for c in insp.get_check_constraints(table)}, table

    def fks(table):
        return {
            (tuple(fk["constrained_columns"]), fk["referred_table"]): fk["options"].get("ondelete")
            for fk in insp.get_foreign_keys(table)
        }

    assert fks("compliance_assessments") == {
        (("organization_id",), "organizations"): "CASCADE",
        (("system_model_id",), "llm_models"): "SET NULL",
        (("project_id",), "projects"): "SET NULL",
        (("supersedes_id",), "compliance_assessments"): "SET NULL",
        (("created_by",), "users"): "SET NULL",
        (("created_by_key_id",), "api_keys"): "SET NULL",
    }
    assert fks("compliance_suite_runs") == {
        (("assessment_id",), "compliance_assessments"): "CASCADE",
        (("created_by",), "users"): "SET NULL",
    }
    # No key on the analysis ids: those tables are not part of this migration.
    assert fks("compliance_findings") == {
        (("suite_run_id", "assessment_id"), "compliance_suite_runs"): "CASCADE",
    }
    uniques = {
        u["name"]: u["column_names"] for u in insp.get_unique_constraints("compliance_suite_runs")
    }
    assert uniques["uq_compliance_suite_runs_id_assessment"] == ["id", "assessment_id"]
    value_type = {c["name"]: c["type"] for c in insp.get_columns("compliance_findings")}["value"]
    assert "DOUBLE" in str(value_type).upper()


def _world(conn):
    """An org, an assessment and a suite run, inserted with plain SQL."""
    org, assessment, run = (str(uuid.uuid4()) for _ in range(3))
    conn.execute(
        text(
            "INSERT INTO organizations (id, name, display_name, slug, is_active, created_at) "
            "VALUES (:id, :id, :id, :id, true, now())"
        ),
        {"id": org},
    )
    conn.execute(
        text(
            "INSERT INTO compliance_assessments (id, organization_id, title) "
            "VALUES (:id, :org, 'Mig 145')"
        ),
        {"id": assessment, "org": org},
    )
    conn.execute(
        text(
            "INSERT INTO compliance_suite_runs (id, assessment_id, suite_id) "
            "VALUES (:id, :a, 'suite')"
        ),
        {"id": run, "a": assessment},
    )
    return org, assessment, run


class TestMigration145:
    def test_revision_chains_after_the_previous_head(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "141_project_wizard_drafts"

    def test_upgrade_is_idempotent_on_existing_schema(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        _assert_shape(conn)

    def test_downgrade_then_upgrade_rebuilds(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load()
        with _op_context(conn):
            mig.downgrade()
        names = set(inspect(conn).get_table_names())
        assert not names & set(TABLES)
        with _op_context(conn):
            mig.upgrade()
        _assert_shape(conn)

    def test_server_defaults_and_double_precision(self, test_db: Session):
        conn = test_db.get_bind()
        _, assessment, run = _world(conn)
        row = conn.execute(
            text(
                "SELECT status, suites, thresholds, contamination_suspected "
                "FROM compliance_assessments WHERE id = :id"
            ),
            {"id": assessment},
        ).one()
        assert tuple(row) == ("draft", [], {}, False)
        status = conn.execute(
            text("SELECT status, analysis_run_ids FROM compliance_suite_runs WHERE id = :id"),
            {"id": run},
        ).one()
        assert tuple(status) == ("queued", [])
        value = -14.107355442212345
        conn.execute(
            text(
                "INSERT INTO compliance_findings (id, suite_run_id, assessment_id, "
                "requirement_ref, metric, verdict, value, analysis_run_id) "
                "VALUES (:id, :r, :a, 'req', 'm', 'pass', :v, 'run-x')"
            ),
            {"id": str(uuid.uuid4()), "r": run, "a": assessment, "v": value},
        )
        stored = conn.execute(
            text("SELECT value FROM compliance_findings WHERE suite_run_id = :r"), {"r": run}
        ).scalar_one()
        assert stored == value

    def test_finding_must_match_its_suite_runs_assessment(self, test_db: Session):
        conn = test_db.get_bind()
        org, _, run = _world(conn)
        other = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO compliance_assessments (id, organization_id, title) "
                "VALUES (:id, :org, 'Other')"
            ),
            {"id": other, "org": org},
        )
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO compliance_findings (id, suite_run_id, assessment_id, "
                        "requirement_ref, metric, verdict) "
                        "VALUES (:id, :r, :a, 'req', 'm', 'pass')"
                    ),
                    {"id": str(uuid.uuid4()), "r": run, "a": other},
                )

    @pytest.mark.parametrize(
        "columns,values",
        [
            ("verdict", "'passed'"),
            ("verdict, ci_low, ci_high", "'pass', 2.0, 1.0"),
            ("verdict, ci_level", "'pass', 1.0"),
            ("verdict, n_tasks", "'pass', -1"),
        ],
    )
    def test_checks_refuse_bad_rows(self, test_db: Session, columns, values):
        conn = test_db.get_bind()
        _, assessment, run = _world(conn)
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO compliance_findings (id, suite_run_id, assessment_id, "
                        f"requirement_ref, metric, {columns}) "
                        f"VALUES (:id, :r, :a, 'req', 'm', {values})"
                    ),
                    {"id": str(uuid.uuid4()), "r": run, "a": assessment},
                )

    @pytest.mark.parametrize(
        "table,column,allowed",
        [
            ("compliance_assessments", "status", "ASSESSMENT_STATUSES"),
            ("compliance_suite_runs", "status", "SUITE_RUN_STATUSES"),
            ("compliance_findings", "verdict", "VERDICTS"),
        ],
    )
    def test_checks_accept_exactly_the_vocabulary(self, test_db: Session, table, column, allowed):
        import compliance_records as records

        conn = test_db.get_bind()
        _, assessment, run = _world(conn)
        values = getattr(records, allowed)

        def set_value(value):
            with conn.begin_nested():
                if table == "compliance_findings":
                    conn.execute(
                        text(
                            "INSERT INTO compliance_findings (id, suite_run_id, assessment_id, "
                            "requirement_ref, metric, verdict) "
                            "VALUES (:id, :r, :a, 'req', 'm', :v)"
                        ),
                        {"id": str(uuid.uuid4()), "r": run, "a": assessment, "v": value},
                    )
                else:
                    row = assessment if table == "compliance_assessments" else run
                    conn.execute(
                        text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
                        {"v": value, "id": row},
                    )

        for value in values:
            set_value(value)
        for value in ("unknown", values[0].upper(), f"{values[0]} "):
            with pytest.raises(IntegrityError):
                set_value(value)

    def test_deleting_the_assessment_cascades(self, test_db: Session):
        conn = test_db.get_bind()
        _, assessment, run = _world(conn)
        conn.execute(
            text(
                "INSERT INTO compliance_findings (id, suite_run_id, assessment_id, "
                "requirement_ref, metric, verdict) VALUES (:id, :r, :a, 'req', 'm', 'fail')"
            ),
            {"id": str(uuid.uuid4()), "r": run, "a": assessment},
        )
        conn.execute(text("DELETE FROM compliance_assessments WHERE id = :id"), {"id": assessment})
        left = conn.execute(
            text("SELECT count(*) FROM compliance_findings WHERE assessment_id = :a"),
            {"a": assessment},
        ).scalar_one()
        runs = conn.execute(
            text("SELECT count(*) FROM compliance_suite_runs WHERE id = :r"), {"r": run}
        ).scalar_one()
        assert (left, runs) == (0, 0)
