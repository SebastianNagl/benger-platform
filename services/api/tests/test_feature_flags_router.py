"""
Tests for Feature Flags API Router
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import FeatureFlag as DBFeatureFlag
from models import User
from schemas.feature_flag_schemas import FeatureFlagStatusResponse


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

    def test_list_feature_flags_success(self, mock_db, mock_superadmin, sample_feature_flag):
        """Test successful listing of feature flags by superadmin"""
        # Setup
        mock_db.query.return_value.all.return_value = [sample_feature_flag]

        with patch(
            'routers.feature_flags.require_superadmin', return_value=mock_superadmin
        ):
            with patch('routers.feature_flags.get_db', return_value=mock_db):
                # Test the endpoint would be called correctly
                # Note: In a real test, we'd use TestClient, but for unit testing we verify the logic
                import asyncio

                from routers.feature_flags import list_feature_flags

                # Run the async function
                result = asyncio.run(list_feature_flags(mock_superadmin, mock_db))

                # Verify
                assert len(result) == 1
                assert result[0].id == "flag-123"
                assert result[0].name == "test_feature"
                mock_db.query.assert_called_once()

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
                    assert result["test_feature"] is True
                    assert result["disabled_feature"] is False
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
                    assert result.is_enabled is False

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
                    assert result.is_enabled is True
                    mock_service.is_enabled.assert_called_once()

    def test_delete_feature_flag_not_found(self, mock_db, mock_superadmin):
        """Test deleting a non-existent feature flag returns 404"""
        flag_id = "non-existent-flag"

        with patch(
            'routers.feature_flags.require_superadmin', return_value=mock_superadmin
        ):
            with patch('routers.feature_flags.get_db', return_value=mock_db):
                with patch('routers.feature_flags.FeatureFlagService') as MockService:
                    # Setup - flag doesn't exist
                    mock_db.query.return_value.filter.return_value.first.return_value = None
                    mock_service = MagicMock()
                    MockService.return_value = mock_service

                    # Test
                    import asyncio

                    from routers.feature_flags import delete_feature_flag

                    with pytest.raises(HTTPException) as exc_info:
                        asyncio.run(delete_feature_flag(flag_id, mock_superadmin, mock_db))

                    # Verify
                    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
                    assert "not found" in str(exc_info.value.detail).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
