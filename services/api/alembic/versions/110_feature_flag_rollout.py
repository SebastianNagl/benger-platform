"""Feature flags: state + allowlist targets, core flags retired

The feature flag system moves to the extended edition, which owns the flag
registry, the evaluation rules and the admin API. The platform keeps only the
tables:

* ``feature_flags.state`` (``off`` | ``everyone`` | ``allowlist``) replaces
  the boolean ``is_enabled``; the unused ``configuration`` column is dropped
  and ``created_by`` becomes nullable (registry-seeded rows have no creator,
  and deleting a user nulls it instead of blocking the delete).
* ``feature_flag_targets`` holds the allowlist: one row per user or
  organization a flag in ``allowlist`` state applies to.
* The flags that gated core pages (``data``, ``generations``,
  ``evaluations``, ``reports``, ``how-to``, ``leaderboards``) and the unread
  ``ORG_API_KEYS`` / ``API_MAIL_SERVICE`` rows are deleted; those pages are
  core now and always on.

Every step is guarded, so a re-run is a no-op.

Revision ID: 110_feature_flag_rollout
Revises: 109_project_seb_settings
Create Date: 2026-10-02
"""

from sqlalchemy import inspect

from alembic import op
import sqlalchemy as sa


revision = "110_feature_flag_rollout"
down_revision = "109_project_seb_settings"
branch_labels = None
depends_on = None

_RETIRED_FLAGS = (
    "data",
    "generations",
    "evaluations",
    "reports",
    "how-to",
    "leaderboards",
    "ORG_API_KEYS",
    "API_MAIL_SERVICE",
)


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _created_by_fks() -> list:
    return [
        fk["name"]
        for fk in inspect(op.get_bind()).get_foreign_keys("feature_flags")
        if fk["constrained_columns"] == ["created_by"]
    ]


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    bind = op.get_bind()

    bind.execute(
        sa.text("DELETE FROM feature_flags WHERE name = ANY(:names)"),
        {"names": list(_RETIRED_FLAGS)},
    )

    cols = _columns("feature_flags")
    if "state" not in cols:
        op.add_column(
            "feature_flags",
            sa.Column("state", sa.String(16), nullable=False, server_default="off"),
        )
        if "is_enabled" in cols:
            op.execute(
                "UPDATE feature_flags SET state = "
                "CASE WHEN is_enabled THEN 'everyone' ELSE 'off' END"
            )
        op.create_check_constraint(
            "ck_feature_flags_state",
            "feature_flags",
            "state IN ('off', 'everyone', 'allowlist')",
        )
    if "is_enabled" in cols:
        op.drop_column("feature_flags", "is_enabled")
    if "configuration" in cols:
        op.drop_column("feature_flags", "configuration")

    op.alter_column("feature_flags", "created_by", nullable=True)
    for name in _created_by_fks():
        op.drop_constraint(name, "feature_flags", type_="foreignkey")
    op.create_foreign_key(
        "feature_flags_created_by_fkey",
        "feature_flags",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    if not inspect(bind).has_table("feature_flag_targets"):
        op.create_table(
            "feature_flag_targets",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "flag_id",
                sa.String(),
                sa.ForeignKey("feature_flags.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "(user_id IS NULL) <> (organization_id IS NULL)",
                name="ck_feature_flag_targets_one_target",
            ),
            sa.UniqueConstraint(
                "flag_id", "user_id", name="uq_feature_flag_targets_user"
            ),
            sa.UniqueConstraint(
                "flag_id", "organization_id", name="uq_feature_flag_targets_org"
            ),
        )
        op.create_index(
            "ix_feature_flag_targets_flag_id", "feature_flag_targets", ["flag_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("feature_flag_targets"):
        op.drop_table("feature_flag_targets")

    cols = _columns("feature_flags")
    if "configuration" not in cols:
        op.add_column("feature_flags", sa.Column("configuration", sa.JSON(), nullable=True))
    if "is_enabled" not in cols:
        op.add_column(
            "feature_flags",
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        if "state" in cols:
            op.execute("UPDATE feature_flags SET is_enabled = (state <> 'off')")
    if "state" in cols:
        op.drop_constraint("ck_feature_flags_state", "feature_flags", type_="check")
        op.drop_column("feature_flags", "state")

    for name in _created_by_fks():
        op.drop_constraint(name, "feature_flags", type_="foreignkey")
    op.create_foreign_key(
        "feature_flags_created_by_fkey", "feature_flags", "users", ["created_by"], ["id"]
    )
    # created_by stays nullable: rows seeded without a creator cannot be
    # given one back. The retired core flag rows are not restored.
