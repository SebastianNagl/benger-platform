"""
Unit tests for routers/feature_flags.py to increase branch coverage.
Covers all feature flag CRUD and check endpoints.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from auth_module.dependencies import require_superadmin, require_user
from database import get_db
from models import FeatureFlag, User as DBUser


@contextmanager
def _as_admin(db_user):
    """Override require_superadmin with a superadmin identity from a seeded DB row.

    The list/get/delete handlers were migrated to the async DB lane, so they run
    on the real ASGI/async-DB stack (async_test_client overrides get_async_db).
    Overriding require_superadmin grants admin access without a mock get_db.
    """
    au = User(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_superadmin] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_superadmin, None)


async def _seed_user(db):
    u = DBUser(
        id=str(uuid.uuid4()),
        username=f"ff-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@x.com",
        name="FF",
        hashed_password="x",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_flag(db, creator, *, name=None, is_enabled=True):
    f = FeatureFlag(
        id=str(uuid.uuid4()),
        name=name or f"flag-{uuid.uuid4().hex[:8]}",
        is_enabled=is_enabled,
        created_by=creator.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(f)
    await db.flush()
    return f


def _make_admin(user_id="admin-123"):
    return User(
        id=user_id,
        username="admin",
        email="admin@example.com",
        name="Admin",
        hashed_password="hashed",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_user(user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.options.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


class TestListFeatureFlags:
    @pytest.mark.asyncio
    async def test_list_flags(self, async_test_client, async_test_db):
        # GET "" is on the async DB lane; drive it through async_test_client and
        # seed a flag so the seeded id appears in the response list.
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get("/api/feature-flags")
            assert resp.status_code == 200
            assert fid in {row["id"] for row in resp.json()}

    @pytest.mark.asyncio
    async def test_list_flags_error(self, async_test_client, async_test_db):
        # Force the async handler's select() to raise so the 500 branch is hit.
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.select", side_effect=Exception("DB error")):
                resp = await async_test_client.get("/api/feature-flags")
                assert resp.status_code == 500


class TestGetAllFeatureFlags:
    def test_get_all_flags(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.get_feature_flags.return_value = {"test_flag": True}
                MockService.return_value = mock_svc
                resp = client.get("/api/feature-flags/all")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_get_all_flags_error(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                MockService.side_effect = Exception("Error")
                resp = client.get("/api/feature-flags/all")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestGetFeatureFlag:
    @pytest.mark.asyncio
    async def test_flag_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get(f"/api/feature-flags/{fid}")
            assert resp.status_code == 200
            assert resp.json()["id"] == fid

    @pytest.mark.asyncio
    async def test_flag_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get(f"/api/feature-flags/{uuid.uuid4()}")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_flag_error(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.select", side_effect=Exception("DB error")):
                resp = await async_test_client.get(f"/api/feature-flags/{uuid.uuid4()}")
                assert resp.status_code == 500


class TestUpdateFeatureFlag:
    def test_update_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        updated_flag = Mock()
        updated_flag.id = "f-1"
        updated_flag.name = "test_flag"
        updated_flag.description = "Updated"
        updated_flag.is_enabled = False
        updated_flag.configuration = {}
        updated_flag.created_by = "admin"
        updated_flag.created_at = datetime.now(timezone.utc)
        updated_flag.updated_at = datetime.now(timezone.utc)
        updated_flag.scope = "global"
        updated_flag.applicable_organization_ids = None

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.update_flag.return_value = updated_flag
                MockService.return_value = mock_svc
                resp = client.put(
                    "/api/feature-flags/f-1",
                    json={"is_enabled": False},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_update_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.update_flag.side_effect = ValueError("Not found")
                MockService.return_value = mock_svc
                resp = client.put(
                    "/api/feature-flags/nonexistent",
                    json={"is_enabled": False},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_update_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.update_flag.side_effect = Exception("Error")
                MockService.return_value = mock_svc
                resp = client.put(
                    "/api/feature-flags/f-1",
                    json={"is_enabled": False},
                )
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


class TestDeleteFeatureFlag:
    @pytest.mark.asyncio
    async def test_delete_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.delete(f"/api/feature-flags/{uuid.uuid4()}")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_success(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                MockService.return_value = Mock()
                resp = await async_test_client.delete(f"/api/feature-flags/{fid}")
                assert resp.status_code == 204

        gone = (
            await async_test_db.execute(
                select(FeatureFlag)
                .where(FeatureFlag.id == fid)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        assert gone is None

    @pytest.mark.asyncio
    async def test_delete_error(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.FeatureFlagService"):
                with patch(
                    "routers.feature_flags.select", side_effect=Exception("DB error")
                ):
                    resp = await async_test_client.delete(f"/api/feature-flags/{fid}")
                    assert resp.status_code == 500


class TestCheckFeatureFlag:
    def test_check_flag(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.organization_memberships = []

        mock_q = MagicMock()
        mock_q.options.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.is_enabled.return_value = True
                MockService.return_value = mock_svc
                resp = client.get("/api/feature-flags/check/test_flag")
                assert resp.status_code == 200
                assert resp.json()["is_enabled"] == True  # noqa: E712
        finally:
            app.dependency_overrides.clear()

    def test_check_flag_with_org(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-123"
        db_user.organization_memberships = []

        mock_q = MagicMock()
        mock_q.options.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                mock_svc.is_enabled.return_value = False
                MockService.return_value = mock_svc
                resp = client.get("/api/feature-flags/check/test_flag?organization_id=org-1")
                assert resp.status_code == 200
                assert resp.json()["is_enabled"] == False  # noqa: E712
        finally:
            app.dependency_overrides.clear()

    def test_check_flag_error(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags/check/test_flag")
            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()
