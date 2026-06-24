"""add project_share_links and project_share_members tables

Student exam-training experience (issue #35) — per-exam password sharing. An
owner mints a share link with a bcrypt-hashed password (never md5/FIPS); an
invitee with a BenGER account joins by entering the password, creating a member
row that captures GDPR consent.

- ``project_share_links``: unique ``token``, bcrypt ``password_hash``,
  lifecycle columns ``expires_at`` / ``max_uses`` / ``revoked_at`` (gate JOIN
  only; member eviction gates ongoing access).
- ``project_share_members``: unique (share_link_id, user_id); ``gdpr_consent_at``
  + ``consent_version`` gate roster/cohort-leaderboard reads. Scores are NOT
  denormalized — best/last are computed from task_evaluations at read time.

All FKs ``ondelete=CASCADE`` for right-to-erasure (deleted user/project
self-cleans memberships and links).

Idempotent — guards on table/index existence; safe to re-run.

Revision ID: 066_add_project_share_tables
Revises: 065_add_flashcard_srs_tables
Create Date: 2026-06-25
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "066_add_project_share_tables"
down_revision = "065_add_flashcard_srs_tables"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _table_exists("project_share_links"):
        op.create_table(
            "project_share_links",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("token", sa.String(length=64), nullable=False, unique=True),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(
        "ix_project_share_links_token", "project_share_links", ["token"]
    )
    _create_index_if_missing(
        "ix_project_share_links_project", "project_share_links", ["project_id"]
    )
    _create_index_if_missing(
        "ix_project_share_links_created_by", "project_share_links", ["created_by"]
    )

    if not _table_exists("project_share_members"):
        op.create_table(
            "project_share_members",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "share_link_id",
                sa.String(),
                sa.ForeignKey("project_share_links.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("gdpr_consent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consent_version", sa.String(length=16), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "share_link_id", "user_id", name="uq_project_share_member"
            ),
        )
    _create_index_if_missing(
        "ix_project_share_members_project", "project_share_members", ["project_id"]
    )
    _create_index_if_missing(
        "ix_project_share_members_user", "project_share_members", ["user_id"]
    )


def downgrade() -> None:
    if _table_exists("project_share_members"):
        op.drop_table("project_share_members")
    if _table_exists("project_share_links"):
        op.drop_table("project_share_links")
