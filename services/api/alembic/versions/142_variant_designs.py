"""Variant designs: ``variant_designs`` and the derived variant columns of ``tasks``

A variant experiment runs the same item in several controlled variants and
compares the answers. Its design is now a first-class, freezable object,
while each task's place in it stays in ``task.meta.variant`` (CORE 2.57):

- New table ``variant_designs``: one row per design of a project (``key``
  unique per project), the spec (JSONB, ``schemas/variant_design.schema.json``),
  ``version``, ``status`` draft|frozen, ``content_hash``, ``frozen_at/by``,
  ``provenance``. Cascades with the project.
- ``tasks.variant_design`` / ``variant_unit`` / ``variant_cell``: derived from
  ``meta.variant`` by the trigger ``trg_tasks_variant_sync`` on every insert
  and on every update of ``meta``, ``data``, ``project_id`` or the columns
  themselves (plain nullable columns, so adding them does not rewrite the
  table; a stored generated column would). The same trigger refuses edits
  of ``data`` and ``meta.variant`` of a task whose design is frozen, and new
  tasks in a frozen design (SQLSTATE 23001, message ``variant_design_frozen``).
- ``uq_tasks_variant_cell``: one task per (project, design, unit, cell),
  partial on ``variant_design IS NOT NULL``. The cell is the design cell, the
  factors of ``meta.variant.factors`` the design declares as within-unit task
  factors; it is jsonb, so reordered keys compare equal.
- ``fk_tasks_variant_design``: (project_id, variant_design) references
  ``variant_designs (project_id, key)``, not deferrable (a deferred key would
  leave a pending trigger event per inserted task, which breaks a later
  ALTER TABLE tasks in the same transaction). Added NOT VALID, then
  validated, so the check does not block writes.

``meta.variant`` is a reserved key from now on. Rows that already carry one
(written before this feature, with no design behind it) get it moved to
``meta.variant_legacy`` before the trigger exists, so no stored row breaks the
new key or the foreign key. That rewrite goes through jsonb and therefore
reorders the keys of those rows' meta.

Idempotent: every step is guarded, so a database built from the models (the
test DB) runs it as a no-op.

Revision ID: 142_variant_designs
Revises: 141_project_wizard_drafts
Create Date: 2026-11-18
"""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa

revision = "142_variant_designs"
down_revision = "141_project_wizard_drafts"
branch_labels = None
depends_on = None

_DESIGNS = "variant_designs"
_FUNCTION = "tasks_variant_sync"
_TRIGGER = "trg_tasks_variant_sync"
_INDEX = "uq_tasks_variant_cell"
_FK = "fk_tasks_variant_design"

# Verbatim copies of project_models.TASKS_VARIANT_FUNCTION / _TRIGGER.
_VARIANT_FUNCTION = """
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
    IF jsonb_typeof(new_meta) = 'object' AND jsonb_typeof(new_meta -> 'variant') = 'object' THEN
        new_variant := new_meta -> 'variant';
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
                old_variant := OLD.meta::jsonb -> 'variant';
            END IF;
            IF NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.data::jsonb IS DISTINCT FROM OLD.data::jsonb
               OR new_variant IS DISTINCT FROM old_variant THEN
                RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                    MESSAGE = 'variant_design_frozen: task ' || OLD.id
                        || ' belongs to the frozen variant design ' || OLD.variant_design
                        || '; its data and meta.variant are read-only';
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
_VARIANT_TRIGGER = """
CREATE OR REPLACE TRIGGER trg_tasks_variant_sync
BEFORE INSERT OR UPDATE OF meta, data, project_id, variant_design, variant_unit, variant_cell
ON tasks
FOR EACH ROW EXECUTE FUNCTION tasks_variant_sync()
"""

# Assignments stored before the key was reserved (no design behind them).
_MOVE_LEGACY_VARIANTS = """
UPDATE tasks
   SET meta = ((meta::jsonb - 'variant')
               || jsonb_build_object('variant_legacy', meta::jsonb -> 'variant'))::json
 WHERE json_typeof(meta) = 'object' AND (meta -> 'variant') IS NOT NULL
"""


def _insp():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _insp().get_indexes(table)}


def _has_fk(table: str, name: str) -> bool:
    return name in {fk["name"] for fk in _insp().get_foreign_keys(table)}


def _has_trigger(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_trigger WHERE tgname = :n"), {"n": name})
        .scalar()
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    if not _has_table(_DESIGNS):
        op.create_table(
            _DESIGNS,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "project_id", sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("key", sa.String(100), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("spec", postgresql.JSONB(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("content_hash", sa.String(64), nullable=True),
            sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "frozen_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("provenance", postgresql.JSONB(), nullable=True),
            sa.Column(
                "created_by", sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=True,
            ),
            sa.UniqueConstraint("project_id", "key", name="uq_variant_designs_project_key"),
            sa.CheckConstraint(
                "status IN ('draft', 'frozen')", name="ck_variant_designs_status"
            ),
            sa.CheckConstraint(
                "(status = 'frozen') = (content_hash IS NOT NULL AND frozen_at IS NOT NULL)",
                name="ck_variant_designs_frozen_hash",
            ),
        )
    if not _has_index(_DESIGNS, "ix_variant_designs_project_id"):
        op.create_index("ix_variant_designs_project_id", _DESIGNS, ["project_id"])

    if not _has_column("tasks", "variant_design"):
        # First run: move assignments written before the key was reserved.
        op.execute(_MOVE_LEGACY_VARIANTS)
        op.add_column("tasks", sa.Column("variant_design", sa.String(100), nullable=True))
    if not _has_column("tasks", "variant_unit"):
        op.add_column("tasks", sa.Column("variant_unit", sa.Text(), nullable=True))
    if not _has_column("tasks", "variant_cell"):
        op.add_column("tasks", sa.Column("variant_cell", postgresql.JSONB(), nullable=True))

    op.execute(_VARIANT_FUNCTION)
    if not _has_trigger(_TRIGGER):
        op.execute(_VARIANT_TRIGGER)

    if not _has_index("tasks", _INDEX):
        op.create_index(
            _INDEX,
            "tasks",
            ["project_id", "variant_design", "variant_unit", "variant_cell"],
            unique=True,
            postgresql_where=sa.text("variant_design IS NOT NULL"),
        )
    if not _has_fk("tasks", _FK):
        op.execute(
            f"ALTER TABLE tasks ADD CONSTRAINT {_FK} "
            "FOREIGN KEY (project_id, variant_design) "
            "REFERENCES variant_designs (project_id, key) NOT VALID"
        )
        op.execute(f"ALTER TABLE tasks VALIDATE CONSTRAINT {_FK}")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _has_fk("tasks", _FK):
        op.drop_constraint(_FK, "tasks", type_="foreignkey")
    if _has_index("tasks", _INDEX):
        op.drop_index(_INDEX, table_name="tasks")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON tasks")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    for column in ("variant_cell", "variant_unit", "variant_design"):
        if _has_column("tasks", column):
            op.drop_column("tasks", column)
    if _has_table(_DESIGNS):
        op.drop_table(_DESIGNS)
