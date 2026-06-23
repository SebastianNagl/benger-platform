"""
Extended tests for feature flags router - covering uncovered branches.

Targets: routers/feature_flags.py lines 37-39, 55-57, 61-63, 76-88, 110-117, 142-148, 152-155, 185-187
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.dependencies import require_superadmin
from auth_module.models import User as AuthUser
from models import FeatureFlag, User


@contextmanager
def _as_admin(db_user):
    """Grant superadmin via require_superadmin override (migrated list/get/delete
    handlers run on the real async-DB stack through async_test_client)."""
    au = AuthUser(
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
    u = User(
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


class TestFeatureFlagsExtended:
    """Test feature flags router covering uncovered branches."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin(self):
        return User(
            id="ff-admin",
            username="ffadmin",
            email="ffadmin@test.com",
            name="FF Admin",
            hashed_password="hashed",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_user(self):
        return User(
            id="ff-user",
            username="ffuser",
            email="ffuser@test.com",
            name="FF User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_list_flags_error(self, async_test_client, async_test_db):
        """Test list feature flags with database error."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.select", side_effect=Exception("DB error")):
                response = await async_test_client.get("/api/feature-flags")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_get_feature_flags_all_with_cache_headers(self, client, mock_user):
        """Test /all endpoint sets cache control headers."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.feature_flags.FeatureFlagService") as mock_service_cls:
            mock_service = Mock()
            mock_service.get_feature_flags.return_value = {"flag1": True}
            mock_service_cls.return_value = mock_service

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/feature-flags/all")
                assert response.status_code == status.HTTP_200_OK
                assert "no-cache" in response.headers.get("cache-control", "")
            finally:
                app.dependency_overrides.clear()

    def test_get_feature_flags_all_error(self, client, mock_user):
        """Test /all endpoint with service error."""
        from database import get_db
        from auth_module.dependencies import require_user

        def override_require_user():
            return mock_user

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.feature_flags.FeatureFlagService") as mock_service_cls:
            mock_service_cls.side_effect = Exception("Service error")

            app.dependency_overrides[require_user] = override_require_user
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.get("/api/feature-flags/all")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_single_flag_not_found(self, async_test_client, async_test_db):
        """Test getting non-existent feature flag."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            response = await async_test_client.get(f"/api/feature-flags/{uuid.uuid4()}")
            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_single_flag_db_error(self, async_test_client, async_test_db):
        """Test getting feature flag with database error."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.select", side_effect=Exception("DB error")):
                response = await async_test_client.get(f"/api/feature-flags/{uuid.uuid4()}")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_update_flag_not_found(self, client, mock_superadmin):
        """Test updating non-existent feature flag."""
        from database import get_db
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.feature_flags.FeatureFlagService") as mock_service_cls:
            mock_service = Mock()
            mock_service.update_flag.side_effect = ValueError("Flag not found")
            mock_service_cls.return_value = mock_service

            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.put(
                    "/api/feature-flags/nonexistent",
                    json={"is_enabled": True},
                )
                assert response.status_code == status.HTTP_404_NOT_FOUND
            finally:
                app.dependency_overrides.clear()

    def test_update_flag_error(self, client, mock_superadmin):
        """Test updating feature flag with unexpected error."""
        from database import get_db
        from auth_module.dependencies import require_superadmin

        def override_require_superadmin():
            return mock_superadmin

        def override_get_db():
            return Mock(spec=Session)

        with patch("routers.feature_flags.FeatureFlagService") as mock_service_cls:
            mock_service = Mock()
            mock_service.update_flag.side_effect = RuntimeError("DB error")
            mock_service_cls.return_value = mock_service

            app.dependency_overrides[require_superadmin] = override_require_superadmin
            app.dependency_overrides[get_db] = override_get_db
            try:
                response = client.put(
                    "/api/feature-flags/some-flag",
                    json={"is_enabled": True},
                )
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_flag_not_found(self, async_test_client, async_test_db):
        """Test deleting non-existent feature flag."""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            response = await async_test_client.delete(f"/api/feature-flags/{uuid.uuid4()}")
            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_flag_error(self, async_test_client, async_test_db):
        """Test deleting feature flag with unexpected error."""
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin)
        fid = flag.id
        await async_test_db.commit()

        with _as_admin(admin):
            with patch("routers.feature_flags.FeatureFlagService"):
                with patch(
                    "routers.feature_flags.select", side_effect=Exception("DB error")
                ):
                    response = await async_test_client.delete(f"/api/feature-flags/{fid}")
                    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_check_flag_error(self, client, mock_user):
        """Test check feature flag with service error."""
        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_db.query.side_effect = Exception("DB error")

        def override_require_user():
            return mock_user

        def override_get_db():
            return mock_db

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/feature-flags/check/some_flag")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        finally:
            app.dependency_overrides.clear()
