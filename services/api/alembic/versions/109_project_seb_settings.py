"""Safe Exam Browser settings on projects

Adds two columns to ``projects`` for Safe Exam Browser (SEB) exams:

* ``seb_required`` (bool, default false): exam content reads and exam writes
  by non-editors must come from SEB with an accepted Config Key.
* ``seb_config`` (JSONB, nullable): the SEB settings the extended edition
  generates the ``.seb`` file from, plus the keys the platform guard accepts
  (``generated_config_key``, ``extra_config_keys``, ``browser_exam_keys``).

Both are guarded by column-exists checks, so a re-run is a no-op.

Revision ID: 109_project_seb_settings
Revises: 108_drop_project_members
Create Date: 2026-09-24
"""

from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
import sqlalchemy as sa


revision = "109_project_seb_settings"
down_revision = "108_drop_project_members"
branch_labels = None
depends_on = None

_TABLE = "projects"


def _columns() -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns()
    op.execute("SET LOCAL lock_timeout = '5s'")
    if "seb_required" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "seb_required",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if "seb_config" not in existing:
        op.add_column(_TABLE, sa.Column("seb_config", JSONB(), nullable=True))


def downgrade() -> None:
    existing = _columns()
    if "seb_config" in existing:
        op.drop_column(_TABLE, "seb_config")
    if "seb_required" in existing:
        op.drop_column(_TABLE, "seb_required")
