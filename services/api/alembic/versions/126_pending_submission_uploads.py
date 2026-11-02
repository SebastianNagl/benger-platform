"""Solutions uploaded for people who are not on BenGER yet

New table ``pending_submission_uploads``: an admin uploads a solution for a
course participant who has no account yet. The participant is invited; the
upload waits here ("parked") until the invitation is accepted, then the
extended acceptance hook turns it into the participant's submission (an
annotation plus a ``submission_files`` row) and records that in
``attached_user_id`` / ``attached_annotation_id`` / ``attached_at``.

The file lives in object storage (``storage_key``, durable ``submissions/``
prefix). ``extracted_text`` is the answer text; it is NULL while a
handwriting OCR job (``ocr_job_id``) still reads a scan. ``status`` is one of
``extracting``, ``waiting``, ``attached``, ``superseded``, ``failed``,
``cancelled``. At most one open (``extracting``/``waiting``) row exists per
task and email (partial unique index).

``project_id`` and ``task_id`` cascade; ``invitation_id``, ``uploaded_by`` and
the ``attached_*`` references are SET NULL so the audit record survives.

Downgrade drops the table. Every step is guarded, so a re-run is a no-op.

Revision ID: 126_pending_submission_uploads
Revises: 125_submission_ocr_jobs
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op


revision = "126_pending_submission_uploads"
down_revision = "125_submission_ocr_jobs"
branch_labels = None
depends_on = None

_TABLE = "pending_submission_uploads"
_OPEN_INDEX = "uq_pending_submission_uploads_open"


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
            "invitation_id",
            sa.String(),
            sa.ForeignKey("invitations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("invitee_name", sa.String(), nullable=True),
        sa.Column(
            "uploaded_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "ocr_job_id",
            sa.String(),
            sa.ForeignKey("submission_ocr_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "attached_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "attached_annotation_id",
            sa.String(),
            sa.ForeignKey("annotations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('extracting','waiting','attached','superseded','failed','cancelled')",
            name="ck_pending_submission_uploads_status",
        ),
    )
    op.create_index(
        _OPEN_INDEX,
        _TABLE,
        ["task_id", "email"],
        unique=True,
        postgresql_where=sa.text("status IN ('extracting','waiting')"),
    )
    op.create_index("ix_pending_submission_uploads_email", _TABLE, ["email"])
    op.create_index("ix_pending_submission_uploads_invitation", _TABLE, ["invitation_id"])
    op.create_index("ix_pending_submission_uploads_project", _TABLE, ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    op.drop_table(_TABLE)
