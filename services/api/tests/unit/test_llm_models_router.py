"""
Tests for LLM models router.

Targets: routers/llm_models.py lines 60-85, 97-109

The /public/models endpoint was migrated to the async DB lane
(Depends(get_async_db) + await db.execute(select(...))), so these tests
exercise it through the real async_test_client / async_test_db fixtures
against actual seeded LLMModel rows instead of a mocked Session — the old
Mock(spec=Session).query(...) shape no longer matches the async handler.
"""

from datetime import datetime, timezone

import pytest
from fastapi import status

from models import LLMModel as DBLLMModel


def _make_model(**overrides):
    """Build an LLMModel row with sensible defaults for the public endpoint.

    Uses a test-only id to avoid colliding with real catalog rows that may
    already be committed in the shared test DB.
    """
    data = dict(
        id="test-gpt-4-public",
        name="GPT-4",
        description="OpenAI GPT-4",
        provider="openai",
        model_type="chat",
        capabilities=["text_generation"],
        config_schema=None,
        default_config=None,
        input_cost_per_million=30.0,
        output_cost_per_million=60.0,
        parameter_constraints={
            "temperature": {"supported": True, "min": 0, "max": 2, "default": 1},
            "max_tokens": {"default": 4096},
        },
        recommended_parameters=None,
        is_active=True,
        is_official=True,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    data.update(overrides)
    return DBLLMModel(**data)


class TestLLMModelsRouter:
    """Test LLM models endpoints."""

    @pytest.mark.asyncio
    async def test_get_public_models_success(self, async_test_client, async_test_db):
        """Test getting public LLM models."""
        async_test_db.add(_make_model())
        await async_test_db.commit()

        response = await async_test_client.get("/api/llm_models/public/models")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        ids = {m["id"]: m for m in data}
        assert "test-gpt-4-public" in ids
        model = ids["test-gpt-4-public"]
        assert model["provider"] == "openai"
        assert "parameter_constraints" in model
        assert model["parameter_constraints"]["temperature"]["supported"] is True
        assert model["parameter_constraints"]["max_tokens"]["default"] == 4096

    @pytest.mark.asyncio
    async def test_get_public_models_empty(self, async_test_client, async_test_db):
        """Inactive models are excluded from the public endpoint.

        The shared test DB may carry seeded models, so assert the inactive
        row we add is excluded rather than asserting a globally-empty list.
        """
        async_test_db.add(_make_model(id="inactive-model", is_active=False))
        await async_test_db.commit()

        response = await async_test_client.get("/api/llm_models/public/models")
        assert response.status_code == status.HTTP_200_OK
        ids = {m["id"] for m in response.json()}
        assert "inactive-model" not in ids

    @pytest.mark.asyncio
    async def test_get_public_models_error(self, async_test_client):
        """A DB-layer failure surfaces as a 500.

        Patch the handler's select() so the try-body raises, exercising the
        except-branch that wraps the error in a 500.
        """
        from unittest.mock import patch

        with patch("routers.llm_models.select", side_effect=Exception("DB error")):
            response = await async_test_client.get("/api/llm_models/public/models")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_get_provider_capabilities(self, client):
        """Test getting provider capabilities (sync, no DB)."""
        response = client.get("/api/llm_models/public/provider-capabilities")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, dict)

    def test_get_provider_capabilities_with_data(self, client):
        """Test getting provider capabilities with mock data."""
        from unittest.mock import patch

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
