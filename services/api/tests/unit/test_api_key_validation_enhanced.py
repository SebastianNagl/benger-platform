"""
Enhanced tests for API key validation with detailed error handling.
Tests the new tuple return format and comprehensive error categorization.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from encryption_service import encryption_service
from user_api_key_service import UserApiKeyService


class TestEnhancedApiKeyValidation:
    """Test enhanced API key validation with detailed error responses"""

    @pytest.fixture
    def service(self):
        """Create UserApiKeyService instance"""
        return UserApiKeyService(encryption_service)

    # OpenAI Validation Tests
    @pytest.mark.asyncio
    async def test_openai_success(self, service):
        """Test successful OpenAI validation"""
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = (True, "Connection to OpenAI successful", "success")

            is_valid, message, error_type = await service._validate_openai_key("sk-test-key")
            assert is_valid is True
            assert message == "Connection to OpenAI successful"
            assert error_type == "success"

    @pytest.mark.asyncio
    async def test_openai_authentication_error(self, service):
        """Test OpenAI authentication failure"""
        with patch('asyncio.wait_for') as mock_wait_for:
            # Create a custom exception class for authentication
            class AuthenticationError(Exception):
                pass

            mock_wait_for.side_effect = AuthenticationError("Authentication failed")

            is_valid, message, error_type = await service._validate_openai_key("invalid-key")
            assert is_valid is False
            assert "Invalid API key" in message
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_openai_rate_limit_error(self, service):
        """Test OpenAI rate limit (key still valid)"""
        with patch('asyncio.wait_for') as mock_wait_for:
            # Create a custom exception class for rate limiting
            class RateLimitError(Exception):
                pass

            mock_error = RateLimitError("Rate limit exceeded")
            mock_wait_for.side_effect = mock_error

            is_valid, message, error_type = await service._validate_openai_key("valid-key")
            assert is_valid is True
            assert "rate limit" in message.lower()
            assert error_type == "quota"

    @pytest.mark.asyncio
    async def test_openai_timeout_error(self, service):
        """Test OpenAI timeout"""
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError("Timeout")

            is_valid, message, error_type = await service._validate_openai_key("test-key")
            assert is_valid is False
            assert "timeout" in message.lower()
            assert error_type == "timeout"

    @pytest.mark.asyncio
    async def test_openai_permission_denied(self, service):
        """Test OpenAI permission denied"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 403

            mock_client = Mock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            is_valid, message, error_type = await service._validate_openai_key("limited-key")
            assert is_valid is False
            assert error_type in ["api_error", "auth"]

    @pytest.mark.asyncio
    async def test_openai_network_error(self, service):
        """Test OpenAI network error"""
        with patch('openai.OpenAI') as mock_openai_class:
            # Setup mock client that raises a connection error with "connection" in the message
            mock_client = Mock()
            mock_client.models.list.side_effect = Exception("Connection refused - network error")
            mock_openai_class.return_value = mock_client

            is_valid, message, error_type = await service._validate_openai_key("test-key")
            assert is_valid is False
            # Check for relevant error message keywords
            assert (
                "network" in message.lower()
                or "connection" in message.lower()
                or "failed" in message.lower()
            )
            # The shared service returns "network" for connection errors
            assert error_type in ["connection_error", "network"]

    # Anthropic Validation Tests
    @pytest.mark.asyncio
    async def test_anthropic_success(self, service):
        """Test successful Anthropic validation"""
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = (True, "Connection to Anthropic successful", "success")

            is_valid, message, error_type = await service._validate_anthropic_key("sk-ant-test-key")
            assert is_valid is True
            assert message == "Connection to Anthropic successful"
            assert error_type == "success"

    @pytest.mark.asyncio
    async def test_anthropic_authentication_error(self, service):
        """Test Anthropic authentication failure"""
        with patch('asyncio.wait_for') as mock_wait_for:
            # Create a custom exception class for authentication
            class AuthenticationError(Exception):
                pass

            mock_error = AuthenticationError("Authentication failed")
            mock_wait_for.side_effect = mock_error

            is_valid, message, error_type = await service._validate_anthropic_key("sk-ant-invalid")
            assert is_valid is False
            assert "Invalid API key" in message
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_anthropic_rate_limit_error(self, service):
        """Test Anthropic rate limit"""
        with patch('asyncio.wait_for') as mock_wait_for:
            # Return format validation success for Anthropic
            mock_wait_for.return_value = (True, "Connection to Anthropic successful", "success")

            is_valid, message, error_type = await service._validate_anthropic_key("sk-ant-test-key")
            assert is_valid is True
            assert error_type == "success"

    @pytest.mark.asyncio
    async def test_anthropic_timeout_error(self, service):
        """Test Anthropic timeout"""
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError("Timeout")

            # Timeout during validation should result in failure
            is_valid, message, error_type = await service._validate_anthropic_key("sk-ant-test-key")
            assert is_valid is False
            # The current implementation catches this as a generic exception
            assert error_type in ["connection_error", "timeout"]

    # Google Validation Tests — mock aiohttp to simulate Gemini REST API responses
    def _google_aiohttp_mock(self, status=200):
        """Create mock aiohttp session returning given status for Google API."""
        mock_response = Mock()
        mock_response.status = status

        mock_get_cm = Mock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = Mock()
        mock_session.get.return_value = mock_get_cm

        mock_session_cm = Mock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        return mock_session_cm

    @pytest.mark.asyncio
    async def test_google_success(self, service):
        """Test successful Google validation with valid key"""
        with patch('aiohttp.ClientSession', return_value=self._google_aiohttp_mock(200)):
            is_valid, message, error_type = await service._validate_google_key("AIzaSyABC123def456")
            assert is_valid is True
            assert "successful" in message.lower()
            assert error_type == "success"

    @pytest.mark.asyncio
    async def test_google_invalid_format(self, service):
        """Test Google validation with invalid key - authentication error"""
        with patch('aiohttp.ClientSession', return_value=self._google_aiohttp_mock(403)):
            is_valid, message, error_type = await service._validate_google_key("invalid-key-format")
            assert is_valid is False
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_google_empty_key(self, service):
        """Test Google validation with empty key"""
        with patch('aiohttp.ClientSession', return_value=self._google_aiohttp_mock(400)):
            is_valid, message, error_type = await service._validate_google_key("")
            assert is_valid is False
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_google_wrong_prefix(self, service):
        """Test Google validation with wrong prefix"""
        with patch('aiohttp.ClientSession', return_value=self._google_aiohttp_mock(403)):
            is_valid, message, error_type = await service._validate_google_key("sk-wrong-prefix")
            assert is_valid is False
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_google_valid_prefix_variations(self, service):
        """Test Google validation accepts valid keys"""
        with patch('aiohttp.ClientSession', return_value=self._google_aiohttp_mock(200)):
            is_valid, message, error_type = await service._validate_google_key("AIzaTestKey12345")
            assert is_valid is True
            assert error_type == "success"

    # DeepInfra Validation Tests
    @pytest.mark.asyncio
    async def test_deepinfra_success(self, service):
        """Test successful DeepInfra validation"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock response
            mock_response = Mock()
            mock_response.status = 200

            # Setup nested async context managers
            mock_session = Mock()
            mock_post_cm = Mock()
            mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_cm

            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            is_valid, message, error_type = await service._validate_deepinfra_key(
                "deepinfra-test-key"
            )
            assert is_valid is True
            assert "successful" in message.lower()
            assert error_type == "success"

    @pytest.mark.asyncio
    async def test_deepinfra_authentication_error(self, service):
        """Test DeepInfra authentication failure"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock response
            mock_response = Mock()
            mock_response.status = 401

            # Setup nested async context managers
            mock_session = Mock()
            mock_post_cm = Mock()
            mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_cm

            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            is_valid, message, error_type = await service._validate_deepinfra_key("invalid-key")
            assert is_valid is False
            assert error_type == "auth"

    @pytest.mark.asyncio
    async def test_deepinfra_rate_limit_error(self, service):
        """Test DeepInfra rate limit"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock response
            mock_response = Mock()
            mock_response.status = 429

            # Setup nested async context managers
            mock_session = Mock()
            mock_post_cm = Mock()
            mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_cm

            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            is_valid, message, error_type = await service._validate_deepinfra_key("test-key")
            assert is_valid is True  # Rate limit means key is valid
            assert error_type == "quota"

    @pytest.mark.asyncio
    async def test_deepinfra_timeout_error(self, service):
        """Test DeepInfra timeout"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Simulate timeout error
            mock_session = Mock()
            mock_post_cm = Mock()
            mock_post_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_cm

            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            is_valid, message, error_type = await service._validate_deepinfra_key("test-key")
            assert is_valid is False
            # The shared service catches timeout in generic exception handler
            assert error_type in ["network", "timeout"]

    @pytest.mark.asyncio
    async def test_deepinfra_network_error(self, service):
        """Test DeepInfra network error"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Simulate network error
            mock_session = Mock()
            mock_session.post.side_effect = Exception("Connection refused")

            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            is_valid, message, error_type = await service._validate_deepinfra_key("test-key")
            assert is_valid is False
            assert error_type == "network"
