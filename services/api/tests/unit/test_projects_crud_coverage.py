"""
Unit tests for routers/projects/crud.py to increase branch coverage.
Covers deep_merge_dicts, project CRUD, visibility, and completion stats.

The CRUD handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``), so the old
``get_db``-Mock / query-chain pattern no longer reaches them. The DB-backed
tests below seed real ORM rows via ``async_test_db`` and drive the surface
through ``async_test_client``; ``require_user`` (or ``get_current_user`` for the
admin-only recalc endpoint) is overridden per-test via ``_as_user`` to an auth
user matching the seeded owner. The pure ``deep_merge_dicts`` tests need no DB
and are unchanged.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from routers.projects.crud import deep_merge_dicts


# ============= deep_merge_dicts =============


class TestDeepMergeDicts:
    def test_both_none(self):
        assert deep_merge_dicts(None, None) == {}

    def test_base_none(self):
        assert deep_merge_dicts(None, {"a": 1}) == {"a": 1}

    def test_update_none(self):
        assert deep_merge_dicts({"a": 1}, None) == {"a": 1}

    def test_both_empty(self):
        assert deep_merge_dicts({}, {}) == {}

    def test_base_empty(self):
        assert deep_merge_dicts({}, {"a": 1}) == {"a": 1}

    def test_update_empty(self):
        assert deep_merge_dicts({"a": 1}, {}) == {"a": 1}

    def test_simple_merge(self):
        result = deep_merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overwrite(self):
        result = deep_merge_dicts({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_nested_merge(self):
        base = {"a": {"b": 1, "c": 2}}
        update = {"a": {"c": 3, "d": 4}}
        result = deep_merge_dicts(base, update)
        assert result == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_none_value_removes_key(self):
        base = {"a": 1, "b": 2}
        update = {"a": None}
        result = deep_merge_dicts(base, update)
        assert result == {"b": 2}

    def test_list_replaced_not_concatenated(self):
        base = {"a": [1, 2]}
        update = {"a": [3, 4]}
        result = deep_merge_dicts(base, update)
        assert result == {"a": [3, 4]}

    def test_deeply_nested(self):
        base = {"level1": {"level2": {"level3": {"value": "old"}}}}
        update = {"level1": {"level2": {"level3": {"value": "new", "extra": True}}}}
        result = deep_merge_dicts(base, update)
        assert result["level1"]["level2"]["level3"]["value"] == "new"
        assert result["level1"]["level2"]["level3"]["extra"] == True  # noqa: E712

    def test_does_not_mutate_input(self):
        base = {"a": {"b": 1}}
        update = {"a": {"c": 2}}
        result = deep_merge_dicts(base, update)
        assert "c" not in base["a"]
        assert result["a"]["c"] == 2

    def test_nested_none_removes_key(self):
        base = {"a": {"b": 1, "c": 2}}
        update = {"a": {"b": None}}
        result = deep_merge_dicts(base, update)
        assert result == {"a": {"c": 2}}

    def test_mixed_types_update_wins(self):
        base = {"a": {"nested": True}}
        update = {"a": "string"}
        result = deep_merge_dicts(base, update)
        assert result == {"a": "string"}


# ============= CRUD endpoint tests via async_test_client =============

from main import app  # noqa: E402
from auth_module import require_user  # noqa: E402
from auth_module.dependencies import get_current_user  # noqa: E402
from auth_module.models import User as AuthUser  # noqa: E402
from models import User  # noqa: E402
from project_models import Project  # noqa: E402


def _uid() -> str:
    return str(uuid.uuid4())


def _auth_user(db_user: User) -> AuthUser:
    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


@contextmanager
def _as_user(db_user: User):
    """Override require_user with an AuthUser matching the seeded DB user."""
    auth_user = _auth_user(db_user)
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


@contextmanager
def _as_current_user(db_user: User):
    """Override get_current_user (the recalc endpoint's dep) with the DB user."""
    app.dependency_overrides[get_current_user] = lambda: db_user
    try:
        yield db_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _make_user(db, *, is_superadmin=False, name="Test User"):
    u = User(
        id=_uid(),
        username=f"pc-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(
    db,
    *,
    created_by,
    title="Test Project",
    is_private=True,
    is_public=False,
    label_config="<View></View>",
):
    p = Project(
        id=_uid(),
        title=title,
        description="d",
        created_by=created_by,
        label_config=label_config,
        is_private=is_private,
        is_public=is_public,
        created_at=datetime.now(timezone.utc),
    )
    db.add(p)
    await db.flush()
    return p


class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_superadmin_non_creator(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_private_project_non_superadmin(
        self, async_test_client, async_test_db
    ):
        # Non-private (org) project, non-superadmin creator -> delete guard only
        # allows superadmins or creators of *private* projects -> 403.
        user = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=user.id, is_private=False
        )
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 403


class TestGetProject:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        # Private project owned by someone else -> non-owner gets 403.
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 403


class TestUpdateProject:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent", json={"title": "New Title"}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied(self, async_test_client, async_test_db):
        # Private project owned by someone else; a non-owner non-superadmin
        # cannot edit it -> 403.
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}", json={"title": "New Title"}
            )
        assert resp.status_code == 403


class TestUpdateProjectVisibility:
    @pytest.mark.asyncio
    async def test_not_superadmin(self, async_test_client, async_test_db):
        # Non-superadmin who is also not the creator cannot change visibility.
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                "/api/projects/nonexistent/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_make_org_assigned_no_org_ids(
        self, async_test_client, async_test_db
    ):
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db, created_by=admin.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_make_private_with_invalid_owner(
        self, async_test_client, async_test_db
    ):
        # Project found, but the requested owner_user_id does not exist -> 404.
        admin = await _make_user(async_test_db, is_superadmin=True)
        project = await _make_project(
            async_test_db, created_by=admin.id, is_private=False
        )
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.patch(
                f"/api/projects/{project.id}/visibility",
                json={"is_private": True, "owner_user_id": "nonexistent"},
            )
        assert resp.status_code == 404


class TestRecalculateStats:
    @pytest.mark.asyncio
    async def test_not_superadmin(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db, is_superadmin=False)
        await async_test_db.commit()

        with _as_current_user(user):
            resp = await async_test_client.post(
                "/api/projects/proj-1/recalculate-stats"
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        admin = await _make_user(async_test_db, is_superadmin=True)
        await async_test_db.commit()

        with _as_current_user(admin):
            resp = await async_test_client.post(
                "/api/projects/nonexistent/recalculate-stats"
            )
        assert resp.status_code == 404


class TestCompletionStats:
    @pytest.mark.asyncio
    async def test_project_not_found(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get(
                "/api/projects/nonexistent/completion-stats"
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_access_denied(self, async_test_client, async_test_db):
        # Private project owned by someone else -> non-owner gets 403.
        owner = await _make_user(async_test_db)
        other = await _make_user(async_test_db)
        project = await _make_project(
            async_test_db, created_by=owner.id, is_private=True
        )
        await async_test_db.commit()

        with _as_user(other):
            resp = await async_test_client.get(
                f"/api/projects/{project.id}/completion-stats"
            )
        assert resp.status_code == 403
