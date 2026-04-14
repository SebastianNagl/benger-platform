"""
Email Validation Utilities for BenGER

This module provides email validation functions to ensure email addresses
are properly formatted and valid before sending notifications.
"""

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# RFC 5322 compliant email regex pattern
# This pattern validates most common email addresses while being RFC-compliant
# Updated to ensure no dots at the end of local part
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._%+-]{0,62}[a-zA-Z0-9_%+-]@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$|^[a-zA-Z0-9]@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)

# Common invalid email patterns to catch
INVALID_PATTERNS = [
    r"@example\.com$",  # Example domain
    r"@test\.com$",  # Test domain
    r"^noreply@",  # No-reply addresses (optional check)
    r"^test@",  # Test addresses
    r"^admin@localhost",  # Localhost addresses
]


def is_valid_email(email: str) -> bool:
    """
    Validate email format using RFC 5322 compliant regex.

    Args:
        email: Email address to validate

    Returns:
        True if email format is valid, False otherwise
    """
    if not email:
        return False

    # Convert to lowercase for validation
    email = email.strip().lower()

    # Check basic format
    if not EMAIL_PATTERN.match(email):
        return False

    # Check for common invalid patterns (optional)
    for pattern in INVALID_PATTERNS:
        if re.search(pattern, email, re.IGNORECASE):
            logger.warning(f"Email {email} matches invalid pattern: {pattern}")
            # We still return True here as these are valid formats,
            # just potentially unwanted. This can be made stricter if needed.

    # Additional checks
    # Check for consecutive dots
    if ".." in email:
        return False

    # Check for valid domain part
    if email.count("@") != 1:
        return False

    local, domain = email.split("@")

    # Local part checks
    if not local or len(local) > 64:
        return False

    # Domain part checks
    if not domain or len(domain) > 253:
        return False

    # Domain should have at least one dot
    if "." not in domain:
        return False

    return True


def validate_email_with_details(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email and return detailed error message if invalid.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if email is valid
        - error_message: Detailed error message if invalid, None if valid
    """
    if not email:
        return False, "Email address is required"

    email = email.strip()

    # Check for whitespace
    if " " in email or "\t" in email or "\n" in email:
        return False, "Email address cannot contain whitespace"

    # Check for @ symbol
    if "@" not in email:
        return False, "Email address must contain @ symbol"

    if email.count("@") > 1:
        return False, "Email address can only contain one @ symbol"

    # Split into local and domain parts
    try:
        local, domain = email.split("@")
    except ValueError:
        return False, "Invalid email format"

    # Validate local part
    if not local:
        return False, "Email address must have a local part before @"

    if len(local) > 64:
        return False, "Local part (before @) is too long (max 64 characters)"

    if local.startswith(".") or local.endswith("."):
        return False, "Local part cannot start or end with a dot"

    if ".." in local:
        return False, "Local part cannot contain consecutive dots"

    # Validate domain part
    if not domain:
        return False, "Email address must have a domain after @"

    if len(domain) > 253:
        return False, "Domain part is too long (max 253 characters)"

    if "." not in domain:
        return False, "Domain must contain at least one dot"

    if domain.startswith(".") or domain.endswith("."):
        return False, "Domain cannot start or end with a dot"

    if ".." in domain:
        return False, "Domain cannot contain consecutive dots"

    # Check with regex for final validation
    if not EMAIL_PATTERN.match(email.lower()):
        return False, "Email address format is invalid"

    return True, None


def sanitize_email(email: str) -> Optional[str]:
    """
    Sanitize and normalize an email address.

    Args:
        email: Email address to sanitize

    Returns:
        Sanitized email address or None if invalid
    """
    if not email:
        return None

    # Remove leading/trailing whitespace
    email = email.strip()

    # Convert to lowercase (email addresses are case-insensitive)
    email = email.lower()

    # Remove any extra spaces
    email = email.replace(" ", "")

    # Validate the sanitized email
    if is_valid_email(email):
        return email

    return None


def extract_domain(email: str) -> Optional[str]:
    """
    Extract the domain part from an email address.

    Args:
        email: Email address

    Returns:
        Domain part of the email or None if invalid
    """
    if not is_valid_email(email):
        return None

    return email.split("@")[1].lower()


def is_disposable_email(email: str) -> bool:
    """
    Check if an email address uses a known disposable email service.

    Args:
        email: Email address to check

    Returns:
        True if the email uses a disposable service, False otherwise
    """
    # Common disposable email domains (this is a small subset)
    DISPOSABLE_DOMAINS = {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "throwaway.email",
        "yopmail.com",
        "temp-mail.org",
        "maildrop.cc",
        "mintemail.com",
        "sharklasers.com",
    }

    domain = extract_domain(email)
    if domain:
        return domain in DISPOSABLE_DOMAINS

    return False


def validate_bulk_emails(emails: list[str]) -> dict:
    """
    Validate multiple email addresses in bulk.

    Args:
        emails: List of email addresses to validate

    Returns:
        Dictionary with validation results:
        - valid: List of valid email addresses
        - invalid: List of tuples (email, error_message)
        - stats: Statistics about the validation
    """
    valid_emails = []
    invalid_emails = []

    for email in emails:
        is_valid, error = validate_email_with_details(email)
        if is_valid:
            valid_emails.append(email)
        else:
            invalid_emails.append((email, error))

    return {
        "valid": valid_emails,
        "invalid": invalid_emails,
        "stats": {
            "total": len(emails),
            "valid_count": len(valid_emails),
            "invalid_count": len(invalid_emails),
            "validity_rate": len(valid_emails) / len(emails) * 100 if emails else 0,
        },
    }
