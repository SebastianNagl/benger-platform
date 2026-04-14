"""
Label Config Output Sanitization

Prevents XSS attacks by sanitizing label config data before sending to frontend.
Complements validation by handling output encoding.

Addresses Issue #798: HIGH RISK - Stored XSS vulnerability in label config field names
"""

import html
import re
from typing import Any, Dict


class LabelConfigSanitizer:
    """Sanitizes label config output to prevent XSS attacks"""

    # Dangerous patterns to remove/escape
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers (onclick, onload, etc.)
        r'<iframe[^>]*>.*?</iframe>',  # Iframes
    ]

    @staticmethod
    def sanitize_field_name(field_name: str) -> str:
        """
        Sanitize a field name for safe output

        Args:
            field_name: Raw field name from label config

        Returns:
            Sanitized field name safe for HTML rendering
        """
        if not field_name:
            return field_name

        # HTML escape to prevent tag injection
        sanitized = html.escape(field_name, quote=True)

        # Remove any remaining dangerous patterns
        for pattern in LabelConfigSanitizer.DANGEROUS_PATTERNS:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)

        return sanitized

    @staticmethod
    def sanitize_field(field_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize all string values in a field dictionary

        Args:
            field_dict: Field metadata dictionary

        Returns:
            Sanitized field dictionary
        """
        if not isinstance(field_dict, dict):
            return field_dict

        sanitized = {}
        for key, value in field_dict.items():
            if isinstance(value, str):
                sanitized[key] = LabelConfigSanitizer.sanitize_field_name(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    LabelConfigSanitizer.sanitize_field_name(v) if isinstance(v, str) else v
                    for v in value
                ]
            elif isinstance(value, dict):
                sanitized[key] = LabelConfigSanitizer.sanitize_field(value)
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def sanitize_label_config_response(label_config: str) -> str:
        """
        Sanitize label config XML for safe display

        Note: This escapes the entire XML for display purposes.
        For rendering actual XML, use proper XML escaping on individual attributes.

        Args:
            label_config: Raw label config XML

        Returns:
            Sanitized XML string
        """
        if not label_config:
            return label_config

        # For XML display, escape the entire content
        return html.escape(label_config, quote=True)
