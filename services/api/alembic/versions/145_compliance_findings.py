"""Compliance records: assessments, suite runs and findings

The persistence layer of the compliance assessments (generic CRUD in
``routers/compliance_records.py``, rules in ``shared/compliance_records.py``):

- ``compliance_assessments``: one assessment per organization (CASCADE) of a
  system (``llm_models``, SET NULL), a project (SET NULL) and/or a benchmark
  release (plain id, the releases table does not exist yet), with the
  catalog version, suites, thresholds and their hash, the status (CHECK on
  the static status list), the registration and attestation stamps, the
  assessment it supersedes (SET NULL) and who created it (user or access key,
  SET NULL).
- ``compliance_suite_runs``: one execution of a suite for an assessment
  (CASCADE) with its inputs (submission, evaluation and analysis run ids,
  parameters), hashes, code version, status (CHECK), timings and error.
  ``UNIQUE (id, assessment_id)`` is the target of the findings' composite key.
- ``compliance_findings``: one result of a suite run, tied to the run and its
  assessment by a composite foreign key (CASCADE), with requirement, metric,
  system key, scope, counts, value and interval in double precision, the
  threshold, the verdict (CHECK) and the ids of the analysis run and estimate
  it was derived from. Those two are plain indexed ids: the analysis tables
  are built separately, and the foreign keys follow once they exist.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 145_compliance_findings
Revises: 141_project_wizard_drafts
Create Date: 2026-11-18
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "145_compliance_findings"
down_revision = "141_project_wizard_drafts"
branch_labels = None
depends_on = None

_ASSESSMENTS = "compliance_assessments"
_RUNS = "compliance_suite_runs"
_FINDINGS = "compliance_findings"

_ASSESSMENT_STATUSES = (
    "draft",
    "registered",
    "collecting",
    "scoring",
    "review",
    "attested",
    "superseded",
    "withdrawn",
)
_SUITE_RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
_VERDICTS = ("pass", "fail", "inconclusive", "informative", "not_applicable")


def _in(column, values):
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def _timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _jsonb(name, default, nullable=False):
    return sa.Column(
        name,
        postgresql.JSONB(),
        nullable=nullable,
        server_default=None if default is None else sa.text(default),
    )


def _index(table, name, columns):
    if not _has_index(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    if not _has_table(_ASSESSMENTS):
        op.create_table(
            _ASSESSMENTS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id", sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("catalog_version", sa.String(64), nullable=True),
            _jsonb("suites", "'[]'"),
            _jsonb("thresholds", "'{}'"),
            sa.Column("thresholds_hash", sa.String(64), nullable=True),
            sa.Column(
                "system_model_id", sa.String(),
                sa.ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("release_id", sa.String(), nullable=True),
            sa.Column(
                "supersedes_id", sa.String(),
                sa.ForeignKey(f"{_ASSESSMENTS}.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "contamination_suspected", sa.Boolean(), nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("limitations_text", sa.Text(), nullable=True),
            sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "created_by_key_id", sa.String(),
                sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True,
            ),
            *_timestamps(),
            sa.CheckConstraint(
                _in("status", _ASSESSMENT_STATUSES), name="ck_compliance_assessments_status"
            ),
        )
    for column in ("organization_id", "system_model_id", "project_id", "release_id"):
        _index(_ASSESSMENTS, f"ix_{_ASSESSMENTS}_{column}", [column])

    if not _has_table(_RUNS):
        op.create_table(
            _RUNS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "assessment_id", sa.String(),
                sa.ForeignKey(f"{_ASSESSMENTS}.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("suite_id", sa.String(100), nullable=False),
            sa.Column("suite_version", sa.String(64), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
            _jsonb("parameters", "'{}'"),
            _jsonb("submission_ids", "'[]'"),
            _jsonb("evaluation_run_ids", "'[]'"),
            _jsonb("analysis_run_ids", "'[]'"),
            sa.Column("inputs_hash", sa.String(128), nullable=True),
            sa.Column("judge_config_hash", sa.String(128), nullable=True),
            sa.Column("code_version", sa.String(128), nullable=True),
            sa.Column("celery_task_id", sa.String(), nullable=True),
            sa.Column("log_object_key", sa.String(1024), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            *_timestamps(),
            sa.CheckConstraint(
                _in("status", _SUITE_RUN_STATUSES), name="ck_compliance_suite_runs_status"
            ),
            sa.UniqueConstraint(
                "id", "assessment_id", name="uq_compliance_suite_runs_id_assessment"
            ),
        )
    _index(_RUNS, f"ix_{_RUNS}_assessment_id", ["assessment_id"])

    if not _has_table(_FINDINGS):
        op.create_table(
            _FINDINGS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("suite_run_id", sa.String(), nullable=False),
            sa.Column("assessment_id", sa.String(), nullable=False),
            sa.Column("requirement_ref", sa.String(200), nullable=False),
            sa.Column("metric", sa.String(200), nullable=False),
            sa.Column("system_key", sa.String(255), nullable=True),
            _jsonb("scope", "'{}'"),
            sa.Column("n_tasks", sa.Integer(), nullable=True),
            sa.Column("n_runs", sa.Integer(), nullable=True),
            sa.Column("value", sa.Float(precision=53), nullable=True),
            sa.Column("ci_low", sa.Float(precision=53), nullable=True),
            sa.Column("ci_high", sa.Float(precision=53), nullable=True),
            sa.Column("ci_level", sa.Float(precision=53), nullable=True),
            sa.Column("ci_method", sa.String(64), nullable=True),
            _jsonb("threshold", None, nullable=True),
            sa.Column("verdict", sa.String(32), nullable=False),
            _jsonb("baseline", None, nullable=True),
            _jsonb("details", None, nullable=True),
            sa.Column("analysis_run_id", sa.String(), nullable=True),
            sa.Column("analysis_estimate_id", sa.String(), nullable=True),
            *_timestamps(),
            sa.ForeignKeyConstraint(
                ["suite_run_id", "assessment_id"],
                [f"{_RUNS}.id", f"{_RUNS}.assessment_id"],
                ondelete="CASCADE",
                name="fk_compliance_findings_suite_run",
            ),
            sa.CheckConstraint(_in("verdict", _VERDICTS), name="ck_compliance_findings_verdict"),
            sa.CheckConstraint(
                "ci_level IS NULL OR (ci_level > 0 AND ci_level < 1)",
                name="ck_compliance_findings_ci_level",
            ),
            sa.CheckConstraint(
                "ci_low IS NULL OR ci_high IS NULL OR ci_low <= ci_high",
                name="ck_compliance_findings_ci_order",
            ),
            sa.CheckConstraint(
                "(n_tasks IS NULL OR n_tasks >= 0) AND (n_runs IS NULL OR n_runs >= 0)",
                name="ck_compliance_findings_counts",
            ),
        )
    for column in ("suite_run_id", "analysis_run_id", "analysis_estimate_id"):
        _index(_FINDINGS, f"ix_{_FINDINGS}_{column}", [column])
    _index(
        _FINDINGS,
        "ix_compliance_findings_assessment_requirement",
        ["assessment_id", "requirement_ref"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in (_FINDINGS, _RUNS, _ASSESSMENTS):
        if _has_table(table):
            op.drop_table(table)
