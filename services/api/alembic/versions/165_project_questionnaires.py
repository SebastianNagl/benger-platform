"""Project questionnaires for three moments, one answer store.

New tables:

- ``project_questionnaires``: one questionnaire per project and moment
  (``trigger`` in before_task, after_submit, korrektur) with ``enabled``,
  ``config`` (label-config XML), ``required`` (false: may be skipped),
  ``frequency`` (once_per_project, once_per_task, once_per_submission) and
  ``version`` (config edits, 0 = never configured).
- ``project_questionnaire_versions``: the config text of every version.
- ``questionnaire_responses``: every answer of every moment, with the
  questionnaire version and config hash it answered and what it is about
  (task, annotation, task evaluation, ``subject_key``).

Backfill, exact: every project with a post-annotation questionnaire (switched
on, configured or answered) gets an ``after_submit`` questionnaire with its
``questionnaire_enabled`` and ``questionnaire_config``, required (the old
modal could not be dismissed) and asked once per submission (as before); a
non-empty config becomes version 1. Every ``post_annotation_responses`` row
is copied with its id, user, task, annotation, result and ``created_at``.
Version 1 is recorded for a copied answer only when its stored config hash
(written since revision 164) matches the config being migrated; older answers
keep a NULL version because the text they answered is not known exactly.
Should a database hold two answers for one annotation, both are kept (the
second gets a distinct subject key).

``projects.questionnaire_enabled`` / ``questionnaire_config`` and the
``post_annotation_responses`` table stay for one release: the API keeps the
two project fields in step with the after_submit questionnaire, and the old
table is no longer written. A later revision drops them.

Idempotent: tables are created only when missing and the backfill skips
projects that already have an after_submit questionnaire and answers whose id
is already copied, so a database built from the models (the test DB) runs it
as a no-op apart from the backfill of any rows it holds.

Revision ID: 165_project_questionnaires
Revises: 164_questionnaire_response_unique_and_hash
Create Date: 2026-11-27
"""

import hashlib
import json
import uuid

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "165_project_questionnaires"
down_revision = "164_questionnaire_response_unique_and_hash"
branch_labels = None
depends_on = None

_TRIGGERS = "trigger IN ('before_task', 'after_submit', 'korrektur')"
_FREQUENCIES = "frequency IN ('once_per_project', 'once_per_task', 'once_per_submission')"


