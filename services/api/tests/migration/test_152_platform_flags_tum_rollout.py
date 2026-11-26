"""Migration 152: the platform flags of CORE 2.75 start as an allowlist with
the TUM organization on deploy.

A flag without a row (never set) becomes ``allowlist`` with TUM as its only
target; a flag an admin already set keeps its state and targets; without a
TUM organization nothing is written; a second run changes nothing. Each test
starts from a database without rows for the three flags, as production is
before this deploy.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

VERSIONS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
)
NAME = "152_platform_flags_tum_rollout"
FLAGS = ("variant_experiments", "compliance_records", "report_paper")
PRODUCTION_TUM_ID = "a22cbcfa-a5ab-4c7e-b93f-dd5585906a8b"


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{NAME}", os.path.join(VERSIONS, f"{NAME}.py"))
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


def _upgrade(conn):
    with _op_context(conn):
        _load().upgrade()


def _fresh(conn):
    """No rows for the three flags and no organization TUM would match."""
    conn.execute(text("DELETE FROM feature_flags WHERE name = ANY(:n)"), {"n": list(FLAGS)})
    conn.execute(
        text("UPDATE organizations SET name = name || ' (renamed)' WHERE name = 'TUM'")
    )
    conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": PRODUCTION_TUM_ID})


def _organization(conn, name: str, org_id: str | None = None) -> str:
    org_id = org_id or str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO organizations (id, name, display_name, slug, is_active, created_at) "
            "VALUES (:id, :name, :name, :slug, true, now())"
        ),
        {"id": org_id, "name": name, "slug": f"{name.lower()}-{org_id[:8]}"},
    )
    return org_id


def _flags(conn):
    rows = conn.execute(
        text(
            "SELECT f.name, f.state, t.organization_id, t.user_id FROM feature_flags f "
            "LEFT JOIN feature_flag_targets t ON t.flag_id = f.id WHERE f.name = ANY(:n) "
            "ORDER BY f.name, t.organization_id"
        ),
        {"n": list(FLAGS)},
    ).all()
    out: dict = {}
    for name, state, organization_id, user_id in rows:
        entry = out.setdefault(name, {"state": state, "targets": []})
        if organization_id or user_id:
            entry["targets"].append(organization_id or f"user:{user_id}")
    return out


class TestMigration152:
    def test_revision_chains_after_151(self):
        mig = _load()
        assert mig.revision == NAME
        assert mig.down_revision == "151_namespaced_variant_key"
        assert set(mig.FLAGS) == set(FLAGS)

    def test_the_flags_it_rolls_out_are_the_registered_platform_flags(self):
        from feature_flags import registry

        # Flags registered after this migration (bug_reports) are not part of
        # its rollout: they start off everywhere until an admin switches them.
        later = {registry.BUG_REPORTS}
        platform = {d.name for d in registry.platform_flags()} - {registry.PUBLIC_API} - later
        assert platform == set(FLAGS)
        for name in FLAGS:
            assert registry.flag(name).default_state == registry.STATE_OFF

    def test_without_tum_nothing_is_written(self, test_db: Session):
        conn = test_db.get_bind()
        _fresh(conn)
        _organization(conn, "Other")
        _upgrade(conn)
        assert _flags(conn) == {}

    def test_with_the_tum_seed_organization_all_flags_are_allowlisted_for_it(self, test_db: Session):
        conn = test_db.get_bind()
        _fresh(conn)
        _organization(conn, "Other")
        tum = _organization(conn, "TUM")
        _upgrade(conn)
        assert _flags(conn) == {name: {"state": "allowlist", "targets": [tum]} for name in FLAGS}

    def test_the_production_tum_organization_wins_over_a_namesake(self, test_db: Session):
        conn = test_db.get_bind()
        _fresh(conn)
        _organization(conn, "TUM")
        production = _organization(conn, "Technische Universität München", PRODUCTION_TUM_ID)
        _upgrade(conn)
        assert _flags(conn) == {
            name: {"state": "allowlist", "targets": [production]} for name in FLAGS
        }

    def test_a_flag_an_admin_already_set_is_left_alone(self, test_db: Session, test_users):
        conn = test_db.get_bind()
        _fresh(conn)
        tum = _organization(conn, "TUM")
        other = _organization(conn, "Other")
        flag_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO feature_flags (id, name, state, created_by, created_at) "
                "VALUES (:id, 'report_paper', 'allowlist', :u, now())"
            ),
            {"id": flag_id, "u": test_users[0].id},
        )
        conn.execute(
            text(
                "INSERT INTO feature_flag_targets (id, flag_id, organization_id, created_by, created_at) "
                "VALUES (:id, :f, :o, :u, now())"
            ),
            {"id": str(uuid.uuid4()), "f": flag_id, "o": other, "u": test_users[0].id},
        )
        conn.execute(
            text(
                "INSERT INTO feature_flags (id, name, state, created_at) "
                "VALUES (:id, 'compliance_records', 'everyone', now())"
            ),
            {"id": str(uuid.uuid4())},
        )
        _upgrade(conn)
        assert _flags(conn) == {
            "variant_experiments": {"state": "allowlist", "targets": [tum]},
            "compliance_records": {"state": "everyone", "targets": []},
            "report_paper": {"state": "allowlist", "targets": [other]},
        }

    def test_running_it_twice_changes_nothing(self, test_db: Session):
        conn = test_db.get_bind()
        _fresh(conn)
        tum = _organization(conn, "TUM")
        _upgrade(conn)
        first = _flags(conn)
        _upgrade(conn)
        assert _flags(conn) == first == {
            name: {"state": "allowlist", "targets": [tum]} for name in FLAGS
        }

    def test_the_registry_sync_keeps_the_rolled_out_state(self, test_db: Session):
        from feature_flags import service

        conn = test_db.get_bind()
        _fresh(conn)
        tum = _organization(conn, "TUM")
        _upgrade(conn)
        for statement in service._sync_statements():
            test_db.execute(statement)
        assert _flags(conn) == {name: {"state": "allowlist", "targets": [tum]} for name in FLAGS}
        descriptions = conn.execute(
            text("SELECT description FROM feature_flags WHERE name = ANY(:n)"), {"n": list(FLAGS)}
        ).scalars().all()
        assert len(descriptions) == 3 and all(descriptions)
