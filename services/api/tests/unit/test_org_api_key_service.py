"""
Unit tests for OrgApiKeyService (Issue #1180)

Tests organization-level API key management including:
- Setting, getting, and removing org API keys
- Key status tracking across providers
- Key resolution based on org settings
- Cross-org isolation
- Provider validation
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from encryption_service import EncryptionService
from models import Organization, User


def _load_api_org_api_key_service():
    """Load OrgApiKeyService from the API module, not the shared module."""
    api_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location(
        "api_org_api_key_service",
        os.path.join(api_path, "org_api_key_service.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OrgApiKeyService


OrgApiKeyService = _load_api_org_api_key_service()


@pytest.fixture
def encryption_svc():
    return EncryptionService()


@pytest.fixture
def service(encryption_svc):
    return OrgApiKeyService(encryption_svc)


@pytest.fixture
def org_a(test_db: Session) -> Organization:
    org = Organization(
        id="org-a-id",
        name="Org A",
        display_name="Org A",
        slug="org-a",
        settings={"require_private_keys": False},
    )
    test_db.add(org)
    test_db.commit()
    return org


@pytest.fixture
def org_b(test_db: Session) -> Organization:
    org = Organization(
        id="org-b-id",
        name="Org B",
        display_name="Org B",
        slug="org-b",
        settings={"require_private_keys": True},
    )
    test_db.add(org)
    test_db.commit()
    return org


@pytest.fixture
def admin_user(test_db: Session) -> User:
    from user_service import get_password_hash

    user = User(
        id="admin-org-key-test",
        username="orgkeyadmin@test.com",
        email="orgkeyadmin@test.com",
        name="Org Key Admin",
        hashed_password=get_password_hash("test"),
        is_superadmin=True,
        is_active=True,
        email_verified=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.mark.unit
class TestSetAndGetOrgApiKey:
    """Test setting and retrieving org API keys with encryption round-trip."""

    def test_set_and_get_openai_key(self, service, test_db, org_a, admin_user):
        api_key = "sk-testapikey1234567890abcdef"
        result = service.set_org_api_key(test_db, org_a.id, "openai", api_key, admin_user.id)
        assert result is True

        decrypted = service.get_org_api_key(test_db, org_a.id, "openai")
        assert decrypted == api_key

    def test_set_key_upserts_existing(self, service, test_db, org_a, admin_user):
        key1 = "sk-firstkey12345678901234"
        key2 = "sk-secondkey1234567890123"

        service.set_org_api_key(test_db, org_a.id, "openai", key1, admin_user.id)
        service.set_org_api_key(test_db, org_a.id, "openai", key2, admin_user.id)

        decrypted = service.get_org_api_key(test_db, org_a.id, "openai")
        assert decrypted == key2

    def test_get_nonexistent_key_returns_none(self, service, test_db, org_a):
        result = service.get_org_api_key(test_db, org_a.id, "openai")
        assert result is None

    def test_set_unsupported_provider_returns_false(self, service, test_db, org_a, admin_user):
        result = service.set_org_api_key(
            test_db, org_a.id, "unsupported", "some-key", admin_user.id
        )
        assert result is False

    def test_get_unsupported_provider_returns_none(self, service, test_db, org_a):
        result = service.get_org_api_key(test_db, org_a.id, "unsupported")
        assert result is None


@pytest.mark.unit
class TestRemoveOrgApiKey:
    """Test removing org API keys."""

    def test_remove_existing_key(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )

        result = service.remove_org_api_key(test_db, org_a.id, "openai")
        assert result is True

        decrypted = service.get_org_api_key(test_db, org_a.id, "openai")
        assert decrypted is None

    def test_remove_nonexistent_key_returns_false(self, service, test_db, org_a):
        result = service.remove_org_api_key(test_db, org_a.id, "openai")
        assert result is False

    def test_remove_unsupported_provider_returns_false(self, service, test_db, org_a):
        result = service.remove_org_api_key(test_db, org_a.id, "unsupported")
        assert result is False


@pytest.mark.unit
class TestOrgApiKeyStatus:
    """Test multi-provider status reporting."""

    def test_status_all_unset(self, service, test_db, org_a):
        status = service.get_org_api_key_status(test_db, org_a.id)
        assert all(v is False for v in status.values())
        assert len(status) == len(service.SUPPORTED_PROVIDERS)

    def test_status_some_set(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )
        service.set_org_api_key(
            test_db,
            org_a.id,
            "anthropic",
            "sk-ant-testapikey12345678901234567890abcdef",
            admin_user.id,
        )

        status = service.get_org_api_key_status(test_db, org_a.id)
        assert status["openai"] is True
        assert status["anthropic"] is True
        assert status["google"] is False
        assert status["deepinfra"] is False

    def test_available_providers_returns_display_names(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )

        available = service.get_org_available_providers(test_db, org_a.id)
        assert "OpenAI" in available
        assert "Anthropic" not in available


@pytest.mark.unit
class TestResolveApiKey:
    """Test key resolution based on org settings."""

    def test_resolve_key_no_org_uses_personal(self, service, test_db, admin_user):
        """No org context -> personal key (backward compat)."""
        mock_uaks = MagicMock()
        mock_uaks.get_user_api_key.return_value = "personal-key"
        with patch.dict(
            "sys.modules",
            {"user_api_key_service": MagicMock(user_api_key_service=mock_uaks)},
        ):
            result = service.resolve_api_key(test_db, admin_user.id, None, "openai")
            assert result == "personal-key"
            mock_uaks.get_user_api_key.assert_called_once()

    def test_resolve_key_org_requires_private_keys(self, service, test_db, org_b, admin_user):
        """Org with require_private_keys=true -> personal key."""
        mock_uaks = MagicMock()
        mock_uaks.get_user_api_key.return_value = "personal-key"
        with patch.dict(
            "sys.modules",
            {"user_api_key_service": MagicMock(user_api_key_service=mock_uaks)},
        ):
            result = service.resolve_api_key(test_db, admin_user.id, org_b.id, "openai")
            assert result == "personal-key"
            mock_uaks.get_user_api_key.assert_called_once()

    def test_resolve_key_org_pays_uses_org_key(self, service, test_db, org_a, admin_user):
        """Org with require_private_keys=false -> org key."""
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )

        result = service.resolve_api_key(test_db, admin_user.id, org_a.id, "openai")
        assert result == "sk-testapikey1234567890abcdef"

    def test_resolve_key_org_pays_no_key_returns_none(self, service, test_db, org_a, admin_user):
        """Org with require_private_keys=false but no key set -> None (provider unavailable)."""
        result = service.resolve_api_key(test_db, admin_user.id, org_a.id, "anthropic")
        assert result is None


@pytest.mark.unit
class TestProviderIsolation:
    """Test that setting one provider doesn't affect another."""

    def test_setting_openai_does_not_affect_anthropic(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )

        assert service.get_org_api_key(test_db, org_a.id, "openai") is not None
        assert service.get_org_api_key(test_db, org_a.id, "anthropic") is None

    def test_removing_one_provider_keeps_others(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )
        service.set_org_api_key(
            test_db,
            org_a.id,
            "anthropic",
            "sk-ant-testapikey12345678901234567890abcdef",
            admin_user.id,
        )

        service.remove_org_api_key(test_db, org_a.id, "openai")

        assert service.get_org_api_key(test_db, org_a.id, "openai") is None
        assert service.get_org_api_key(test_db, org_a.id, "anthropic") is not None


