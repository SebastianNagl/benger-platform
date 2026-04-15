"""
Unit tests for routers/generation.py to increase branch coverage.
Covers generation status, stop, pause, resume, retry, delete, and parse metrics endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User


def _make_user(is_superadmin=False, user_id="user-123"):
    user = User(
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
    return user


def _make_generation(gen_id="gen-1", status_val="running", created_by="user-123"):
    gen = Mock()
    gen.id = gen_id
    gen.status = status_val
    gen.created_by = created_by
    gen.celery_task_id = "celery-task-1"
    gen.project_id = "proj-1"
    gen.model_id = "gpt-4"
    gen.task_id = "task-1"
    gen.error_message = None
    gen.completed_at = None
    gen.current_progress = 0
    gen.completed_tasks = 0
    gen.retry_count = 0
    gen.paused_at = None
    gen.resumed_at = None
    return gen


class TestGetGenerationStatus:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/generation/status/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_success(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation()
        mock_task = Mock()
        mock_task.project_id = "proj-1"

        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = mock_task
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.check_project_accessible", return_value=True):
                resp = client.get("/api/generation/status/gen-1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["id"] == "gen-1"
                assert data["status"] == "running"
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation()
        mock_task = Mock()
        mock_task.project_id = "proj-1"

        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = mock_task
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.check_project_accessible", return_value=False):
                resp = client.get("/api/generation/status/gen-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestStopGeneration:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/stop")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(created_by="other-user")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/stop")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_wrong_status(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="completed")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/stop")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_success(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.celery_app") as mock_celery:
                mock_celery.control.revoke = Mock()
                resp = client.post("/api/generation/gen-1/stop")
                assert resp.status_code == 200
                assert resp.json()["status"] == "stopped"
        finally:
            app.dependency_overrides.clear()

    def test_success_pending(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="pending")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.celery_app") as mock_celery:
                mock_celery.control.revoke = Mock()
                resp = client.post("/api/generation/gen-1/stop")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_celery_revoke_fails_gracefully(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.celery_app") as mock_celery:
                mock_celery.control.revoke.side_effect = Exception("celery down")
                resp = client.post("/api/generation/gen-1/stop")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestPauseGeneration:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/pause")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(created_by="other-user")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/pause")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_wrong_status(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="pending")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/pause")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_success_with_redis(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        gen.current_progress = 50
        gen.completed_tasks = 5
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.get_redis_client") as mock_redis:
                mock_redis.return_value = Mock()
                resp = client.post("/api/generation/gen-1/pause")
                assert resp.status_code == 200
                assert resp.json()["status"] == "paused"
        finally:
            app.dependency_overrides.clear()

    def test_success_no_redis(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.get_redis_client") as mock_redis:
                mock_redis.return_value = None
                resp = client.post("/api/generation/gen-1/pause")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestResumeGeneration:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/resume")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="paused", created_by="other-user")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/resume")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_wrong_status(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/resume")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_resume_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="paused")
        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = None  # Project not found
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.get_redis_client") as mock_redis:
                mock_redis.return_value = None
                with patch("routers.generation.celery_app") as mock_celery:
                    resp = client.post("/api/generation/gen-1/resume")
                    assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestRetryGeneration:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/retry")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="failed", created_by="other-user")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/retry")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_wrong_status(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/generation/gen-1/retry")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_retry_project_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="failed")
        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.first.return_value = None
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.celery_app") as mock_celery:
                resp = client.post("/api/generation/gen-1/retry")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDeleteGeneration:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/generation/gen-1")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_not_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="completed", created_by="other-user")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/generation/gen-1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_cannot_delete_running(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="running")
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = gen
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/generation/gen-1")
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_success(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="completed")
        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.delete.return_value = 5  # deleted responses
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/generation/gen-1")
            assert resp.status_code == 200
            assert resp.json()["deleted_responses"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_superadmin_can_delete_others(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module import require_user

        gen = _make_generation(status_val="failed", created_by="other-user")
        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = gen
            else:
                mock_q.delete.return_value = 0
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/generation/gen-1")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


class TestParseMetrics:
    def test_project_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.check_project_accessible", return_value=False):
                resp = client.get("/api/generation/parse-metrics?project_id=proj-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_empty_results(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.count.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.check_project_accessible", return_value=True):
                resp = client.get("/api/generation/parse-metrics?project_id=proj-1")
                assert resp.status_code == 200
                assert resp.json()["total_generations"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_no_project_id_empty_accessible(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.count.return_value = 0
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.generation.get_accessible_project_ids", return_value=[]):
                resp = client.get("/api/generation/parse-metrics")
                assert resp.status_code == 200
                assert resp.json()["total_generations"] == 0
        finally:
            app.dependency_overrides.clear()
