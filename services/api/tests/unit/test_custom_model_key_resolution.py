"""Tests for shared/custom_model_key_resolution.py — the single source of
truth for "can this user invoke this custom model, and with which key".

Precedence mirrors the worker dispatch path
(``user_aware_ai_service.get_ai_service_for_model_row``):

- ``source="user"`` — a personal credential always wins.
- ``source="org"`` — only when ALL hold: live ``ModelOrganization`` share,
  ACTIVE ``OrganizationMembership`` of the user in that org, org in
  shared-billing mode (``settings.require_private_keys`` falsy — defaults to
  True), and a stored ``CustomModelOrgCredential`` row.
- ``source=None`` — no usable key; ``can_invoke`` is ``not requires_api_key``.

Org scoping: ``organization_id`` resolves against ONE org context;
``search_user_orgs=True`` considers every org the user actively belongs to;
neither → personal-only. Several usable orgs → lowest org id, deterministic.

Credentials are stored through the real services so Fernet round-trips are
exercised (``include_key=True`` must decrypt the winning lane's key). Runs
against ``async_test_db`` (the SAVEPOINT-isolated AsyncSession fixture).
"""

import uuid

import pytest

from custom_model_credential_service import set_credential_async
from custom_model_key_resolution import resolve_custom_model_credential_async
from custom_model_org_credential_service import set_org_credential_async
from models import (
    LLMModel,
    ModelOrganization,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    User,
)

