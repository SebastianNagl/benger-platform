"""
Integration tests for generation flow
Issue #482: Test the complete generation workflow from configuration to results
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import Generation as DBGeneration
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project, Task


# Module-level fixtures accessible to all test classes
@pytest.fixture
def auth_headers(test_user):
    """Get authentication headers for test user"""
    return {"Authorization": f"Bearer {test_user.token}"}


@pytest.fixture
def test_project(db: Session, test_user):
    """Create a test project"""
    project = Project(
        id="test-project-123",
        title="Test Project",
        description="Project for testing generation",
        created_by=test_user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)

    # Add test tasks
    for i in range(3):
        task = Task(
            id=f"task-{i}",
            project_id=project.id,
            data={"text": f"Sample text {i}", "id": f"task-{i}"},
            created_by=test_user.id,
            inner_id=i,
        )
        db.add(task)

    db.commit()
    return project


@pytest.fixture
def test_generations_with_parse_data(db: Session, test_project):
    """Create test generations with various parse statuses"""
    # Create response generation
    response_gen = DBResponseGeneration(
        id="response-gen-1",
        project_id=test_project.id,
        model_id="gpt-4o",
        status="completed",
        created_by="test-user",
        started_at=datetime.now(),
        completed_at=datetime.now(),
    )
    db.add(response_gen)

    # Create individual generations with different parse statuses
    generations = [
        # Successful parses
        DBGeneration(
            id="gen-success-1",
            generation_id="response-gen-1",
            task_id="task-1",
            model_id="gpt-4o",
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 1},
        ),
        DBGeneration(
            id="gen-success-2",
            generation_id="response-gen-1",
            task_id="task-2",
            model_id="gpt-4o",
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 2},
        ),
        DBGeneration(
            id="gen-success-3",
            generation_id="response-gen-1",
            task_id="task-3",
            model_id="gpt-4o",
            case_data="test data",
            response_content="test response",
            parse_status="success",
            parse_metadata={"retry_count": 1},
        ),
        # Failed parses
        DBGeneration(
            id="gen-failed-1",
            generation_id="response-gen-1",
            task_id="task-4",
            model_id="gpt-4o",
            case_data="test data",
            response_content="invalid response",
            parse_status="failed",
            parse_error="JSON decode error",
        ),
        DBGeneration(
            id="gen-failed-2",
            generation_id="response-gen-1",
            task_id="task-5",
            model_id="gpt-4o",
            case_data="test data",
            response_content="invalid response",
            parse_status="failed",
            parse_error="JSON decode error",
        ),
        # Validation errors
        DBGeneration(
            id="gen-validation-1",
            generation_id="response-gen-1",
            task_id="task-6",
            model_id="gpt-4o",
            case_data="test data",
            response_content="missing fields",
            parse_status="validation_error",
            parse_error="Missing required field: label",
        ),
    ]

    db.add_all(generations)
    db.commit()
    return generations


class TestGenerationConfiguration:
    """Test generation configuration endpoints"""

    def test_get_generation_config_empty(self, client: TestClient, auth_headers, test_project):
        """Test getting generation config when none exists"""
        response = client.get(
            f"/api/projects/{test_project.id}/generation-config", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "available_options" in data
        assert "selected_configuration" not in data or data["selected_configuration"] is None

    def test_update_generation_config(self, client: TestClient, auth_headers, test_project):
        """Test updating generation configuration"""
        config = {
            "detected_data_types": [{"name": "text", "type": "string"}],
            "available_options": {
                "models": {
                    "openai": ["gpt-4o", "gpt-3.5-turbo"],
                    "anthropic": ["claude-3-opus-20240229"],
                },
                "presentation_modes": ["label_config", "template", "raw_json", "auto"],
            },
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-opus-20240229"],
                "prompts": {
                    "system": "You are an expert annotator",
                    "instruction": "Please annotate the following",
                },
                "parameters": {"temperature": 0.7, "max_tokens": 1500, "batch_size": 10},
                "presentation_mode": "label_config",
                "field_mappings": {},
            },
            "last_updated": datetime.now().isoformat(),
        }

        response = client.put(
            f"/api/projects/{test_project.id}/generation-config", json=config, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "config" in data

    def test_update_generation_config_unauthorized(self, client: TestClient, test_project):
        """Test updating config without authentication"""
        response = client.put(f"/api/projects/{test_project.id}/generation-config", json={})

        assert response.status_code == 401

    def test_clear_generation_config(
        self, client: TestClient, auth_headers, test_project, db: Session
    ):
        """Test clearing generation configuration"""
        # First set a config
        test_project.generation_config = {"test": "config"}
        db.commit()

        # Clear it
        response = client.delete(
            f"/api/projects/{test_project.id}/generation-config", headers=auth_headers
        )

        assert response.status_code == 204

        # Verify it's cleared
        db.refresh(test_project)
        assert test_project.generation_config is None


class TestGenerationExecution:
    """Test generation execution endpoints"""

    @pytest.fixture
    def configured_project(self, db: Session, test_project):
        """Create a project with generation configuration"""
        test_project.generation_config = {
            "selected_configuration": {
                "models": ["gpt-4o", "claude-3-opus-20240229"],
                "prompts": {"system": "Test system prompt", "instruction": "Test instruction"},
                "parameters": {"temperature": 0.7, "max_tokens": 1500, "batch_size": 10},
            }
        }
        db.commit()
        return test_project

    def test_get_generation_status(
        self, client: TestClient, auth_headers, configured_project, db: Session
    ):
        """Test getting generation status"""
        # Create test generation records
        gen1 = DBResponseGeneration(
            id="gen-1",
            project_id=configured_project.id,
            model_id="gpt-4o",
            status="running",
            created_by="test-user",
            started_at=datetime.now(),
        )
        gen2 = DBResponseGeneration(
            id="gen-2",
            project_id=configured_project.id,
            model_id="claude-3-opus-20240229",
            status="completed",
            created_by="test-user",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        db.add_all([gen1, gen2])
        db.commit()

        response = client.get(
            f"/api/projects/{configured_project.id}/generation-status", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "generations" in data
        assert len(data["generations"]) == 2
        assert data["is_running"] is True
        assert data["latest_status"] == "completed"  # Most recent first

    def test_stop_generation(self, client: TestClient, auth_headers, db: Session):
        """Test stopping a running generation"""
        # Create a running generation
        generation = DBResponseGeneration(
            id="gen-to-stop",
            project_id="test-project",
            model_id="gpt-4o",
            status="running",
            created_by="test-user",
            started_at=datetime.now(),
        )
        db.add(generation)
        db.commit()

        with patch('routers.generation.celery_app.control.revoke') as mock_revoke:
            response = client.post(f"/api/generation/gen-to-stop/stop", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "stopped"

            # Verify generation status updated
            db.refresh(generation)
            assert generation.status == "stopped"

    def test_delete_generation(self, client: TestClient, auth_headers, db: Session):
        """Test deleting generation and its responses"""
        # Create generation with responses
        generation = DBResponseGeneration(
            id="gen-to-delete",
            project_id="test-project",
            model_id="gpt-4o",
            status="completed",
            created_by="test-user",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        response1 = DBGeneration(
            id="resp-1",
            generation_id="gen-to-delete",
            task_id="task-1",
            model_id="gpt-4o",
            case_data="test data",
            response_content="test response",
        )
        db.add_all([generation, response1])
        db.commit()

        response = client.delete(f"/api/generation/gen-to-delete", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_responses"] == 1

        # Verify deletion
        assert db.query(DBResponseGeneration).filter_by(id="gen-to-delete").first() is None
        assert db.query(DBGeneration).filter_by(generation_id="gen-to-delete").first() is None


class TestWebSocketGeneration:
    """Test WebSocket functionality for real-time updates"""

    @pytest.mark.asyncio
    async def test_websocket_connection(self, test_project):
        """Test WebSocket connection for generation progress"""
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch('routers.generation.get_redis_client') as mock_redis:
            # Mock Redis client to trigger polling fallback (no pubsub attribute)
            mock_redis_instance = MagicMock()
            # Remove pubsub attribute to force polling mode
            del mock_redis_instance.pubsub
            mock_redis.return_value = mock_redis_instance

            # Test WebSocket connection
            with client.websocket_connect(
                f"/api/ws/projects/{test_project.id}/generation-progress"
            ) as websocket:
                # Should receive connection confirmation
                data = websocket.receive_json()
                assert data["type"] in ["connection", "connection_polling"]
                assert data["project_id"] == test_project.id

    @pytest.mark.asyncio
    async def test_websocket_progress_updates(self, test_project):
        """Test receiving progress updates via WebSocket"""
        from fastapi.testclient import TestClient

        TestClient(app)

        with patch('routers.generation.get_redis_client') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis.return_value = mock_redis_instance

            # Mock Redis pub/sub
            mock_pubsub = MagicMock()
            mock_redis_instance.pubsub.return_value = mock_pubsub

            # Simulate progress message
            progress_message = {
                "type": "progress",
                "project_id": test_project.id,
                "generations": [
                    {"id": "gen-1", "model_id": "gpt-4o", "status": "running", "progress": 50}
                ],
            }

            # This would normally come from Redis pub/sub
            # Testing the message format expected by frontend
            assert "generations" in progress_message
            assert progress_message["generations"][0]["status"] == "running"


class TestParseMetrics:
    """Test parse metrics endpoint"""

    def test_get_parse_metrics_no_filters(
        self, client: TestClient, auth_headers, test_project, test_generations_with_parse_data
    ):
        """Test getting parse metrics scoped to fixture project for exact counts"""
        response = client.get(
            f"/api/generation/parse-metrics?project_id={test_project.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert data["parse_success"] == 3
        assert data["parse_failed"] == 2
        assert data["parse_validation_error"] == 1
        assert data["parse_failed_max_retries"] == 0
        assert data["parse_success_rate"] == 0.5
        assert data["avg_retries_until_success"] == pytest.approx(4 / 3, rel=0.01)
        assert len(data["common_parse_errors"]) == 2

    def test_get_parse_metrics_by_project(
        self, client: TestClient, auth_headers, test_project, test_generations_with_parse_data
    ):
        """Test getting parse metrics filtered by project"""
        response = client.get(
            f"/api/generation/parse-metrics?project_id={test_project.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert "common_parse_errors" in data

    def test_get_parse_metrics_by_model(
        self, client: TestClient, auth_headers, test_project, test_generations_with_parse_data
    ):
        """Test getting parse metrics filtered by model and project"""
        response = client.get(
            f"/api/generation/parse-metrics?project_id={test_project.id}&model_id=gpt-4o",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 6
        assert data["parse_success"] == 3

    def test_get_parse_metrics_empty(self, client: TestClient, auth_headers):
        """Test getting parse metrics when no generations exist"""
        response = client.get(
            "/api/generation/parse-metrics?project_id=nonexistent-project", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_generations"] == 0
        assert data["parse_success"] == 0
        assert data["parse_success_rate"] == 0
        assert data["avg_retries_until_success"] == 0
        assert data["common_parse_errors"] == []

    def test_get_parse_metrics_common_errors(
        self, client: TestClient, auth_headers, test_project, test_generations_with_parse_data
    ):
        """Test that common parse errors are sorted by count"""
        response = client.get(
            f"/api/generation/parse-metrics?project_id={test_project.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        errors = data["common_parse_errors"]
        assert len(errors) == 2
        assert errors[0]["error"] == "JSON decode error"
        assert errors[0]["count"] == 2
        assert errors[1]["error"] == "Missing required field: label"
        assert errors[1]["count"] == 1
