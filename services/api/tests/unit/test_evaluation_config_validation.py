"""
Unit tests for evaluation config validation with metric parameters.

Tests the fix for Issue #794: Bug: Evaluation config save fails when metrics have parameters
This test suite verifies that the evaluation config endpoint correctly handles both:
1. Simple string format: "bleu"
2. Object format with parameters: {"name": "bleu", "parameters": {...}}
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import User
from project_models import Project
from routers.evaluations import extract_metric_name


class TestExtractMetricName:
    """Test the extract_metric_name helper function"""

    def test_extract_from_string_format(self):
        """Test extraction from simple string format"""
        result = extract_metric_name("bleu")
        assert result == "bleu"

    def test_extract_from_object_format(self):
        """Test extraction from object format with parameters"""
        metric = {"name": "bleu", "parameters": {"max_order": 4}}
        result = extract_metric_name(metric)
        assert result == "bleu"

    def test_extract_from_object_with_empty_parameters(self):
        """Test extraction from object with empty parameters"""
        metric = {"name": "rouge", "parameters": {}}
        result = extract_metric_name(metric)
        assert result == "rouge"

    def test_extract_from_object_without_parameters(self):
        """Test extraction from object without parameters key"""
        metric = {"name": "meteor"}
        result = extract_metric_name(metric)
        assert result == "meteor"

    def test_extract_from_none(self):
        """Test extraction from None returns empty string"""
        result = extract_metric_name(None)
        assert result == ""

    def test_extract_from_empty_dict(self):
        """Test extraction from empty dict returns empty string"""
        result = extract_metric_name({})
        assert result == ""

    def test_extract_from_dict_without_name(self):
        """Test extraction from dict without 'name' key returns empty string"""
        metric = {"parameters": {"max_order": 4}}
        result = extract_metric_name(metric)
        assert result == ""

    def test_extract_from_integer(self):
        """Test extraction from invalid type (integer) returns empty string"""
        result = extract_metric_name(123)
        assert result == ""

    def test_extract_from_list(self):
        """Test extraction from invalid type (list) returns empty string"""
        result = extract_metric_name(["bleu"])
        assert result == ""


class TestEvaluationConfigValidation:
    """Test evaluation config endpoint validation with different metric formats"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def mock_superadmin(self):
        """Create a mock superadmin user for testing"""
        return User(
            id="admin-123",
            username="admin",
            email="admin@example.com",
            name="Admin User",
            hashed_password="hashed_password",
            is_superadmin=True,
            is_active=True,
            email_verified=True,
            use_pseudonym=False,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_project(self):
        """Create a mock project with label config"""
        return Project(
            id="project-123",
            title="Test Project",
            description="Test project for evaluation config",
            created_by="admin-123",
            label_config='<View><Choices name="answer" toName="text" choice="single"><Choice value="A"/><Choice value="B"/></Choices><Text name="text" value="$text"/></View>',
            label_config_version="v1",
            evaluation_config={
                "detected_answer_types": [
                    {"name": "answer", "type": "single_choice", "tag": "choices"}
                ],
                "available_methods": {
                    "answer": {
                        "type": "single_choice",
                        "tag": "choices",
                        # New flat structure - all metrics in a single list
                        "available_metrics": [
                            "exact_match",
                            "accuracy",
                            "bleu",
                            "rouge",
                            "llm_judge_accuracy",
                            "llm_judge_correctness",
                        ],
                        "enabled_metrics": [],
                    }
                },
                "selected_methods": {},
                "last_updated": None,
            },
            is_published=False,
            is_archived=False,
            immediate_evaluation_enabled=False,
            created_at=datetime.now(timezone.utc),
        )

    def test_validate_string_format_metrics(self, client, mock_superadmin, mock_project):
        """Test validation accepts string format metrics in automated array"""
        from database import get_db
        from routers.evaluations import require_user

        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                # String format metrics in automated array
                "answer": {
                    "automated": ["exact_match", "accuracy"],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        def override_require_user():
            return mock_superadmin

        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_project

        def override_get_db():
            return mock_session

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("sqlalchemy.orm.attributes.flag_modified"):
                response = client.put(
                    f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
                )

                assert response.status_code == status.HTTP_200_OK
                assert "message" in response.json()
                assert response.json()["message"] == "Evaluation configuration updated successfully"
        finally:
            app.dependency_overrides.clear()

    def test_validate_object_format_metrics(self, client, mock_superadmin, mock_project):
        """Test validation accepts object format metrics with parameters"""
        from database import get_db
        from routers.evaluations import require_user

        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [
                        {"name": "bleu", "parameters": {"max_order": 2}},
                        {"name": "rouge", "parameters": {"variant": "rougeL"}},
                    ],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        def override_require_user():
            return mock_superadmin

        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_project

        def override_get_db():
            return mock_session

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("sqlalchemy.orm.attributes.flag_modified"):
                response = client.put(
                    f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
                )

                assert response.status_code == status.HTTP_200_OK
                assert (
                    response.json()["config"]["selected_methods"]["answer"]["automated"][0]["name"]
                    == "bleu"
                )
                assert (
                    response.json()["config"]["selected_methods"]["answer"]["automated"][0][
                        "parameters"
                    ]["max_order"]
                    == 2
                )
        finally:
            app.dependency_overrides.clear()

    def test_validate_mixed_format_metrics(self, client, mock_superadmin, mock_project):
        """Test validation accepts mixed string and object formats"""
        from database import get_db
        from routers.evaluations import require_user

        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [
                        "exact_match",  # String format
                        {"name": "bleu", "parameters": {"max_order": 4}},  # Object format
                        "accuracy",  # String format
                    ],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        def override_require_user():
            return mock_superadmin

        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_project

        def override_get_db():
            return mock_session

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

        try:
            with patch("sqlalchemy.orm.attributes.flag_modified"):
                response = client.put(
                    f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
                )

                assert response.status_code == status.HTTP_200_OK
        finally:
            app.dependency_overrides.clear()

    def _setup_dependencies(self, mock_superadmin, mock_project):
        """Helper method to set up dependency overrides"""
        from database import get_db
        from routers.evaluations import require_user

        def override_require_user():
            return mock_superadmin

        mock_session = Mock(spec=Session)
        mock_session.query.return_value.filter.return_value.first.return_value = mock_project

        def override_get_db():
            return mock_session

        app.dependency_overrides[require_user] = override_require_user
        app.dependency_overrides[get_db] = override_get_db

    def _cleanup_dependencies(self):
        """Helper method to clean up dependency overrides"""
        app.dependency_overrides.clear()

    def test_validate_rejects_invalid_string_metric(self, client, mock_superadmin, mock_project):
        """Test validation rejects invalid metric names in string format"""
        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {"answer": {"automated": ["invalid_metric"], "human": []}},
            "last_updated": datetime.now().isoformat(),
        }

        self._setup_dependencies(mock_superadmin, mock_project)
        try:
            response = client.put(
                f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "invalid_metric" in response.json()["detail"]
        finally:
            self._cleanup_dependencies()

    def test_validate_rejects_invalid_object_metric(self, client, mock_superadmin, mock_project):
        """Test validation rejects invalid metric names in object format"""
        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [{"name": "invalid_metric", "parameters": {"param": "value"}}],
                    "human": [],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        self._setup_dependencies(mock_superadmin, mock_project)
        try:
            response = client.put(
                f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "invalid_metric" in response.json()["detail"]
        finally:
            self._cleanup_dependencies()

    def test_validate_empty_name_in_object_format(self, client, mock_superadmin, mock_project):
        """Test validation rejects object format with empty name"""
        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [{"name": "", "parameters": {"param": "value"}}],
                    "human": [],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        self._setup_dependencies(mock_superadmin, mock_project)
        try:
            response = client.put(
                f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            self._cleanup_dependencies()

    def test_validate_object_without_name_key(self, client, mock_superadmin, mock_project):
        """Test validation rejects object format without name key"""
        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [{"parameters": {"param": "value"}}],  # Missing "name" key
                    "human": [],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        self._setup_dependencies(mock_superadmin, mock_project)
        try:
            response = client.put(
                f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
        finally:
            self._cleanup_dependencies()

    def test_validate_preserves_parameters_in_response(self, client, mock_superadmin, mock_project):
        """Test that parameters are preserved in the response"""
        custom_params = {"max_order": 2, "weights": [0.5, 0.3, 0.1, 0.1], "smoothing": "method2"}
        config = {
            "detected_answer_types": mock_project.evaluation_config["detected_answer_types"],
            "available_methods": mock_project.evaluation_config["available_methods"],
            "selected_methods": {
                "answer": {
                    "automated": [{"name": "bleu", "parameters": custom_params}],
                    "human": [],
                }
            },
            "last_updated": datetime.now().isoformat(),
        }

        self._setup_dependencies(mock_superadmin, mock_project)
        try:
            with patch("sqlalchemy.orm.attributes.flag_modified"):
                response = client.put(
                    f"/api/evaluations/projects/{mock_project.id}/evaluation-config", json=config
                )
                assert response.status_code == status.HTTP_200_OK
                saved_metric = response.json()["config"]["selected_methods"]["answer"]["automated"][
                    0
                ]
                assert saved_metric["name"] == "bleu"
                assert saved_metric["parameters"] == custom_params
        finally:
            self._cleanup_dependencies()
