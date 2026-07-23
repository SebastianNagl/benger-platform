"""
Tests for the custom (BYOM) model router (routers/custom_models.py).

Uses the real async fixtures (async_test_client / async_test_db) with
require_user overridden per-test via _as_user, mirroring
test_api_keys_router.py / test_generation_flow.py.

CUSTOM_MODEL_ALLOW_PRIVATE_URLS is set for the whole module so the SSRF
guard skips DNS resolution (tests use RFC1918 literals); structural URL
checks still run, which is what the 400-path tests exercise.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi import status
from sqlalchemy import select

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import CustomModelCredential, CustomModelOrgCredential
from models import Generation as DBGeneration
from models import LLMModel as DBLLMModel
from models import ModelOrganization, Organization, OrganizationMembership
from models import ResponseGeneration as DBResponseGeneration
from models import User

from custom_model_credential_service import set_credential_async
from custom_model_org_credential_service import set_org_credential_async


@pytest.fixture(autouse=True)
def _allow_private_urls(monkeypatch):
    monkeypatch.setenv("CUSTOM_MODEL_ALLOW_PRIVATE_URLS", "1")


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


def _make_user(*, is_superadmin=False) -> User:
    uid = _uid()
    return User(
        id=uid,
        username=f"cm-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Custom Model User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_org(**overrides) -> Organization:
    uid = _uid()
    data = dict(
        id=uid,
        name=f"Org {uid[:8]}",
        display_name=f"Org {uid[:8]}",
        slug=f"cm-org-{uid[:8]}",
        created_at=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return Organization(**data)


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


def _make_official_model(**overrides) -> DBLLMModel:
    data = dict(
        id=f"test-official-{_uid()[:8]}",
        name="Official",
        provider="openai",
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


async def _seed_shared_setup(db):
    """Creator A, org-member B (active), org O; model by A shared with O."""
    a, b = _make_user(), _make_user()
    org = _make_org()
    db.add_all([a, b, org])
    await db.flush()
    db.add(
        OrganizationMembership(
            id=_uid(), user_id=b.id, organization_id=org.id,
            role="CONTRIBUTOR", is_active=True,
        )
    )
    model = _make_custom_model(a.id, is_private=False)
    db.add(model)
    await db.flush()
    db.add(
        ModelOrganization(
            id=_uid(), model_id=model.id, organization_id=org.id, assigned_by=a.id
        )
    )
    await db.commit()
    return a, b, org, model


class TestCreateCustomModel:
    @pytest.mark.asyncio
    async def test_create_success(self, async_test_client, async_test_db):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "My Llama",
                    "base_url": "http://10.10.3.7:8000/v1",
                    "endpoint_model_name": "llama-3-8b",
                },
            )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["id"].startswith("custom-")
        assert data["provider"] == "Custom"
        assert data["is_official"] is False
        assert data["is_private"] is True
        assert data["is_public"] is False
        assert data["is_active"] is True
        assert data["can_edit"] is True
        assert data["has_credential"] is False
        assert data["created_by"] == user.id
        assert data["requires_api_key"] is True

    @pytest.mark.asyncio
    async def test_create_with_api_key_stores_credential(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "My Llama",
                    "base_url": "http://10.10.3.7:8000/v1",
                    "endpoint_model_name": "llama-3-8b",
                    "api_key": "sk-super-secret-key",
                },
            )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["has_credential"] is True
        # Credential material must never be serialized.
        assert "sk-super-secret-key" not in response.text

        row = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == data["id"],
                    CustomModelCredential.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        assert row is not None
        assert "sk-super-secret-key" not in (row.encrypted_api_key or "")

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_url(self, async_test_client, async_test_db):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "Bad",
                    # Full completions route pasted — structural rejection
                    # that applies even with private URLs allowed.
                    "base_url": "http://10.10.3.7:8000/v1/chat/completions",
                    "endpoint_model_name": "llama-3-8b",
                },
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "chat/completions" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_rejects_overlong_base_url_422(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "Too Long",
                    # Over the llm_models.base_url String(500) cap — must 422
                    # at request validation instead of 500 at commit.
                    "base_url": "http://h.example/" + "a" * 500,
                    "endpoint_model_name": "llama-3-8b",
                },
            )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestParameterConstraintsValidation:
    """The CustomModelCreate/Update validator rejects malformed
    parameter_constraints shapes with a 422 instead of silently storing a
    config the readers will ignore. Well-formed and absent are accepted."""

    _MALFORMED = [
        {"temperature": "high"},              # temperature must be an object
        {"temperature": {"min": "warm"}},     # min must be numeric
        {"temperature": {"supported": "yes"}},  # supported must be a bool
        {"max_tokens": {"max": "big"}},       # max must be numeric
        {"max_tokens": "8000"},               # max_tokens must be an object
        {"seed": True},                       # seed must be an object
    ]

    _WELL_FORMED = {
        "temperature": {"supported": False, "required_value": 1},
        "max_tokens": {"max": 8000, "default": 2000},
        "seed": {"supported": True},
        # Unknown key allowed (forward-compat).
        "some_future_key": {"whatever": 1},
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", _MALFORMED)
    async def test_create_rejects_malformed_constraints(
        self, async_test_client, async_test_db, bad
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "Bad Constraints",
                    "base_url": "http://10.10.3.7:8000/v1",
                    "endpoint_model_name": "llama-3-8b",
                    "parameter_constraints": bad,
                },
            )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_accepts_well_formed_constraints(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "Good Constraints",
                    "base_url": "http://10.10.3.7:8000/v1",
                    "endpoint_model_name": "llama-3-8b",
                    "parameter_constraints": self._WELL_FORMED,
                },
            )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["parameter_constraints"] == self._WELL_FORMED

    @pytest.mark.asyncio
    async def test_create_accepts_absent_constraints(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.post(
                "/api/custom-models/",
                json={
                    "name": "No Constraints",
                    "base_url": "http://10.10.3.7:8000/v1",
                    "endpoint_model_name": "llama-3-8b",
                },
            )
        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", _MALFORMED)
    async def test_update_rejects_malformed_constraints(
        self, async_test_client, async_test_db, bad
    ):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                json={"parameter_constraints": bad},
            )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_accepts_well_formed_constraints(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                json={"parameter_constraints": {"max_tokens": {"max": 16000}}},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["parameter_constraints"] == {"max_tokens": {"max": 16000}}


class TestOrgSharedAccess:
    @pytest.mark.asyncio
    async def test_org_member_can_read_but_not_modify(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)

        with _as_user(b):
            get_resp = await async_test_client.get(f"/api/custom-models/{model.id}")
            patch_resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}", json={"name": "hijacked"}
            )
            delete_resp = await async_test_client.delete(
                f"/api/custom-models/{model.id}"
            )
            vis_resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_public": True},
            )

        assert get_resp.status_code == status.HTTP_200_OK
        data = get_resp.json()
        assert data["can_edit"] is False
        assert data["organization_ids"] == [org.id]
        assert patch_resp.status_code == status.HTTP_403_FORBIDDEN
        assert delete_resp.status_code == status.HTTP_403_FORBIDDEN
        assert vis_resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, async_test_client, async_test_db):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        outsider = _make_user()
        async_test_db.add(outsider)
        await async_test_db.commit()

        with _as_user(outsider):
            response = await async_test_client.get(f"/api/custom-models/{model.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_list_includes_shared_model_for_member(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)

        with _as_user(b):
            response = await async_test_client.get("/api/custom-models/")
        assert response.status_code == status.HTTP_200_OK
        by_id = {m["id"]: m for m in response.json()}
        assert model.id in by_id
        assert by_id[model.id]["can_edit"] is False
        assert by_id[model.id]["created_by_username"] == a.username


class TestVisibility:
    @pytest.mark.asyncio
    async def test_org_share_shape(self, async_test_client, async_test_db):
        user = _make_user()
        org = _make_org()
        model = _make_custom_model(user.id)
        async_test_db.add_all([user, org])
        await async_test_db.flush()
        # Org-sharing requires the sharer to be an ACTIVE member of every
        # target org (non-superadmins).
        async_test_db.add(
            OrganizationMembership(
                id=_uid(), user_id=user.id, organization_id=org.id,
                role="CONTRIBUTOR", is_active=True,
            )
        )
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_private"] is False
        assert data["is_public"] is False
        assert data["organization_ids"] == [org.id]

        link = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalar_one_or_none()
        assert link is not None
        assert link.organization_id == org.id
        assert link.assigned_by == user.id

    @pytest.mark.asyncio
    async def test_org_share_without_membership_403(
        self, async_test_client, async_test_db
    ):
        # Sharing plants a creator-controlled endpoint inside an org whose
        # admins may then provision an org key that flows to it — so a
        # non-member must not be able to inject a model into a foreign org.
        user = _make_user()
        org = _make_org()
        model = _make_custom_model(user.id)
        async_test_db.add_all([user, org])
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == (
            "You can only share a model with organizations you are "
            "an active member of"
        )
        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalars().all()
        assert links == []

    @pytest.mark.asyncio
    async def test_org_share_with_inactive_membership_403(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        org = _make_org()
        model = _make_custom_model(user.id)
        async_test_db.add_all([user, org])
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(), user_id=user.id, organization_id=org.id,
                role="CONTRIBUTOR", is_active=False,
            )
        )
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalars().all()
        assert links == []

    @pytest.mark.asyncio
    async def test_superadmin_org_share_without_membership_200(
        self, async_test_client, async_test_db
    ):
        superadmin = _make_user(is_superadmin=True)
        org = _make_org()
        model = _make_custom_model(superadmin.id)
        async_test_db.add_all([superadmin, org])
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(superadmin):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": [org.id]},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["organization_ids"] == [org.id]

    @pytest.mark.asyncio
    async def test_org_share_partial_membership_shares_nothing(
        self, async_test_client, async_test_db
    ):
        # Member of org A but not org B, sharing into [A, B]: all-or-nothing —
        # 403 and NEITHER link row is created (not even A's).
        user = _make_user()
        org_a, org_b = _make_org(), _make_org()
        model = _make_custom_model(user.id)
        async_test_db.add_all([user, org_a, org_b])
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(), user_id=user.id, organization_id=org_a.id,
                role="CONTRIBUTOR", is_active=True,
            )
        )
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={
                    "is_private": False,
                    "organization_ids": [org_a.id, org_b.id],
                },
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalars().all()
        assert links == []
        await async_test_db.refresh(model)
        assert model.is_private is True

    @pytest.mark.asyncio
    async def test_public_shape_clears_org_rows(self, async_test_client, async_test_db):
        a, b, org, model = await _seed_shared_setup(async_test_db)

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_public": True},
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_public"] is True
        assert data["is_private"] is False
        assert data["organization_ids"] == []

        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalars().all()
        assert links == []

    @pytest.mark.asyncio
    async def test_private_shape_clears_org_rows(self, async_test_client, async_test_db):
        a, b, org, model = await _seed_shared_setup(async_test_db)

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": True},
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["is_private"] is True
        assert data["is_public"] is False
        assert data["organization_ids"] == []

        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model.id
                )
            )
        ).scalars().all()
        assert links == []

    @pytest.mark.asyncio
    async def test_private_and_public_400(self, async_test_client, async_test_db):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": True, "is_public": True},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_unknown_org_404(self, async_test_client, async_test_db):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": ["no-such-org"]},
            )
        # The caller has no memberships at all, so this also pins the check
        # order: unknown org is 404, evaluated BEFORE the membership 403.
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "no-such-org" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_org_ids_400(self, async_test_client, async_test_db):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": []},
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestDelete:
    @pytest.mark.asyncio
    async def test_hard_delete_when_unreferenced(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.flush()
        async_test_db.add(
            CustomModelCredential(
                id=_uid(), user_id=user.id, model_id=model.id,
                encrypted_api_key="ciphertext",
            )
        )
        await async_test_db.commit()
        model_id = model.id

        with _as_user(user):
            response = await async_test_client.delete(f"/api/custom-models/{model_id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"deleted": "hard"}

        async_test_db.expire_all()
        row = (
            await async_test_db.execute(
                select(DBLLMModel).where(DBLLMModel.id == model_id)
            )
        ).scalar_one_or_none()
        assert row is None
        # FK cascade removed the credential.
        cred = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model_id
                )
            )
        ).scalar_one_or_none()
        assert cred is None

    @pytest.mark.asyncio
    async def test_soft_delete_when_generations_reference_it(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        model_id = model.id

        # A child Generation row references the custom model id.
        parent_id = _uid()
        async_test_db.add(
            DBResponseGeneration(
                id=parent_id, project_id="p-x", model_id="gpt-4o",
                status="completed", created_by=a.id,
            )
        )
        await async_test_db.flush()
        async_test_db.add(
            DBGeneration(
                id=_uid(), generation_id=parent_id, task_id="t-x",
                model_id=model_id, run_index=0,
                case_data="case", response_content="resp",
            )
        )
        async_test_db.add(
            CustomModelCredential(
                id=_uid(), user_id=b.id, model_id=model_id,
                encrypted_api_key="ciphertext",
            )
        )
        async_test_db.add(
            CustomModelOrgCredential(
                id=_uid(), organization_id=org.id, model_id=model_id,
                encrypted_api_key="org-ciphertext",
            )
        )
        await async_test_db.commit()

        with _as_user(a):
            response = await async_test_client.delete(f"/api/custom-models/{model_id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"deleted": "soft"}

        async_test_db.expire_all()
        row = (
            await async_test_db.execute(
                select(DBLLMModel).where(DBLLMModel.id == model_id)
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.is_active is False
        assert row.is_private is True
        assert row.is_public is False
        # Org links removed; PERSONAL credentials kept (cascade only on hard
        # delete) — but ORG shared credentials are dropped along with the
        # shares, or they'd linger un-manageable and re-attach on a re-share.
        links = (
            await async_test_db.execute(
                select(ModelOrganization).where(
                    ModelOrganization.model_id == model_id
                )
            )
        ).scalars().all()
        assert links == []
        cred = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model_id
                )
            )
        ).scalar_one_or_none()
        assert cred is not None
        org_creds = (
            await async_test_db.execute(
                select(CustomModelOrgCredential).where(
                    CustomModelOrgCredential.model_id == model_id
                )
            )
        ).scalars().all()
        assert org_creds == []

    @pytest.mark.asyncio
    async def test_soft_deleted_row_listed_for_creator_only(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        model.is_active = False
        await async_test_db.commit()

        with _as_user(a):
            creator_list = await async_test_client.get("/api/custom-models/")
        with _as_user(b):
            member_list = await async_test_client.get("/api/custom-models/")

        creator_ids = {m["id"]: m for m in creator_list.json()}
        assert model.id in creator_ids
        assert creator_ids[model.id]["is_active"] is False
        assert model.id not in {m["id"] for m in member_list.json()}


class TestBaseUrlPatch:
    @pytest.mark.asyncio
    async def test_base_url_change_wipes_other_users_credentials(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        model_id = model.id
        creator_id, member_id = a.id, b.id
        async_test_db.add_all(
            [
                CustomModelCredential(
                    id=_uid(), user_id=creator_id, model_id=model_id,
                    encrypted_api_key="creator-cipher",
                ),
                CustomModelCredential(
                    id=_uid(), user_id=member_id, model_id=model_id,
                    encrypted_api_key="member-cipher",
                ),
            ]
        )
        await async_test_db.commit()

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model_id}",
                json={"base_url": "http://10.20.30.40:9000/v1"},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["base_url"] == "http://10.20.30.40:9000/v1"

        async_test_db.expire_all()
        creds = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model_id
                )
            )
        ).scalars().all()
        assert [c.user_id for c in creds] == [creator_id]

    @pytest.mark.asyncio
    async def test_unchanged_base_url_keeps_credentials(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        async_test_db.add(
            CustomModelCredential(
                id=_uid(), user_id=b.id, model_id=model.id,
                encrypted_api_key="member-cipher",
            )
        )
        await async_test_db.commit()

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                json={"base_url": model.base_url, "name": "renamed"},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "renamed"

        creds = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model.id
                )
            )
        ).scalars().all()
        assert len(creds) == 1

    @pytest.mark.asyncio
    async def test_base_url_change_wipes_org_credentials(
        self, async_test_client, async_test_db
    ):
        # Org shared keys were consented for the OLD host; unlike personal
        # credentials there is no editor exception — a base_url change drops
        # them ALL, while the editor's own personal credential is spared.
        a, b, org, model = await _seed_shared_setup(async_test_db)
        model_id, creator_id = model.id, a.id
        async_test_db.add_all(
            [
                CustomModelCredential(
                    id=_uid(), user_id=creator_id, model_id=model_id,
                    encrypted_api_key="creator-cipher",
                ),
                CustomModelOrgCredential(
                    id=_uid(), organization_id=org.id, model_id=model_id,
                    encrypted_api_key="org-cipher",
                ),
            ]
        )
        await async_test_db.commit()

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model_id}",
                json={"base_url": "http://10.20.30.40:9000/v1"},
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["base_url"] == "http://10.20.30.40:9000/v1"

        async_test_db.expire_all()
        org_creds = (
            await async_test_db.execute(
                select(CustomModelOrgCredential).where(
                    CustomModelOrgCredential.model_id == model_id
                )
            )
        ).scalars().all()
        assert org_creds == []
        creds = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model_id
                )
            )
        ).scalars().all()
        assert [c.user_id for c in creds] == [creator_id]

    @pytest.mark.asyncio
    async def test_unchanged_base_url_keeps_org_credentials(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await _seed_shared_setup(async_test_db)
        async_test_db.add(
            CustomModelOrgCredential(
                id=_uid(), organization_id=org.id, model_id=model.id,
                encrypted_api_key="org-cipher",
            )
        )
        await async_test_db.commit()

        with _as_user(a):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                json={"base_url": model.base_url, "name": "renamed"},
            )
        assert response.status_code == status.HTTP_200_OK

        org_creds = (
            await async_test_db.execute(
                select(CustomModelOrgCredential).where(
                    CustomModelOrgCredential.model_id == model.id
                )
            )
        ).scalars().all()
        assert len(org_creds) == 1

    @pytest.mark.asyncio
    async def test_patch_rejects_overlong_base_url_422(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            response = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                # Over the llm_models.base_url String(500) cap — must 422 at
                # request validation instead of 500 at commit.
                json={"base_url": "http://h.example/" + "a" * 500},
            )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        await async_test_db.refresh(model)
        assert model.base_url == "http://10.10.3.7:8000/v1"


class TestOfficialRowsUntouchable:
    @pytest.mark.asyncio
    async def test_official_id_is_404_on_custom_endpoints(
        self, async_test_client, async_test_db
    ):
        user = _make_user(is_superadmin=True)
        official = _make_official_model()
        async_test_db.add_all([user, official])
        await async_test_db.commit()

        with _as_user(user):
            get_resp = await async_test_client.get(
                f"/api/custom-models/{official.id}"
            )
            patch_resp = await async_test_client.patch(
                f"/api/custom-models/{official.id}", json={"name": "nope"}
            )
            delete_resp = await async_test_client.delete(
                f"/api/custom-models/{official.id}"
            )

        assert get_resp.status_code == status.HTTP_404_NOT_FOUND
        assert patch_resp.status_code == status.HTTP_404_NOT_FOUND
        assert delete_resp.status_code == status.HTTP_404_NOT_FOUND


class TestConnectionProbe:
    """The two /test endpoints. Security contract: url_guard runs before any
    outbound request, and /{id}/test uses strictly the CALLER's credential,
    never the model owner's. Real network is stubbed by patching the probe
    functions at the router module."""

    @pytest.mark.asyncio
    async def test_adhoc_probe_rejects_bad_url_before_network(
        self, async_test_client, async_test_db, monkeypatch
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.commit()

        called = {"probe": False}

        async def _spy(*a, **k):
            called["probe"] = True
            return (True, "ok", "success")

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )

        with _as_user(user):
            resp = await async_test_client.post(
                "/api/custom-models/test",
                json={"base_url": "ftp://not-http/v1"},
            )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        # url_guard rejected structurally -> the network probe never ran.
        assert called["probe"] is False

    @pytest.mark.asyncio
    async def test_saved_probe_uses_callers_credential_not_owners(
        self, async_test_client, async_test_db, monkeypatch
    ):
        # Owner A shares a keyed model with org O; member B has their OWN
        # credential. B's probe must send B's key, never A's. Real creds are
        # stored via the service so the router's key resolution decrypts the
        # actual Fernet ciphertexts (there is no per-user getter left on the
        # router module to patch).
        a, b, org, model = await _seed_shared_setup(async_test_db)
        assert await set_credential_async(
            async_test_db, a.id, model.id, "sk-owner-personal"
        ) is True
        assert await set_credential_async(
            async_test_db, b.id, model.id, "sk-member-personal"
        ) is True

        seen = {}

        async def _spy(url, api_key=None, **k):
            seen["api_key"] = api_key
            return (True, "ok", "success")

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )

        with _as_user(b):
            resp = await async_test_client.post(
                f"/api/custom-models/{model.id}/test", json={}
            )
        assert resp.status_code == status.HTTP_200_OK
        assert seen["api_key"] == "sk-member-personal"
        assert seen["api_key"] != "sk-owner-personal"

    @pytest.mark.asyncio
    async def test_patch_base_url_rejects_bad_url(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        async_test_db.add(user)
        await async_test_db.flush()
        model = _make_custom_model(user.id)
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}",
                json={"base_url": "http://x/v1/chat/completions"},
            )
        # url_guard rejects the /chat/completions suffix -> 400, not stored.
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        await async_test_db.refresh(model)
        assert model.base_url == "http://10.10.3.7:8000/v1"


class TestOrgCredentialAnnotationsAndTestFallback:
    """has_credential annotations + /{id}/test key fallback via ORG shared
    keys. The org route counts only when ALL hold: live ModelOrganization
    share, ACTIVE membership of the caller in that org, org in shared-billing
    mode (settings.require_private_keys falsy — defaults to True), and a
    stored org credential. A personal credential always wins."""

    ORG_SECRET = "sk-org-shared-secret"

    async def _seed_org_key_setup(
        self, db, *, org_settings, org_key=ORG_SECRET
    ):
        """Creator A; active org-member B with NO personal credential; org
        with ``org_settings``; model by A shared with the org; org shared key
        stored via the real service (Fernet round-trip). Returns
        (a, b, org, model)."""
        a, b = _make_user(), _make_user()
        org = _make_org(settings=org_settings)
        db.add_all([a, b, org])
        await db.flush()
        db.add(
            OrganizationMembership(
                id=_uid(), user_id=b.id, organization_id=org.id,
                role="CONTRIBUTOR", is_active=True,
            )
        )
        model = _make_custom_model(a.id, is_private=False)
        db.add(model)
        await db.flush()
        db.add(
            ModelOrganization(
                id=_uid(), model_id=model.id, organization_id=org.id,
                assigned_by=a.id,
            )
        )
        await db.commit()
        if org_key is not None:
            assert await set_org_credential_async(db, org.id, model.id, org_key) is True
        return a, b, org, model

    @pytest.mark.asyncio
    async def test_get_has_credential_true_via_org_paying_share(
        self, async_test_client, async_test_db
    ):
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db, org_settings={"require_private_keys": False}
        )

        with _as_user(b):
            response = await async_test_client.get(f"/api/custom-models/{model.id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["has_credential"] is True
        # The shared key itself must never be serialized.
        assert self.ORG_SECRET not in response.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "org_settings", [{"require_private_keys": True}, None]
    )
    async def test_get_has_credential_false_without_org_pays_mode(
        self, async_test_client, async_test_db, org_settings
    ):
        # require_private_keys True — or absent, which DEFAULTS to True — means
        # the org key is not usable, so it must not annotate as a credential.
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db, org_settings=org_settings
        )

        with _as_user(b):
            response = await async_test_client.get(f"/api/custom-models/{model.id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["has_credential"] is False

    @pytest.mark.asyncio
    async def test_list_has_credential_agrees_with_single_get(
        self, async_test_client, async_test_db
    ):
        # Model 1 via an org-pays org (usable org key), model 2 via a
        # default-settings org (org key stored but NOT usable). List and
        # single-GET must annotate identically.
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db, org_settings={"require_private_keys": False}
        )
        org2 = _make_org(settings=None)
        async_test_db.add(org2)
        await async_test_db.flush()
        async_test_db.add(
            OrganizationMembership(
                id=_uid(), user_id=b.id, organization_id=org2.id,
                role="CONTRIBUTOR", is_active=True,
            )
        )
        model2 = _make_custom_model(a.id, is_private=False)
        async_test_db.add(model2)
        await async_test_db.flush()
        async_test_db.add(
            ModelOrganization(
                id=_uid(), model_id=model2.id, organization_id=org2.id,
                assigned_by=a.id,
            )
        )
        await async_test_db.commit()
        assert await set_org_credential_async(
            async_test_db, org2.id, model2.id, "sk-org2-secret"
        ) is True

        with _as_user(b):
            single_1 = await async_test_client.get(f"/api/custom-models/{model.id}")
            single_2 = await async_test_client.get(f"/api/custom-models/{model2.id}")
            listed = await async_test_client.get("/api/custom-models/")
        assert single_1.json()["has_credential"] is True
        assert single_2.json()["has_credential"] is False
        by_id = {m["id"]: m for m in listed.json()}
        assert by_id[model.id]["has_credential"] is True
        assert by_id[model2.id]["has_credential"] is False

    @pytest.mark.asyncio
    async def test_model_test_uses_org_key_when_no_personal(
        self, async_test_client, async_test_db, monkeypatch
    ):
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db,
            org_settings={"require_private_keys": False},
            org_key="org-secret",
        )

        seen = {}

        async def _spy(url, api_key=None, **k):
            seen["api_key"] = api_key
            return (True, "ok", "success")

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )

        with _as_user(b):
            resp = await async_test_client.post(
                f"/api/custom-models/{model.id}/test", json={}
            )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "success"
        assert seen["api_key"] == "org-secret"

    @pytest.mark.asyncio
    async def test_model_test_personal_key_wins_over_org(
        self, async_test_client, async_test_db, monkeypatch
    ):
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db,
            org_settings={"require_private_keys": False},
            org_key="org-secret",
        )
        assert await set_credential_async(
            async_test_db, b.id, model.id, "sk-personal-wins"
        ) is True

        seen = {}

        async def _spy(url, api_key=None, **k):
            seen["api_key"] = api_key
            return (True, "ok", "success")

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )

        with _as_user(b):
            resp = await async_test_client.post(
                f"/api/custom-models/{model.id}/test", json={}
            )
        assert resp.status_code == status.HTTP_200_OK
        assert seen["api_key"] == "sk-personal-wins"

    @pytest.mark.asyncio
    async def test_model_test_keyless_probe_when_no_usable_route(
        self, async_test_client, async_test_db, monkeypatch
    ):
        # An org key EXISTS but the org runs the default private-keys mode →
        # the org route is unusable. No personal key either → the probe runs
        # keyless (api_key None) and must not leak the org key or raise.
        a, b, org, model = await self._seed_org_key_setup(
            async_test_db, org_settings=None, org_key="org-secret"
        )

        seen = {"called": False}

        async def _spy(url, api_key=None, **k):
            seen["called"] = True
            seen["api_key"] = api_key
            return (True, "ok", "success")

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )

        with _as_user(b):
            resp = await async_test_client.post(
                f"/api/custom-models/{model.id}/test", json={}
            )
        assert resp.status_code == status.HTTP_200_OK
        assert seen["called"] is True
        assert seen["api_key"] is None
