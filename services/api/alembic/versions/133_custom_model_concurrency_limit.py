"""Concurrency limit of a custom model endpoint.

- ``llm_models.max_concurrent_requests`` (Integer, nullable): how many
  requests generation runs keep in flight at once against a custom (BYOM)
  model's endpoint. NULL means the worker default
  (``generation/endpoint_slots.py``), which every existing row keeps.
- ``ck_llm_models_max_concurrent_requests_positive``: NULL or at least 1.

Pure additive and idempotent: column and constraint are guarded by inspector
checks, so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 133_custom_model_concurrency_limit
Revises: 132_refresh_token_rotation
Create Date: 2026-11-14
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "133_custom_model_concurrency_limit"
down_revision = "132_refresh_token_rotation"
branch_labels = None
depends_on = None

_TABLE = "llm_models"
_COLUMN = "max_concurrent_requests"
_CHECK = "ck_llm_models_max_concurrent_requests_positive"


def _columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def _checks() -> set:
    return {ck["name"] for ck in inspect(op.get_bind()).get_check_constraints(_TABLE)}


def upgrade() -> None:
    if _COLUMN not in _columns():
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))
    if _CHECK not in _checks():
        op.create_check_constraint(
            _CHECK, _TABLE, f"{_COLUMN} IS NULL OR {_COLUMN} >= 1"
        )


def downgrade() -> None:
    if _CHECK in _checks():
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    if _COLUMN in _columns():
        op.drop_column(_TABLE, _COLUMN)
