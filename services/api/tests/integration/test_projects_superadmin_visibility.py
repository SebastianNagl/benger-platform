"""Integration tests for the superadmin "narrow by default" projects-list behavior.

`get_accessible_project_ids` no longer short-circuits to None for every
superadmin. A superadmin's `GET /api/projects/` is now scoped the same way a
regular user's is (own private + public + org-scoped) unless they explicitly
pass `?include_all_private=true`. These tests exercise that contract end-to-end
against a real Postgres test DB.

The projects-list endpoint (``routers/projects/crud.py``) is on the async DB
lane, so the suite drives it through ``async_test_client`` / ``async_test_db``
and authenticates via the ``_as_user`` override.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from models import Organization, User
from project_models import Project, ProjectOrganization
from auth_module.user_service import get_password_hash


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _make_user(db, *, is_superadmin: bool, slug: str) -> User:
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
    await db.flush()
    return user


async def _make_project(
    db, *, creator_id: str, is_private: bool, is_public: bool, title: str
) -> Project:
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
    await db.flush()
    return project


async def _seed_project_set(db):
    """A's private, B's private, a public project (+ the two superadmins and a
    regular user). Returns the seeded objects."""
    superadmin_a = await _make_user(db, is_superadmin=True, slug="superadmin-a")
    superadmin_b = await _make_user(db, is_superadmin=True, slug="superadmin-b")
    regular_user = await _make_user(db, is_superadmin=False, slug="regular")

    p_a_private = await _make_project(
        db, creator_id=superadmin_a.id, is_private=True, is_public=False,
        title="A private",
    )
    p_b_private = await _make_project(
        db, creator_id=superadmin_b.id, is_private=True, is_public=False,
        title="B private",
    )
    p_public = await _make_project(
        db, creator_id=superadmin_a.id, is_private=False, is_public=True,
        title="Public",
    )
    await db.commit()
    return {
        "superadmin_a": superadmin_a,
        "superadmin_b": superadmin_b,
        "regular_user": regular_user,
        "a_private": p_a_private,
        "b_private": p_b_private,
        "public": p_public,
    }


class TestSuperadminVisibilityDefault:
    @pytest.mark.asyncio
    async def test_default_hides_other_superadmin_private(
        self, async_test_client, async_test_db
    ):
        """Without the flag, superadmin A must NOT see superadmin B's private project."""
        s = await _seed_project_set(async_test_db)
        with _as_user(s["superadmin_a"]):
            response = await async_test_client.get("/api/projects/")
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert s["a_private"].id in ids
        assert s["public"].id in ids
        assert s["b_private"].id not in ids

    @pytest.mark.asyncio
    async def test_include_all_private_reveals_others(
        self, async_test_client, async_test_db
    ):
        """With `?include_all_private=true`, superadmin A sees every project."""
        s = await _seed_project_set(async_test_db)
        with _as_user(s["superadmin_a"]):
            response = await async_test_client.get(
                "/api/projects/?include_all_private=true",
            )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert s["a_private"].id in ids
        assert s["b_private"].id in ids
        assert s["public"].id in ids

    @pytest.mark.asyncio
    async def test_param_ignored_for_non_superadmin(
        self, async_test_client, async_test_db
    ):
        """Non-superadmins cannot escalate visibility via the flag."""
        s = await _seed_project_set(async_test_db)
        with _as_user(s["regular_user"]):
            response = await async_test_client.get(
                "/api/projects/?include_all_private=true",
            )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        # Regular user sees only public (they own no private projects here).
        assert s["public"].id in ids
        assert s["a_private"].id not in ids
        assert s["b_private"].id not in ids

    @pytest.mark.asyncio
    async def test_default_view_is_org_agnostic(
        self, async_test_client, async_test_db
    ):
        """A superadmin sees projects from every org regardless of the
        X-Organization-Context header — even orgs they aren't a member of."""
        s = await _seed_project_set(async_test_db)
        superadmin_a = s["superadmin_a"]
        # Org A's project, scoped via ProjectOrganization. Superadmin A is NOT
        # a member of org-foreign.
        org = Organization(
            id=f"org-foreign-{uuid.uuid4().hex[:8]}",
            name="Foreign Org",
            display_name="Foreign Org",
            slug=f"foreign-{uuid.uuid4().hex[:8]}",
        )
        async_test_db.add(org)
        await async_test_db.flush()
        org_proj = await _make_project(
            async_test_db, creator_id=superadmin_a.id, is_private=False, is_public=False,
            title="Foreign org project",
        )
        async_test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=org_proj.id,
                organization_id=org.id,
                assigned_by=superadmin_a.id,
            )
        )
        await async_test_db.commit()

        # Send a private-mode header — superadmin should still see the
        # org-scoped project from an org they don't belong to.
        with _as_user(superadmin_a):
            response = await async_test_client.get(
                "/api/projects/",
                headers={"X-Organization-Context": "private"},
            )
        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert org_proj.id in ids
        # And other users' private projects still hidden by default.
        assert s["b_private"].id not in ids
