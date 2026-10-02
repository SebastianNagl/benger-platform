"""Shape tests for migration 110: feature flag state + allowlist targets.

The shared test DB is built by ``Base.metadata.create_all``, so it already has
the post-110 shape. These tests check the models against Postgres (the check
constraints, unique constraints and cascades the extended edition relies on),
that ``upgrade()`` is idempotent on that shape, and that a ``downgrade()``
followed by ``upgrade()`` backfills ``state`` from ``is_enabled`` and deletes
the retired core flags. Every test runs inside the ``test_db`` transaction,
which rolls back.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "110_feature_flag_rollout.py",
    )
)

RETIRED = (
    "data",
    "generations",
    "evaluations",
    "reports",
    "how-to",
    "leaderboards",
    "ORG_API_KEYS",
    "API_MAIL_SERVICE",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_110", MIGRATION_PATH)
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


def _make_user(db: Session):
    from models import User

    user = User(
        id=_uid(),
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="U",
    )
    db.add(user)
    db.flush()
    return user


def _make_org(db: Session):
    from models import Organization

    suffix = uuid.uuid4().hex[:8]
    org = Organization(
        id=_uid(),
        name=f"Org {suffix}",
        slug=f"org-{suffix}",
        display_name=f"Org {suffix}",
    )
    db.add(org)
    db.flush()
    return org


def _make_flag(db: Session, state: str = "off", created_by=None):
    from models import FeatureFlag

    flag = FeatureFlag(
        id=_uid(),
        name=f"flag_{uuid.uuid4().hex[:8]}",
        description="test flag",
        state=state,
        created_by=created_by,
    )
    db.add(flag)
    db.flush()
    return flag


class TestMigration110Chain:
    def test_revision_chains_after_109(self):
        mig = _load_migration()
        assert mig.revision == "110_feature_flag_rollout"
        assert mig.down_revision == "109_project_seb_settings"

    def test_model_columns(self):
        from models import FeatureFlag, FeatureFlagTarget

        cols = FeatureFlag.__table__.columns
        assert set(cols.keys()) == {
            "id",
            "name",
            "description",
            "state",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert cols["state"].nullable is False
        assert cols["created_by"].nullable is True
        assert set(FeatureFlagTarget.__table__.columns.keys()) == {
            "id",
            "flag_id",
            "user_id",
            "organization_id",
            "created_by",
            "created_at",
        }


class TestFeatureFlagModels:
    def test_state_defaults_to_off(self, test_db: Session):
        from models import FeatureFlag

        flag = FeatureFlag(id=_uid(), name=f"flag_{uuid.uuid4().hex[:8]}")
        test_db.add(flag)
        test_db.flush()
        test_db.refresh(flag)
        assert flag.state == "off"
        assert flag.created_by is None

    def test_flag_with_user_and_org_targets(self, test_db: Session):
        from models import FeatureFlagTarget

        user = _make_user(test_db)
        org = _make_org(test_db)
        flag = _make_flag(test_db, state="allowlist", created_by=user.id)
        flag.targets.append(FeatureFlagTarget(id=_uid(), user_id=user.id))
        flag.targets.append(FeatureFlagTarget(id=_uid(), organization_id=org.id))
        test_db.flush()
        test_db.expire_all()

        rows = test_db.execute(
            text(
                "SELECT user_id, organization_id FROM feature_flag_targets "
                "WHERE flag_id = :f ORDER BY user_id NULLS LAST"
            ),
            {"f": flag.id},
        ).all()
        assert rows == [(user.id, None), (None, org.id)]
        assert flag.state == "allowlist"
        assert len(flag.targets) == 2

    @pytest.mark.parametrize("state", ["off", "everyone", "allowlist"])
    def test_valid_states_accepted(self, test_db: Session, state):
        flag = _make_flag(test_db, state=state)
        assert test_db.execute(
            text("SELECT state FROM feature_flags WHERE id = :id"), {"id": flag.id}
        ).scalar_one() == state

    def test_bad_state_rejected(self, test_db: Session):
        with test_db.begin_nested():
            with pytest.raises(IntegrityError, match="ck_feature_flags_state"):
                _make_flag(test_db, state="on")

    def test_target_without_user_or_org_rejected(self, test_db: Session):
        from models import FeatureFlagTarget

        flag = _make_flag(test_db, state="allowlist")
        with test_db.begin_nested():
            test_db.add(FeatureFlagTarget(id=_uid(), flag_id=flag.id))
            with pytest.raises(IntegrityError, match="ck_feature_flag_targets_one_target"):
                test_db.flush()

    def test_target_with_both_user_and_org_rejected(self, test_db: Session):
        from models import FeatureFlagTarget

        user = _make_user(test_db)
        org = _make_org(test_db)
        flag = _make_flag(test_db, state="allowlist")
        with test_db.begin_nested():
            test_db.add(
                FeatureFlagTarget(
                    id=_uid(), flag_id=flag.id, user_id=user.id, organization_id=org.id
                )
            )
            with pytest.raises(IntegrityError, match="ck_feature_flag_targets_one_target"):
                test_db.flush()

    def test_duplicate_user_target_rejected(self, test_db: Session):
        from models import FeatureFlagTarget

        user = _make_user(test_db)
        flag = _make_flag(test_db, state="allowlist")
        test_db.add(FeatureFlagTarget(id=_uid(), flag_id=flag.id, user_id=user.id))
        test_db.flush()
        with test_db.begin_nested():
            test_db.add(FeatureFlagTarget(id=_uid(), flag_id=flag.id, user_id=user.id))
            with pytest.raises(IntegrityError, match="uq_feature_flag_targets_user"):
                test_db.flush()

    def test_duplicate_org_target_rejected(self, test_db: Session):
        from models import FeatureFlagTarget

        org = _make_org(test_db)
        flag = _make_flag(test_db, state="allowlist")
        test_db.add(FeatureFlagTarget(id=_uid(), flag_id=flag.id, organization_id=org.id))
        test_db.flush()
        with test_db.begin_nested():
            test_db.add(
                FeatureFlagTarget(id=_uid(), flag_id=flag.id, organization_id=org.id)
            )
            with pytest.raises(IntegrityError, match="uq_feature_flag_targets_org"):
                test_db.flush()

    def test_deleting_flag_cascades_to_targets(self, test_db: Session):
        user = _make_user(test_db)
        flag = _make_flag(test_db, state="allowlist")
        test_db.execute(
            text(
                "INSERT INTO feature_flag_targets (id, flag_id, user_id) "
                "VALUES (:id, :f, :u)"
            ),
            {"id": _uid(), "f": flag.id, "u": user.id},
        )
        test_db.execute(text("DELETE FROM feature_flags WHERE id = :id"), {"id": flag.id})
        assert test_db.execute(
            text("SELECT count(*) FROM feature_flag_targets WHERE flag_id = :f"),
            {"f": flag.id},
        ).scalar_one() == 0

    def test_deleting_user_or_org_removes_target_and_nulls_creator(self, test_db: Session):
        creator = _make_user(test_db)
        member = _make_user(test_db)
        org = _make_org(test_db)
        flag = _make_flag(test_db, state="allowlist", created_by=creator.id)
        for col, val in (("user_id", member.id), ("organization_id", org.id)):
            test_db.execute(
                text(
                    f"INSERT INTO feature_flag_targets (id, flag_id, {col}, created_by) "
                    "VALUES (:id, :f, :v, :c)"
                ),
                {"id": _uid(), "f": flag.id, "v": val, "c": creator.id},
            )
        test_db.expunge_all()

        test_db.execute(text("DELETE FROM users WHERE id = :id"), {"id": member.id})
        test_db.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org.id})
        test_db.execute(text("DELETE FROM users WHERE id = :id"), {"id": creator.id})

        assert test_db.execute(
            text("SELECT count(*) FROM feature_flag_targets WHERE flag_id = :f"),
            {"f": flag.id},
        ).scalar_one() == 0
        assert test_db.execute(
            text("SELECT created_by FROM feature_flags WHERE id = :id"), {"id": flag.id}
        ).scalar_one() is None


class TestMigration110UpDown:
    def test_upgrade_is_idempotent_on_current_shape(self, test_db: Session):
        conn = test_db.get_bind()
        flag = _make_flag(test_db, state="everyone")
        mig = _load_migration()
        with _op_context(conn):
            mig.upgrade()
            mig.upgrade()
        cols = _columns(conn, "feature_flags")
        assert "state" in cols
        assert not {"is_enabled", "configuration"} & set(cols)
        assert cols["created_by"]["nullable"] is True
        assert inspect(conn).has_table("feature_flag_targets")
        assert conn.execute(
            text("SELECT state FROM feature_flags WHERE id = :id"), {"id": flag.id}
        ).scalar_one() == "everyone"

    def test_downgrade_then_upgrade_backfills_and_retires(self, test_db: Session):
        conn = test_db.get_bind()
        user = _make_user(test_db)
        mig = _load_migration()
        with _op_context(conn):
            mig.downgrade()
            cols = _columns(conn, "feature_flags")
            assert {"is_enabled", "configuration"} <= set(cols)
            assert "state" not in cols
            assert not inspect(conn).has_table("feature_flag_targets")

            # Seed the pre-110 shape: retired core flags plus two live ones.
            for name in RETIRED:
                conn.execute(
                    text(
                        "INSERT INTO feature_flags (id, name, is_enabled, created_by) "
                        "VALUES (:id, :n, true, :u)"
                    ),
                    {"id": _uid(), "n": name, "u": user.id},
                )
            for name, enabled in (("keep_on", True), ("keep_off", False)):
                conn.execute(
                    text(
                        "INSERT INTO feature_flags (id, name, is_enabled, created_by) "
                        "VALUES (:id, :n, :e, :u)"
                    ),
                    {"id": _uid(), "n": name, "e": enabled, "u": user.id},
                )

            mig.upgrade()

        rows = dict(
            conn.execute(
                text(
                    "SELECT name, state FROM feature_flags "
                    "WHERE name = ANY(:names)"
                ),
                {"names": list(RETIRED) + ["keep_on", "keep_off"]},
            ).all()
        )
        assert rows == {"keep_on": "everyone", "keep_off": "off"}
        cols = _columns(conn, "feature_flags")
        assert not {"is_enabled", "configuration"} & set(cols)
        assert cols["state"]["nullable"] is False
        assert cols["created_by"]["nullable"] is True
        fks = [
            fk
            for fk in inspect(conn).get_foreign_keys("feature_flags")
            if fk["constrained_columns"] == ["created_by"]
        ]
        assert len(fks) == 1
        assert fks[0]["options"].get("ondelete") == "SET NULL"
        target_cols = _columns(conn, "feature_flag_targets")
        assert set(target_cols) == {
            "id",
            "flag_id",
            "user_id",
            "organization_id",
            "created_by",
            "created_at",
        }
        uniques = {
            uc["name"] for uc in inspect(conn).get_unique_constraints("feature_flag_targets")
        }
        assert uniques == {"uq_feature_flag_targets_user", "uq_feature_flag_targets_org"}
