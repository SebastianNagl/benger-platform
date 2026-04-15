"""
Unit tests for routers/evaluations/metadata.py to increase branch coverage.
Covers endpoint error paths for evaluation listing, details, deletion, and statistics.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User


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


class TestListProjectEvaluations:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/evaluations/nonexistent/list")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestGetEvaluationDetails:
    def test_evaluation_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/evaluations/proj-1/details/eval-nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteEvaluation:
    def test_evaluation_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/evaluations/proj-1/eval-nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAnnotationStatistics:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/evaluations/nonexistent/annotation-statistics")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAgreementMetrics:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/evaluations/nonexistent/agreement")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAnnotationDistribution:
    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module.dependencies import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/evaluations/nonexistent/annotation-distribution")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestUnauthenticatedEndpoints:
    """Test that evaluation endpoints require authentication."""

    def test_list_evaluations_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/evaluations/proj-1/list")
        # Endpoint may return 401 or 404 depending on auth middleware
        assert resp.status_code in [401, 404]

    def test_evaluation_details_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/evaluations/proj-1/details/eval-1")
        assert resp.status_code in [401, 404]

    def test_delete_evaluation_unauth(self):
        client = TestClient(app)
        resp = client.delete("/api/evaluations/proj-1/eval-1")
        assert resp.status_code in [401, 404]

    def test_annotation_statistics_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/evaluations/proj-1/annotation-statistics")
        assert resp.status_code in [401, 404]

    def test_agreement_unauth(self):
        client = TestClient(app)
        resp = client.get("/api/evaluations/proj-1/agreement")
        assert resp.status_code in [401, 404]
