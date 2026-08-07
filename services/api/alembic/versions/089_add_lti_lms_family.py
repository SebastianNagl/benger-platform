"""add lms_family to lti_platform_registrations

Advisory LMS-vendor tag for a platform registration (``'moodle'`` |
``'ilias'``; NULL = unspecified/generic). Drives admin-UI URL presets,
per-LMS field hints and warnings (e.g. "ILIAS validates client assertions
only via a JWKS URL"), docs deep-links, and grade-push diagnostics (ILIAS
discards the AGS score ``comment``). The LTI protocol code deliberately
NEVER branches on it — launches stay spec-driven; anything a launch needs
comes from the id_token itself (``tool_platform.product_family_code``).

Schema is platform-owned (split rule); the extended edition reads the column
through its registration loader. Community edition carries it forward-
compatibly like the rest of the ``lti_*`` schema.

Pure additive. Idempotent — guards on column/constraint existence.

Revision ID: 089_add_lti_lms_family
Revises: 087_task_evaluations_metrics_jsonb
Create Date: 2026-08-06
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "089_add_lti_lms_family"
down_revision = "087_task_evaluations_metrics_jsonb"
branch_labels = None
depends_on = None

_TABLE = "lti_platform_registrations"
_COLUMN = "lms_family"
_CHECK = "ck_lti_platform_registrations_lms_family"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def _check_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ck["name"] for ck in insp.get_check_constraints(table)}


def upgrade() -> None:
    if not _column_exists(_TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(length=16), nullable=True),
        )
    if not _check_exists(_TABLE, _CHECK):
        op.create_check_constraint(
            _CHECK,
            _TABLE,
            f"{_COLUMN} IN ('moodle', 'ilias')",
        )


def downgrade() -> None:
    if _check_exists(_TABLE, _CHECK):
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    if _column_exists(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
