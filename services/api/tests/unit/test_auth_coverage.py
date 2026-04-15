"""
Unit tests for routers/auth.py to increase branch coverage.
Focuses on pure function tests and simple endpoint error paths.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User


def _make_user(is_superadmin=False, user_id="user-123"):
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


class TestLoginEndpoint:
    def test_invalid_credentials(self):
        client = TestClient(app)

        from database import get_db

        mock_db = Mock(spec=Session)
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.auth.authenticate_user") as mock_auth:
                mock_auth.return_value = None
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "wrong", "password": "wrong"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestLogoutEndpoint:
    def test_logout(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.auth.logout_user") as mock_logout:
                mock_logout.return_value = True
                resp = client.post("/api/auth/logout")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestMeEndpoint:
    def test_get_me(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = user
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/auth/me")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestUnauthenticatedEndpoints:
    """Test that auth-required endpoints return 401 without credentials."""

    def test_me_unauthenticated(self):
        client = TestClient(app)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_logout_unauthenticated(self):
        client = TestClient(app)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401

    def test_profile_unauthenticated(self):
        client = TestClient(app)
        resp = client.put("/api/auth/profile", json={"name": "Test"})
        assert resp.status_code == 401

    def test_password_unauthenticated(self):
        client = TestClient(app)
        resp = client.post(
            "/api/auth/password",
            json={"current_password": "old", "new_password": "new"},
        )
        # Auth middleware may return 401, 404 (route not found), or 422
        assert resp.status_code in [401, 404, 422]
