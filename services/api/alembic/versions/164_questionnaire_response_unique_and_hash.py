"""One questionnaire response per annotation, and the config it answered.

- ``post_annotation_responses.annotation_id`` gets a unique index
  (``ix_post_annotation_responses_annotation_id``, the name the model
  declares) in place of the non-unique ``ix_par_annotation_id`` from 015.
  Until now the submit route's duplicate check was the only guard, so two
  submits racing past it could store two responses for one annotation.
- ``post_annotation_responses.config_hash`` (String(64), nullable): the
  SHA-256 of the questionnaire config a response answered, written by the
  submit route. NULL for responses stored before this revision.

A database that already holds duplicate responses keeps them: the unique
index is then not created (a warning names the count) and the route's check
stays the guard, since picking which duplicate to delete is not a migration's
call. Idempotent: every step is guarded by an inspector check, so a database
built from the models (the test DB) runs it as a no-op.

Revision ID: 164_questionnaire_response_unique_and_hash
Revises: 163_llm_model_display_order
Create Date: 2026-11-27
"""

import logging

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa

revision = "164_questionnaire_response_unique_and_hash"
down_revision = "163_llm_model_display_order"
branch_labels = None
depends_on = None

_TABLE = "post_annotation_responses"
_COLUMN = "config_hash"
_UNIQUE_INDEX = "ix_post_annotation_responses_annotation_id"
_OLD_INDEX = "ix_par_annotation_id"

logger = logging.getLogger("alembic.runtime.migration")


def _indexes() -> dict:
    insp = inspect(op.get_bind())
    return {ix["name"]: ix for ix in insp.get_indexes(_TABLE)}


def _table_exists() -> bool:
    return _TABLE in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists():
        return

    columns = {col["name"] for col in inspect(op.get_bind()).get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=64), nullable=True))

    indexes = _indexes()
    if indexes.get(_UNIQUE_INDEX, {}).get("unique"):
        return

    duplicates = op.get_bind().execute(
        sa.text(
            f"SELECT count(*) FROM (SELECT annotation_id FROM {_TABLE} "
            "GROUP BY annotation_id HAVING count(*) > 1) d"
        )
    ).scalar()
    if duplicates:
        logger.warning(
            "%s: %d annotations have more than one questionnaire response; "
            "the unique index %s is not created until they are resolved",
            _TABLE,
            duplicates,
            _UNIQUE_INDEX,
        )
        return

    # A non-unique index of the model's name (a DB built from the old model)
    # gives way to the unique one, as does the 015 index it replaces.
    for name in (_UNIQUE_INDEX, _OLD_INDEX):
        if name in indexes:
            op.drop_index(name, table_name=_TABLE)
    op.create_index(_UNIQUE_INDEX, _TABLE, ["annotation_id"], unique=True)


def downgrade() -> None:
    if not _table_exists():
        return
    indexes = _indexes()
    if _UNIQUE_INDEX in indexes:
        op.drop_index(_UNIQUE_INDEX, table_name=_TABLE)
    if _OLD_INDEX not in indexes:
        op.create_index(_OLD_INDEX, _TABLE, ["annotation_id"])
    columns = {col["name"] for col in inspect(op.get_bind()).get_columns(_TABLE)}
    if _COLUMN in columns:
        op.drop_column(_TABLE, _COLUMN)
