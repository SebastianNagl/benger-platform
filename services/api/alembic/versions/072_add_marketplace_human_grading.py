"""add vendor human-grading to the marketplace

Vendors can offer human grading of student exam attempts as a separately-priced
add-on. The actual grading reuses the existing Korrektur human-evaluation
pipeline (a human ``TaskEvaluation`` under the singleton human ``EvaluationRun``);
this migration only adds the marketplace-side schema:

- ``marketplace_listings`` gains ``grading_mode`` (ai|human|both), the add-on
  price ``human_grading_price_cents`` and the credit count ``human_grading_quantity``.
- ``marketplace_orders`` gains ``product_type`` (exam_access|human_grading).
- ``marketplace_grading_credits``: the student's HG wallet — one row per
  (user, project); buying the add-on increments ``total_credits``, requesting a
  grade increments ``used_credits``.
- ``marketplace_grading_requests``: one row per attempt submitted for human
  grading (unique ``annotation_id``); the vendor correctors' queue item, linked
  to the resulting ``task_evaluation`` once graded.

Idempotent — guards on table/column/index existence; safe to re-run.

Revision ID: 072_add_marketplace_human_grading
Revises: 071_add_marketplace_tables
Create Date: 2026-06-28
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "072_add_marketplace_human_grading"
down_revision = "071_add_marketplace_tables"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return name in {ix["name"] for ix in insp.get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns: list) -> None:
    if not _index_exists(table, name):
        op.create_index(name, table, columns)


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if not _column_exists(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    # --- listing: grading mode + human-grading add-on price/quantity --------- #
    _add_column_if_missing(
        "marketplace_listings",
        sa.Column(
            "grading_mode", sa.String(length=16), nullable=False, server_default="ai"
        ),
    )
    _add_column_if_missing(
        "marketplace_listings",
        sa.Column("human_grading_price_cents", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "marketplace_listings",
        sa.Column(
            "human_grading_quantity", sa.Integer(), nullable=False, server_default="1"
        ),
    )

    # --- order: which product was bought ------------------------------------ #
    _add_column_if_missing(
        "marketplace_orders",
        sa.Column(
            "product_type",
            sa.String(),
            nullable=False,
            server_default="exam_access",
        ),
    )

    # --- grading credits (the student's HG wallet) -------------------------- #
    if not _table_exists("marketplace_grading_credits"):
        op.create_table(
            "marketplace_grading_credits",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "vendor_org_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "listing_id",
                sa.String(),
                sa.ForeignKey("marketplace_listings.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("total_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "user_id",
                "project_id",
                name="uq_marketplace_grading_credit_user_project",
            ),
        )
    _create_index_if_missing(
        "ix_marketplace_grading_credits_user", "marketplace_grading_credits", ["user_id"]
    )
    _create_index_if_missing(
        "ix_marketplace_grading_credits_project",
        "marketplace_grading_credits",
        ["project_id"],
    )

    # --- grading requests (the vendor correctors' queue) -------------------- #
    if not _table_exists("marketplace_grading_requests"):
        op.create_table(
            "marketplace_grading_requests",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.String(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "annotation_id",
                sa.String(),
                sa.ForeignKey("annotations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "vendor_org_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "listing_id",
                sa.String(),
                sa.ForeignKey("marketplace_listings.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "status", sa.String(length=16), nullable=False, server_default="pending"
            ),
            sa.Column(
                "assigned_grader_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "task_evaluation_id",
                sa.String(),
                sa.ForeignKey("task_evaluations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "annotation_id", name="uq_marketplace_grading_request_annotation"
            ),
        )
    _create_index_if_missing(
        "ix_marketplace_grading_requests_vendor_status",
        "marketplace_grading_requests",
        ["vendor_org_id", "status"],
    )
    _create_index_if_missing(
        "ix_marketplace_grading_requests_user",
        "marketplace_grading_requests",
        ["user_id"],
    )


def downgrade() -> None:
    if _table_exists("marketplace_grading_requests"):
        op.drop_table("marketplace_grading_requests")
    if _table_exists("marketplace_grading_credits"):
        op.drop_table("marketplace_grading_credits")
    if _column_exists("marketplace_orders", "product_type"):
        op.drop_column("marketplace_orders", "product_type")
    for col in ("human_grading_quantity", "human_grading_price_cents", "grading_mode"):
        if _column_exists("marketplace_listings", col):
            op.drop_column("marketplace_listings", col)
