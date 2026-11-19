"""Handwritten solution uploads on by default

- ``projects.handwriting_ocr_enabled`` gets the server default TRUE, so new
  projects take handwritten uploads unless a teacher switches them off.
- Existing exam-shaped projects (a label config with a ``Loesung`` field
  carrying ``name`` and ``toName``, the field the upload fills) whose switch
  is off are switched on. Their ids are recorded in
  ``handwriting_ocr_backfill_149`` so ``downgrade()`` switches exactly those
  back off and leaves every switch a teacher set alone.

Which model reads the pages is unchanged in the schema: the project's
override, else the organization default, else the platform default
(``shared/org_ocr.py``).

Idempotent: the backfill only touches projects still off and records each
id once, so a re-run (or a database built from the models) is safe.

Revision ID: 149_handwriting_ocr_default_on
Revises: 148_analysis_lookup_tables
Create Date: 2026-11-19
"""

import xml.etree.ElementTree as ET

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "149_handwriting_ocr_default_on"
down_revision = "148_analysis_lookup_tables"
branch_labels = None
depends_on = None

_PROJECTS = "projects"
_COLUMN = "handwriting_ocr_enabled"
_BACKFILL = "handwriting_ocr_backfill_149"
_ANSWER_TAG = "Loesung"


def has_answer_field(label_config) -> bool:
    """Whether the label config has a ``Loesung`` field with ``name`` and
    ``toName`` (the extended upload's ``answer_field`` test, self-contained
    so the migration does not depend on the extension registering the tag)."""
    if not label_config or _ANSWER_TAG not in label_config:
        return False
    try:
        root = ET.fromstring(label_config)
    except ET.ParseError:
        return False
    return any(
        elem.get("name") and elem.get("toName") for elem in root.iter(_ANSWER_TAG)
    )


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    return table in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_column(_PROJECTS, _COLUMN):
        return
    op.alter_column(_PROJECTS, _COLUMN, server_default=sa.true())

    if not _has_table(_BACKFILL):
        op.create_table(
            _BACKFILL,
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT id, label_config FROM {_PROJECTS} "
            f"WHERE {_COLUMN} IS FALSE AND label_config LIKE :tag"
        ),
        {"tag": f"%{_ANSWER_TAG}%"},
    ).fetchall()
    ids = [row.id for row in rows if has_answer_field(row.label_config)]
    if not ids:
        return
    bind.execute(
        sa.text(
            f"INSERT INTO {_BACKFILL} (project_id) SELECT unnest(CAST(:ids AS varchar[])) "
            "ON CONFLICT DO NOTHING"
        ),
        {"ids": ids},
    )
    bind.execute(
        sa.text(f"UPDATE {_PROJECTS} SET {_COLUMN} = TRUE WHERE id = ANY(CAST(:ids AS varchar[]))"),
        {"ids": ids},
    )


def downgrade() -> None:
    if _has_table(_BACKFILL):
        op.execute(
            f"UPDATE {_PROJECTS} SET {_COLUMN} = FALSE "
            f"WHERE id IN (SELECT project_id FROM {_BACKFILL})"
        )
        op.drop_table(_BACKFILL)
    if _has_column(_PROJECTS, _COLUMN):
        op.alter_column(_PROJECTS, _COLUMN, server_default=sa.false())
