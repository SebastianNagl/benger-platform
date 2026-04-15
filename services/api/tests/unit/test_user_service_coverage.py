"""
Unit tests for auth_module/user_service.py — covers core user management functions.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from auth_module.user_service import (
    sanitize_user_input,
    get_user_by_id,
    get_user_by_username,
    get_user_by_email,
    get_user_by_username_or_email,
    get_users,
    authenticate_user,
    verify_password,
    get_password_hash,
    hash_password,
    check_password,
)


# ============= sanitize_user_input =============


class TestSanitizeUserInput:
    def test_none_input(self):
        assert sanitize_user_input(None) is None

    def test_empty_string(self):
        assert sanitize_user_input("") == ""

    def test_normal_input(self):
        assert sanitize_user_input("John Doe") == "John Doe"

    def test_strips_whitespace(self):
        assert sanitize_user_input("  hello  ") == "hello"

    def test_html_escape(self):
        result = sanitize_user_input("<b>bold</b>")
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_script_removal(self):
        result = sanitize_user_input('test<script>alert("xss")</script>')
        assert "script" not in result.lower() or "&lt;script&gt;" in result

    def test_iframe_removal(self):
        result = sanitize_user_input('<iframe src="evil.com"></iframe>')
        assert "iframe" not in result.lower() or "&lt;iframe" in result

    def test_javascript_protocol(self):
        result = sanitize_user_input("javascript:alert(1)")
        assert "javascript:" not in result.lower()

    def test_data_protocol(self):
        result = sanitize_user_input("data:text/html,<script>alert(1)</script>")
        assert "data:" not in result.lower()

    def test_vbscript_protocol(self):
        result = sanitize_user_input("vbscript:msgbox")
        assert "vbscript:" not in result.lower()

    def test_length_limit(self):
        long_input = "a" * 200
        result = sanitize_user_input(long_input)
        assert len(result) <= 100

    def test_object_tag_removal(self):
        result = sanitize_user_input('<object data="evil"></object>')
        assert "object" not in result.lower() or "&lt;object" in result

    def test_embed_tag_removal(self):
        result = sanitize_user_input('<embed src="evil">')
        assert "embed" not in result.lower() or "&lt;embed" in result


# ============= get_user_by_id =============


class TestGetUserById:
    def test_found(self):
        db = Mock()
        user = Mock(id="u1")
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_by_id(db, "u1")
        assert result == user

    def test_not_found(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_id(db, "u1")
        assert result is None

    def test_schema_issue_in_test_mode(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception(
            "no such column: users.is_superadmin"
        )
        with patch.dict("os.environ", {"TESTING": "true"}):
            result = get_user_by_id(db, "u1")
            assert result is None

    def test_schema_issue_non_test_mode(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception(
            "no such column: users.is_superadmin"
        )
        with patch.dict("os.environ", {"TESTING": "false"}):
            with pytest.raises(Exception):
                get_user_by_id(db, "u1")

    def test_other_exception_raised(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception("Connection error")
        with pytest.raises(Exception, match="Connection error"):
            get_user_by_id(db, "u1")


# ============= get_user_by_username =============


class TestGetUserByUsername:
    def test_found(self):
        db = Mock()
        user = Mock(username="testuser")
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_by_username(db, "testuser")
        assert result == user

    def test_not_found(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_username(db, "unknown")
        assert result is None

    def test_schema_issue(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception(
            "no such column: users.is_superadmin"
        )
        with patch.dict("os.environ", {"TESTING": "true"}):
            result = get_user_by_username(db, "test")
            assert result is None


# ============= get_user_by_email =============


class TestGetUserByEmail:
    def test_found(self):
        db = Mock()
        user = Mock(email="test@test.com")
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_by_email(db, "test@test.com")
        assert result == user

    def test_not_found(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_email(db, "unknown@test.com")
        assert result is None

    def test_schema_issue(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception(
            "no such column: users.is_superadmin"
        )
        with patch.dict("os.environ", {"TESTING": "true"}):
            result = get_user_by_email(db, "test@test.com")
            assert result is None


# ============= get_user_by_username_or_email =============


class TestGetUserByUsernameOrEmail:
    def test_found_by_username(self):
        db = Mock()
        user = Mock(username="testuser")
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_by_username_or_email(db, "testuser")
        assert result == user

    def test_found_by_email(self):
        db = Mock()
        user = Mock(email="test@test.com")
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_by_username_or_email(db, "test@test.com")
        assert result == user

    def test_not_found(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_by_username_or_email(db, "unknown")
        assert result is None

    def test_schema_issue(self):
        db = Mock()
        db.query.return_value.filter.side_effect = Exception(
            "no such column: users.is_superadmin"
        )
        with patch.dict("os.environ", {"TESTING": "true"}):
            result = get_user_by_username_or_email(db, "test")
            assert result is None


# ============= get_users =============


class TestGetUsers:
    def test_default_pagination(self):
        db = Mock()
        users = [Mock(), Mock()]
        db.query.return_value.offset.return_value.limit.return_value.all.return_value = users
        result = get_users(db)
        assert len(result) == 2

    def test_custom_pagination(self):
        db = Mock()
        db.query.return_value.offset.return_value.limit.return_value.all.return_value = []
        result = get_users(db, skip=10, limit=5)
        assert result == []


# ============= authenticate_user =============


class TestAuthenticateUser:
    def test_user_not_found(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = authenticate_user(db, "unknown", "password")
        assert result is None

    def test_wrong_password(self):
        db = Mock()
        user = Mock(hashed_password=get_password_hash("correct_password"))
        db.query.return_value.filter.return_value.first.return_value = user
        result = authenticate_user(db, "testuser", "wrong_password")
        assert result is None

    def test_correct_password(self):
        db = Mock()
        correct_hash = get_password_hash("correct_password")
        user = Mock(hashed_password=correct_hash)
        db.query.return_value.filter.return_value.first.return_value = user
        result = authenticate_user(db, "testuser", "correct_password")
        assert result == user


# ============= Password hashing =============


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "test_password_123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        hashed = get_password_hash("password1")
        assert verify_password("password2", hashed) is False

    def test_aliases(self):
        assert hash_password == get_password_hash
        assert check_password == verify_password

    def test_verify_invalid_hash(self):
        # Should return False, not raise
        result = verify_password("test", "not_a_valid_hash")
        assert result is False

    def test_hash_produces_different_values(self):
        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        # bcrypt generates different salts
        assert h1 != h2

    def test_empty_password(self):
        hashed = get_password_hash("")
        assert verify_password("", hashed) is True
        assert verify_password("non-empty", hashed) is False
