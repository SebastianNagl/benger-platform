"""Round-trip tests for shared/custom_model_credential_service.py.

Custom-model credentials are per-(user, model) Fernet-encrypted API keys —
sharing a custom model shares only the endpoint definition, every user
brings their own key. The service exposes an async lane for the API and a
sync `get_credential` for the workers (Celery process pool, no event loop).

Async functions run against `async_test_db` (the SAVEPOINT-isolated
AsyncSession fixture from tests/fixtures/database.py). The sync lane is
exercised through `AsyncSession.run_sync`, which hands the service the
underlying sync Session — same transaction, so it sees the async lane's
writes without needing a second (isolated) sync fixture.
"""

import uuid

import pytest
from sqlalchemy import func, select

from custom_model_credential_service import (
    delete_credential_async,
    get_credential,
    get_credential_async,
    get_credential_model_ids_async,
    has_credential_async,
    set_credential_async,
)
from models import CustomModelCredential, LLMModel, User

PLAINTEXT_KEY = "sk-custom-secret-12345"


@pytest.fixture(scope="module", autouse=True)
def _ensure_byom_schema():
    """Backstop for long-lived test DBs bootstrapped before migration 080
    (the custom llm_models rows below need the BYOM columns). Same pattern
    as tests/integration/test_project_visibility_constraints.py; runs on
    the sync engine — same database the async fixture connects to.
    """
    from tests.fixtures.database import _get_engine
    from tests.utils.byom_schema import ensure_byom_llm_schema

    engine, _ = _get_engine()
    ensure_byom_llm_schema(engine)
    yield


def _make_user():
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=f"cred-user-{suffix}",
        username=f"cred-{suffix}",
        email=f"cred-{suffix}@test.com",
        name="Credential Test User",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )


def _make_custom_model():
    return LLMModel(
        id=f"custom-{uuid.uuid4().hex[:8]}",
        name="Credential test model",
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


async def _seed_user_and_model(db):
    """User + custom model rows to satisfy the credential FKs."""
    user = _make_user()
    model = _make_custom_model()
    db.add_all([user, model])
    await db.commit()
    return user.id, model.id


async def _credential_row_count(db, user_id, model_id):
    result = await db.execute(
        select(func.count())
        .select_from(CustomModelCredential)
        .where(
            CustomModelCredential.user_id == user_id,
            CustomModelCredential.model_id == model_id,
        )
    )
    return result.scalar()


@pytest.mark.asyncio
async def test_set_and_get_round_trip(async_test_db):
    user_id, model_id = await _seed_user_and_model(async_test_db)

    assert await set_credential_async(async_test_db, user_id, model_id, PLAINTEXT_KEY) is True

    # Stored ciphertext is Fernet output, never the plaintext.
    result = await async_test_db.execute(
        select(CustomModelCredential).where(
            CustomModelCredential.user_id == user_id,
            CustomModelCredential.model_id == model_id,
        )
    )
    row = result.scalar_one()
    assert row.encrypted_api_key != PLAINTEXT_KEY
    assert PLAINTEXT_KEY not in row.encrypted_api_key

    # Async lane (API) decrypts back to the plaintext.
    assert await get_credential_async(async_test_db, user_id, model_id) == PLAINTEXT_KEY

    # Sync lane (workers) sees the same row and agrees.
    sync_value = await async_test_db.run_sync(
        lambda sync_session: get_credential(sync_session, user_id, model_id)
    )
    assert sync_value == PLAINTEXT_KEY


@pytest.mark.asyncio
async def test_missing_credential_returns_none_on_both_lanes(async_test_db):
    user_id, model_id = await _seed_user_and_model(async_test_db)

    assert await get_credential_async(async_test_db, user_id, model_id) is None
    assert await has_credential_async(async_test_db, user_id, model_id) is False
    sync_value = await async_test_db.run_sync(
        lambda sync_session: get_credential(sync_session, user_id, model_id)
    )
    assert sync_value is None


@pytest.mark.asyncio
async def test_set_again_overwrites_in_place(async_test_db):
    """Upsert semantics: the unique (user_id, model_id) row is updated, not
    duplicated (a second INSERT would trip unique_custom_model_credential)."""
    user_id, model_id = await _seed_user_and_model(async_test_db)

    assert await set_credential_async(async_test_db, user_id, model_id, "sk-old-key") is True
    assert await set_credential_async(async_test_db, user_id, model_id, "sk-new-key") is True

    assert await _credential_row_count(async_test_db, user_id, model_id) == 1
    assert await get_credential_async(async_test_db, user_id, model_id) == "sk-new-key"


@pytest.mark.asyncio
async def test_has_and_delete_lifecycle(async_test_db):
    user_id, model_id = await _seed_user_and_model(async_test_db)

    assert await has_credential_async(async_test_db, user_id, model_id) is False
    assert await delete_credential_async(async_test_db, user_id, model_id) is False

    await set_credential_async(async_test_db, user_id, model_id, PLAINTEXT_KEY)
    assert await has_credential_async(async_test_db, user_id, model_id) is True

    assert await delete_credential_async(async_test_db, user_id, model_id) is True
    assert await has_credential_async(async_test_db, user_id, model_id) is False
    assert await get_credential_async(async_test_db, user_id, model_id) is None
    # Idempotent: second delete reports nothing removed.
    assert await delete_credential_async(async_test_db, user_id, model_id) is False


@pytest.mark.asyncio
async def test_get_credential_model_ids_returns_only_own_set(async_test_db):
    user = _make_user()
    other_user = _make_user()
    model_a = _make_custom_model()
    model_b = _make_custom_model()
    model_c = _make_custom_model()
    async_test_db.add_all([user, other_user, model_a, model_b, model_c])
    await async_test_db.commit()

    await set_credential_async(async_test_db, user.id, model_a.id, "sk-key-a")
    await set_credential_async(async_test_db, user.id, model_b.id, "sk-key-b")
    await set_credential_async(async_test_db, other_user.id, model_c.id, "sk-key-c")

    assert await get_credential_model_ids_async(async_test_db, user.id) == {
        model_a.id,
        model_b.id,
    }
    assert await get_credential_model_ids_async(async_test_db, other_user.id) == {
        model_c.id
    }


@pytest.mark.asyncio
async def test_empty_or_whitespace_key_is_rejected(async_test_db):
    user_id, model_id = await _seed_user_and_model(async_test_db)

    assert await set_credential_async(async_test_db, user_id, model_id, "") is False
    assert await set_credential_async(async_test_db, user_id, model_id, "   ") is False

    assert await _credential_row_count(async_test_db, user_id, model_id) == 0
    assert await has_credential_async(async_test_db, user_id, model_id) is False
