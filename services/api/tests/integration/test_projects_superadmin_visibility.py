"""Integration tests for the superadmin "narrow by default" projects-list behavior.

`get_accessible_project_ids` no longer short-circuits to None for every
superadmin. A superadmin's `GET /api/projects/` is now scoped the same way a
regular user's is (own private + public + org-scoped) unless they explicitly
pass `?include_all_private=true`. These tests exercise that contract end-to-end
against a real Postgres test DB.
"""

import uuid
from datetime import datetime, timezone

import pytest

from auth_module import create_access_token
from models import User
from project_models import Project
from user_service import get_password_hash


def _uid() -> str:
    return str(uuid.uuid4())


def _make_user(db, *, is_superadmin: bool, slug: str) -> User:
    user = User(
        id=f"{slug}-{_uid()}",
        username=f"{slug}-{uuid.uuid4().hex[:8]}@test.com",
        email=f"{slug}-{uuid.uuid4().hex[:8]}@test.com",
        name=f"Visibility {slug}",
        hashed_password=get_password_hash("x"),
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _make_project(db, *, creator_id: str, is_private: bool, is_public: bool, title: str) -> Project:
    project = Project(
        id=_uid(),
        title=title,
        created_by=creator_id,
        is_private=is_private,
        is_public=is_public,
        public_role="ANNOTATOR" if is_public else None,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    return project


def _auth(user: User) -> dict:
    token = create_access_token(data={"user_id": user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def superadmin_a(test_db):
    return _make_user(test_db, is_superadmin=True, slug="superadmin-a")


@pytest.fixture
def superadmin_b(test_db):
    return _make_user(test_db, is_superadmin=True, slug="superadmin-b")


@pytest.fixture
def regular_user(test_db):
    return _make_user(test_db, is_superadmin=False, slug="regular")


@pytest.fixture
def project_set(test_db, superadmin_a, superadmin_b):
    """A's private, B's private, a public project."""
    p_a_private = _make_project(
        test_db, creator_id=superadmin_a.id, is_private=True, is_public=False,
        title="A private",
    )
    p_b_private = _make_project(
        test_db, creator_id=superadmin_b.id, is_private=True, is_public=False,
        title="B private",
    )
    p_public = _make_project(
        test_db, creator_id=superadmin_a.id, is_private=False, is_public=True,
        title="Public",
    )
    test_db.commit()
    return {"a_private": p_a_private, "b_private": p_b_private, "public": p_public}


class TestSuperadminVisibilityDefault:
    def test_default_hides_other_superadmin_private(
        self, client, superadmin_a, project_set
    ):
        """Without the flag, superadmin A must NOT see superadmin B's private project."""
        response = client.get("/api/projects/", headers=_auth(superadmin_a))
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert project_set["a_private"].id in ids
        assert project_set["public"].id in ids
        assert project_set["b_private"].id not in ids

    def test_include_all_private_reveals_others(
        self, client, superadmin_a, project_set
    ):
        """With `?include_all_private=true`, superadmin A sees every project."""
        response = client.get(
            "/api/projects/?include_all_private=true",
            headers=_auth(superadmin_a),
        )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert project_set["a_private"].id in ids
        assert project_set["b_private"].id in ids
        assert project_set["public"].id in ids

    def test_param_ignored_for_non_superadmin(
        self, client, regular_user, project_set
    ):
        """Non-superadmins cannot escalate visibility via the flag."""
        response = client.get(
            "/api/projects/?include_all_private=true",
            headers=_auth(regular_user),
        )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        # Regular user sees only public (they own no private projects here).
        assert project_set["public"].id in ids
        assert project_set["a_private"].id not in ids
        assert project_set["b_private"].id not in ids