USER_KEY = "sk-user-lane-secret"
ORG_KEY = "sk-org-lane-secret"


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Backstop for long-lived test DBs bootstrapped before migration 080
    (the custom llm_models rows below need the BYOM columns). The credential
    tables are always created by create_all."""
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


def _make_user():
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=f"keyres-user-{suffix}",
        username=f"keyres-{suffix}",
        email=f"keyres-{suffix}@test.com",
        name="Key Resolution Test User",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )


def _make_org(**settings):
    suffix = uuid.uuid4().hex[:8]
    return Organization(
        id=f"org-{suffix}",
        name=f"Org {suffix}",
        display_name=f"Org {suffix}",
        slug=f"org-{suffix}",
        settings=settings or None,
        is_active=True,
    )


def _make_custom_model(**overrides):
    data = dict(
        id=f"custom-{uuid.uuid4().hex[:8]}",
        name="Key resolution test model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        is_private=True,
        is_public=False,
        # ck_llm_models_custom_endpoint_required: custom rows need both.
        base_url="http://localhost:11434/v1",
        endpoint_model_name="llama3:8b",
        requires_api_key=True,
    )
    data.update(overrides)
    return LLMModel(**data)


def _membership(user_id, org_id, *, is_active=True):
    return OrganizationMembership(
        id=str(uuid.uuid4()),
        user_id=user_id,
        organization_id=org_id,
        role=OrganizationRole.CONTRIBUTOR,
        is_active=is_active,
    )


def _share(model_id, org_id):
    return ModelOrganization(
        id=str(uuid.uuid4()), model_id=model_id, organization_id=org_id
    )


async def _seed_org_route(
    db,
    *,
    require_private_keys=False,
    membership="active",  # "active" | "inactive" | None
    share=True,
    org_key=ORG_KEY,
):
    """User + org + custom model with the org route's ingredients toggled.

    The defaults build a fully USABLE org route: live share, active
    membership, shared-billing org (require_private_keys False), stored org
    key. ``require_private_keys=None`` leaves ``settings`` absent entirely
    (the falls-back-to-True case). Returns (user, org, model).
    """
    user = _make_user()
    org = (
        _make_org()
        if require_private_keys is None
        else _make_org(require_private_keys=require_private_keys)
    )
    model = _make_custom_model()
    db.add_all([user, org, model])
    await db.flush()
    if membership is not None:
        db.add(_membership(user.id, org.id, is_active=(membership == "active")))
    if share:
        db.add(_share(model.id, org.id))
    await db.commit()
    if org_key is not None:
        assert await set_org_credential_async(db, org.id, model.id, org_key) is True
    return user, org, model


@pytest.mark.asyncio
async def test_personal_credential_wins_over_org(async_test_db):
    user, org, model = await _seed_org_route(async_test_db)
    assert await set_credential_async(async_test_db, user.id, model.id, USER_KEY) is True

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.source == "user"
    assert resolution.can_invoke is True
    assert resolution.has_credential is True
    assert resolution.organization_id is None
    # include_key not requested → the key is never decrypted.
    assert resolution.api_key is None


@pytest.mark.asyncio
@pytest.mark.parametrize("require_private_keys", [True, None])
async def test_org_route_requires_org_pays_mode(async_test_db, require_private_keys):
    # require_private_keys True — or absent, which DEFAULTS to True — means
    # members bring their own keys; the stored org key must not resolve.
    user, org, model = await _seed_org_route(
        async_test_db, require_private_keys=require_private_keys
    )

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.source is None
    assert resolution.has_credential is False
    assert resolution.can_invoke is False  # requires_api_key model, no key


@pytest.mark.asyncio
@pytest.mark.parametrize("membership", [None, "inactive"])
async def test_org_route_requires_active_membership(async_test_db, membership):
    user, org, model = await _seed_org_route(async_test_db, membership=membership)

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.source is None
    assert resolution.can_invoke is False


@pytest.mark.asyncio
async def test_org_route_requires_live_share(async_test_db):
    # The org key row exists but the ModelOrganization share does not (e.g.
    # it was revoked) — the leftover key must not stay usable.
    user, org, model = await _seed_org_route(async_test_db, share=False)

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.source is None
    assert resolution.can_invoke is False


@pytest.mark.asyncio
async def test_explicit_org_scopes_to_that_org_only(async_test_db):
    # Usable route via org B only; the user also actively belongs to org A.
    user, org_b, model = await _seed_org_route(async_test_db)
    org_a = _make_org(require_private_keys=False)
    async_test_db.add(org_a)
    await async_test_db.flush()
    async_test_db.add(_membership(user.id, org_a.id))
    await async_test_db.commit()

    scoped_to_a = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, organization_id=org_a.id
    )
    assert scoped_to_a.source is None
    assert scoped_to_a.can_invoke is False

    scoped_to_b = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, organization_id=org_b.id
    )
    assert scoped_to_b.source == "org"
    assert scoped_to_b.organization_id == org_b.id
    assert scoped_to_b.can_invoke is True


@pytest.mark.asyncio
async def test_search_all_orgs_deterministic_pick(async_test_db):
    # TWO fully usable org routes → the lowest org id wins, deterministically,
    # and the exposed organization_id names the picked org.
    user, org_1, model = await _seed_org_route(async_test_db)
    org_2 = _make_org(require_private_keys=False)
    async_test_db.add(org_2)
    await async_test_db.flush()
    async_test_db.add_all([_membership(user.id, org_2.id), _share(model.id, org_2.id)])
    await async_test_db.commit()
    assert (
        await set_org_credential_async(async_test_db, org_2.id, model.id, "sk-org-two")
        is True
    )

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.source == "org"
    assert resolution.organization_id == min(org_1.id, org_2.id)


@pytest.mark.asyncio
async def test_keyless_model_can_invoke_without_credentials(async_test_db):
    user = _make_user()
    model = _make_custom_model(requires_api_key=False)
    async_test_db.add_all([user, model])
    await async_test_db.commit()

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model, search_user_orgs=True
    )
    assert resolution.can_invoke is True
    assert resolution.source is None
    assert resolution.has_credential is False


@pytest.mark.asyncio
async def test_include_key_decrypts_correct_lane(async_test_db):
    # Two members of the same org-pays org: one with a personal credential
    # (user lane), one without (org lane). include_key=True must decrypt the
    # winning lane's key — never the other lane's.
    user_personal, org, model = await _seed_org_route(async_test_db)
    user_org_only = _make_user()
    async_test_db.add(user_org_only)
    await async_test_db.flush()
    async_test_db.add(_membership(user_org_only.id, org.id))
    await async_test_db.commit()
    assert (
        await set_credential_async(async_test_db, user_personal.id, model.id, USER_KEY)
        is True
    )

    personal = await resolve_custom_model_credential_async(
        async_test_db,
        user_personal.id,
        model,
        search_user_orgs=True,
        include_key=True,
    )
    assert personal.source == "user"
    assert personal.api_key == USER_KEY

    via_org = await resolve_custom_model_credential_async(
        async_test_db,
        user_org_only.id,
        model,
        search_user_orgs=True,
        include_key=True,
    )
    assert via_org.source == "org"
    assert via_org.organization_id == org.id
    assert via_org.api_key == ORG_KEY


@pytest.mark.asyncio
async def test_no_context_no_search_is_personal_only(async_test_db):
    # A fully usable org route exists — but with neither organization_id nor
    # search_user_orgs the resolution is personal-only (matching generation
    # without org context) and must NOT surface the org key.
    user, org, model = await _seed_org_route(async_test_db)

    resolution = await resolve_custom_model_credential_async(
        async_test_db, user.id, model
    )
    assert resolution.source is None
    assert resolution.has_credential is False
    assert resolution.can_invoke is False
