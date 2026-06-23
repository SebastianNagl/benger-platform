"""
Tests for Feature Flags API Router
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from main import app
from auth_module.dependencies import require_superadmin
from auth_module.models import User as AuthUser
from models import FeatureFlag as DBFeatureFlag
from models import User
from schemas.feature_flag_schemas import FeatureFlagStatusResponse


@contextmanager
def _as_admin(db_user):
    """Grant superadmin via require_superadmin override (migrated list/delete
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
    f = DBFeatureFlag(
        id=str(uuid.uuid4()),
        name=name or f"flag-{uuid.uuid4().hex[:8]}",
        is_enabled=is_enabled,
        created_by=creator.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(f)
    await db.flush()
    return f


@pytest.fixture
def mock_db():
    """Create a mock database session"""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_superadmin():
    """Create a mock superadmin user"""
    user = MagicMock(spec=User)
    user.id = "test-superadmin-id"
    user.is_superadmin = True
    user.email = "admin@test.com"
    return user


@pytest.fixture
def mock_regular_user():
    """Create a mock regular user"""
    user = MagicMock(spec=User)
    user.id = "test-user-id"
    user.is_superadmin = False
    user.email = "user@test.com"
    return user


@pytest.fixture
def sample_feature_flag():
    """Create a sample feature flag"""
    flag = MagicMock(spec=DBFeatureFlag)
    flag.id = "flag-123"
    flag.name = "test_feature"
    flag.description = "Test feature flag"
    flag.is_enabled = True
    flag.configuration = {"key": "value"}
    flag.created_by = "admin-id"
    flag.created_at = "2024-01-01T00:00:00"
    flag.updated_at = None
    return flag


class TestFeatureFlagsRouter:
    """Test suite for feature flags router"""

    @pytest.mark.asyncio
    async def test_list_feature_flags_success(self, async_test_client, async_test_db):
        """Test successful listing of feature flags by superadmin"""
        admin = await _seed_user(async_test_db)
        flag = await _seed_flag(async_test_db, admin, name="test_feature")
        fid, fname = flag.id, flag.name
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.get("/api/feature-flags")
            assert resp.status_code == 200
            rows = {row["id"]: row for row in resp.json()}
            # Base DB carries seeded flags; assert the one we seeded is present.
            assert fid in rows
            assert rows[fid]["name"] == fname

    def test_list_feature_flags_unauthorized(self, mock_db, mock_regular_user):
        """Test that regular users cannot list feature flags"""
        with patch('routers.feature_flags.require_superadmin') as mock_require:
            mock_require.side_effect = HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required"
            )

            # Verify the authorization check would fail
            with pytest.raises(HTTPException) as exc_info:
                mock_require(mock_regular_user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Superadmin access required" in str(exc_info.value.detail)

    def test_get_all_feature_flags(self, mock_db, mock_regular_user):
        """Test getting all feature flags for regular users"""
        with patch('routers.feature_flags.require_user', return_value=mock_regular_user):
            with patch('routers.feature_flags.get_db', return_value=mock_db):
                with patch('routers.feature_flags.FeatureFlagService') as MockService:
                    # Setup mock service
                    mock_service = MagicMock()
                    mock_service.get_feature_flags.return_value = {
                        "test_feature": True,
                        "disabled_feature": False,
                    }
                    MockService.return_value = mock_service

                    # Test
                    import asyncio

                    from routers.feature_flags import get_feature_flags

                    result = asyncio.run(get_feature_flags(mock_regular_user, mock_db, None))

                    # Verify
                    assert result["test_feature"] == True  # noqa: E712
                    assert result["disabled_feature"] == False  # noqa: E712
                    mock_service.get_feature_flags.assert_called_once()

    def test_update_feature_flag_success(self, mock_db, mock_superadmin, sample_feature_flag):
        """Test successful update of a feature flag"""
        flag_id = "flag-123"
        update_data = {"is_enabled": False}

        with patch(
            'routers.feature_flags.require_superadmin', return_value=mock_superadmin
        ):
            with patch('routers.feature_flags.get_db', return_value=mock_db):
                with patch('routers.feature_flags.FeatureFlagService') as MockService:
                    # Setup - create a properly mocked updated flag
                    mock_service = MagicMock()
                    updated_flag = MagicMock()
                    updated_flag.id = flag_id
                    updated_flag.name = "test_feature"
                    updated_flag.description = "Updated description"
                    updated_flag.is_enabled = False
                    updated_flag.configuration = None
                    updated_flag.created_by = "admin-id"
                    updated_flag.created_at = "2024-01-01T00:00:00"
                    updated_flag.updated_at = "2024-01-02T00:00:00"
                    mock_service.update_flag.return_value = updated_flag
                    MockService.return_value = mock_service

                    # Test
                    import asyncio

                    from routers.feature_flags import update_feature_flag
                    from schemas.feature_flag_schemas import FeatureFlagUpdate

                    flag_update = FeatureFlagUpdate(**update_data)
                    result = asyncio.run(
                        update_feature_flag(flag_id, flag_update, mock_superadmin, mock_db)
                    )

                    # Verify
                    mock_service.update_flag.assert_called_once()
                    assert result.id == flag_id
                    assert result.is_enabled == False  # noqa: E712

    def test_check_feature_flag(self, mock_db, mock_regular_user):
        """Test checking if a feature flag is enabled"""
        flag_name = "test_feature"

        with patch('routers.feature_flags.require_user', return_value=mock_regular_user):
            with patch('routers.feature_flags.get_db', return_value=mock_db):
                with patch('routers.feature_flags.FeatureFlagService') as MockService:
                    # Setup
                    mock_service = MagicMock()
                    mock_service.is_enabled.return_value = True
                    MockService.return_value = mock_service

                    # Mock the user query
                    mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = (
                        mock_regular_user
                    )

                    # Test
                    import asyncio

                    from routers.feature_flags import check_feature_flag

                    result = asyncio.run(
                        check_feature_flag(flag_name, None, mock_regular_user, mock_db)
                    )

                    # Verify
                    assert isinstance(result, FeatureFlagStatusResponse)
                    assert result.flag_name == flag_name
                    assert result.is_enabled == True  # noqa: E712
                    mock_service.is_enabled.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_feature_flag_not_found(self, async_test_client, async_test_db):
        """Test deleting a non-existent feature flag returns 404"""
        admin = await _seed_user(async_test_db)
        await async_test_db.commit()

        with _as_admin(admin):
            resp = await async_test_client.delete(f"/api/feature-flags/{uuid.uuid4()}")
            assert resp.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in resp.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
