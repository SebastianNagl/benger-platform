"""Request timeout of a custom model endpoint.

- ``llm_models.request_timeout_seconds`` (Integer, nullable): how many seconds
  one HTTP attempt against a custom (BYOM) model's endpoint may take. The
  completion is not streamed, so the whole answer of a reasoning model has to
  arrive within it. NULL means the default of 300 s
  (``ai_services/openai_compatible_service.py``), which every existing row
  keeps, so behavior is unchanged until an owner sets a value.
- ``ck_llm_models_request_timeout_seconds_range``: NULL or 30-1500. The upper
  bound stays below the generation job's 1,800 s Celery soft limit.

Pure additive and idempotent: column and constraint are guarded by inspector
checks, so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 135_custom_model_request_timeout
Revises: 134_pending_email_change
Create Date: 2026-11-16
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "135_custom_model_request_timeout"
down_revision = "134_pending_email_change"
branch_labels = None
depends_on = None

_TABLE = "llm_models"
_COLUMN = "request_timeout_seconds"
_CHECK = "ck_llm_models_request_timeout_seconds_range"


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
            _CHECK, _TABLE, f"{_COLUMN} IS NULL OR {_COLUMN} BETWEEN 30 AND 1500"
        )


def downgrade() -> None:
    if _CHECK in _checks():
        op.drop_constraint(_CHECK, _TABLE, type_="check")
    if _COLUMN in _columns():
        op.drop_column(_TABLE, _COLUMN)
