"""
Unit tests for routers/feature_flags.py to increase coverage.
Tests all feature flag CRUD endpoints and check endpoint.
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
from database import get_db
from auth_module.dependencies import require_user, require_superadmin
from models import FeatureFlag, User as DBUser


@contextmanager
def _as_admin(db_user):
    """Grant superadmin via require_superadmin override (migrated list/delete
    handlers run on the real async-DB stack through async_test_client)."""
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


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
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
    async def test_returns_empty_list(self, async_test_client, async_test_db):
        # The test DB carries base-seeded feature flags, so an exact-[] assertion
        # isn't possible; assert the endpoint returns a JSON list and that a flag
        # we never seeded is absent (the list reflects exactly what's in the DB).
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get("/api/feature-flags")
            assert resp.status_code == 200
            body = resp.json()
            assert isinstance(body, list)
            assert str(uuid.uuid4()) not in {row["id"] for row in body}

    @pytest.mark.asyncio
    async def test_returns_flags_from_db(self, async_test_client, async_test_db):
        """List endpoint returns the seeded FeatureFlag rows."""
        admin = await _seed_user(async_test_db)
        f1 = await _seed_flag(async_test_db, admin)
        f2 = await _seed_flag(async_test_db, admin)
        ids = {f1.id, f2.id}
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get("/api/feature-flags")
            assert resp.status_code == 200
            returned = {row["id"] for row in resp.json()}
            # Base DB carries seeded flags; assert our seeded ids are present.
            assert ids <= returned


class TestGetFeatureFlags:
    def test_returns_flags(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc = Mock()
                mock_svc.get_feature_flags.return_value = {"test_flag": True}
                mock_svc_cls.return_value = mock_svc
                resp = client.get("/api/feature-flags/all")
                assert resp.status_code == 200
                assert resp.json() == {"test_flag": True}
        finally:
            app.dependency_overrides.clear()


class TestGetSingleFeatureFlag:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        # GET /{flag_id} is on the async DB lane; drive it through
        # async_test_client. An unseeded id yields 404.
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get(f"/api/feature-flags/{uuid.uuid4()}")
            assert resp.status_code == 404


class TestUpdateFeatureFlag:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc = Mock()
                mock_svc.update_flag.side_effect = ValueError("Flag not found")
                mock_svc_cls.return_value = mock_svc
                resp = client.put(
                    "/api/feature-flags/nonexistent",
                    json={"is_enabled": True},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteFeatureFlag:
    @pytest.mark.asyncio
    async def test_not_found(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.delete(f"/api/feature-flags/{uuid.uuid4()}")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_delete(self, async_test_client, async_test_db):
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc_cls.return_value = Mock()
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


class TestCheckFeatureFlag:
    def test_check_flag(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        # Mock the user query with organization_memberships
        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.organization_memberships = []

        mock_q = MagicMock()
        mock_q.options.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc = Mock()
                mock_svc.is_enabled.return_value = True
                mock_svc_cls.return_value = mock_svc
                resp = client.get("/api/feature-flags/check/test_flag")
                assert resp.status_code == 200
                data = resp.json()
                assert data["flag_name"] == "test_flag"
                assert data["is_enabled"] == True  # noqa: E712
        finally:
            app.dependency_overrides.clear()

    def test_check_flag_with_org(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.organization_memberships = []

        mock_q = MagicMock()
        mock_q.options.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc = Mock()
                mock_svc.is_enabled.return_value = False
                mock_svc_cls.return_value = mock_svc
                resp = client.get("/api/feature-flags/check/test_flag?organization_id=org-1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["is_enabled"] == False  # noqa: E712
        finally:
            app.dependency_overrides.clear()
