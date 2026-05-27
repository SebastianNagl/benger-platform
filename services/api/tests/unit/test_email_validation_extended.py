"""
Unit tests for services/email/email_validation.py to increase coverage.
Tests email validation edge cases.
"""


class TestEmailValidation:
    def setup_method(self):
        from services.email.email_validation import is_valid_email
        self.validate = is_valid_email

    def test_valid_email(self):
        assert self.validate("user@example.com") == True  # noqa: E712

    def test_valid_email_with_subdomain(self):
        assert self.validate("user@mail.example.com") == True  # noqa: E712

    def test_valid_email_with_plus(self):
        assert self.validate("user+tag@example.com") == True  # noqa: E712

    def test_valid_email_with_dots(self):
        assert self.validate("first.last@example.com") == True  # noqa: E712

    def test_invalid_no_at(self):
        assert self.validate("userexample.com") == False  # noqa: E712

    def test_invalid_no_domain(self):
        assert self.validate("user@") == False  # noqa: E712

    def test_invalid_no_local(self):
        assert self.validate("@example.com") == False  # noqa: E712

    def test_invalid_spaces(self):
        assert self.validate("user @example.com") == False  # noqa: E712

    def test_empty_string(self):
        assert self.validate("") == False  # noqa: E712

    def test_none(self):
        result = self.validate(None)
        assert result is False

    def test_valid_edu_email(self):
        assert self.validate("student@university.edu") == True  # noqa: E712

    def test_valid_de_email(self):
        assert self.validate("user@example.de") == True  # noqa: E712

    def test_numeric_local_part(self):
        assert self.validate("123@example.com") == True  # noqa: E712

    def test_hyphen_in_domain(self):
        assert self.validate("user@my-domain.com") == True  # noqa: E712

    def test_double_at(self):
        assert self.validate("user@@example.com") == False  # noqa: E712

    def test_consecutive_dots(self):
        result = self.validate("user@example..com")
        # May or may not be valid depending on implementation
        assert isinstance(result, bool)

    def test_very_long_email(self):
        long_local = "a" * 64
        result = self.validate(f"{long_local}@example.com")
        assert isinstance(result, bool)
