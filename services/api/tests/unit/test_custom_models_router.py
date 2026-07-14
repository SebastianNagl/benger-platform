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
from models import CustomModelCredential
from models import Generation as DBGeneration
from models import LLMModel as DBLLMModel
from models import ModelOrganization, Organization, OrganizationMembership
from models import ResponseGeneration as DBResponseGeneration
from models import User


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


def _make_org() -> Organization:
    uid = _uid()
    return Organization(
        id=uid,
        name=f"Org {uid[:8]}",
        display_name=f"Org {uid[:8]}",
        slug=f"cm-org-{uid[:8]}",
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
        # Org links removed; credentials kept (cascade only on hard delete).
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
        # credential. B's probe must send B's key, never A's.
        a, b, org, model = await _seed_shared_setup(async_test_db)
        async_test_db.add_all(
            [
                CustomModelCredential(
                    id=_uid(), user_id=a.id, model_id=model.id,
                    encrypted_api_key="OWNER-CIPHERTEXT",
                ),
                CustomModelCredential(
                    id=_uid(), user_id=b.id, model_id=model.id,
                    encrypted_api_key="MEMBER-CIPHERTEXT",
                ),
            ]
        )
        await async_test_db.commit()

        seen = {}

        async def _spy(url, api_key=None, **k):
            seen["api_key"] = api_key
            return (True, "ok", "success")

        # The stored ciphertext decrypts to garbage, so assert on identity by
        # patching get_credential_async to echo which user was asked.
        async def _fake_get_cred(db, user_id, model_id):
            return f"KEY-FOR-{user_id}"

        monkeypatch.setattr(
            "routers.custom_models.validate_openai_compatible_endpoint", _spy
        )
        monkeypatch.setattr(
            "routers.custom_models.get_credential_async", _fake_get_cred
        )

        with _as_user(b):
            resp = await async_test_client.post(
                f"/api/custom-models/{model.id}/test", json={}
            )
        assert resp.status_code == status.HTTP_200_OK
        assert seen["api_key"] == f"KEY-FOR-{b.id}"
        assert a.id not in (seen["api_key"] or "")

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
