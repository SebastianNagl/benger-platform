"""
Unit tests for routers/auth.py internal helpers — 20.82% coverage.

Tests _ensure_dict, get_user_primary_role, and auth models.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestEnsureDict:
    """Test _ensure_dict helper function."""

    def test_none_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(None) is None

    def test_dict_passthrough(self):
        from routers.auth import _ensure_dict
        d = {"key": "value"}
        assert _ensure_dict(d) == d

    def test_json_string_parsed(self):
        from routers.auth import _ensure_dict
        result = _ensure_dict('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_array_string_returns_none(self):
        from routers.auth import _ensure_dict
        result = _ensure_dict('[1, 2, 3]')
        assert result is None

    def test_invalid_json_string_returns_none(self):
        from routers.auth import _ensure_dict
        result = _ensure_dict("not-json")
        assert result is None

    def test_empty_dict(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict({}) == {}

    def test_empty_json_string(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("{}") == {}

    def test_integer_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(42) is None

    def test_list_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict([1, 2]) is None

    def test_nested_dict(self):
        from routers.auth import _ensure_dict
        d = {"outer": {"inner": "value"}}
        assert _ensure_dict(d) == d

    def test_nested_json_string(self):
        from routers.auth import _ensure_dict
        result = _ensure_dict('{"item_1": 3, "item_2": 5}')
        assert result == {"item_1": 3, "item_2": 5}

    def test_empty_string_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict("") is None

    def test_bool_returns_none(self):
        from routers.auth import _ensure_dict
        assert _ensure_dict(True) is None


class TestGetUserPrimaryRole:
    """Test get_user_primary_role function."""

    def test_no_memberships_returns_none(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []
        result = get_user_primary_role(user, db)
        assert result is None

    def test_single_admin_membership(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        membership = MagicMock()
        membership.role.value = "ORG_ADMIN"
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [membership]
        result = get_user_primary_role(user, db)
        assert result == "ORG_ADMIN"

    def test_single_contributor_membership(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        membership = MagicMock()
        membership.role.value = "CONTRIBUTOR"
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [membership]
        result = get_user_primary_role(user, db)
        assert result == "CONTRIBUTOR"

    def test_single_annotator_membership(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        membership = MagicMock()
        membership.role.value = "ANNOTATOR"
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [membership]
        result = get_user_primary_role(user, db)
        assert result == "ANNOTATOR"

    def test_multiple_memberships_admin_priority(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        m1 = MagicMock()
        m1.role.value = "ANNOTATOR"
        m2 = MagicMock()
        m2.role.value = "ORG_ADMIN"
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [m1, m2]
        result = get_user_primary_role(user, db)
        assert result == "ORG_ADMIN"

    def test_multiple_memberships_contributor_over_annotator(self):
        from routers.auth import get_user_primary_role
        user = SimpleNamespace(id="user-1")
        m1 = MagicMock()
        m1.role.value = "ANNOTATOR"
        m2 = MagicMock()
        m2.role.value = "CONTRIBUTOR"
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [m1, m2]
        result = get_user_primary_role(user, db)
        assert result == "CONTRIBUTOR"


class TestSanitizeUserInput:
    """Test sanitize_user_input from user_service."""

    def test_normal_input(self):
        from auth_module.user_service import sanitize_user_input
        result = sanitize_user_input("Hello World")
        assert result == "Hello World"

    def test_strips_whitespace(self):
        from auth_module.user_service import sanitize_user_input
        result = sanitize_user_input("  hello  ")
        assert result == "hello"

    def test_removes_script_tags(self):
        from auth_module.user_service import sanitize_user_input
        result = sanitize_user_input("<script>alert('xss')</script>hello")
        assert "<script>" not in result

    def test_empty_string(self):
        from auth_module.user_service import sanitize_user_input
        result = sanitize_user_input("")
        assert result == ""

    def test_unicode_preserved(self):
        from auth_module.user_service import sanitize_user_input
        result = sanitize_user_input("Herr M\u00fcller")
        assert "\u00fc" in result
