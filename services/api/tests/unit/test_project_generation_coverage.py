"""
Unit tests for routers/projects/generation.py — targets uncovered lines 28-150.
Covers: get_generation_config, update_generation_config,
clear_generation_config, get_project_generation_status.
"""

from unittest.mock import MagicMock, Mock, patch
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException


class TestGetGenerationConfig:

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_project_not_found(self, mock_auth, mock_org):
        from routers.projects.generation import get_generation_config

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        request = Mock()
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_generation_config("p1", request, mock_db, user)
        assert exc_info.value.status_code == 404

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_no_permission(self, mock_auth, mock_org):
        from routers.projects.generation import get_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = False
        request = Mock()
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            get_generation_config("p1", request, mock_db, user)
        assert exc_info.value.status_code == 403

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_no_config_returns_defaults(self, mock_auth, mock_org):
        from routers.projects.generation import get_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        project.generation_config = None
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = True
        request = Mock()
        user = Mock()

        result = get_generation_config("p1", request, mock_db, user)
        assert "available_options" in result
        assert "selected_configuration" not in result

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_with_config_returns_selected(self, mock_auth, mock_org):
        from routers.projects.generation import get_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        project.generation_config = {"selected_configuration": {"models": ["gpt-4o"]}}
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = True
        request = Mock()
        user = Mock()

        result = get_generation_config("p1", request, mock_db, user)
        assert result["selected_configuration"] == {"models": ["gpt-4o"]}


class TestUpdateGenerationConfig:

    @patch("routers.projects.generation.flag_modified")
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_success(self, mock_auth, mock_org, mock_flag):
        from routers.projects.generation import update_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        project.generation_config = {}
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = True
        request = Mock()
        user = Mock()
        config = {"selected_configuration": {"models": ["gpt-4o"]}}

        result = update_generation_config("p1", config, request, mock_db, user)
        assert result["message"] == "Generation configuration updated successfully"
        assert project.generation_config == config

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_no_permission(self, mock_auth, mock_org):
        from routers.projects.generation import update_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = False
        request = Mock()
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            update_generation_config("p1", {}, request, mock_db, user)
        assert exc_info.value.status_code == 403


class TestClearGenerationConfig:

    @patch("routers.projects.generation.flag_modified")
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_success(self, mock_auth, mock_org, mock_flag):
        from routers.projects.generation import clear_generation_config

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"
        project.generation_config = {"old": "config"}
        mock_db.query.return_value.filter.return_value.first.return_value = project
        mock_auth.check_project_access.return_value = True
        request = Mock()
        user = Mock()

        result = clear_generation_config("p1", request, mock_db, user)
        assert project.generation_config is None

    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    @patch("routers.projects.generation.auth_service")
    def test_project_not_found(self, mock_auth, mock_org):
        from routers.projects.generation import clear_generation_config

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        request = Mock()
        user = Mock()

        with pytest.raises(HTTPException) as exc_info:
            clear_generation_config("p1", request, mock_db, user)
        assert exc_info.value.status_code == 404


class TestGetProjectGenerationStatus:

    @patch("routers.projects.generation.check_project_accessible", return_value=True)
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    def test_no_generations(self, mock_org, mock_access):
        from routers.projects.generation import get_project_generation_status

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"

        call_count = [0]
        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q
        mock_db.query.side_effect = query_side_effect

        request = Mock()
        user = Mock()

        result = get_project_generation_status("p1", request, mock_db, user)
        assert result["generations"] == []
        assert result["is_running"] is False

    @patch("routers.projects.generation.check_project_accessible", return_value=True)
    @patch("routers.projects.generation.get_org_context_from_request", return_value=None)
    def test_with_running_generation(self, mock_org, mock_access):
        from routers.projects.generation import get_project_generation_status

        mock_db = MagicMock()
        project = Mock()
        project.id = "p1"

        gen = Mock()
        gen.id = "g1"
        gen.model_id = "gpt-4o"
        gen.status = "running"
        gen.started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        gen.completed_at = None
        gen.error_message = None

        call_count = [0]
        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = project
            else:
                q.filter.return_value.order_by.return_value.all.return_value = [gen]
            return q
        mock_db.query.side_effect = query_side_effect

        request = Mock()
        user = Mock()

        result = get_project_generation_status("p1", request, mock_db, user)
        assert result["is_running"] is True
        assert result["latest_status"] == "running"
        assert len(result["generations"]) == 1
