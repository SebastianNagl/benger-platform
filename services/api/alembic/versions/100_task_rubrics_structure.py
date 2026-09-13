"""task_rubrics: hierarchical structure, per-rubric Notenschlüssel, float totals

A Bewertungsbogen (per-task grading rubric) becomes an ordered OUTLINE:
``structure`` (JSONB, ``{"version": 1, "nodes": [...]}``) holds sections and
scored steps with labels, hints, Schwerpunkt markers and section notes; the
flat ``criteria`` dict the LLM judge and the human grading form consume is
regenerated from it on every write (legacy rows keep ``structure = NULL``
and their hand-written criteria). ``grade_scale`` (JSONB) is an optional
per-rubric Notenschlüssel (18 thresholds + rounding + pass grade); NULL means
the default Falllösung table scaled to the rubric total.

``total_points`` changes Integer → Float: Bewertungseinheiten are awarded in
half points (0.5 BE steps), so a sheet may total 72.5. Halves are exactly
representable in a double; Numeric would leak Decimal into the JSON
serializers.

Idempotent — guards on column existence and current column type; safe to
re-run. Downgrade drops the two columns and rounds totals back to integers.

Revision ID: 100_task_rubrics_structure
Revises: 099_add_grading_feedback
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "100_task_rubrics_structure"
down_revision = "099_add_grading_feedback"
branch_labels = None
depends_on = None

TABLE = "task_rubrics"


def _columns(table: str) -> dict:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return {}
    return {c["name"]: c for c in insp.get_columns(table)}


def _is_float_type(column: dict) -> bool:
    return isinstance(column.get("type"), (sa.Float, sa.Numeric))


def upgrade() -> None:
    columns = _columns(TABLE)
    if not columns:
        return  # table created by a later create_all / missing on this deployment

    if "structure" not in columns:
        op.add_column(TABLE, sa.Column("structure", JSONB(), nullable=True))
    if "grade_scale" not in columns:
        op.add_column(TABLE, sa.Column("grade_scale", JSONB(), nullable=True))

    total = columns.get("total_points")
    if total is not None and not _is_float_type(total):
        op.alter_column(
            TABLE,
            "total_points",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
            existing_server_default="100",
            postgresql_using="total_points::double precision",
        )


def downgrade() -> None:
    columns = _columns(TABLE)
    if not columns:
        return

    total = columns.get("total_points")
    if total is not None and _is_float_type(total):
        op.alter_column(
            TABLE,
            "total_points",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
            existing_server_default="100",
            postgresql_using="round(total_points)::integer",
        )
    if "grade_scale" in columns:
        op.drop_column(TABLE, "grade_scale")
    if "structure" in columns:
        op.drop_column(TABLE, "structure")