def _tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def _create_tables(existing: set) -> None:
    if "project_questionnaires" not in existing:
        op.create_table(
            "project_questionnaires",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("trigger", sa.String(length=32), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("config", sa.Text(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("frequency", sa.String(length=32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "project_id", "trigger", name="uq_project_questionnaires_project_trigger"
            ),
            sa.CheckConstraint(_TRIGGERS, name="ck_project_questionnaires_trigger"),
            sa.CheckConstraint(_FREQUENCIES, name="ck_project_questionnaires_frequency"),
        )
        op.create_index(
            "ix_project_questionnaires_project_id", "project_questionnaires", ["project_id"]
        )

    if "project_questionnaire_versions" not in existing:
        op.create_table(
            "project_questionnaire_versions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "questionnaire_id",
                sa.String(),
                sa.ForeignKey("project_questionnaires.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("config", sa.Text(), nullable=False),
            sa.Column("config_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "questionnaire_id", "version", name="uq_project_questionnaire_versions_version"
            ),
        )
        op.create_index(
            "ix_project_questionnaire_versions_questionnaire_id",
            "project_questionnaire_versions",
            ["questionnaire_id"],
        )

    if "questionnaire_responses" not in existing:
        op.create_table(
            "questionnaire_responses",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "questionnaire_id",
                sa.String(),
                sa.ForeignKey("project_questionnaires.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("trigger", sa.String(length=32), nullable=False),
            sa.Column("questionnaire_version", sa.Integer(), nullable=True),
            sa.Column("config_hash", sa.String(length=64), nullable=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
            ),
            sa.Column(
                "annotation_id",
                sa.String(),
                sa.ForeignKey("annotations.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "task_evaluation_id",
                sa.String(),
                sa.ForeignKey("task_evaluations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("subject_key", sa.String(length=160), nullable=False),
            sa.Column("skipped", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("result", postgresql.JSONB(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
            ),
            sa.UniqueConstraint(
                "questionnaire_id",
                "user_id",
                "subject_key",
                name="uq_questionnaire_responses_subject",
            ),
            sa.CheckConstraint(_TRIGGERS, name="ck_questionnaire_responses_trigger"),
        )
        for name, cols in (
            ("ix_questionnaire_responses_project_id", ["project_id"]),
            ("ix_questionnaire_responses_questionnaire_id", ["questionnaire_id"]),
            ("ix_questionnaire_responses_annotation_id", ["annotation_id"]),
            ("ix_questionnaire_responses_task_evaluation_id", ["task_evaluation_id"]),
            ("ix_questionnaire_responses_project_trigger", ["project_id", "trigger"]),
            ("ix_questionnaire_responses_user_project", ["user_id", "project_id"]),
        ):
            op.create_index(name, "questionnaire_responses", cols)


def _sha256(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def _backfill(existing: set) -> None:
    bind = op.get_bind()
    has_old_answers = "post_annotation_responses" in existing
    project_columns = _columns("projects")
    if "questionnaire_enabled" not in project_columns:
        return

    answered_projects = set()
    if has_old_answers:
        answered_projects = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT DISTINCT project_id FROM post_annotation_responses")
            )
        }

    projects = bind.execute(
        sa.text(
            "SELECT id, questionnaire_enabled, questionnaire_config FROM projects "
            "WHERE questionnaire_enabled IS TRUE "
            "OR COALESCE(btrim(questionnaire_config), '') <> ''"
        )
    ).fetchall()
    wanted = {row[0]: (bool(row[1]), row[2]) for row in projects}
    if answered_projects:
        missing = answered_projects - set(wanted)
        if missing:
            for row in bind.execute(
                sa.text(
                    "SELECT id, questionnaire_enabled, questionnaire_config FROM projects "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": list(missing)},
            ):
                wanted[row[0]] = (bool(row[1]), row[2])

    already = {
        row[0]: row[1]
        for row in bind.execute(
            sa.text(
                "SELECT project_id, id FROM project_questionnaires WHERE trigger = 'after_submit'"
            )
        )
    }

    # project id -> (questionnaire id, hash of its version 1 or None)
    questionnaire_of = {}
    for project_id, qid in already.items():
        v1 = bind.execute(
            sa.text(
                "SELECT config_hash FROM project_questionnaire_versions "
                "WHERE questionnaire_id = :q AND version = 1"
            ),
            {"q": qid},
        ).scalar()
        questionnaire_of[project_id] = (qid, v1)

    for project_id, (enabled, config) in wanted.items():
        if project_id in questionnaire_of:
            continue
        qid = str(uuid.uuid4())
        has_config = bool((config or "").strip())
        bind.execute(
            sa.text(
                "INSERT INTO project_questionnaires "
                "(id, project_id, trigger, enabled, config, required, frequency, version) "
                "VALUES (:id, :p, 'after_submit', :enabled, :config, true, "
                "'once_per_submission', :version)"
            ),
            {
                "id": qid,
                "p": project_id,
                "enabled": enabled,
                "config": config,
                "version": 1 if has_config else 0,
            },
        )
        v1_hash = None
        if has_config:
            v1_hash = _sha256(config)
            bind.execute(
                sa.text(
                    "INSERT INTO project_questionnaire_versions "
                    "(id, questionnaire_id, version, config, config_hash) "
                    "VALUES (:id, :q, 1, :config, :hash)"
                ),
                {"id": str(uuid.uuid4()), "q": qid, "config": config, "hash": v1_hash},
            )
        questionnaire_of[project_id] = (qid, v1_hash)

    if not has_old_answers:
        return

    hash_column = "config_hash" in _columns("post_annotation_responses")
    rows = bind.execute(
        sa.text(
            "SELECT par.id, par.project_id, par.user_id, par.task_id, par.annotation_id, "
            "par.result, par.created_at, "
            + ("par.config_hash, " if hash_column else "NULL AS config_hash, ")
            + "row_number() OVER (PARTITION BY par.project_id, par.user_id, par.annotation_id "
            "ORDER BY par.created_at, par.id) AS rn "
            "FROM post_annotation_responses par "
            "WHERE NOT EXISTS (SELECT 1 FROM questionnaire_responses qr WHERE qr.id = par.id)"
        )
    ).fetchall()

    insert = sa.text(
        "INSERT INTO questionnaire_responses "
        "(id, project_id, questionnaire_id, trigger, questionnaire_version, config_hash, "
        "user_id, task_id, annotation_id, task_evaluation_id, subject_key, skipped, result, "
        "created_at) VALUES (:id, :project_id, :qid, 'after_submit', :version, :hash, "
        ":user_id, :task_id, :annotation_id, NULL, :subject, false, "
        "CAST(:result AS JSONB), :created_at)"
    )

    for row in rows:
        qid, v1_hash = questionnaire_of[row.project_id]
        subject = f"annotation:{row.annotation_id}"
        if row.rn > 1:
            subject = f"{subject}#{row.id}"
        version = 1 if (row.config_hash and v1_hash and row.config_hash == v1_hash) else None
        bind.execute(
            insert,
            {
                "id": row.id,
                "project_id": row.project_id,
                "qid": qid,
                "version": version,
                "hash": row.config_hash,
                "user_id": row.user_id,
                "task_id": row.task_id,
                "annotation_id": row.annotation_id,
                "subject": subject,
                "result": json.dumps(row.result if row.result is not None else []),
                "created_at": row.created_at,
            },
        )


def upgrade() -> None:
    existing = _tables()
    _create_tables(existing)
    _backfill(existing)


def downgrade() -> None:
    # The answers copied from post_annotation_responses are still there (the
    # table is kept); answers given since are dropped with the new tables.
    existing = _tables()
    for table in (
        "questionnaire_responses",
        "project_questionnaire_versions",
        "project_questionnaires",
    ):
        if table in existing:
            op.drop_table(table)
