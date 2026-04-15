"""
Unit tests for routers/projects/crud.py to increase branch coverage.
Covers deep_merge_dicts, project CRUD, visibility, and completion stats.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from routers.projects.crud import deep_merge_dicts


# ============= deep_merge_dicts =============


class TestDeepMergeDicts:
    def test_both_none(self):
        assert deep_merge_dicts(None, None) == {}

    def test_base_none(self):
        assert deep_merge_dicts(None, {"a": 1}) == {"a": 1}

    def test_update_none(self):
        assert deep_merge_dicts({"a": 1}, None) == {"a": 1}

    def test_both_empty(self):
        assert deep_merge_dicts({}, {}) == {}

    def test_base_empty(self):
        assert deep_merge_dicts({}, {"a": 1}) == {"a": 1}

    def test_update_empty(self):
        assert deep_merge_dicts({"a": 1}, {}) == {"a": 1}

    def test_simple_merge(self):
        result = deep_merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overwrite(self):
        result = deep_merge_dicts({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_nested_merge(self):
        base = {"a": {"b": 1, "c": 2}}
        update = {"a": {"c": 3, "d": 4}}
        result = deep_merge_dicts(base, update)
        assert result == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_none_value_removes_key(self):
        base = {"a": 1, "b": 2}
        update = {"a": None}
        result = deep_merge_dicts(base, update)
        assert result == {"b": 2}

    def test_list_replaced_not_concatenated(self):
        base = {"a": [1, 2]}
        update = {"a": [3, 4]}
        result = deep_merge_dicts(base, update)
        assert result == {"a": [3, 4]}

    def test_deeply_nested(self):
        base = {"level1": {"level2": {"level3": {"value": "old"}}}}
        update = {"level1": {"level2": {"level3": {"value": "new", "extra": True}}}}
        result = deep_merge_dicts(base, update)
        assert result["level1"]["level2"]["level3"]["value"] == "new"
        assert result["level1"]["level2"]["level3"]["extra"] is True

    def test_does_not_mutate_input(self):
        base = {"a": {"b": 1}}
        update = {"a": {"c": 2}}
        result = deep_merge_dicts(base, update)
        assert "c" not in base["a"]
        assert result["a"]["c"] == 2

    def test_nested_none_removes_key(self):
        base = {"a": {"b": 1, "c": 2}}
        update = {"a": {"b": None}}
        result = deep_merge_dicts(base, update)
        assert result == {"a": {"c": 2}}

    def test_mixed_types_update_wins(self):
        base = {"a": {"nested": True}}
        update = {"a": "string"}
        result = deep_merge_dicts(base, update)
        assert result == {"a": "string"}


# ============= CRUD endpoint tests via TestClient =============

from main import app
from fastapi.testclient import TestClient
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


class TestDeleteProject:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

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
            resp = client.delete("/api/projects/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_non_superadmin_non_creator(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False, user_id="user-123")

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.is_private = True
        mock_project.created_by = "other-user"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/projects/proj-1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_non_private_project_non_superadmin(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False, user_id="user-123")

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.is_private = False
        mock_project.created_by = "user-123"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.delete("/api/projects/proj-1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestGetProject:
    def test_not_found(self):
        client = TestClient(app)
        user = _make_user()

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.get("/api/projects/nonexistent")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.options.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.projects.crud.check_project_accessible", return_value=False):
                resp = client.get("/api/projects/proj-1")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestUpdateProject:
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
            resp = client.patch("/api/projects/nonexistent", json={"title": "New Title"})
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_permission_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.projects.crud.check_user_can_edit_project", return_value=False):
                resp = client.patch("/api/projects/proj-1", json={"title": "New Title"})
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestUpdateProjectVisibility:
    def test_not_superadmin(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_db = Mock(spec=Session)
        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.patch(
                "/api/projects/proj-1/visibility",
                json={"is_private": True},
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

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
            resp = client.patch(
                "/api/projects/nonexistent/visibility",
                json={"is_private": True},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_make_org_assigned_no_org_ids(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.is_private = True

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.patch(
                "/api/projects/proj-1/visibility",
                json={"is_private": False, "organization_ids": []},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_make_private_with_invalid_owner(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"
        mock_project.is_private = False

        mock_db = Mock(spec=Session)
        call_count = {"n": 0}

        def query_side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            if call_count["n"] == 1:
                mock_q.first.return_value = mock_project  # Project found
            elif call_count["n"] == 2:
                mock_q.first.return_value = None  # Owner not found
            else:
                mock_q.first.return_value = None
                mock_q.delete.return_value = 0
            return mock_q

        mock_db.query.side_effect = query_side_effect

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.patch(
                "/api/projects/proj-1/visibility",
                json={"is_private": True, "owner_user_id": "nonexistent"},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestRecalculateStats:
    def test_not_superadmin(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module.dependencies import get_current_user

        mock_db = Mock(spec=Session)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/projects/proj-1/recalculate-stats")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_project_not_found(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=True)

        from database import get_db
        from auth_module.dependencies import get_current_user

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            resp = client.post("/api/projects/nonexistent/recalculate-stats")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestCompletionStats:
    def test_project_not_found(self):
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
            resp = client.get("/api/projects/nonexistent/completion-stats")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user = _make_user(is_superadmin=False)

        from database import get_db
        from auth_module import require_user

        mock_project = Mock()
        mock_project.id = "proj-1"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_project
        mock_db.query.return_value = mock_q

        app.dependency_overrides[require_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            with patch("routers.projects.crud.check_project_accessible", return_value=False):
                resp = client.get("/api/projects/proj-1/completion-stats")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
