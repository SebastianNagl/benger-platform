"""Open-weight DeepInfra models for variant experiments are selectable.

Four DeepInfra models were added to the catalog (Llama 3.1 8B Turbo,
Mistral Small 3.2 24B, Phi-4, gpt-oss-20b), and gpt-oss-20b, Qwen 3.8 27B,
Gemma 4 26B A4B and Nemotron 3.5 Lightning declare their reasoning knob, so
the model picker can run each of them with thinking on and off (two systems
of one model, see ``services/shared/system_profile.py``).

* The real YAML catalog seeds them as active official rows carrying the
  reasoning declaration.
* ``GET /api/users/api-keys/available-models`` offers them to a caller with
  a DeepInfra key, with the ``default_config`` the picker renders from.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from database import initialize_llm_models
from main import app
from models import LLMModel as DBLLMModel
from models import User
from seeds.llm_models_loader import load_catalog

ADDED = [
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "microsoft/phi-4",
    "openai/gpt-oss-20b",
]
THINKING_SWITCH = {
    "Qwen/Qwen3.8-27B": "on",
    "google/gemma-4-26B-A4B-it": "off",
    "nvidia/NVIDIA-Nemotron-3.5-Lightning": "off",
}


def _catalog_rows(ids):
    by_id = {m["id"]: dict(m) for m in load_catalog().models}
    rows = []
    for model_id in ids:
        row = by_id[model_id]
        if "constraints" in row:
            row["parameter_constraints"] = row.pop("constraints")
        row["is_official"] = True
        rows.append(row)
    return rows


class TestSeededOpenWeightModels:
    def test_seed_writes_active_official_rows_with_reasoning_declarations(
        self, test_db
    ):
        initialize_llm_models(test_db)
        test_db.expire_all()

        for model_id in ADDED:
            row = test_db.query(DBLLMModel).filter(DBLLMModel.id == model_id).first()
            assert row is not None, model_id
            assert row.is_active is True
            assert row.is_official is True
            assert row.provider == "DeepInfra"

        gpt_oss = (
            test_db.query(DBLLMModel)
            .filter(DBLLMModel.id == "openai/gpt-oss-20b")
            .first()
        )
        rc = gpt_oss.default_config["reasoning_config"]
        assert rc["parameter"] == "reasoning_effort"
        assert rc["values"] == ["low", "medium", "high"]

        for model_id, default in THINKING_SWITCH.items():
            row = test_db.query(DBLLMModel).filter(DBLLMModel.id == model_id).first()
            rc = row.default_config["reasoning_config"]
            assert rc["parameter"] == "enable_thinking"
            assert rc["values"] == ["off", "on"]
            assert rc["default"] == default


@contextmanager
def _as_user(db_user: User):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at,
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


@pytest.mark.flags_on("variant_experiments")
class TestAvailableModelsOffersOpenWeight:
    @pytest.mark.asyncio
    async def test_caller_with_deepinfra_key_sees_the_models(
        self, async_test_client, async_test_db
    ):
        uid = str(uuid.uuid4())
        user = User(
            id=uid,
            username=f"openw-{uid[:8]}",
            email=f"{uid[:8]}@test.com",
            name="Open Weight User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(user)
        for row in _catalog_rows(ADDED + list(THINKING_SWITCH)):
            await async_test_db.merge(DBLLMModel(**row))
        await async_test_db.commit()

        with _as_user(user), patch(
            "routers.api_keys.user_api_key_service.get_user_available_providers_async",
            new=AsyncMock(return_value=["DeepInfra"]),
        ):
            resp = await async_test_client.get("/api/users/api-keys/available-models")

        assert resp.status_code == status.HTTP_200_OK
        offered = {m["id"]: m for m in resp.json()}
        for model_id in ADDED + list(THINKING_SWITCH):
            assert model_id in offered, model_id
            assert offered[model_id]["provider"] == "DeepInfra"
        assert (
            offered["openai/gpt-oss-20b"]["default_config"]["reasoning_config"][
                "parameter"
            ]
            == "reasoning_effort"
        )
        assert (
            offered["Qwen/Qwen3.8-27B"]["default_config"]["reasoning_config"]["default"]
            == "on"
        )
        # The panel model carries only its flag mark (catalog_flags).
        assert offered["microsoft/phi-4"]["default_config"] == {
            "feature_flag": "variant_experiments"
        }

    @pytest.mark.asyncio
    async def test_caller_without_deepinfra_key_does_not(
        self, async_test_client, async_test_db
    ):
        uid = str(uuid.uuid4())
        user = User(
            id=uid,
            username=f"openw-{uid[:8]}",
            email=f"{uid[:8]}@test.com",
            name="Open Weight User",
            hashed_password="hashed",
            is_superadmin=False,
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        async_test_db.add(user)
        for row in _catalog_rows(ADDED):
            await async_test_db.merge(DBLLMModel(**row))
        await async_test_db.commit()

        with _as_user(user), patch(
            "routers.api_keys.user_api_key_service.get_user_available_providers_async",
            new=AsyncMock(return_value=["OpenAI"]),
        ):
            resp = await async_test_client.get("/api/users/api-keys/available-models")

        assert resp.status_code == status.HTTP_200_OK
        offered = {m["id"] for m in resp.json()}
        assert not offered.intersection(ADDED)
