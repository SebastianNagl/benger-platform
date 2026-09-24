"""Drop the legacy ``project_members`` table

``project_members`` came from the permission model that predates
organizations. No endpoint wrote to it any more; the only writer was the full
project import, which copied rows over from older exports. It never granted
project access. Project roles now come from organization memberships only
(org role, group admin, LTI author, superadmin), so the table and every
reader go.

Upgrade drops the table and its three indexes. It is guarded by a
table-exists check, so a re-run, or a database that never had the table, is a
no-op. Row data is not preserved: in production every row duplicated a role
the user already holds through an attached organization.

Downgrade recreates the empty table exactly as ``001_complete_baseline``
created it.

Revision ID: 108_drop_project_members
Revises: 107_invitation_email_state
Create Date: 2026-09-24
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "108_drop_project_members"
down_revision = "107_invitation_email_state"
branch_labels = None
depends_on = None

_TABLE = "project_members"
_INDEXES = (
    ("ix_project_members_id", ["id"]),
    ("ix_project_members_project_id", ["project_id"]),
    ("ix_project_members_user_id", ["user_id"]),
)


def _table_exists() -> bool:
    return _TABLE in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists():
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    existing = {ix["name"] for ix in inspect(op.get_bind()).get_indexes(_TABLE)}
    for name, _cols in reversed(_INDEXES):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)


def downgrade() -> None:
    if _table_exists():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("assigned_by", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="unique_project_member"),
    )
    for name, cols in _INDEXES:
        op.create_index(name, _TABLE, cols, unique=False)
