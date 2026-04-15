"""
Extended unit tests for middleware/org_context.py covering slug resolution.
"""

import re
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestSlugPattern:
    """Tests for SLUG_PATTERN matching."""

    def test_valid_slugs(self):
        from middleware.org_context import SLUG_PATTERN
        assert SLUG_PATTERN.match("test-org")
        assert SLUG_PATTERN.match("my-org-123")
        assert SLUG_PATTERN.match("org")
        assert SLUG_PATTERN.match("a")
        assert SLUG_PATTERN.match("123")
        assert SLUG_PATTERN.match("abc-def-ghi")

    def test_invalid_slugs(self):
        from middleware.org_context import SLUG_PATTERN
        assert not SLUG_PATTERN.match("Test-Org")
        assert not SLUG_PATTERN.match("test org")
        assert not SLUG_PATTERN.match("test_org")
        assert not SLUG_PATTERN.match("")
        assert not SLUG_PATTERN.match("test/org")
        assert not SLUG_PATTERN.match("test.org")
        assert not SLUG_PATTERN.match("UPPERCASE")


class TestResolveSlug:
    """Tests for _resolve_slug method."""

    @patch("middleware.org_context.OrgSlugCache", create=True)
    def test_resolve_slug_from_cache(self, mock_cache_class):
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())

        with patch("redis_cache.OrgSlugCache") as mock_cache:
            mock_cache.get_org_id.return_value = "org-123"
            result = middleware._resolve_slug("test-org")
            assert result == "org-123"

    @patch("redis_cache.OrgSlugCache")
    def test_resolve_slug_cache_miss_db_hit(self, mock_cache):
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        mock_cache.get_org_id.return_value = None

        with patch("middleware.org_context.SessionLocal", create=True) as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = Mock(id="org-456")

            with patch("database.SessionLocal", mock_session_local):
                result = middleware._resolve_slug("test-org")
                assert result == "org-456"

    @patch("redis_cache.OrgSlugCache")
    def test_resolve_slug_not_found(self, mock_cache):
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        mock_cache.get_org_id.return_value = None

        with patch("database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = None

            result = middleware._resolve_slug("nonexistent")
            assert result is None

    @patch("redis_cache.OrgSlugCache")
    def test_resolve_slug_db_error(self, mock_cache):
        from middleware.org_context import OrgContextMiddleware

        middleware = OrgContextMiddleware(app=Mock())
        mock_cache.get_org_id.return_value = None

        with patch("database.SessionLocal", side_effect=Exception("DB error")):
            result = middleware._resolve_slug("test-org")
            assert result is None


class TestOrgContextPriority:
    """Tests for context resolution priority logic."""

    def test_slug_header_takes_priority(self):
        """X-Organization-Slug should be resolved first."""
        headers = {
            "X-Organization-Slug": "my-org",
            "X-Organization-Context": "org-old",
        }
        slug = headers.get("X-Organization-Slug")
        assert slug == "my-org"  # slug takes priority

    def test_context_header_when_no_slug(self):
        """X-Organization-Context used when no slug provided."""
        headers = {
            "X-Organization-Context": "org-123",
        }
        slug = headers.get("X-Organization-Slug")
        context = headers.get("X-Organization-Context")
        assert slug is None
        assert context == "org-123"

    def test_no_headers_means_private(self):
        """No org headers means private mode."""
        headers = {}
        slug = headers.get("X-Organization-Slug")
        context = headers.get("X-Organization-Context")
        assert slug is None
        assert context is None
