"""
Tests for the custom (BYOM) pass in GET /api/users/api-keys/available-models
(routers/api_keys.py get_available_models_for_user).

Rules under test:
- keyless custom models (requires_api_key=False) appear without a credential
- requires_api_key custom models are hidden until the caller stores one
- other users' private customs never appear
- official entries carry is_official=true and keep the provider-key filter
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import CustomModelCredential, CustomModelOrgCredential
from models import LLMModel as DBLLMModel
from models import (
    ModelOrganization,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)


def _uid() -> str:
    return str(uuid.uuid4())


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
        username=f"am-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Available Models User",
        hashed_password="hashed",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_custom_model(created_by, **overrides) -> DBLLMModel:
    data = dict(
        id=f"custom-{uuid.uuid4()}",
        name="Custom vLLM",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        created_by=created_by,
        is_private=True,
        is_public=False,
        base_url="http://10.10.3.7:8000/v1",
        endpoint_model_name="llama-3-8b",
        requires_api_key=True,
        created_at=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return DBLLMModel(**data)


def _make_official_model(provider="openai", **overrides) -> DBLLMModel:
    data = dict(
        id=f"test-official-{_uid()[:8]}",
        name="Official",
        provider=provider,
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=True,
        is_private=False,
        is_public=False,
        created_at=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return DBLLMModel(**data)


def _providers(providers):
    return patch(
        "routers.api_keys.user_api_key_service.get_user_available_providers_async",
        new=AsyncMock(return_value=providers),
    )


def _org_providers(providers):
    """Patch the org-context provider resolver (official pass under org
    context). The custom pass reads require_private_keys / the shared
    credentials directly from the DB, so those stay real."""
    return patch(
        "services.org_api_key_service.org_api_key_service."
        "get_available_providers_for_context_async",
        new=AsyncMock(return_value=providers),
    )


def _make_org(require_private_keys=None) -> Organization:
    uid = _uid()
    settings = None
    if require_private_keys is not None:
        settings = {"require_private_keys": require_private_keys}
    return Organization(
        id=f"org-{uid[:8]}",
        name=f"Org {uid[:8]}",
        display_name=f"Org {uid[:8]}",
        slug=f"org-{uid[:8]}",
        settings=settings,
        is_active=True,
    )


async def _seed_org_shared_model(async_test_db, *, require_private_keys):
    """Caller (member) + org + a private custom model shared with the org."""
    caller = _make_user()
    owner = _make_user()
    org = _make_org(require_private_keys=require_private_keys)
    async_test_db.add_all([caller, owner, org])
    await async_test_db.flush()
    model = _make_custom_model(owner.id, requires_api_key=True)
    async_test_db.add(model)
    await async_test_db.flush()
    async_test_db.add_all(
        [
            OrganizationMembership(
                id=_uid(),
                user_id=caller.id,
                organization_id=org.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=True,
            ),
            ModelOrganization(id=_uid(), model_id=model.id, organization_id=org.id),
        ]
    )
    await async_test_db.commit()
    return caller, org, model


class TestAvailableModelsOrgCredentialSource:
    """The custom pass honors the org shared credential ONLY in org-pays mode
    (require_private_keys False); the user's own key always wins the
    credential_source."""

    @pytest.mark.asyncio
    async def test_org_shared_credential_satisfies_in_org_pays_mode(
        self, async_test_client, async_test_db
    ):
        caller, org, model = await _seed_org_shared_model(
            async_test_db, require_private_keys=False
        )
        async_test_db.add(
            CustomModelOrgCredential(
                id=_uid(),
                organization_id=org.id,
                model_id=model.id,
                encrypted_api_key="ciphertext",
            )
        )
        await async_test_db.commit()

        with _as_user(caller), _org_providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": org.id},
            )
        assert resp.status_code == status.HTTP_200_OK
        entry = {m["id"]: m for m in resp.json()}[model.id]
        assert entry["has_credential"] is True
        assert entry["credential_source"] == "org"

    @pytest.mark.asyncio
    async def test_org_shared_credential_ignored_in_private_mode(
        self, async_test_client, async_test_db
    ):
        caller, org, model = await _seed_org_shared_model(
            async_test_db, require_private_keys=True
        )
        async_test_db.add(
            CustomModelOrgCredential(
                id=_uid(),
                organization_id=org.id,
                model_id=model.id,
                encrypted_api_key="ciphertext",
            )
        )
        await async_test_db.commit()

        with _as_user(caller), _org_providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": org.id},
            )
        entry = {m["id"]: m for m in resp.json()}[model.id]
        # require_private_keys True → shared key never counts.
        assert entry["has_credential"] is False
        assert entry["credential_source"] is None

    @pytest.mark.asyncio
    async def test_user_own_key_wins_credential_source(
        self, async_test_client, async_test_db
    ):
        caller, org, model = await _seed_org_shared_model(
            async_test_db, require_private_keys=False
        )
        async_test_db.add_all(
            [
                CustomModelOrgCredential(
                    id=_uid(),
                    organization_id=org.id,
                    model_id=model.id,
                    encrypted_api_key="org-ciphertext",
                ),
                CustomModelCredential(
                    id=_uid(),
                    user_id=caller.id,
                    model_id=model.id,
                    encrypted_api_key="user-ciphertext",
                ),
            ]
        )
        await async_test_db.commit()

        with _as_user(caller), _org_providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": org.id},
            )
        entry = {m["id"]: m for m in resp.json()}[model.id]
        assert entry["has_credential"] is True
        assert entry["credential_source"] == "user"

    @pytest.mark.asyncio
    async def test_no_org_context_source_is_user_or_none(
        self, async_test_client, async_test_db
    ):
        # Without an org header the field still exists; org key is irrelevant.
        user = _make_user()
        model = _make_custom_model(user.id, requires_api_key=False)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user), _providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        entry = {m["id"]: m for m in resp.json()}[model.id]
        assert entry["has_credential"] is False
        assert entry["credential_source"] is None


class TestAvailableModelsCustomPass:
    @pytest.mark.asyncio
    async def test_keyless_custom_visible_without_credential(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id, requires_api_key=False)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user), _providers([]):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)  # stays a flat array
        by_id = {m["id"]: m for m in data}
        assert model.id in by_id
        entry = by_id[model.id]
        assert entry["is_official"] is False
        assert entry["requires_api_key"] is False
        assert entry["has_credential"] is False
        assert entry["base_url"] == model.base_url
        assert entry["created_by"] == user.id

    @pytest.mark.asyncio
    async def test_keyed_custom_visible_with_credential_flag(
        self, async_test_client, async_test_db
    ):
        # A visible keyed custom model is ALWAYS listed — the picker needs
        # it to render a disabled "add your key" row rather than silently
        # drop a model a project may be configured to use. has_credential
        # flips false -> true once the caller stores a key; the worker (not
        # this endpoint) is what refuses to run a keyless requires_api_key
        # model.
        user = _make_user()
        model = _make_custom_model(user.id, requires_api_key=True)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user), _providers([]):
            before = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        before_by_id = {m["id"]: m for m in before.json()}
        assert model.id in before_by_id
        assert before_by_id[model.id]["has_credential"] is False
        assert before_by_id[model.id]["requires_api_key"] is True

        async_test_db.add(
            CustomModelCredential(
                id=_uid(), user_id=user.id, model_id=model.id,
                encrypted_api_key="ciphertext",
            )
        )
        await async_test_db.commit()

        with _as_user(user), _providers([]):
            after = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        by_id = {m["id"]: m for m in after.json()}
        assert model.id in by_id
        assert by_id[model.id]["has_credential"] is True

    @pytest.mark.asyncio
    async def test_foreign_private_custom_absent(
        self, async_test_client, async_test_db
    ):
        owner = _make_user()
        caller = _make_user()
        model = _make_custom_model(owner.id, requires_api_key=False)
        async_test_db.add_all([owner, caller])
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(caller), _providers([]):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        assert model.id not in {m["id"] for m in response.json()}

    @pytest.mark.asyncio
    async def test_inactive_custom_absent_even_with_credential(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id, requires_api_key=False, is_active=False)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user), _providers([]):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        assert model.id not in {m["id"] for m in response.json()}

    @pytest.mark.asyncio
    async def test_official_entries_flagged_and_provider_filtered(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        with_key = _make_official_model(provider="openai")
        without_key = _make_official_model(provider="anthropic")
        async_test_db.add_all([user, with_key, without_key])
        await async_test_db.commit()

        with _as_user(user), _providers(["openai"]):
            response = await async_test_client.get(
                "/api/users/api-keys/available-models"
            )
        assert response.status_code == status.HTTP_200_OK
        by_id = {m["id"]: m for m in response.json()}
        assert with_key.id in by_id
        assert by_id[with_key.id]["is_official"] is True
        # Provider-key filtering is unchanged for officials.
        assert without_key.id not in by_id


class TestAvailableModelsNonMemberOrgSuppressed:
    """X-Organization-Context is caller-supplied and unvalidated, so the org
    shared-credential annotation is honored ONLY for ACTIVE members of that
    org. A non-member passing another org's id must not learn whether that org
    has provisioned a shared credential for a PUBLIC custom model."""

    async def _seed_public_model_with_org_cred(self, async_test_db):
        """Owner + a PUBLIC custom model + org A (shared-billing) that has a
        shared credential for the model. Returns (org_a, model)."""
        owner = _make_user()
        org_a = _make_org(require_private_keys=False)  # org-pays mode
        async_test_db.add_all([owner, org_a])
        await async_test_db.flush()
        model = _make_custom_model(
            owner.id, requires_api_key=True, is_public=True, is_private=False
        )
        async_test_db.add(model)
        await async_test_db.flush()
        async_test_db.add(
            CustomModelOrgCredential(
                id=_uid(),
                organization_id=org_a.id,
                model_id=model.id,
                encrypted_api_key="ciphertext",
            )
        )
        await async_test_db.commit()
        return org_a, model

    @pytest.mark.asyncio
    async def test_non_member_org_context_is_suppressed(
        self, async_test_client, async_test_db
    ):
        org_a, model = await self._seed_public_model_with_org_cred(async_test_db)
        outsider = _make_user()  # NOT a member of org A
        async_test_db.add(outsider)
        await async_test_db.commit()

        with _as_user(outsider), _org_providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": org_a.id},
            )
        assert resp.status_code == status.HTTP_200_OK
        entry = {m["id"]: m for m in resp.json()}[model.id]
        # Org annotation suppressed for the non-member: source not "org",
        # has_credential reflects only the (absent) user key.
        assert entry["credential_source"] != "org"
        assert entry["credential_source"] is None
        assert entry["has_credential"] is False

    @pytest.mark.asyncio
    async def test_active_member_org_context_is_honored(
        self, async_test_client, async_test_db
    ):
        # Contrast: an ACTIVE member of the SAME org, same public model + org
        # credential → the org annotation IS applied.
        org_a, model = await self._seed_public_model_with_org_cred(async_test_db)
        member = _make_user()
        async_test_db.add(member)
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=member.id,
                organization_id=org_a.id,
                role=OrganizationRole.CONTRIBUTOR,
                is_active=True,
            )
        )
        await async_test_db.commit()

        with _as_user(member), _org_providers([]):
            resp = await async_test_client.get(
                "/api/users/api-keys/available-models",
                headers={"X-Organization-Context": org_a.id},
            )
        entry = {m["id"]: m for m in resp.json()}[model.id]
        assert entry["credential_source"] == "org"
        assert entry["has_credential"] is True
