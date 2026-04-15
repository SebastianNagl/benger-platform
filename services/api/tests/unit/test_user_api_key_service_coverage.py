"""
Unit tests for services/user_api_key_service.py to increase coverage.
"""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from services.user_api_key_service import UserApiKeyService


class TestInit:
    def test_initialization(self):
        mock_enc = Mock()
        service = UserApiKeyService(mock_enc)
        assert service.encryption_service == mock_enc

    def test_supported_providers(self):
        service = UserApiKeyService(Mock())
        assert "openai" in service.SUPPORTED_PROVIDERS
        assert "anthropic" in service.SUPPORTED_PROVIDERS
        assert "google" in service.SUPPORTED_PROVIDERS

    def test_api_key_fields_mapping(self):
        service = UserApiKeyService(Mock())
        assert service.API_KEY_FIELDS["openai"] == "encrypted_openai_api_key"
        assert service.API_KEY_FIELDS["anthropic"] == "encrypted_anthropic_api_key"


class TestSetUserApiKey:
    def test_unsupported_provider(self):
        service = UserApiKeyService(Mock())
        mock_db = Mock(spec=Session)
        result = service.set_user_api_key(mock_db, "user-1", "unsupported", "key")
        assert result is False

    def test_invalid_format(self):
        mock_enc = Mock()
        mock_enc.is_valid_api_key_format.return_value = False
        service = UserApiKeyService(mock_enc)
        mock_db = Mock(spec=Session)
        result = service.set_user_api_key(mock_db, "user-1", "openai", "bad-key")
        assert result is False

    def test_user_not_found(self):
        mock_enc = Mock()
        mock_enc.is_valid_api_key_format.return_value = True
        service = UserApiKeyService(mock_enc)
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q
        result = service.set_user_api_key(mock_db, "nonexistent", "openai", "sk-test")
        assert result is False

    def test_success(self):
        mock_enc = Mock()
        mock_enc.is_valid_api_key_format.return_value = True
        mock_enc.encrypt_api_key.return_value = "encrypted"

        mock_user = Mock()
        mock_user.id = "user-1"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(mock_enc)
        result = service.set_user_api_key(mock_db, "user-1", "openai", "sk-test")
        assert result is True

    def test_encryption_fails(self):
        mock_enc = Mock()
        mock_enc.is_valid_api_key_format.return_value = True
        mock_enc.encrypt_api_key.return_value = None

        mock_user = Mock()
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(mock_enc)
        result = service.set_user_api_key(mock_db, "user-1", "openai", "sk-test")
        assert result is False


class TestGetUserApiKey:
    def test_unsupported_provider(self):
        service = UserApiKeyService(Mock())
        mock_db = Mock(spec=Session)
        result = service.get_user_api_key(mock_db, "user-1", "unsupported")
        assert result is None

    def test_user_not_found(self):
        service = UserApiKeyService(Mock())
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q
        result = service.get_user_api_key(mock_db, "nonexistent", "openai")
        assert result is None

    def test_no_key_stored(self):
        mock_user = Mock()
        mock_user.encrypted_openai_api_key = None

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.get_user_api_key(mock_db, "user-1", "openai")
        assert result is None

    def test_success(self):
        mock_enc = Mock()
        mock_enc.decrypt_api_key.return_value = "sk-decrypted"

        mock_user = Mock()
        mock_user.encrypted_openai_api_key = "encrypted_value"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(mock_enc)
        result = service.get_user_api_key(mock_db, "user-1", "openai")
        assert result == "sk-decrypted"


class TestRemoveUserApiKey:
    def test_unsupported_provider(self):
        service = UserApiKeyService(Mock())
        mock_db = Mock(spec=Session)
        result = service.remove_user_api_key(mock_db, "user-1", "unsupported")
        assert result is False

    def test_success(self):
        mock_user = Mock()
        mock_user.encrypted_openai_api_key = "encrypted"

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.remove_user_api_key(mock_db, "user-1", "openai")
        assert result is True


class TestGetUserApiKeyStatus:
    def test_user_found(self):
        mock_user = Mock()
        mock_user.encrypted_openai_api_key = "val"
        mock_user.encrypted_anthropic_api_key = None
        mock_user.encrypted_google_api_key = "val"
        mock_user.encrypted_deepinfra_api_key = None
        mock_user.encrypted_grok_api_key = None
        mock_user.encrypted_mistral_api_key = None
        mock_user.encrypted_cohere_api_key = None

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.get_user_api_key_status(mock_db, "user-1")
        assert isinstance(result, dict)

    def test_user_not_found(self):
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.get_user_api_key_status(mock_db, "nonexistent")
        assert isinstance(result, dict)


class TestGetUserAvailableProviders:
    def test_some_available(self):
        mock_user = Mock()
        mock_user.encrypted_openai_api_key = "val"
        mock_user.encrypted_anthropic_api_key = "val"
        mock_user.encrypted_google_api_key = None
        mock_user.encrypted_deepinfra_api_key = None
        mock_user.encrypted_grok_api_key = None
        mock_user.encrypted_mistral_api_key = None
        mock_user.encrypted_cohere_api_key = None

        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_user
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.get_user_available_providers(mock_db, "user-1")
        assert isinstance(result, list)

    def test_user_not_found(self):
        mock_db = Mock(spec=Session)
        mock_q = Mock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        service = UserApiKeyService(Mock())
        result = service.get_user_available_providers(mock_db, "nonexistent")
        assert result == []
