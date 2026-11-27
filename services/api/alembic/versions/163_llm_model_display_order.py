"""Display order of the model catalog.

- ``llm_models.display_order`` (Integer, nullable): the position of an
  official model in ``seeds/llm_models.yaml``. The seed writes it on every
  run, and every model list a user picks from orders by it
  (``models.llm_model_display_order``), so the pickers show the catalog
  grouped by provider instead of in storage order. NULL for custom models,
  which list after the catalog, and for rows until the next seed fills it.

Pure additive and idempotent: the column is guarded by an inspector check,
so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 163_llm_model_display_order
Revises: 162_retired_model_references_everywhere
Create Date: 2026-11-27
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "163_llm_model_display_order"
down_revision = "162_retired_model_references_everywhere"
branch_labels = None
depends_on = None

_TABLE = "llm_models"
_COLUMN = "display_order"


def _columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def upgrade() -> None:
    if _COLUMN not in _columns():
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if _COLUMN in _columns():
        op.drop_column(_TABLE, _COLUMN)
