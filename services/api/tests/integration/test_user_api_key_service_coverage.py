"""Behavioral integration tests for ``services/user_api_key_service.py``.

These exercise the service against a REAL Postgres ``test_db`` session and the
REAL ``encryption_service`` singleton (which derives a deterministic Fernet key
under pytest — see ``shared/encryption_service.py``). Unlike the mock-heavy
``tests/unit/test_user_api_key_service*.py`` siblings, every test here asserts
**persisted DB state**: the encrypted column actually changes on the ``users``
row, the encrypt→store→retrieve round-trip returns the original plaintext, and
remove actually nulls the column. The ciphertext is never asserted directly —
only that decrypt(store(x)) == x.

Uncovered arms targeted (complement of the mock unit suite, which stubbed the
DB so the real ORM persistence + real Fernet round-trip were never executed):
  - set/get/remove against a real row for multiple providers
  - the encrypt→persist→decrypt round-trip through real Fernet
  - update-vs-insert (overwrite an existing key with a new value)
  - invalid-provider + invalid-format + user-not-found early returns observed
    to leave the DB untouched
  - get returns None when the stored column is empty (real NULL, not a Mock)
  - the async ``validate_api_key`` provider dispatch + unsupported fallthrough
    (network calls patched at the per-provider validator so no real HTTP fires)
"""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from encryption_service import encryption_service
from models import User
from services.user_api_key_service import UserApiKeyService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service() -> UserApiKeyService:
    """A service wired to the real (pytest-deterministic) encryption singleton."""
    return UserApiKeyService(encryption_service)


