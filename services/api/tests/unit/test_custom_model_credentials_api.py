"""
Tests for the per-user custom-model credential endpoints
(PUT/GET/DELETE /api/custom-models/{model_id}/credential).

Credential material must NEVER appear in any response body — asserted on the
full serialized JSON of every response in the round-trip test.
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
from models import LLMModel as DBLLMModel
from models import User

from custom_model_credential_service import get_credential_async


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
        username=f"cred-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Credential User",
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


SECRET = "sk-credential-roundtrip-secret"


class TestCredentialRoundTrip:
    @pytest.mark.asyncio
    async def test_put_get_delete_and_no_key_leak(
        self, async_test_client, async_test_db
    ):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            # Initially: no credential.
            status_resp = await async_test_client.get(
                f"/api/custom-models/{model.id}/credential"
            )
            assert status_resp.status_code == status.HTTP_200_OK
            assert status_resp.json() == {"has_credential": False, "updated_at": None}

            # PUT stores it.
            put_resp = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": SECRET},
            )
            assert put_resp.status_code == status.HTTP_200_OK
            assert put_resp.json() == {"has_credential": True}

            # GET reports status + timestamp, never the key.
            status_resp2 = await async_test_client.get(
                f"/api/custom-models/{model.id}/credential"
            )
            assert status_resp2.status_code == status.HTTP_200_OK
            body = status_resp2.json()
            assert body["has_credential"] is True
            assert body["updated_at"] is not None

            # The model detail response must not leak it either.
            detail_resp = await async_test_client.get(
                f"/api/custom-models/{model.id}"
            )
            assert detail_resp.json()["has_credential"] is True

            # DELETE removes it; second DELETE is 404.
            del_resp = await async_test_client.delete(
                f"/api/custom-models/{model.id}/credential"
            )
            assert del_resp.status_code == status.HTTP_200_OK
            assert del_resp.json() == {"has_credential": False}
            del_resp2 = await async_test_client.delete(
                f"/api/custom-models/{model.id}/credential"
            )
            assert del_resp2.status_code == status.HTTP_404_NOT_FOUND

        # The raw key never appeared in ANY response body.
        for resp in (status_resp, put_resp, status_resp2, detail_resp, del_resp, del_resp2):
            assert SECRET not in resp.text

    @pytest.mark.asyncio
    async def test_put_upsert_overwrites(self, async_test_client, async_test_db):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            first = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": "sk-first"},
            )
            second = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": "sk-second"},
            )
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK

        # Exactly one row, decrypting to the second key.
        rows = (
            await async_test_db.execute(
                select(CustomModelCredential).where(
                    CustomModelCredential.model_id == model.id,
                    CustomModelCredential.user_id == user.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        decrypted = await get_credential_async(async_test_db, user.id, model.id)
        assert decrypted == "sk-second"

    @pytest.mark.asyncio
    async def test_empty_api_key_rejected(self, async_test_client, async_test_db):
        user = _make_user()
        model = _make_custom_model(user.id)
        async_test_db.add(user)
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(user):
            # Pydantic min_length rejects "" outright.
            empty = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": ""},
            )
            # Whitespace passes min_length but the service refuses to store it.
            blank = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": "   "},
            )
        assert empty.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert blank.status_code == status.HTTP_400_BAD_REQUEST


class TestCredentialAccess:
    @pytest.mark.asyncio
    async def test_non_visible_user_cannot_touch_credentials(
        self, async_test_client, async_test_db
    ):
        owner = _make_user()
        outsider = _make_user()
        model = _make_custom_model(owner.id)  # private to owner
        async_test_db.add_all([owner, outsider])
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(outsider):
            put_resp = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": "sk-nope"},
            )
            get_resp = await async_test_client.get(
                f"/api/custom-models/{model.id}/credential"
            )
            del_resp = await async_test_client.delete(
                f"/api/custom-models/{model.id}/credential"
            )
        assert put_resp.status_code in (403, 404)
        assert get_resp.status_code in (403, 404)
        assert del_resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_view_access_suffices_for_own_credential(
        self, async_test_client, async_test_db
    ):
        """Every allowed user brings their own key — 'view' is the bar."""
        owner = _make_user()
        other = _make_user()
        model = _make_custom_model(owner.id, is_private=False, is_public=True)
        async_test_db.add_all([owner, other])
        await async_test_db.flush()
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(other):
            put_resp = await async_test_client.put(
                f"/api/custom-models/{model.id}/credential",
                json={"api_key": "sk-other-users-own"},
            )
        assert put_resp.status_code == status.HTTP_200_OK

        # Stored under the caller's id, not the owner's.
        rows = (
            await async_test_db.execute(
                select(CustomModelCredential.user_id).where(
                    CustomModelCredential.model_id == model.id
                )
            )
        ).all()
        assert [r[0] for r in rows] == [other.id]
