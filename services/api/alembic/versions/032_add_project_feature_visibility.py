"""Add per-project feature-visibility flags.

Three booleans on `projects` controlling which top-level configuration
cards render on the project detail page: annotation, generation, evaluation.
Pure UI gate today (data and endpoints stay untouched when flipped off).

All existing projects get TRUE for each so the page looks the same after
the migration. Wizard maps `wizardData.features.*` checkboxes to these
columns at creation.

Revision ID: 032_add_project_feature_visibility
Revises: 031_rename_feedback_to_korrektur
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "032_add_project_feature_visibility"
down_revision = "031_rename_feedback_to_korrektur"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "enable_annotation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "enable_generation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "enable_evaluation",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "enable_evaluation")
    op.drop_column("projects", "enable_generation")
    op.drop_column("projects", "enable_annotation")
