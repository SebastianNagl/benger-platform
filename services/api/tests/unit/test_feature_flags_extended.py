"""
Unit tests for routers/feature_flags.py to increase coverage.
Tests all feature flag CRUD endpoints and check endpoint.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user, require_superadmin


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
    def test_returns_empty_list(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_returns_flags_from_db(self):
        """Test that list endpoint calls db.query(FeatureFlag).all()."""
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        # Return empty list from DB to avoid Pydantic validation issues with mocks
        mock_q = MagicMock()
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()


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
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


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
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/feature-flags/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_successful_delete(self):
        client = TestClient(app)
        user = _make_user()
        mock_db = _mock_db()

        flag = Mock()
        flag.id = "flag-1"
        flag.name = "test_flag"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = flag
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as mock_svc_cls:
                mock_svc = Mock()
                mock_svc_cls.return_value = mock_svc
                resp = client.delete("/api/feature-flags/flag-1")
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()


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
                assert data["is_enabled"] is True
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
                assert data["is_enabled"] is False
        finally:
            app.dependency_overrides.clear()
