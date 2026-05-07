"""Add research_data_consent_accepted_at to users.

Captures the timestamp at which a user accepted the platform's research
data use policy ("I agree to the use of my anonymized data for research").
The column is nullable: community deployments without the extended package
do not collect this consent at signup, and the column stays NULL.

Existing rows are backfilled to NOW() at migration time — pre-existing
users on this deployment have already consented out-of-band (the operator
knows them personally), so capturing the migration timestamp gives us
auditable backfill provenance.

The mandatory-checkbox-at-signup logic and the modal/policy UI live in
the extended package; only the persistence column lives here, per the
open-core split rule that platform owns DB schema for all features.

Revision ID: 045_add_research_data_consent
Revises: 044_backfill_judge_model_id_from_snapshot
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "045_add_research_data_consent"
down_revision = "044_backfill_judge_model_id_from_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "research_data_consent_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE users SET research_data_consent_accepted_at = NOW() "
        "WHERE research_data_consent_accepted_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "research_data_consent_accepted_at")
