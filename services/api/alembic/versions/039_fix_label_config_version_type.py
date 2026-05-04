"""Convert projects.label_config_version from integer to varchar(50)

Long-standing schema drift: the SQLAlchemy model declares
`label_config_version = Column(String(50), nullable=True)` but on
production the column is still `integer` from an old baseline migration
that never got reconciled. The application writes string version tags
("v1", "v2", ...) via `LabelConfigVersionService`, so every label-config
update that bumps the version raises:

    psycopg2.errors.InvalidTextRepresentation:
    invalid input syntax for type integer: "v2"

…and surfaces as a 500 in `PATCH /api/projects/{id}`. The 19 existing
non-null rows in prod all hold the integer value `1`; we convert them
in place to `'v1'` so the post-migration shape matches what the model
and the version service expect.

The cast is wrapped in a `USING` clause so PostgreSQL coerces existing
integer rows to the new type without a separate data migration. On dev
/ fresh DBs (where the column is already varchar) the ALTER is a no-op
because PG short-circuits when source and target types match — but to
keep things idempotent we guard with a column-type check first.

Revision ID: 039_fix_label_config_version_type
Revises: 038_korrektur_backfill_orphan_human_runs
Create Date: 2026-05-04
"""

from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text


revision = "039_fix_label_config_version_type"
down_revision = "038_korrektur_backfill_orphan_human_runs"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _column_type(conn, table: str, column: str) -> str:
    return conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    current = _column_type(conn, "projects", "label_config_version")
    if current == "integer":
        logger.info("[039] projects.label_config_version is integer; converting to varchar(50)")
        conn.execute(
            text(
                """
                ALTER TABLE projects
                ALTER COLUMN label_config_version
                TYPE varchar(50)
                USING CASE
                    WHEN label_config_version IS NULL THEN NULL
                    ELSE 'v' || label_config_version::text
                END
                """
            )
        )
    elif current in ("character varying", "varchar", "text"):
        logger.info("[039] projects.label_config_version already %s; nothing to do", current)
    else:
        logger.warning(
            "[039] projects.label_config_version unexpected type %r; leaving as-is", current
        )


def downgrade() -> None:
    """Revert to integer, dropping the 'v' prefix. Rows whose tag isn't a
    pure 'v<n>' string become NULL — irrecoverable, but the upgrade was
    designed to land permanently. The downgrade exists for completeness
    and is not expected to run in production."""
    conn = op.get_bind()
    current = _column_type(conn, "projects", "label_config_version")
    if current in ("character varying", "varchar", "text"):
        conn.execute(
            text(
                """
                ALTER TABLE projects
                ALTER COLUMN label_config_version
                TYPE integer
                USING CASE
                    WHEN label_config_version ~ '^v[0-9]+$'
                        THEN substring(label_config_version FROM 2)::integer
                    ELSE NULL
                END
                """
            )
        )
