"""
Tests for LLM models router.

Targets: routers/llm_models.py lines 60-85, 97-109
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app


class TestLLMModelsRouter:
    """Test LLM models endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_public_models_success(self, client):
        """Test getting public LLM models."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_model = Mock()
        mock_model.id = "gpt-4"
        mock_model.name = "GPT-4"
        mock_model.description = "OpenAI GPT-4"
        mock_model.provider = "openai"
        mock_model.model_type = "chat"
        mock_model.capabilities = ["text_generation"]
        mock_model.config_schema = None
        mock_model.default_config = None
        mock_model.input_cost_per_million = 30.0
        mock_model.output_cost_per_million = 60.0
        mock_model.parameter_constraints = {
            "temperature": {"supported": True, "min": 0, "max": 2, "default": 1},
            "max_tokens": {"default": 4096},
        }
        mock_model.is_active = True
        mock_model.created_at = datetime.now(timezone.utc)
        mock_model.updated_at = None

        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = [mock_model]
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/llm_models/public/models")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "gpt-4"
            assert data[0]["provider"] == "openai"
            assert "parameter_constraints" in data[0]
            assert data[0]["parameter_constraints"]["temperature"]["supported"] is True
            assert data[0]["parameter_constraints"]["max_tokens"]["default"] == 4096
        finally:
            app.dependency_overrides.clear()

    def test_get_public_models_empty(self, client):
        """Test getting public LLM models when none exist."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = []
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        def override_get_db():
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/llm_models/public/models")
            assert response.status_code == status.HTTP_200_OK
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    def test_get_public_models_error(self, client):
        """Test getting public LLM models with database error."""
        from database import get_db

        mock_db = Mock(spec=Session)
        mock_db.query.side_effect = Exception("DB error")

        def override_get_db():
            return mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = client.get("/api/llm_models/public/models")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        finally:
            app.dependency_overrides.clear()

    def test_get_provider_capabilities(self, client):
        """Test getting provider capabilities."""
        response = client.get("/api/llm_models/public/provider-capabilities")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, dict)

    def test_get_provider_capabilities_with_data(self, client):
        """Test getting provider capabilities with mock data."""
        mock_caps = {
            "openai": {
                "display_name": "OpenAI",
                "temperature": {"min": 0, "max": 2, "default": 1},
                "structured_output": {
                    "method": "json_schema",
                    "strict_mode": True,
                    "guaranteed": True,
                },
                "determinism": {"seed_support": True},
            }
        }
        with patch("routers.llm_models.PROVIDER_CAPABILITIES", mock_caps):
            response = client.get("/api/llm_models/public/provider-capabilities")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "openai" in data
            assert data["openai"]["display_name"] == "OpenAI"
