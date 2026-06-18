"""
Response Validation Layer for AI Service Outputs.

Provides post-generation validation for providers without strict schema
enforcement: extracts JSON from markdown/code blocks and validates it against a
schema.

There is intentionally NO repair pass. The earlier repair machinery was dead
code (``extract_json_from_text`` only ever returns already-parseable JSON, so the
repair branch was unreachable), and for an academic benchmark fail-closed is the
correct posture anyway: a malformed provider response is reported as a failure
rather than silently rewritten into data of uncertain provenance.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import Draft7Validator

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of JSON schema validation."""
    valid: bool
    data: Optional[Dict[str, Any]]
    errors: List[str]
    raw_content: str
    extracted_json: Optional[str]


class ResponseValidator:
    """
    Validates JSON responses from AI providers.

    Used primarily for providers that don't guarantee valid JSON output
    (Google, DeepInfra, Grok, Mistral, Cohere when using prompt-based).
    """

    # Patterns for extracting JSON from various formats
    JSON_PATTERNS = [
        # Code blocks with json language specifier
        re.compile(r'```json\s*([\s\S]*?)\s*```', re.IGNORECASE),
        # Generic code blocks
        re.compile(r'```\s*([\s\S]*?)\s*```'),
        # Standalone JSON objects (greedy, from first { to last })
        re.compile(r'(\{[\s\S]*\})'),
        # JSON arrays
        re.compile(r'(\[[\s\S]*\])'),
    ]

    def __init__(self, strict: bool = True):
        """
        Initialize the validator.

        Args:
            strict: If True, validation fails on any schema violation.
                   If False, allows additional properties.
        """
        self.strict = strict

    def validate_response(
        self,
        response_content: str,
        json_schema: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate a response against a JSON schema.

        Extracts JSON from the (possibly markdown-wrapped) response and validates
        it against the schema. A response from which no valid JSON can be
        extracted, or that violates the schema, is reported as ``valid=False`` —
        there is no repair pass (fail-closed).

        Args:
            response_content: Raw response content from AI provider
            json_schema: JSON Schema to validate against

        Returns:
            ValidationResult with validation status and parsed data
        """
        errors: List[str] = []

        # Step 1: extract JSON. extract_json_from_text only returns a candidate
        # that already json.loads-es, or None.
        extracted_json = self.extract_json_from_text(response_content)

        if not extracted_json:
            errors.append("Could not extract JSON from response")
            return ValidationResult(
                valid=False,
                data=None,
                errors=errors,
                raw_content=response_content,
                extracted_json=None,
            )

        # Step 2: parse. Guaranteed to succeed (extract_json_from_text already
        # parsed this candidate), so this cannot raise.
        parsed_data = json.loads(extracted_json)

        # Step 3: validate against schema
        schema_errors = self._validate_against_schema(parsed_data, json_schema)

        if schema_errors:
            errors.extend(schema_errors)
            return ValidationResult(
                valid=False,
                data=parsed_data,  # Return parsed data even if schema invalid
                errors=errors,
                raw_content=response_content,
                extracted_json=extracted_json,
            )

        return ValidationResult(
            valid=True,
            data=parsed_data,
            errors=errors,
            raw_content=response_content,
            extracted_json=extracted_json,
        )

    def extract_json_from_text(self, text: str) -> Optional[str]:
        """
        Extract JSON from text that may contain markdown or other content.

        Tries multiple extraction patterns in order of specificity. Only returns
        a candidate that already parses as JSON.

        Args:
            text: Raw text potentially containing JSON

        Returns:
            Extracted JSON string or None if no valid JSON found
        """
        if not text:
            return None

        # First, try to parse the entire content as JSON
        text = text.strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Try each pattern
        for pattern in self.JSON_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                candidate = match.strip() if isinstance(match, str) else match[0].strip()
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue

        return None

    def _validate_against_schema(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> List[str]:
        """
        Validate parsed JSON against a JSON Schema.

        Args:
            data: Parsed JSON data
            schema: JSON Schema

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: List[str] = []

        try:
            validator = Draft7Validator(schema)
            for error in validator.iter_errors(data):
                path = " -> ".join(str(p) for p in error.path) if error.path else "root"
                errors.append(f"Schema error at {path}: {error.message}")
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")

        return errors


def validate_structured_response(
    response_content: str,
    json_schema: Dict[str, Any],
    provider: str,
    strict: bool = True
) -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
    """
    Convenience function to validate a structured response.

    Args:
        response_content: Raw response content
        json_schema: Expected JSON schema
        provider: Provider name (for logging)
        strict: Whether to use strict validation

    Returns:
        Tuple of (is_valid, parsed_data, error_messages)
    """
    validator = ResponseValidator(strict=strict)
    result = validator.validate_response(response_content, json_schema)

    if not result.valid:
        logger.warning(
            f"Response validation failed for {provider}: {result.errors}"
        )

    return result.valid, result.data, result.errors
