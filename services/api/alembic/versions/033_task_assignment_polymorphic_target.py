"""Make task_assignments polymorphic so Korrektur can reuse it.

Adds two nullable columns — `target_type` and `target_id` — to allow an
assignment to scope to a specific (annotation | generation) item inside a
task instead of the whole task. Existing rows default to `target_type='task'`
which preserves their meaning (assign the whole task).

Replaces the legacy `unique_task_assignment(task_id, user_id)` constraint
with two partial unique indexes:
  - one task-level assignment per (task, user)         WHERE target_type = 'task'
  - one item-level assignment per (task, user, target) WHERE target_type <> 'task'

Plus a covering index for the Korrektur picker's queue lookup.

Revision ID: 033_task_assignment_polymorphic_target
Revises: 032_add_project_feature_visibility
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "033_task_assignment_polymorphic_target"
down_revision = "032_add_project_feature_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_assignments",
        sa.Column(
            "target_type",
            sa.String(length=50),
            server_default="task",
            nullable=False,
        ),
    )
    op.add_column(
        "task_assignments",
        sa.Column("target_id", sa.String(), nullable=True),
    )

    # Old whole-row unique constraint is too narrow once items exist.
    op.drop_constraint("unique_task_assignment", "task_assignments", type_="unique")

    op.create_index(
        "uniq_task_level_assignment",
        "task_assignments",
        ["task_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("target_type = 'task'"),
    )
    op.create_index(
        "uniq_item_level_assignment",
        "task_assignments",
        ["task_id", "user_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("target_type <> 'task'"),
    )

    # Picker lookup: "is item X assigned to user U on task T?"
    op.create_index(
        "ix_task_assignment_item_lookup",
        "task_assignments",
        ["task_id", "target_type", "target_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_assignment_item_lookup", table_name="task_assignments")
    op.drop_index("uniq_item_level_assignment", table_name="task_assignments")
    op.drop_index("uniq_task_level_assignment", table_name="task_assignments")

    # Re-create the original whole-row uniqueness. Will fail if item-level
    # rows exist — the migration must be cleaned up before downgrade.
    op.create_unique_constraint(
        "unique_task_assignment", "task_assignments", ["task_id", "user_id"]
    )

    op.drop_column("task_assignments", "target_id")
    op.drop_column("task_assignments", "target_type")
