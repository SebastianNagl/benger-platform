"""Integration tests for the three CHECK constraints on the projects table
introduced by alembic migration 035 (also mirrored in Project.__table_args__).

Each test inserts a row that violates one of:
  - ck_projects_visibility_exclusive          NOT (is_private AND is_public)
  - ck_projects_public_role_required_when_public  NOT is_public OR public_role IS NOT NULL
  - ck_projects_public_role_valid             public_role IN ('ANNOTATOR','CONTRIBUTOR') or NULL

and asserts that PostgreSQL raises IntegrityError.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import User
from project_models import Project


@pytest.fixture(scope="module", autouse=True)
def _ensure_constraints():
    """The session-scoped test DB was created by Base.metadata.create_all
    *before* the visibility CHECK constraints were added to Project.__table_args__,
    so the existing `projects` table can be missing them on first run.
    Add any that aren't present, idempotently, so this test exercises the
    same constraints the migration applies in prod.
    """
    from tests.fixtures.database import _get_engine

    engine, _ = _get_engine()
    constraints = [
        (
            "ck_projects_visibility_exclusive",
            "NOT (is_private AND is_public)",
        ),
        (
            "ck_projects_public_role_valid",
            "public_role IS NULL OR public_role IN ('ANNOTATOR', 'CONTRIBUTOR')",
        ),
        (
            "ck_projects_public_role_required_when_public",
            "NOT is_public OR public_role IS NOT NULL",
        ),
    ]
    for name, expr in constraints:
        with engine.begin() as conn:
            existing = conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = :name"
                ),
                {"name": name},
            ).scalar()
            if not existing:
                conn.execute(
                    text(
                        f"ALTER TABLE projects "
                        f"ADD CONSTRAINT {name} CHECK ({expr})"
                    )
                )
    yield


@pytest.fixture
def project_owner(test_db):
    """Real user row to satisfy projects.created_by FK."""
    user = User(
        id=f"vc-owner-{uuid.uuid4()}",
        username=f"vc-{uuid.uuid4().hex[:8]}",
        email=f"vc-{uuid.uuid4().hex[:8]}@test.com",
        name="Visibility Constraint Test Owner",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.flush()
    return user


def _make_project(owner_id, **overrides):
    base = dict(
        id=str(uuid.uuid4()),
        title="Constraint test",
        created_by=owner_id,
        is_private=False,
        is_public=False,
        public_role=None,
    )
    base.update(overrides)
    return Project(**base)


class TestProjectVisibilityConstraints:
    def test_private_and_public_cannot_both_be_true(self, test_db, project_owner):
        test_db.add(
            _make_project(
                project_owner.id,
                is_private=True,
                is_public=True,
                public_role="ANNOTATOR",
            )
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_public_requires_role(self, test_db, project_owner):
        test_db.add(
            _make_project(project_owner.id, is_public=True, public_role=None)
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_public_role_must_be_a_valid_value(self, test_db, project_owner):
        test_db.add(
            _make_project(project_owner.id, is_public=True, public_role="WRONG")
        )
        with pytest.raises(IntegrityError):
            test_db.flush()
        test_db.rollback()

    def test_valid_public_annotator_passes(self, test_db, project_owner):
        test_db.add(
            _make_project(
                project_owner.id, is_public=True, public_role="ANNOTATOR"
            )
        )
        test_db.flush()  # no error

    def test_valid_public_contributor_passes(self, test_db, project_owner):
        test_db.add(
            _make_project(
                project_owner.id, is_public=True, public_role="CONTRIBUTOR"
            )
        )
        test_db.flush()

    def test_private_with_no_public_role_passes(self, test_db, project_owner):
        test_db.add(_make_project(project_owner.id, is_private=True))
        test_db.flush()

    def test_org_scoped_with_no_public_role_passes(self, test_db, project_owner):
        test_db.add(_make_project(project_owner.id))
        test_db.flush()
