"""Variant assignments under the namespaced key ``meta.benger_variant``

The first version of migration 142 reserved ``task.meta.variant`` for the
variant assignment of a task and moved every value users had stored there to
``meta.variant_legacy``. A key that plain names could already hold is the
wrong place for a reserved one, so the assignment now lives in
``meta.benger_variant`` and ``meta.variant`` is plain data again (CORE 2.71);
migration 142 itself was changed to reserve the new key and to rewrite
nothing.

This migration converts a database that ran the first version of 142 (its
trigger function still reads ``meta -> 'variant'``):

- every variant assignment (a ``meta.variant`` the trigger derived a design
  from) moves to ``meta.benger_variant``, so every assignment is kept;
- every ``meta.variant_legacy`` moves back to ``meta.variant`` and the key is
  gone;
- no stored value is overwritten: a row that already holds the target key
  keeps both keys as they are;
- the trigger function ``tasks_variant_sync()`` reads the new key. The
  derived columns, the unique index and the foreign key stay as they are:
  the assignments they were derived from are the same.

The trigger is disabled while the rows move (a move is no edit of the
assignment, and the frozen-design check would otherwise refuse it). A
database that came from main or ran the changed 142 has the new function
already; for it the upgrade only re-creates the function (no row changes).

Downgrade restores what the code before this migration expects: the
assignment back in ``meta.variant``, a plain ``meta.variant`` in
``meta.variant_legacy`` (rows that already hold a ``variant_legacy`` keep
both keys as they are), and the old function.

Revision ID: 151_namespaced_variant_key
Revises: 150_handwriting_ocr_default_on
Create Date: 2026-11-19
"""

from alembic import op
import sqlalchemy as sa

revision = "151_namespaced_variant_key"
down_revision = "150_handwriting_ocr_default_on"
branch_labels = None
depends_on = None

_TRIGGER = "trg_tasks_variant_sync"
_NEW_KEY = "benger_variant"
_OLD_KEY = "variant"
_LEGACY_KEY = "variant_legacy"

# Verbatim copy of project_models.TASKS_VARIANT_FUNCTION (the new key).
_FUNCTION_NEW = """
CREATE OR REPLACE FUNCTION tasks_variant_sync() RETURNS trigger AS $fn$
DECLARE
    new_meta jsonb := NEW.meta::jsonb;
    new_variant jsonb;
    old_variant jsonb;
    design_status text;
    new_status text;
    design_factors jsonb;
    cell jsonb;
BEGIN
    IF jsonb_typeof(new_meta) = 'object' AND jsonb_typeof(new_meta -> 'benger_variant') = 'object' THEN
        new_variant := new_meta -> 'benger_variant';
        NEW.variant_design := new_variant ->> 'design';
        NEW.variant_unit := new_variant ->> 'unit';
        cell := new_variant -> 'factors';
        IF NEW.variant_design IS NOT NULL THEN
            SELECT d.status, d.spec -> 'factors' INTO new_status, design_factors
              FROM variant_designs d
             WHERE d.project_id = NEW.project_id AND d.key = NEW.variant_design
               FOR SHARE;
            IF jsonb_typeof(cell) = 'object' AND jsonb_typeof(design_factors) = 'array' THEN
                SELECT COALESCE(jsonb_object_agg(f ->> 'name', cell -> (f ->> 'name')), '{}'::jsonb)
                  INTO cell
                  FROM jsonb_array_elements(design_factors) AS f
                 WHERE COALESCE(f ->> 'source', 'task') = 'task'
                   AND COALESCE(f ->> 'varies', 'within_unit') = 'within_unit'
                   AND cell ? (f ->> 'name');
            END IF;
        END IF;
        NEW.variant_cell := cell;
    ELSE
        NEW.variant_design := NULL;
        NEW.variant_unit := NULL;
        NEW.variant_cell := NULL;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.variant_design IS NOT NULL THEN
        SELECT d.status INTO design_status FROM variant_designs d
         WHERE d.project_id = OLD.project_id AND d.key = OLD.variant_design
           FOR SHARE;
        IF design_status = 'frozen' THEN
            IF jsonb_typeof(OLD.meta::jsonb) = 'object' THEN
                old_variant := OLD.meta::jsonb -> 'benger_variant';
            END IF;
            IF NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.data::jsonb IS DISTINCT FROM OLD.data::jsonb
               OR new_variant IS DISTINCT FROM old_variant THEN
                RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                    MESSAGE = 'variant_design_frozen: task ' || OLD.id
                        || ' belongs to the frozen variant design ' || OLD.variant_design
                        || '; its data and meta.benger_variant are read-only';
            END IF;
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.variant_design IS NOT NULL AND (
        TG_OP = 'INSERT'
        OR NEW.variant_design IS DISTINCT FROM OLD.variant_design
        OR NEW.project_id IS DISTINCT FROM OLD.project_id
    ) THEN
        IF new_status = 'frozen' THEN
            RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                MESSAGE = 'variant_design_frozen: the variant design ' || NEW.variant_design
                    || ' is frozen and takes no new tasks';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql
"""

# The first version of 142 (the old key), for the downgrade.
_FUNCTION_OLD = _FUNCTION_NEW.replace("'benger_variant'", "'variant'").replace(
    "meta.benger_variant are read-only", "meta.variant are read-only"
)


def _move_key(source: str, target: str, where: str = "") -> str:
    """UPDATE moving ``meta.<source>`` to ``meta.<target>``; a row that
    already holds ``target`` is left alone, so no stored value is ever
    overwritten. ``where`` narrows the rows further."""
    return f"""
UPDATE tasks
   SET meta = ((meta::jsonb - '{source}')
               || jsonb_build_object('{target}', meta::jsonb -> '{source}'))::json
 WHERE json_typeof(meta) = 'object' AND (meta -> '{source}') IS NOT NULL
   AND (meta -> '{target}') IS NULL{where}
"""


def _function_source():
    return (
        op.get_bind()
        .execute(sa.text("SELECT prosrc FROM pg_proc WHERE proname = 'tasks_variant_sync'"))
        .scalar()
    )


def _has_trigger() -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_trigger WHERE tgname = :n"), {"n": _TRIGGER})
        .scalar()
    )


def _reads_old_key(source) -> bool:
    return bool(source) and f"'{_NEW_KEY}'" not in source


def _with_trigger_disabled(statements) -> None:
    trigger = _has_trigger()
    if trigger:
        op.execute(f"ALTER TABLE tasks DISABLE TRIGGER {_TRIGGER}")
    for statement in statements:
        op.execute(statement)
    if trigger:
        op.execute(f"ALTER TABLE tasks ENABLE TRIGGER {_TRIGGER}")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    source = _function_source()
    if source is None:
        return
    if not _reads_old_key(source):
        op.execute(_FUNCTION_NEW)
        return
    _with_trigger_disabled(
        [
            _FUNCTION_NEW,
            # An assignment is a meta.variant the trigger derived a design
            # from (the foreign key guarantees the design exists).
            _move_key(_OLD_KEY, _NEW_KEY, " AND variant_design IS NOT NULL"),
            _move_key(_LEGACY_KEY, _OLD_KEY),
        ]
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    source = _function_source()
    if source is None or _reads_old_key(source):
        return
    _with_trigger_disabled(
        [
            _FUNCTION_OLD,
            _move_key(_OLD_KEY, _LEGACY_KEY),
            # A row whose plain meta.variant could not move keeps it; its
            # assignment then stays under the new key.
            _move_key(_NEW_KEY, _OLD_KEY),
        ]
    )