@pytest.mark.unit
class TestCrossOrgIsolation:
    """Test that org A keys are not visible in org B context."""

    def test_keys_isolated_between_orgs(self, service, test_db, org_a, org_b, admin_user):
        # org_b has require_private_keys=true, so set it to false for this test
        org_b.settings = {"require_private_keys": False}
        test_db.commit()

        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-orgAkey12345678901234", admin_user.id
        )
        service.set_org_api_key(
            test_db, org_b.id, "openai", "sk-orgBkey12345678901234", admin_user.id
        )

        key_a = service.get_org_api_key(test_db, org_a.id, "openai")
        key_b = service.get_org_api_key(test_db, org_b.id, "openai")

        assert key_a == "sk-orgAkey12345678901234"
        assert key_b == "sk-orgBkey12345678901234"
        assert key_a != key_b


@pytest.mark.unit
class TestRequirePrivateKeysEnforcement:
    """Test that set_org_api_key works regardless of require_private_keys setting."""

    def test_can_set_org_key_even_when_private_required(self, service, test_db, org_b, admin_user):
        """Admins can pre-configure org keys before toggling the setting."""
        result = service.set_org_api_key(
            test_db, org_b.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )
        assert result is True

    def test_can_set_org_key_when_org_pays(self, service, test_db, org_a, admin_user):
        result = service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )
        assert result is True


@pytest.mark.unit
class TestGetAvailableProvidersForContext:
    """Test context-aware provider listing."""

    def test_private_context_uses_personal_providers(self, service, test_db, admin_user):
        mock_uaks = MagicMock()
        mock_uaks.get_user_available_providers.return_value = ["OpenAI"]
        with patch.dict(
            "sys.modules",
            {"user_api_key_service": MagicMock(user_api_key_service=mock_uaks)},
        ):
            result = service.get_available_providers_for_context(test_db, admin_user.id, None)
            assert result == ["OpenAI"]
            mock_uaks.get_user_available_providers.assert_called_once()

    def test_org_pays_uses_org_providers(self, service, test_db, org_a, admin_user):
        service.set_org_api_key(
            test_db, org_a.id, "openai", "sk-testapikey1234567890abcdef", admin_user.id
        )

        result = service.get_available_providers_for_context(test_db, admin_user.id, org_a.id)
        assert "OpenAI" in result

    def test_members_pay_uses_personal_providers(self, service, test_db, org_b, admin_user):
        mock_uaks = MagicMock()
        mock_uaks.get_user_available_providers.return_value = ["Anthropic"]
        with patch.dict(
            "sys.modules",
            {"user_api_key_service": MagicMock(user_api_key_service=mock_uaks)},
        ):
            result = service.get_available_providers_for_context(test_db, admin_user.id, org_b.id)
            assert result == ["Anthropic"]
