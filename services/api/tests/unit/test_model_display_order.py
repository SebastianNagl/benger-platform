"""Order of the model lists users pick from.

The catalog's list order (seeds/llm_models.yaml) is the order every model
picker shows: one block per provider, newest and most capable first within
a provider. The seed stores each official model's position in
``llm_models.display_order`` and every listing endpoint orders by it
(``models.llm_model_display_order``), custom models after the catalog.
Without that the database returns rows in storage order, which put models
added or updated later at the end of the list.
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
from models import Organization, OrganizationMembership, OrganizationRole, User
from seeds.llm_models_loader import PLATFORM_YAML, _load_yaml_file, load_catalog

# The provider blocks of the catalog, in picker order.
PROVIDER_ORDER = [
    "OpenAI",
    "Anthropic",
    "Google",
    "DeepInfra",
    "Mistral",
    "Cohere",
    "Grok",
]


def _uid() -> str:
    return str(uuid.uuid4())


class TestCatalogOrder:
    """The YAML itself: the list order is the picker order."""

    def test_each_provider_is_one_block_in_picker_order(self):
        providers = [m["provider"] for m in _load_yaml_file(PLATFORM_YAML)["models"]]
        blocks = [p for i, p in enumerate(providers) if i == 0 or providers[i - 1] != p]
        # A provider showing up twice means a model was appended at the end
        # of the file instead of at its place in its provider's block.
        assert blocks == PROVIDER_ORDER

    def test_newest_generation_leads_its_provider(self):
        ids = [m["id"] for m in _load_yaml_file(PLATFORM_YAML)["models"]]

        def before(a: str, b: str) -> bool:
            return ids.index(a) < ids.index(b)

        # Spot checks of "newest and most capable first" in each big block.
        assert before("gpt-6.2-astra", "gpt-6-astra")
        assert before("gpt-6-luna", "gpt-5.6-sol")
        assert before("gpt-5.5-pro", "gpt-5.5")
        assert before("claude-fable-5-2", "claude-opus-5-5")
        assert before("claude-opus-5-5", "claude-haiku-5-5")
        assert before("claude-haiku-5-5", "claude-fable-5-1")
        assert before("gemini-4-carbon", "gemini-4-hydrogen")
        assert before("gemini-4-hydrogen", "gemini-3.1-pro-preview")
        assert before("grok-4.7", "grok-4.3")


class TestSeederWritesPositions:
    def test_display_order_is_the_catalog_position(self, test_db):
        initialize_llm_models(test_db)
        test_db.expire_all()

        catalog = load_catalog().models
        rows = {
            r.id: r.display_order
            for r in test_db.query(DBLLMModel).filter(DBLLMModel.is_official.is_(True))
        }
        for position, model in enumerate(catalog):
            assert rows[model["id"]] == position, model["id"]

    def test_moved_model_gets_its_new_position(self, test_db):
        initialize_llm_models(test_db)
        catalog = load_catalog()
        first, *rest = catalog.models
        moved = type(catalog)(
            models=[*rest, first],
            content_hash=catalog.content_hash,
            sources=catalog.sources,
        )
        with patch("seeds.llm_models_loader.load_catalog", return_value=moved):
            initialize_llm_models(test_db)
        test_db.expire_all()

        row = test_db.query(DBLLMModel).filter(DBLLMModel.id == first["id"]).one()
        assert row.display_order == len(catalog.models) - 1


# --- Endpoints ---------------------------------------------------------------


@contextmanager
def _as_user(db_user: User):
    au = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


def _make_user() -> User:
    uid = _uid()
    return User(
        id=uid,
        username=f"mo-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Model Order User",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _official(model_id: str, provider: str, name: str, display_order: int) -> DBLLMModel:
    return DBLLMModel(
        id=model_id,
        name=name,
        provider=provider,
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=True,
        is_private=False,
        is_public=False,
        display_order=display_order,
    )


def _custom(created_by: str, name: str) -> DBLLMModel:
    return DBLLMModel(
        id=f"custom-{uuid.uuid4()}",
        name=name,
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        created_by=created_by,
        is_private=True,
        is_public=False,
        base_url="http://vllm.internal:8000/v1",
        endpoint_model_name="llama",
        requires_api_key=False,
    )


async def _seed_out_of_order(db, tag: str):
    """Official rows stored in the reverse of their catalog order, the way a
    model added later lands at the end of the table. Returns the ids in
    catalog order."""
    expected = [
        (f"order-{tag}-a", "OpenAI", "Zeta newest", 900_000),
        (f"order-{tag}-b", "OpenAI", "Alpha older", 900_001),
        (f"order-{tag}-c", "Anthropic", "Mid", 900_002),
    ]
    for model_id, provider, name, position in reversed(expected):
        db.add(_official(model_id, provider, name, position))
        await db.flush()
    await db.commit()
    return [e[0] for e in expected]


def _subsequence(ids, wanted):
    return [i for i in ids if i in set(wanted)]


class TestEndpointsOrderByCatalog:
    @pytest.mark.asyncio
    async def test_public_catalog(self, async_test_client, async_test_db):
        expected = await _seed_out_of_order(async_test_db, _uid()[:8])

        resp = await async_test_client.get("/api/llm_models/public/models")

        assert resp.status_code == status.HTTP_200_OK
        assert _subsequence([m["id"] for m in resp.json()], expected) == expected

    @pytest.mark.asyncio
    async def test_available_models_officials_then_customs(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.flush()
        expected = await _seed_out_of_order(async_test_db, _uid()[:8])
        # Stored before the officials' catalog positions would put them.
        custom_b = _custom(user.id, "Beta custom")
        custom_a = _custom(user.id, "Alpha custom")
        async_test_db.add_all([custom_b, custom_a])
        await async_test_db.commit()

        with _as_user(user), patch(
            "routers.api_keys.user_api_key_service.get_user_available_providers_async",
            new=AsyncMock(return_value=["OpenAI", "Anthropic"]),
        ):
            resp = await async_test_client.get("/api/users/api-keys/available-models")

        assert resp.status_code == status.HTTP_200_OK
        ids = [m["id"] for m in resp.json()]
        wanted = [*expected, custom_a.id, custom_b.id]
        assert _subsequence(ids, wanted) == wanted

    @pytest.mark.asyncio
    async def test_org_available_models(self, async_test_client, async_test_db):
        user = _make_user()
        org_uid = _uid()[:8]
        org = Organization(
            id=f"org-{org_uid}",
            name=f"Org {org_uid}",
            display_name=f"Org {org_uid}",
            slug=f"org-{org_uid}",
            is_active=True,
        )
        async_test_db.add_all([user, org])
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=True,
            )
        )
        expected = await _seed_out_of_order(async_test_db, _uid()[:8])

        with _as_user(user), patch(
            "services.org_api_key_service.org_api_key_service."
            "get_available_providers_for_context_async",
            new=AsyncMock(return_value=["OpenAI", "Anthropic"]),
        ):
            resp = await async_test_client.get(
                f"/api/organizations/{org.id}/api-keys/available-models"
            )

        assert resp.status_code == status.HTTP_200_OK
        assert _subsequence([m["id"] for m in resp.json()], expected) == expected
