"""Migration 111: group memberships and group invitations carry a role.

The shared test DB is built by ``Base.metadata.create_all`` (post-111
shape). ``downgrade()`` restores the booleans, the seeded pre-111 rows are
then upgraded again and the backfill matrix is checked: a group admin becomes
ORG_ADMIN, a plain member gets their ACTIVE org role in the group's org, and
ANNOTATOR without one; a group invitation's ``group_role`` is ORG_ADMIN when
it invited a group admin, else its org role, and NULL without a group. Every
test runs inside the ``test_db`` transaction, which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "111_group_membership_roles.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_111", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _uid() -> str:
    return str(uuid.uuid4())


def _columns(conn, table: str) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns(table)}


def _user(db: Session) -> str:
    from models import User

    uid = _uid()
    db.add(User(id=uid, username=uid, email=f"{uid[:8]}@example.com", name="U"))
    db.flush()
    return uid


def _org(db: Session) -> str:
    from models import Organization

    oid = _uid()
    db.add(Organization(id=oid, name=oid, display_name=oid, slug=f"org-{oid[:8]}"))
    db.flush()
    return oid


def _membership(conn, user_id, org_id, role, active=True):
    conn.execute(
        text(
            "INSERT INTO organization_memberships (id, user_id, organization_id, role, "
            "is_active, joined_at) VALUES (:id, :u, :o, :r, :a, now())"
        ),
        {"id": _uid(), "u": user_id, "o": org_id, "r": role, "a": active},
    )


class TestMigration111Chain:
    def test_revision_chains_after_110(self):
        mig = _load_migration()
        assert mig.revision == "111_group_membership_roles"
        assert mig.down_revision == "110_feature_flag_rollout"

    def test_model_columns(self):
        from models import ImportJob, Invitation, OrganizationGroupMembership

        gm = OrganizationGroupMembership.__table__.columns
        assert "is_group_admin" not in gm
        assert gm["role"].nullable is False
        inv = Invitation.__table__.columns
        assert "invited_as_group_admin" not in inv
        assert inv["group_role"].nullable is True
        assert ImportJob.__table__.columns["organization_group_id"].nullable is True


class TestMigration111UpDown:
    def test_upgrade_is_idempotent_on_current_shape(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        gm = _columns(conn, "organization_group_memberships")
        assert "role" in gm and "is_group_admin" not in gm
        assert gm["role"]["nullable"] is False
        inv = _columns(conn, "invitations")
        assert "group_role" in inv and "invited_as_group_admin" not in inv
        assert "organization_group_id" in _columns(conn, "import_jobs")

    def test_downgrade_then_upgrade_backfills(self, test_db: Session):
        conn = test_db.get_bind()
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            gm_cols = _columns(conn, "organization_group_memberships")
            assert "is_group_admin" in gm_cols and "role" not in gm_cols
            inv_cols = _columns(conn, "invitations")
            assert "invited_as_group_admin" in inv_cols and "group_role" not in inv_cols
            assert "organization_group_id" not in _columns(conn, "import_jobs")

            org, other_org = _org(test_db), _org(test_db)
            group = _uid()
            conn.execute(
                text(
                    "INSERT INTO organization_groups (id, organization_id, name, "
                    "is_active, created_at) VALUES (:id, :o, 'LS', true, now())"
                ),
                {"id": group, "o": org},
            )
            admin_annot = _user(test_db)  # group admin, org ANNOTATOR
            contrib = _user(test_db)  # plain member, org CONTRIBUTOR
            removed = _user(test_db)  # plain member, inactive org ADMIN row
            elsewhere = _user(test_db)  # plain member, CONTRIBUTOR of another org
            _membership(conn, admin_annot, org, "ANNOTATOR")
            _membership(conn, contrib, org, "CONTRIBUTOR")
            _membership(conn, removed, org, "ORG_ADMIN", active=False)
            _membership(conn, elsewhere, other_org, "CONTRIBUTOR")
            for user_id, is_admin in (
                (admin_annot, True),
                (contrib, False),
                (removed, False),
                (elsewhere, False),
            ):
                conn.execute(
                    text(
                        "INSERT INTO organization_group_memberships (id, group_id, "
                        "user_id, is_group_admin, created_at) VALUES (:id, :g, :u, :a, now())"
                    ),
                    {"id": _uid(), "g": group, "u": user_id, "a": is_admin},
                )

            expires = datetime.now(timezone.utc) + timedelta(days=7)
            invites = {}
            for key, group_id, role, as_admin in (
                ("group_admin", group, "CONTRIBUTOR", True),
                ("group_plain", group, "CONTRIBUTOR", False),
                ("org_only", None, "ORG_ADMIN", False),
            ):
                invites[key] = _uid()
                conn.execute(
                    text(
                        "INSERT INTO invitations (id, organization_id, email, role, "
                        "group_id, invited_as_group_admin, token, invited_by, expires_at, "
                        "accepted, created_at) VALUES (:id, :o, :e, :r, :g, :a, :t, :by, "
                        ":x, false, now())"
                    ),
                    {
                        "id": invites[key],
                        "o": org,
                        "e": f"{key}@example.com",
                        "r": role,
                        "g": group_id,
                        "a": as_admin,
                        "t": _uid(),
                        "by": contrib,
                        "x": expires,
                    },
                )

            mig.upgrade()

        roles = dict(
            conn.execute(
                text(
                    "SELECT user_id, role::text FROM organization_group_memberships "
                    "WHERE group_id = :g"
                ),
                {"g": group},
            ).all()
        )
        assert roles == {
            admin_annot: "ORG_ADMIN",
            contrib: "CONTRIBUTOR",
            removed: "ANNOTATOR",
            elsewhere: "ANNOTATOR",
        }
        group_roles = dict(
            conn.execute(
                text("SELECT id, group_role::text FROM invitations WHERE id = ANY(:ids)"),
                {"ids": list(invites.values())},
            ).all()
        )
        assert group_roles == {
            invites["group_admin"]: "ORG_ADMIN",
            invites["group_plain"]: "CONTRIBUTOR",
            invites["org_only"]: None,
        }
        gm_cols = _columns(conn, "organization_group_memberships")
        assert "is_group_admin" not in gm_cols
        assert gm_cols["role"]["nullable"] is False
        assert "invited_as_group_admin" not in _columns(conn, "invitations")
        assert "organization_group_id" in _columns(conn, "import_jobs")

    def test_downgrade_restores_admin_flags(self, test_db: Session):
        conn = test_db.get_bind()
        org = _org(test_db)
        group = _uid()
        conn.execute(
            text(
                "INSERT INTO organization_groups (id, organization_id, name, is_active, "
                "created_at) VALUES (:id, :o, 'LS', true, now())"
            ),
            {"id": group, "o": org},
        )
        admin, contrib = _user(test_db), _user(test_db)
        for user_id, role in ((admin, "ORG_ADMIN"), (contrib, "CONTRIBUTOR")):
            conn.execute(
                text(
                    "INSERT INTO organization_group_memberships (id, group_id, user_id, "
                    "role, created_at) VALUES (:id, :g, :u, :r, now())"
                ),
                {"id": _uid(), "g": group, "u": user_id, "r": role},
            )
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
        flags = dict(
            conn.execute(
                text(
                    "SELECT user_id, is_group_admin FROM organization_group_memberships "
                    "WHERE group_id = :g"
                ),
                {"g": group},
            ).all()
        )
        assert flags == {admin: True, contrib: False}
        with _op_context(conn):
            mig.upgrade()
