"""Uploaded solution files for a task submission

New table ``submission_files``: one row per file a person handed in as their
answer to a task, instead of typing it in the editor. The file itself lives in
object storage (``storage_key``); the row records whose answer it is
(``user_id``), who uploaded it (``uploaded_by``, differs from ``user_id`` when
an admin uploads on someone's behalf), the original name, type, size, SHA-256
and the format the text was extracted from. When an upload replaced an
existing submission, ``replaced_result`` keeps the replaced annotation result
for the audit trail.

``project_id``, ``task_id`` and ``user_id`` cascade on delete; ``uploaded_by``
and ``annotation_id`` are SET NULL so the record survives the uploader's
account or the annotation. Index ``ix_submission_files_task_user`` serves the
"files of this person's answer" lookup.

Downgrade drops the table. Every step is guarded, so a re-run is a no-op.

Revision ID: 113_submission_files
Revises: 112_lti_resource_link_task
Create Date: 2026-10-07
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


revision = "113_submission_files"
down_revision = "112_lti_resource_link_task"
branch_labels = None
depends_on = None

_TABLE = "submission_files"
_INDEX = "ix_submission_files_task_user"


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "annotation_id",
            sa.String(),
            sa.ForeignKey("annotations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("extracted_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replaced_result", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(_INDEX, _TABLE, ["task_id", "user_id", "created_at"])
    op.create_index("ix_submission_files_project", _TABLE, ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    op.drop_table(_TABLE)
