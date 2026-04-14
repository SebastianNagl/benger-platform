"""
Unit tests for routers/users.py to increase branch coverage.
Covers all user management endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_superadmin


def _make_admin(user_id="admin-123"):
    return User(
        id=user_id,
        username="admin",
        email="admin@example.com",
        name="Admin User",
        hashed_password="hashed",
        is_superadmin=True,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_db.query.return_value = mock_q
    return mock_db


class TestGetAllUsers:
    def test_returns_users(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.get_all_users", return_value=[]):
                resp = client.get("/api/users")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestUpdateUserRole:
    def test_non_boolean_is_superadmin(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch(
                "/api/users/user-1/role",
                json={"is_superadmin": "not_a_bool"},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.update_user_superadmin_status", return_value=None):
                resp = client.patch(
                    "/api/users/user-1/role",
                    json={"is_superadmin": True},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_update_role_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        updated_user = _make_admin(user_id="user-1")
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.update_user_superadmin_status", return_value=updated_user):
                resp = client.patch(
                    "/api/users/user-1/role",
                    json={"is_superadmin": True},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestUpdateUserStatus:
    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.update_user_status", return_value=None):
                resp = client.patch(
                    "/api/users/user-1/status",
                    json={"is_active": False},
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_update_status_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        updated_user = _make_admin(user_id="user-1")
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.update_user_status", return_value=updated_user):
                resp = client.patch(
                    "/api/users/user-1/status",
                    json={"is_active": False},
                )
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestVerifyUserEmail:
    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.patch("/api/users/nonexistent/verify-email")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_verification_failure(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.email_verification_service") as mock_evs:
                mock_evs.mark_email_verified.return_value = False
                resp = client.patch("/api/users/user-1/verify-email")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()

    def test_verification_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        db_user = Mock()
        db_user.id = "user-1"
        db_user.username = "testuser"
        db_user.email = "test@example.com"
        db_user.name = "Test"
        db_user.hashed_password = "hashed"
        db_user.is_superadmin = False
        db_user.is_active = True
        db_user.email_verified = True
        db_user.created_at = datetime.now(timezone.utc)
        db_user.organizations = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = db_user
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.users.email_verification_service") as mock_evs:
                mock_evs.mark_email_verified.return_value = True
                resp = client.patch("/api/users/user-1/verify-email")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestDeleteUser:
    def test_delete_self(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/users/admin-123")
            assert resp.status_code == 400
            assert "Cannot delete your own" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_user_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("user_service.delete_user", return_value=False):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_delete_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("user_service.delete_user", return_value=True):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_unexpected_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("user_service.delete_user", side_effect=Exception("DB error")):
                resp = client.delete("/api/users/user-1")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()
