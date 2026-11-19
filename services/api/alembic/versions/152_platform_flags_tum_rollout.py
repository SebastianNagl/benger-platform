"""Roll the platform flags of CORE 2.75 out to the TUM organization

The flags ``variant_experiments``, ``compliance_records`` and
``report_paper`` are registered with the default state ``off``. On
production they start as an allowlist with the TUM organization as their
only target, so the pilot gets the features on deploy while every other
user keeps the platform as it was.

For each of the three flags whose row does not exist yet (a flag nobody has
set: the registry sync creates missing rows only after the migrations, and
an admin's change always goes through an existing row), the upgrade creates
the row in state ``allowlist`` with the TUM organization as target, when
that organization exists: the production organization by its id, else an
organization named ``TUM`` (development and test seeds). A flag whose row
exists is left exactly as it is, and without a TUM organization nothing is
written; the registry sync then creates the rows at ``off``. The registry
sync later fills in the descriptions and never changes a row's state or
targets. Running the upgrade again changes nothing.

The downgrade leaves the rows alone: after the upgrade an admin may have
changed them, and the code before this migration ignores flags it does not
register.

Revision ID: 152_platform_flags_tum_rollout
Revises: 151_namespaced_variant_key
Create Date: 2026-11-19
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "152_platform_flags_tum_rollout"
down_revision = "151_namespaced_variant_key"
branch_labels = None
depends_on = None

FLAGS = ("variant_experiments", "compliance_records", "report_paper")
TUM_ORGANIZATION_ID = "a22cbcfa-a5ab-4c7e-b93f-dd5585906a8b"
TUM_NAME = "TUM"


def _tum_organization_id(conn):
    return conn.execute(
        sa.text(
            "SELECT id FROM organizations WHERE id = :id OR name = :name "
            "ORDER BY (id = :id) DESC, created_at, id LIMIT 1"
        ),
        {"id": TUM_ORGANIZATION_ID, "name": TUM_NAME},
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    organization_id = _tum_organization_id(conn)
    if organization_id is None:
        return
    for name in FLAGS:
        flag_id = conn.execute(
            sa.text(
                "INSERT INTO feature_flags (id, name, state, created_at) "
                "VALUES (:id, :name, 'allowlist', now()) "
                "ON CONFLICT (name) DO NOTHING RETURNING id"
            ),
            {"id": str(uuid.uuid4()), "name": name},
        ).scalar()
        if flag_id is None:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO feature_flag_targets (id, flag_id, organization_id, created_at) "
                "VALUES (:id, :flag_id, :organization_id, now())"
            ),
            {"id": str(uuid.uuid4()), "flag_id": flag_id, "organization_id": organization_id},
        )


def downgrade() -> None:
    pass
