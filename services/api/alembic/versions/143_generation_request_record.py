"""Record what a generation sent, and the first answer of a format retry.

- ``generations.request_record`` (JSONB, nullable): the requests the
  provider client sent for the generation, as the client sent them (the
  first request, then any format retry), with a provider-neutral view of the
  first one (model id, messages, response format, parameters). See
  ``ai_services.request_capture``. NULL for rows written before it existed.
- ``generations.request_sha256`` (String(64), nullable, indexed): SHA-256 of
  the first request's body in canonical JSON, so identical requests can be
  found across runs and imports.
- ``generations.first_response_content`` (Text, nullable): the first answer
  when a format retry asked again; ``response_content`` holds the final one.
- ``generations.retried`` (Boolean, NOT NULL, default FALSE): whether a
  format retry was sent. A constant default, so the column is added without
  a table rewrite.

Pure additive and idempotent: each step is guarded by an inspector check,
so a database built from the models (the test DB) runs it as a no-op.

Revision ID: 143_generation_request_record
Revises: 142_variant_designs
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "143_generation_request_record"
down_revision = "142_variant_designs"
branch_labels = None
depends_on = None

_TABLE = "generations"
_INDEX = "ix_generations_request_sha256"


def _columns() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(_TABLE)}


def _indexes() -> set:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(_TABLE)}


def upgrade() -> None:
    existing = _columns()
    if "request_record" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "request_record", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
        )
    if "request_sha256" not in existing:
        op.add_column(_TABLE, sa.Column("request_sha256", sa.String(64), nullable=True))
    if "first_response_content" not in existing:
        op.add_column(
            _TABLE, sa.Column("first_response_content", sa.Text(), nullable=True)
        )
    if "retried" not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                "retried", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, ["request_sha256"])


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
    existing = _columns()
    for column in (
        "retried",
        "first_response_content",
        "request_sha256",
        "request_record",
    ):
        if column in existing:
            op.drop_column(_TABLE, column)
