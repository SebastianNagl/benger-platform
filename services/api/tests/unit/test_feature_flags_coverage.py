"""
Unit tests for routers/feature_flags.py to increase branch coverage.
Covers all feature flag CRUD and check endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_superadmin, require_user


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
    def test_list_flags(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        flag = Mock()
        flag.id = "f-1"
        flag.name = "test_flag"
        flag.description = "A test flag"
        flag.is_enabled = True
        flag.configuration = {}
        flag.created_by = "admin"
        flag.created_at = datetime.now(timezone.utc)
        flag.updated_at = None
        flag.scope = "global"
        flag.applicable_organization_ids = None

        mock_q = MagicMock()
        mock_q.all.return_value = [flag]
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_list_flags_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags")
            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


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
    def test_flag_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        flag = Mock()
        flag.id = "f-1"
        flag.name = "test_flag"
        flag.description = "A test flag"
        flag.is_enabled = True
        flag.created_at = datetime.now(timezone.utc)
        flag.updated_at = None
        flag.scope = "global"
        flag.applicable_organization_ids = None
        flag.configuration = {}
        flag.created_by = "admin"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = flag
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags/f-1")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_flag_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_flag_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.get("/api/feature-flags/f-1")
            assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


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
    def test_delete_not_found(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()
        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            resp = client.delete("/api/feature-flags/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_delete_success(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        flag = Mock()
        flag.id = "f-1"
        flag.name = "test_flag"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = flag
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                mock_svc = Mock()
                MockService.return_value = mock_svc
                resp = client.delete("/api/feature-flags/f-1")
                assert resp.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_error(self):
        client = TestClient(app)
        admin = _make_admin()
        mock_db = _mock_db()

        flag = Mock()
        flag.id = "f-1"
        flag.name = "test_flag"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = flag
        mock_db.query.return_value = mock_q
        mock_db.delete.side_effect = Exception("DB error")

        app.dependency_overrides[require_superadmin] = lambda: admin
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            with patch("routers.feature_flags.FeatureFlagService") as MockService:
                MockService.return_value = Mock()
                resp = client.delete("/api/feature-flags/f-1")
                assert resp.status_code == 500
        finally:
            app.dependency_overrides.clear()


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
                assert resp.json()["is_enabled"] is True
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
                assert resp.json()["is_enabled"] is False
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
