"""
Tests for org context middleware.

Targets: middleware/org_context.py lines 31-52, 56-81
"""

from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from main import app
from middleware.org_context import OrgContextMiddleware, SLUG_PATTERN


class TestSlugPattern:
    """Test the SLUG_PATTERN regex."""

    def test_valid_slug(self):
        assert SLUG_PATTERN.match("my-org") is not None

    def test_valid_slug_numbers(self):
        assert SLUG_PATTERN.match("org123") is not None

    def test_invalid_slug_uppercase(self):
        assert SLUG_PATTERN.match("My-Org") is None

    def test_invalid_slug_special(self):
        assert SLUG_PATTERN.match("my_org!") is None

    def test_invalid_slug_spaces(self):
        assert SLUG_PATTERN.match("my org") is None


class TestOrgContextMiddleware:
    """Test OrgContextMiddleware dispatch logic."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_request_without_org_headers(self, client):
        """Test request without any organization headers."""
        response = client.get("/healthz")
        assert response.status_code == status.HTTP_200_OK

    def test_request_with_org_context_header(self, client):
        """Test request with X-Organization-Context header passes through."""
        response = client.get(
            "/healthz",
            headers={"X-Organization-Context": "org-id-123"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_request_with_invalid_slug(self, client):
        """Test request with invalid slug format returns 400."""
        response = client.get(
            "/healthz",
            headers={"X-Organization-Slug": "INVALID_SLUG!"},
        )
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_request_with_valid_slug_not_found(self, client):
        """Test request with valid slug that doesn't resolve."""
        with patch("middleware.org_context.OrgContextMiddleware._resolve_slug") as mock_resolve:
            mock_resolve.return_value = None
            response = client.get(
                "/healthz",
                headers={"X-Organization-Slug": "unknown-org"},
            )
            assert response.status_code == status.HTTP_200_OK

    def test_resolve_slug_from_cache(self):
        """Test slug resolution from Redis cache."""
        middleware = OrgContextMiddleware(app)
        with patch("redis_cache.OrgSlugCache") as mock_cache:
            mock_cache.get_org_id.return_value = "cached-org-id"
            result = middleware._resolve_slug("test-org")
            assert result == "cached-org-id"

    def test_resolve_slug_from_db(self):
        """Test slug resolution from database when cache misses."""
        middleware = OrgContextMiddleware(app)
        with patch("redis_cache.OrgSlugCache") as mock_cache:
            mock_cache.get_org_id.return_value = None
            mock_cache.set_org_id.return_value = None

            with patch("database.SessionLocal") as mock_session_local:
                mock_db = Mock()
                mock_result = Mock()
                mock_result.id = "db-org-id"
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.first.return_value = mock_result
                mock_query.filter.return_value = mock_filter
                mock_db.query.return_value = mock_query
                mock_session_local.return_value = mock_db

                result = middleware._resolve_slug("test-org")
                assert result == "db-org-id"
                mock_db.close.assert_called_once()

    def test_resolve_slug_db_not_found(self):
        """Test slug resolution when slug not in DB."""
        middleware = OrgContextMiddleware(app)
        with patch("redis_cache.OrgSlugCache") as mock_cache:
            mock_cache.get_org_id.return_value = None

            with patch("database.SessionLocal") as mock_session_local:
                mock_db = Mock()
                mock_query = Mock()
                mock_filter = Mock()
                mock_filter.first.return_value = None
                mock_query.filter.return_value = mock_filter
                mock_db.query.return_value = mock_query
                mock_session_local.return_value = mock_db

                result = middleware._resolve_slug("nonexistent-org")
                assert result is None

    def test_resolve_slug_db_exception(self):
        """Test slug resolution with DB exception."""
        middleware = OrgContextMiddleware(app)
        with patch("redis_cache.OrgSlugCache") as mock_cache:
            mock_cache.get_org_id.return_value = None

            with patch("database.SessionLocal") as mock_session_local:
                mock_session_local.side_effect = Exception("DB error")

                result = middleware._resolve_slug("test-org")
                assert result is None
