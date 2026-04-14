"""
Unit tests for email validation functionality
"""

import pytest

# Import the actual email validation functions
from email_validation import (
    extract_domain,
    is_disposable_email,
    is_valid_email,
    sanitize_email,
    validate_bulk_emails,
    validate_email_with_details,
)


class TestEmailValidation:
    """Test email validation functions"""

    def test_valid_emails(self):
        """Test that valid emails are correctly identified"""
        valid_emails = [
            "user@example.com",
            "john.doe@company.co.uk",
            "alice+tag@domain.org",
            "bob_smith@sub.domain.com",
            "123@numbers.com",
            "a@b.co",
        ]

        for email in valid_emails:
            assert is_valid_email(email), f"{email} should be valid"
            is_valid, error = validate_email_with_details(email)
            assert is_valid, f"{email} should be valid, got error: {error}"

    def test_invalid_emails(self):
        """Test that invalid emails are correctly identified"""
        invalid_emails = [
            "",  # Empty
            "notanemail",  # No @
            "@example.com",  # No local part
            "user@",  # No domain
            "user @example.com",  # Space
            "user@example",  # No TLD
            "user..name@example.com",  # Consecutive dots
            ".user@example.com",  # Starts with dot
            "user.@example.com",  # Ends with dot
            "user@@example.com",  # Double @
            "user@.example.com",  # Domain starts with dot
            "user@example..com",  # Domain has consecutive dots
            "a" * 65 + "@example.com",  # Local part too long
            "user@" + "a" * 254 + ".com",  # Domain too long
        ]

        for email in invalid_emails:
            assert not is_valid_email(email), f"{email} should be invalid"
            is_valid, error = validate_email_with_details(email)
            assert not is_valid, f"{email} should be invalid"
            assert error is not None, f"Should have error message for {email}"

    def test_validate_email_with_details_messages(self):
        """Test that detailed error messages are correct"""
        test_cases = [
            ("", "Email address is required"),
            ("user @example.com", "Email address cannot contain whitespace"),
            ("notanemail", "Email address must contain @ symbol"),
            ("user@@example.com", "Email address can only contain one @ symbol"),
            ("@example.com", "Email address must have a local part before @"),
            ("user@", "Email address must have a domain after @"),
            ("user@example", "Domain must contain at least one dot"),
            (".user@example.com", "Local part cannot start or end with a dot"),
            ("user..name@example.com", "Local part cannot contain consecutive dots"),
            ("user@.example.com", "Domain cannot start or end with a dot"),
        ]

        for email, expected_error in test_cases:
            is_valid, error = validate_email_with_details(email)
            assert not is_valid, f"{email} should be invalid"
            assert (
                expected_error in error
            ), f"Expected '{expected_error}' in error for {email}, got: {error}"

    def test_sanitize_email(self):
        """Test email sanitization"""
        test_cases = [
            ("  user@example.com  ", "user@example.com"),  # Trim whitespace
            ("USER@EXAMPLE.COM", "user@example.com"),  # Lowercase
            ("user @example.com", "user@example.com"),  # Remove spaces
            ("valid@email.com", "valid@email.com"),  # Already valid
            ("invalid@@email", None),  # Cannot be sanitized
            ("", None),  # Empty
        ]

        for input_email, expected in test_cases:
            result = sanitize_email(input_email)
            assert (
                result == expected
            ), f"sanitize_email('{input_email}') = {result}, expected {expected}"

    def test_extract_domain(self):
        """Test domain extraction"""
        test_cases = [
            ("user@example.com", "example.com"),
            ("alice@sub.domain.org", "sub.domain.org"),
            ("BOB@COMPANY.COM", "company.com"),  # Lowercase
            ("invalid", None),  # Invalid email
            ("", None),  # Empty
        ]

        for email, expected in test_cases:
            result = extract_domain(email)
            assert result == expected, f"extract_domain('{email}') = {result}, expected {expected}"

    def test_is_disposable_email(self):
        """Test disposable email detection"""
        disposable_emails = [
            "test@mailinator.com",
            "user@guerrillamail.com",
            "temp@10minutemail.com",
            "throwaway@yopmail.com",
        ]

        regular_emails = [
            "user@gmail.com",
            "alice@company.com",
            "bob@university.edu",
        ]

        for email in disposable_emails:
            assert is_disposable_email(email), f"{email} should be identified as disposable"

        for email in regular_emails:
            assert not is_disposable_email(email), f"{email} should not be identified as disposable"

    def test_validate_bulk_emails(self):
        """Test bulk email validation"""
        emails = [
            "valid1@example.com",
            "valid2@company.org",
            "invalid@@email",
            "",
            "nospace @test.com",
            "valid3@domain.co.uk",
        ]

        result = validate_bulk_emails(emails)

        assert len(result["valid"]) == 3
        assert len(result["invalid"]) == 3
        assert result["stats"]["total"] == 6
        assert result["stats"]["valid_count"] == 3
        assert result["stats"]["invalid_count"] == 3
        assert result["stats"]["validity_rate"] == 50.0

        # Check that valid emails are correct
        assert "valid1@example.com" in result["valid"]
        assert "valid2@company.org" in result["valid"]
        assert "valid3@domain.co.uk" in result["valid"]

        # Check that invalid emails have error messages
        invalid_dict = {email: error for email, error in result["invalid"]}
        assert "invalid@@email" in invalid_dict
        assert "" in invalid_dict
        assert "nospace @test.com" in invalid_dict

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        # Maximum valid lengths
        max_local = "a" * 64
        max_domain = "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "com"
        assert is_valid_email(f"{max_local}@example.com")
        assert is_valid_email(f"user@{max_domain}")

        # Just over maximum lengths
        too_long_local = "a" * 65
        assert not is_valid_email(f"{too_long_local}@example.com")

        # Unicode and special characters (should be invalid in our implementation)
        assert not is_valid_email("üser@example.com")
        assert not is_valid_email("user@exämple.com")

    def test_case_insensitivity(self):
        """Test that email validation is case-insensitive"""
        emails = [
            "User@Example.Com",
            "USER@EXAMPLE.COM",
            "user@example.com",
            "UsEr@ExAmPlE.cOm",
        ]

        for email in emails:
            assert is_valid_email(email), f"{email} should be valid regardless of case"
            sanitized = sanitize_email(email)
            assert sanitized == "user@example.com", f"All should sanitize to lowercase"


class TestEmailValidationIntegration:
    """Integration tests for email validation with notification system"""

    # test_notification_skips_invalid_emails, test_user_creation_validates_email,
    # and test_profile_update_validates_email removed: all had empty bodies.
    # These belong in integration tests with real services.
    pass


if __name__ == "__main__":
    import sys

    pytest.main([sys.argv[0], "-v"])
