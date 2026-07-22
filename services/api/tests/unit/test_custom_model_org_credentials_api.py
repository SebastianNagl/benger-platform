"""Tests for the org shared-credential endpoints
(PUT/GET/DELETE /api/organizations/{org}/custom-models/{model}/credential
and the sibling list endpoint).

Guards under test:
- ORG_ADMIN (or superadmin) only — a plain member or outsider is 403.
- the model must be a CUSTOM model shared with THIS org — an official model,
  an unshared model, or a missing model is 404.
- credential material NEVER appears in any response body.
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
from models import CustomModelOrgCredential
from models import LLMModel as DBLLMModel
from models import (
    ModelOrganization,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)

from custom_model_org_credential_service import get_org_credential_async


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


def _make_user(is_superadmin=False) -> User:
    uid = _uid()
    return User(
        id=uid,
        username=f"oc-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Org Cred User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _make_org() -> Organization:
    uid = _uid()
    return Organization(
        id=f"org-{uid[:8]}",
        name=f"Org {uid[:8]}",
        display_name=f"Org {uid[:8]}",
        slug=f"org-{uid[:8]}",
        settings=None,
        is_active=True,
    )


def _membership(user_id, org_id, role) -> OrganizationMembership:
    return OrganizationMembership(
        id=_uid(), user_id=user_id, organization_id=org_id, role=role, is_active=True
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


def _make_official_model() -> DBLLMModel:
    return DBLLMModel(
        id=f"official-{_uid()[:8]}",
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


def _share(model_id, org_id) -> ModelOrganization:
    return ModelOrganization(id=_uid(), model_id=model_id, organization_id=org_id)


async def _seed_shared(async_test_db, *, admin_role=OrganizationRole.ORG_ADMIN):
    """Admin + org + custom model shared with org. Returns (admin, org, model)."""
    admin = _make_user()
    owner = _make_user()
    org = _make_org()
    async_test_db.add_all([admin, owner, org])
    await async_test_db.flush()
    model = _make_custom_model(owner.id)
    async_test_db.add(model)
    await async_test_db.flush()
    async_test_db.add_all(
        [_membership(admin.id, org.id, admin_role), _share(model.id, org.id)]
    )
    await async_test_db.commit()
    return admin, org, model


SECRET = "sk-org-shared-roundtrip-secret"


class TestOrgCredentialRoundTrip:
    @pytest.mark.asyncio
    async def test_put_get_delete_and_no_key_leak(
        self, async_test_client, async_test_db
    ):
        admin, org, model = await _seed_shared(async_test_db)

        with _as_user(admin):
            # Initially: no shared credential.
            status_resp = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            assert status_resp.status_code == status.HTTP_200_OK
            assert status_resp.json() == {"has_credential": False, "updated_at": None}

            # PUT stores it.
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": SECRET},
            )
            assert put_resp.status_code == status.HTTP_200_OK
            assert put_resp.json() == {"has_credential": True}

            # GET reports status + timestamp, never the key.
            status_resp2 = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            body = status_resp2.json()
            assert body["has_credential"] is True
            assert body["updated_at"] is not None

            # List endpoint reflects has_org_credential.
            list_resp = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models"
            )
            assert list_resp.status_code == status.HTTP_200_OK
            listed = {m["id"]: m for m in list_resp.json()}
            assert listed[model.id]["has_org_credential"] is True

            # DELETE removes it; second DELETE is 404.
            del_resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            assert del_resp.status_code == status.HTTP_200_OK
            assert del_resp.json() == {"has_credential": False}
            del_resp2 = await async_test_client.delete(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            assert del_resp2.status_code == status.HTTP_404_NOT_FOUND

        # The raw key never appeared in ANY response body.
        for resp in (status_resp, put_resp, status_resp2, list_resp, del_resp, del_resp2):
            assert SECRET not in resp.text

    @pytest.mark.asyncio
    async def test_put_upsert_overwrites(self, async_test_client, async_test_db):
        admin, org, model = await _seed_shared(async_test_db)

        with _as_user(admin):
            first = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "sk-first"},
            )
            second = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "sk-second"},
            )
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK

        rows = (
            await async_test_db.execute(
                select(CustomModelOrgCredential).where(
                    CustomModelOrgCredential.model_id == model.id,
                    CustomModelOrgCredential.organization_id == org.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        decrypted = await get_org_credential_async(async_test_db, org.id, model.id)
        assert decrypted == "sk-second"

    @pytest.mark.asyncio
    async def test_empty_api_key_rejected(self, async_test_client, async_test_db):
        admin, org, model = await _seed_shared(async_test_db)

        with _as_user(admin):
            empty = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": ""},
            )
            blank = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "   "},
            )
        assert empty.status_code == status.HTTP_400_BAD_REQUEST
        assert blank.status_code == status.HTTP_400_BAD_REQUEST


class TestOrgCredentialAuthz:
    @pytest.mark.asyncio
    async def test_non_admin_member_forbidden(self, async_test_client, async_test_db):
        _admin, org, model = await _seed_shared(async_test_db)
        member = _make_user()
        async_test_db.add(member)
        await async_test_db.flush()
        async_test_db.add(
            _membership(member.id, org.id, OrganizationRole.CONTRIBUTOR)
        )
        await async_test_db.commit()

        with _as_user(member):
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "sk-nope"},
            )
            get_resp = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            del_resp = await async_test_client.delete(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential"
            )
            list_resp = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models"
            )
        assert put_resp.status_code == status.HTTP_403_FORBIDDEN
        assert get_resp.status_code == status.HTTP_403_FORBIDDEN
        assert del_resp.status_code == status.HTTP_403_FORBIDDEN
        assert list_resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_outsider_forbidden(self, async_test_client, async_test_db):
        _admin, org, model = await _seed_shared(async_test_db)
        outsider = _make_user()
        async_test_db.add(outsider)
        await async_test_db.commit()

        with _as_user(outsider):
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "sk-nope"},
            )
        assert put_resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_superadmin_allowed(self, async_test_client, async_test_db):
        _admin, org, model = await _seed_shared(async_test_db)
        superadmin = _make_user(is_superadmin=True)
        async_test_db.add(superadmin)
        await async_test_db.commit()

        with _as_user(superadmin):
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{model.id}/credential",
                json={"api_key": "sk-super"},
            )
        assert put_resp.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_model_not_shared_with_org_404(
        self, async_test_client, async_test_db
    ):
        admin, org, _model = await _seed_shared(async_test_db)
        # A second custom model that is NOT shared with the org.
        owner = _make_user()
        async_test_db.add(owner)
        await async_test_db.flush()
        unshared = _make_custom_model(owner.id)
        async_test_db.add(unshared)
        await async_test_db.commit()

        with _as_user(admin):
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{unshared.id}/credential",
                json={"api_key": "sk-nope"},
            )
            get_resp = await async_test_client.get(
                f"/api/organizations/{org.id}/custom-models/{unshared.id}/credential"
            )
        assert put_resp.status_code == status.HTTP_404_NOT_FOUND
        assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_official_model_rejected(self, async_test_client, async_test_db):
        admin, org, _model = await _seed_shared(async_test_db)
        official = _make_official_model()
        async_test_db.add(official)
        await async_test_db.flush()
        # Even if (pathologically) an org link existed, an official row is 404.
        async_test_db.add(_share(official.id, org.id))
        await async_test_db.commit()

        with _as_user(admin):
            put_resp = await async_test_client.put(
                f"/api/organizations/{org.id}/custom-models/{official.id}/credential",
                json={"api_key": "sk-nope"},
            )
        assert put_resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_missing_org_404(self, async_test_client, async_test_db):
        admin = _make_user(is_superadmin=True)
        owner = _make_user()
        async_test_db.add_all([admin, owner])
        await async_test_db.flush()
        model = _make_custom_model(owner.id)
        async_test_db.add(model)
        await async_test_db.commit()

        with _as_user(admin):
            resp = await async_test_client.put(
                f"/api/organizations/does-not-exist/custom-models/{model.id}/credential",
                json={"api_key": "sk-nope"},
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestVisibilityChangeDropsOrgCredentials:
    """A visibility PATCH that unshares a custom model from an org must delete
    that org's leftover shared-credential row — otherwise it stays billable /
    usable via the org-billing fallback and becomes an un-manageable orphan
    (the credential endpoints gate on the model still being shared).

    The visibility endpoint requires model-EDIT access, so the caller acts as
    the model creator (owner).
    """

    async def _seed_owned(self, async_test_db, org_ids):
        """Owner + a private custom model they created, shared with each org in
        ``org_ids``, each org carrying a shared-credential row. The owner is an
        ACTIVE member of every org — re-sharing via /visibility requires an
        active membership in each target org. Returns
        (owner, model, {org_id: Organization})."""
        owner = _make_user()
        orgs = {oid: _make_org() for oid in org_ids}
        async_test_db.add(owner)
        async_test_db.add_all(list(orgs.values()))
        await async_test_db.flush()
        model = _make_custom_model(owner.id)
        async_test_db.add(model)
        await async_test_db.flush()
        for org in orgs.values():
            async_test_db.add_all(
                [
                    _membership(owner.id, org.id, OrganizationRole.CONTRIBUTOR),
                    _share(model.id, org.id),
                    CustomModelOrgCredential(
                        id=_uid(),
                        organization_id=org.id,
                        model_id=model.id,
                        encrypted_api_key=f"ct-{org.id}",
                    ),
                ]
            )
        await async_test_db.commit()
        return owner, model, orgs

    async def _remaining_cred_org_ids(self, async_test_db, model_id) -> set:
        # Select the column directly (not ORM rows) so there is no lazy
        # attribute access — a fresh SELECT reflects the handler's committed
        # deletes without needing expire_all (which would expire the seeded
        # owner object and break the sync _as_user() read that follows).
        rows = (
            await async_test_db.execute(
                select(CustomModelOrgCredential.organization_id).where(
                    CustomModelOrgCredential.model_id == model_id
                )
            )
        ).all()
        return {r[0] for r in rows}

    @pytest.mark.asyncio
    async def test_make_public_deletes_org_shared_credential(
        self, async_test_client, async_test_db
    ):
        owner, model, orgs = await self._seed_owned(async_test_db, ["A"])
        org = orgs["A"]
        # Precondition: the shared credential row exists.
        assert await self._remaining_cred_org_ids(async_test_db, model.id) == {org.id}

        with _as_user(owner):
            resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_public": True},
            )
        assert resp.status_code == status.HTTP_200_OK

        # Model unshared from every org → its org credential row is gone.
        assert await self._remaining_cred_org_ids(async_test_db, model.id) == set()

    @pytest.mark.asyncio
    async def test_make_private_deletes_org_shared_credential(
        self, async_test_client, async_test_db
    ):
        owner, model, orgs = await self._seed_owned(async_test_db, ["A"])

        with _as_user(owner):
            resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": True},
            )
        assert resp.status_code == status.HTTP_200_OK
        assert await self._remaining_cred_org_ids(async_test_db, model.id) == set()

    @pytest.mark.asyncio
    async def test_reshare_drops_only_removed_org_credentials(
        self, async_test_client, async_test_db
    ):
        owner, model, orgs = await self._seed_owned(async_test_db, ["A", "B"])
        org_a, org_b = orgs["A"], orgs["B"]
        assert await self._remaining_cred_org_ids(async_test_db, model.id) == {
            org_a.id,
            org_b.id,
        }

        # Re-share to ONLY org B → org A's leftover credential is dropped, org
        # B's is kept (its admin shouldn't have to re-enter the key).
        with _as_user(owner):
            resp = await async_test_client.patch(
                f"/api/custom-models/{model.id}/visibility",
                json={"is_private": False, "organization_ids": [org_b.id]},
            )
        assert resp.status_code == status.HTTP_200_OK

        remaining = await self._remaining_cred_org_ids(async_test_db, model.id)
        assert org_a.id not in remaining
        assert remaining == {org_b.id}
