"""Handwritten solution uploads on by default

- ``projects.handwriting_ocr_enabled`` gets the server default TRUE, so new
  projects take handwritten uploads unless a teacher switches them off.
- Every existing project whose switch is off is switched on, matching the
  new default, so handwriting works across the whole app.

Which model reads the pages is unchanged in the schema: the project's
override, else the organization default, else the platform default
(``shared/org_ocr.py``).

``downgrade()`` restores the server default FALSE only. Leaving the
per-project values on is a deliberate no-op: the server only uses the flag on
exam-shaped projects (a ``Loesung`` answer field), and prod had it on for 0
projects before this migration, so nothing meaningful is lost.

Idempotent: the backfill only touches projects still off, so a re-run (or a
database built from the models) is safe.

Revision ID: 149_handwriting_ocr_default_on
Revises: 148_analysis_lookup_tables
Create Date: 2026-11-19
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "149_handwriting_ocr_default_on"
down_revision = "148_analysis_lookup_tables"
branch_labels = None
depends_on = None

_PROJECTS = "projects"
_COLUMN = "handwriting_ocr_enabled"


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column(_PROJECTS, _COLUMN):
        return
    op.alter_column(_PROJECTS, _COLUMN, server_default=sa.true())
    op.execute(f"UPDATE {_PROJECTS} SET {_COLUMN} = TRUE WHERE {_COLUMN} IS FALSE")


def downgrade() -> None:
    if _has_column(_PROJECTS, _COLUMN):
        op.alter_column(_PROJECTS, _COLUMN, server_default=sa.false())
