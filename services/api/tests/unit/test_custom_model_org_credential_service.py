"""Round-trip + precedence-helper tests for
shared/custom_model_org_credential_service.py.

Org-owned custom-model credentials are per-(organization, model) Fernet-
encrypted API keys — the org-level counterpart of the per-user
custom_model_credential_service. The service exposes an async lane for the
API and a sync ``get_org_credential`` for the workers (Celery process pool,
no event loop), plus the ``org_requires_private_keys`` shared-billing read.

Async functions run against ``async_test_db`` (the SAVEPOINT-isolated
AsyncSession fixture). The sync lane is exercised through
``AsyncSession.run_sync`` — same transaction, so it sees the async lane's
writes without a second sync fixture.
"""

import uuid

import pytest
from sqlalchemy import func, select

from custom_model_org_credential_service import (
    delete_org_credential_async,
    get_org_credential,
    get_org_credential_async,
    get_org_credential_model_ids_async,
    has_org_credential_async,
    org_requires_private_keys,
    set_org_credential_async,
)
from models import CustomModelOrgCredential, LLMModel, Organization, User

PLAINTEXT_KEY = "sk-org-shared-secret-98765"


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Backstop for long-lived test DBs bootstrapped before migration 080
    (the custom llm_models rows below need the BYOM columns). The new table
    custom_model_org_credentials is always created by create_all."""
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


def _make_user():
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=f"orgcred-user-{suffix}",
        username=f"orgcred-{suffix}",
        email=f"orgcred-{suffix}@test.com",
        name="Org Credential Test User",
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


def _make_custom_model():
    return LLMModel(
        id=f"custom-{uuid.uuid4().hex[:8]}",
        name="Org credential test model",
        provider="Custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_active=True,
        is_official=False,
        is_private=True,
        is_public=False,
        base_url="http://localhost:11434/v1",
        endpoint_model_name="llama3:8b",
        requires_api_key=True,
    )


async def _seed_org_and_model(db):
    """Org + custom model rows to satisfy the credential FKs."""
    org = _make_org()
    model = _make_custom_model()
    db.add_all([org, model])
    await db.commit()
    return org.id, model.id


async def _credential_row_count(db, org_id, model_id):
    result = await db.execute(
        select(func.count())
        .select_from(CustomModelOrgCredential)
        .where(
            CustomModelOrgCredential.organization_id == org_id,
            CustomModelOrgCredential.model_id == model_id,
        )
    )
    return result.scalar()


@pytest.mark.asyncio
async def test_set_and_get_round_trip(async_test_db):
    org_id, model_id = await _seed_org_and_model(async_test_db)

    assert (
        await set_org_credential_async(async_test_db, org_id, model_id, PLAINTEXT_KEY)
        is True
    )

    # Stored ciphertext is Fernet output, never the plaintext.
    result = await async_test_db.execute(
        select(CustomModelOrgCredential).where(
            CustomModelOrgCredential.organization_id == org_id,
            CustomModelOrgCredential.model_id == model_id,
        )
    )
    row = result.scalar_one()
    assert row.encrypted_api_key != PLAINTEXT_KEY
    assert PLAINTEXT_KEY not in row.encrypted_api_key

    # Async lane (API) decrypts back to the plaintext.
    assert await get_org_credential_async(async_test_db, org_id, model_id) == PLAINTEXT_KEY

    # Sync lane (workers) sees the same row and agrees.
    sync_value = await async_test_db.run_sync(
        lambda sync_session: get_org_credential(sync_session, org_id, model_id)
    )
    assert sync_value == PLAINTEXT_KEY


@pytest.mark.asyncio
async def test_created_by_is_persisted(async_test_db):
    org_id, model_id = await _seed_org_and_model(async_test_db)
    admin = _make_user()
    async_test_db.add(admin)
    await async_test_db.commit()

    await set_org_credential_async(
        async_test_db, org_id, model_id, PLAINTEXT_KEY, created_by=admin.id
    )
    row = (
        await async_test_db.execute(
            select(CustomModelOrgCredential).where(
                CustomModelOrgCredential.organization_id == org_id,
                CustomModelOrgCredential.model_id == model_id,
            )
        )
    ).scalar_one()
    assert row.created_by == admin.id


@pytest.mark.asyncio
async def test_missing_credential_returns_none_on_both_lanes(async_test_db):
    org_id, model_id = await _seed_org_and_model(async_test_db)

    assert await get_org_credential_async(async_test_db, org_id, model_id) is None
    assert await has_org_credential_async(async_test_db, org_id, model_id) is False
    sync_value = await async_test_db.run_sync(
        lambda sync_session: get_org_credential(sync_session, org_id, model_id)
    )
    assert sync_value is None


@pytest.mark.asyncio
async def test_set_again_overwrites_in_place(async_test_db):
    """Upsert semantics: the unique (organization_id, model_id) row is
    updated, not duplicated (a second INSERT would trip
    unique_custom_model_org_credential)."""
    org_id, model_id = await _seed_org_and_model(async_test_db)

    assert await set_org_credential_async(async_test_db, org_id, model_id, "sk-old") is True
    assert await set_org_credential_async(async_test_db, org_id, model_id, "sk-new") is True

    assert await _credential_row_count(async_test_db, org_id, model_id) == 1
    assert await get_org_credential_async(async_test_db, org_id, model_id) == "sk-new"


@pytest.mark.asyncio
async def test_has_and_delete_lifecycle(async_test_db):
    org_id, model_id = await _seed_org_and_model(async_test_db)

    assert await has_org_credential_async(async_test_db, org_id, model_id) is False
    assert await delete_org_credential_async(async_test_db, org_id, model_id) is False

    await set_org_credential_async(async_test_db, org_id, model_id, PLAINTEXT_KEY)
    assert await has_org_credential_async(async_test_db, org_id, model_id) is True

    assert await delete_org_credential_async(async_test_db, org_id, model_id) is True
    assert await has_org_credential_async(async_test_db, org_id, model_id) is False
    assert await get_org_credential_async(async_test_db, org_id, model_id) is None
    # Idempotent: second delete reports nothing removed.
    assert await delete_org_credential_async(async_test_db, org_id, model_id) is False


@pytest.mark.asyncio
async def test_get_org_credential_model_ids_returns_only_own_org(async_test_db):
    org = _make_org()
    other_org = _make_org()
    model_a = _make_custom_model()
    model_b = _make_custom_model()
    model_c = _make_custom_model()
    async_test_db.add_all([org, other_org, model_a, model_b, model_c])
    await async_test_db.commit()

    await set_org_credential_async(async_test_db, org.id, model_a.id, "sk-a")
    await set_org_credential_async(async_test_db, org.id, model_b.id, "sk-b")
    await set_org_credential_async(async_test_db, other_org.id, model_c.id, "sk-c")

    assert await get_org_credential_model_ids_async(async_test_db, org.id) == {
        model_a.id,
        model_b.id,
    }
    assert await get_org_credential_model_ids_async(async_test_db, other_org.id) == {
        model_c.id
    }


@pytest.mark.asyncio
async def test_empty_or_whitespace_key_is_rejected(async_test_db):
    org_id, model_id = await _seed_org_and_model(async_test_db)

    assert await set_org_credential_async(async_test_db, org_id, model_id, "") is False
    assert await set_org_credential_async(async_test_db, org_id, model_id, "   ") is False

    assert await _credential_row_count(async_test_db, org_id, model_id) == 0
    assert await has_org_credential_async(async_test_db, org_id, model_id) is False


@pytest.mark.asyncio
async def test_org_requires_private_keys_reads_settings(async_test_db):
    """Sync helper mirrors shared_org_api_key_service: True default,
    True/False honored from Organization.settings.require_private_keys."""
    default_org = _make_org()  # settings=None
    shared_org = _make_org(require_private_keys=False)
    private_org = _make_org(require_private_keys=True)
    async_test_db.add_all([default_org, shared_org, private_org])
    await async_test_db.commit()

    def _read(org_id):
        return async_test_db.run_sync(
            lambda sync_session: org_requires_private_keys(sync_session, org_id)
        )

    # Missing org → default True (fails closed to personal keys).
    assert await _read("does-not-exist") is True
    # settings=None → default True.
    assert await _read(default_org.id) is True
    assert await _read(shared_org.id) is False
    assert await _read(private_org.id) is True
