"""
Tests for the custom (BYOM) model access helpers (routers/model_access.py).

Real-DB matrix over get_accessible_model_ids_async /
check_model_accessible_async (async fixtures, mirroring
test_llm_models_router.py) plus pure-function tests for
check_user_can_edit_model.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from models import LLMModel as DBLLMModel
from models import ModelOrganization, Organization, OrganizationMembership, User

from routers.model_access import (
    check_model_accessible_async,
    check_user_can_edit_model,
    get_accessible_model_ids_async,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _make_user(*, is_superadmin=False) -> User:
    uid = _uid()
    return User(
        id=uid,
        username=f"ma-{uid[:8]}",
        email=f"{uid[:8]}@test.com",
        name="Model Access User",
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
        slug=f"ma-org-{uid[:8]}",
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


async def _seed_matrix(db):
    """Users A (creator), B (other), C (active org member), D (inactive
    membership), S (superadmin); org O; models: A-private, public (by B),
    org-shared with O (by B), plus one official row."""
    a, b, c, d, s = (
        _make_user(),
        _make_user(),
        _make_user(),
        _make_user(),
        _make_user(is_superadmin=True),
    )
    org = _make_org()
    db.add_all([a, b, c, d, s, org])
    await db.flush()

    db.add_all(
        [
            OrganizationMembership(
                id=_uid(), user_id=c.id, organization_id=org.id,
                role="CONTRIBUTOR", is_active=True,
            ),
            OrganizationMembership(
                id=_uid(), user_id=d.id, organization_id=org.id,
                role="CONTRIBUTOR", is_active=False,
            ),
        ]
    )

    m_private_a = _make_custom_model(a.id)
    m_public = _make_custom_model(b.id, is_private=False, is_public=True)
    m_org = _make_custom_model(b.id, is_private=False)
    official = _make_official_model()
    db.add_all([m_private_a, m_public, m_org, official])
    await db.flush()

    db.add(
        ModelOrganization(
            id=_uid(), model_id=m_org.id, organization_id=org.id, assigned_by=b.id
        )
    )
    await db.commit()

    return {
        "a": a, "b": b, "c": c, "d": d, "s": s, "org": org,
        "m_private_a": m_private_a, "m_public": m_public,
        "m_org": m_org, "official": official,
    }


class TestGetAccessibleModelIds:
    @pytest.mark.asyncio
    async def test_creator_sees_own_private_and_public(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        ids = set(await get_accessible_model_ids_async(async_test_db, ctx["a"]))
        assert ctx["m_private_a"].id in ids
        assert ctx["m_public"].id in ids
        assert ctx["m_org"].id not in ids

    @pytest.mark.asyncio
    async def test_other_user_does_not_see_foreign_private(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        ids = set(await get_accessible_model_ids_async(async_test_db, ctx["b"]))
        assert ctx["m_private_a"].id not in ids
        # B created m_public and m_org, so both are visible to B.
        assert ctx["m_public"].id in ids
        assert ctx["m_org"].id in ids

    @pytest.mark.asyncio
    async def test_active_org_member_sees_org_shared(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        ids = set(await get_accessible_model_ids_async(async_test_db, ctx["c"]))
        assert ctx["m_org"].id in ids
        assert ctx["m_public"].id in ids
        assert ctx["m_private_a"].id not in ids

    @pytest.mark.asyncio
    async def test_inactive_membership_does_not_grant_org_shared(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        ids = set(await get_accessible_model_ids_async(async_test_db, ctx["d"]))
        assert ctx["m_org"].id not in ids
        assert ctx["m_public"].id in ids

    @pytest.mark.asyncio
    async def test_superadmin_sees_all_custom(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        ids = set(await get_accessible_model_ids_async(async_test_db, ctx["s"]))
        assert {ctx["m_private_a"].id, ctx["m_public"].id, ctx["m_org"].id} <= ids

    @pytest.mark.asyncio
    async def test_official_models_never_included(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        for who in ("a", "b", "c", "s"):
            ids = set(await get_accessible_model_ids_async(async_test_db, ctx[who]))
            assert ctx["official"].id not in ids


class TestCheckModelAccessible:
    @pytest.mark.asyncio
    async def test_official_accessible_to_everyone(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        assert await check_model_accessible_async(
            async_test_db, ctx["b"], ctx["official"]
        )

    @pytest.mark.asyncio
    async def test_private_creator_only(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        assert await check_model_accessible_async(
            async_test_db, ctx["a"], ctx["m_private_a"]
        )
        assert not await check_model_accessible_async(
            async_test_db, ctx["b"], ctx["m_private_a"]
        )
        assert await check_model_accessible_async(
            async_test_db, ctx["s"], ctx["m_private_a"]
        )

    @pytest.mark.asyncio
    async def test_public_accessible_to_anyone(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        assert await check_model_accessible_async(
            async_test_db, ctx["d"], ctx["m_public"]
        )

    @pytest.mark.asyncio
    async def test_org_shared_requires_active_membership(self, async_test_db):
        ctx = await _seed_matrix(async_test_db)
        assert await check_model_accessible_async(async_test_db, ctx["c"], ctx["m_org"])
        assert not await check_model_accessible_async(
            async_test_db, ctx["d"], ctx["m_org"]
        )
        assert not await check_model_accessible_async(
            async_test_db, ctx["a"], ctx["m_org"]
        )


class TestCheckUserCanEditModel:
    """Pure function — no DB needed."""

    def test_creator_can_edit(self):
        user = Mock(id="u1", is_superadmin=False)
        model = Mock(created_by="u1")
        assert check_user_can_edit_model(user, model) is True

    def test_non_creator_cannot_edit(self):
        user = Mock(id="u2", is_superadmin=False)
        model = Mock(created_by="u1")
        assert check_user_can_edit_model(user, model) is False

    def test_superadmin_can_edit(self):
        user = Mock(id="u2", is_superadmin=True)
        model = Mock(created_by="u1")
        assert check_user_can_edit_model(user, model) is True

    def test_created_by_none_only_superadmin(self):
        """Creator deleted (FK SET NULL): nobody but superadmins may edit."""
        model = Mock(created_by=None)
        assert check_user_can_edit_model(Mock(id="u1", is_superadmin=False), model) is False
        assert check_user_can_edit_model(Mock(id="u1", is_superadmin=True), model) is True