def _seed_user(test_db: Session, user_id: str = "apikey-user-1") -> User:
    user = User(
        id=user_id,
        username=f"{user_id}@test.com",
        email=f"{user_id}@test.com",
        name="API Key User",
        hashed_password="x",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


def _reload(test_db: Session, user_id: str) -> User:
    test_db.expire_all()
    return test_db.query(User).filter(User.id == user_id).first()


# Valid-format sample keys per provider (must pass is_valid_api_key_format).
_VALID_KEYS = {
    "openai": "sk-" + "a" * 40,
    "anthropic": "sk-ant-" + "b" * 40,
    "google": "AIza" + "c" * 30,
    "deepinfra": "d" * 32,
    "grok": "xai-" + "e" * 30,
    "mistral": "f" * 40,
    "cohere": "g" * 40,
}


# ---------------------------------------------------------------------------
# set_user_api_key — real persistence + round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSetAndGetRoundTrip:
    @pytest.mark.parametrize("provider", list(_VALID_KEYS.keys()))
    def test_store_then_retrieve_returns_plaintext(self, test_db, provider):
        """encrypt→persist→decrypt returns the original plaintext, and the
        encrypted column on the persisted row is non-null + NOT the plaintext."""
        svc = _service()
        _seed_user(test_db)
        plaintext = _VALID_KEYS[provider]

        assert svc.set_user_api_key(test_db, "apikey-user-1", provider, plaintext) is True

        # Column actually populated on the persisted row, and ciphertext != plaintext.
        field = svc.API_KEY_FIELDS[provider]
        reloaded = _reload(test_db, "apikey-user-1")
        ciphertext = getattr(reloaded, field)
        assert ciphertext is not None
        assert ciphertext != plaintext

        # Round-trip through the service decrypts back to the original.
        assert svc.get_user_api_key(test_db, "apikey-user-1", provider) == plaintext

    def test_provider_name_normalized_to_lowercase_field(self, test_db):
        """An uppercase provider name writes to the lowercase field and is
        retrievable case-insensitively."""
        svc = _service()
        _seed_user(test_db)
        plaintext = _VALID_KEYS["openai"]

        assert svc.set_user_api_key(test_db, "apikey-user-1", "OpenAI", plaintext) is True
        reloaded = _reload(test_db, "apikey-user-1")
        assert reloaded.encrypted_openai_api_key is not None
        assert svc.get_user_api_key(test_db, "apikey-user-1", "OPENAI") == plaintext

    def test_overwrite_updates_existing_key(self, test_db):
        """Setting a key for a provider that already has one updates in place
        (update-vs-insert) — the new value round-trips, the old is gone."""
        svc = _service()
        _seed_user(test_db)
        first = _VALID_KEYS["anthropic"]
        second = "sk-ant-" + "z" * 40

        assert svc.set_user_api_key(test_db, "apikey-user-1", "anthropic", first) is True
        first_cipher = _reload(test_db, "apikey-user-1").encrypted_anthropic_api_key

        assert svc.set_user_api_key(test_db, "apikey-user-1", "anthropic", second) is True
        second_cipher = _reload(test_db, "apikey-user-1").encrypted_anthropic_api_key

        assert second_cipher != first_cipher
        assert svc.get_user_api_key(test_db, "apikey-user-1", "anthropic") == second

    def test_multiple_providers_coexist_independently(self, test_db):
        """Two providers' keys persist side by side without clobbering."""
        svc = _service()
        _seed_user(test_db)
        assert svc.set_user_api_key(
            test_db, "apikey-user-1", "openai", _VALID_KEYS["openai"]
        ) is True
        assert svc.set_user_api_key(
            test_db, "apikey-user-1", "google", _VALID_KEYS["google"]
        ) is True

        reloaded = _reload(test_db, "apikey-user-1")
        assert reloaded.encrypted_openai_api_key is not None
        assert reloaded.encrypted_google_api_key is not None
        assert svc.get_user_api_key(test_db, "apikey-user-1", "openai") == _VALID_KEYS["openai"]
        assert svc.get_user_api_key(test_db, "apikey-user-1", "google") == _VALID_KEYS["google"]


# ---------------------------------------------------------------------------
# set_user_api_key — rejection branches leave DB untouched
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSetRejectionBranches:
    def test_unsupported_provider_returns_false_no_write(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.set_user_api_key(test_db, "apikey-user-1", "bogus", "whatever") is False
        # No column written anywhere.
        reloaded = _reload(test_db, "apikey-user-1")
        assert all(
            getattr(reloaded, f) is None for f in svc.API_KEY_FIELDS.values()
        )

    def test_invalid_format_returns_false_no_write(self, test_db):
        """A key that fails the provider format check is rejected before any
        encryption/persist happens."""
        svc = _service()
        _seed_user(test_db)
        # 'short' is < 16 chars and lacks the sk- prefix → invalid for openai.
        assert svc.set_user_api_key(test_db, "apikey-user-1", "openai", "short") is False
        assert _reload(test_db, "apikey-user-1").encrypted_openai_api_key is None

    def test_user_not_found_returns_false(self, test_db):
        svc = _service()
        # No user seeded with this id.
        assert (
            svc.set_user_api_key(
                test_db, "ghost-user", "openai", _VALID_KEYS["openai"]
            )
            is False
        )

    def test_encryption_returning_none_returns_false_no_write(self, test_db):
        """If the encryption layer yields None, the column stays null."""
        svc = _service()
        _seed_user(test_db)
        with patch.object(svc.encryption_service, "encrypt_api_key", return_value=None):
            assert (
                svc.set_user_api_key(
                    test_db, "apikey-user-1", "openai", _VALID_KEYS["openai"]
                )
                is False
            )
        assert _reload(test_db, "apikey-user-1").encrypted_openai_api_key is None


# ---------------------------------------------------------------------------
# get_user_api_key — empty / unsupported / decrypt-failure
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetBranches:
    def test_get_when_no_key_stored_returns_none(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.get_user_api_key(test_db, "apikey-user-1", "openai") is None

    def test_get_unsupported_provider_returns_none(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.get_user_api_key(test_db, "apikey-user-1", "bogus") is None

    def test_get_user_not_found_returns_none(self, test_db):
        svc = _service()
        assert svc.get_user_api_key(test_db, "ghost-user", "openai") is None

    def test_get_with_corrupt_ciphertext_returns_none(self, test_db):
        """A column holding non-Fernet bytes decrypts to None (InvalidToken),
        the service swallows it and returns None rather than raising."""
        svc = _service()
        user = _seed_user(test_db)
        user.encrypted_openai_api_key = "this-is-not-valid-fernet-ciphertext"
        test_db.commit()
        assert svc.get_user_api_key(test_db, "apikey-user-1", "openai") is None


# ---------------------------------------------------------------------------
# remove_user_api_key — real nulling
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRemove:
    def test_remove_nulls_persisted_column(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.set_user_api_key(
            test_db, "apikey-user-1", "openai", _VALID_KEYS["openai"]
        ) is True
        assert _reload(test_db, "apikey-user-1").encrypted_openai_api_key is not None

        assert svc.remove_user_api_key(test_db, "apikey-user-1", "openai") is True
        assert _reload(test_db, "apikey-user-1").encrypted_openai_api_key is None
        # Retrieval now returns None.
        assert svc.get_user_api_key(test_db, "apikey-user-1", "openai") is None

    def test_remove_unsupported_provider_returns_false(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.remove_user_api_key(test_db, "apikey-user-1", "bogus") is False

    def test_remove_user_not_found_returns_false(self, test_db):
        svc = _service()
        assert svc.remove_user_api_key(test_db, "ghost-user", "openai") is False


# ---------------------------------------------------------------------------
# status / available-providers — computed over real rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStatusAndAvailableProviders:
    def test_status_reflects_persisted_columns(self, test_db):
        svc = _service()
        _seed_user(test_db)
        svc.set_user_api_key(test_db, "apikey-user-1", "openai", _VALID_KEYS["openai"])
        svc.set_user_api_key(test_db, "apikey-user-1", "cohere", _VALID_KEYS["cohere"])

        status = svc.get_user_api_key_status(test_db, "apikey-user-1")
        assert status["openai"] is True
        assert status["cohere"] is True
        assert status["anthropic"] is False
        assert status["google"] is False
        # Every supported provider present as a key.
        assert set(status.keys()) == set(svc.SUPPORTED_PROVIDERS)

    def test_status_user_not_found_returns_empty(self, test_db):
        svc = _service()
        assert svc.get_user_api_key_status(test_db, "ghost-user") == {}

    def test_available_providers_capitalized_names(self, test_db):
        svc = _service()
        _seed_user(test_db)
        svc.set_user_api_key(test_db, "apikey-user-1", "openai", _VALID_KEYS["openai"])
        svc.set_user_api_key(test_db, "apikey-user-1", "anthropic", _VALID_KEYS["anthropic"])

        providers = svc.get_user_available_providers(test_db, "apikey-user-1")
        assert set(providers) == {"OpenAI", "Anthropic"}

    def test_available_providers_none_when_empty(self, test_db):
        svc = _service()
        _seed_user(test_db)
        assert svc.get_user_available_providers(test_db, "apikey-user-1") == []


# ---------------------------------------------------------------------------
# validate_api_key — async provider dispatch (no real network)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestValidateDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_to_provider_validator(self):
        """validate_api_key routes to the right per-provider coroutine; the
        validator itself is patched so no HTTP fires."""
        svc = _service()
        with patch.object(
            svc, "_validate_anthropic_key", return_value=(True, "ok", "success")
        ) as m:
            ok, msg, kind = await svc.validate_api_key("sk-ant-xyz", "Anthropic")
        m.assert_awaited_once()
        assert ok is True and kind == "success"

    @pytest.mark.asyncio
    async def test_unsupported_provider_fallthrough(self):
        svc = _service()
        ok, msg, kind = await svc.validate_api_key("whatever", "no-such-provider")
        assert ok is False
        assert "Unsupported provider" in msg
        assert kind == "unknown"

    @pytest.mark.asyncio
    async def test_validator_exception_is_caught(self):
        """A raising validator is caught and reported as an unknown error,
        never propagated."""
        svc = _service()
        with patch.object(
            svc, "_validate_openai_key", side_effect=RuntimeError("boom")
        ):
            ok, msg, kind = await svc.validate_api_key("sk-x", "openai")
        assert ok is False
        assert "Validation error" in msg
        assert kind == "unknown"
