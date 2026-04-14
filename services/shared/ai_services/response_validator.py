"""
Response Validation Layer for AI Service Outputs.

Provides post-generation validation for providers without strict schema enforcement.
Handles JSON extraction from markdown blocks, validation against schemas, and
repair of common JSON formatting issues.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import jsonschema
from jsonschema import Draft7Validator, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of JSON schema validation."""
    valid: bool
    data: Optional[Dict[str, Any]]
    errors: List[str]
    raw_content: str
    extracted_json: Optional[str]
    repair_attempted: bool
    repair_successful: bool


@dataclass
class RepairResult:
    """Result of JSON repair attempt."""
    success: bool
    repaired_json: Optional[str]
    original_error: str
    repair_method: Optional[str]


class ResponseValidator:
    """
    Validates and repairs JSON responses from AI providers.

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
        attempt_repair: bool = True
    ) -> ValidationResult:
        """
        Validate a response against a JSON schema.

        Args:
            response_content: Raw response content from AI provider
            json_schema: JSON Schema to validate against
            attempt_repair: Whether to attempt repair on invalid JSON

        Returns:
            ValidationResult with validation status and parsed data
        """
        errors: List[str] = []
        extracted_json: Optional[str] = None
        repair_attempted = False
        repair_successful = False
        parsed_data: Optional[Dict[str, Any]] = None

        # Step 1: Try to extract JSON from the response
        extracted_json = self.extract_json_from_text(response_content)

        if not extracted_json:
            errors.append("Could not extract JSON from response")
            return ValidationResult(
                valid=False,
                data=None,
                errors=errors,
                raw_content=response_content,
                extracted_json=None,
                repair_attempted=False,
                repair_successful=False,
            )

        # Step 2: Try to parse the extracted JSON
        try:
            parsed_data = json.loads(extracted_json)
        except json.JSONDecodeError as e:
            errors.append(f"JSON parse error: {str(e)}")

            if attempt_repair:
                repair_attempted = True
                repair_result = self.attempt_repair(extracted_json, str(e))

                if repair_result.success and repair_result.repaired_json:
                    try:
                        parsed_data = json.loads(repair_result.repaired_json)
                        extracted_json = repair_result.repaired_json
                        repair_successful = True
                        errors.append(f"Repair successful via {repair_result.repair_method}")
                    except json.JSONDecodeError as e2:
                        errors.append(f"Repair failed: {str(e2)}")

        if parsed_data is None:
            return ValidationResult(
                valid=False,
                data=None,
                errors=errors,
                raw_content=response_content,
                extracted_json=extracted_json,
                repair_attempted=repair_attempted,
                repair_successful=repair_successful,
            )

        # Step 3: Validate against schema
        schema_errors = self._validate_against_schema(parsed_data, json_schema)

        if schema_errors:
            errors.extend(schema_errors)
            return ValidationResult(
                valid=False,
                data=parsed_data,  # Return parsed data even if schema invalid
                errors=errors,
                raw_content=response_content,
                extracted_json=extracted_json,
                repair_attempted=repair_attempted,
                repair_successful=repair_successful,
            )

        return ValidationResult(
            valid=True,
            data=parsed_data,
            errors=errors,  # May contain repair notes
            raw_content=response_content,
            extracted_json=extracted_json,
            repair_attempted=repair_attempted,
            repair_successful=repair_successful,
        )

    def extract_json_from_text(self, text: str) -> Optional[str]:
        """
        Extract JSON from text that may contain markdown or other content.

        Tries multiple extraction patterns in order of specificity.

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

    def attempt_repair(self, json_string: str, error: str) -> RepairResult:
        """
        Attempt to repair common JSON formatting issues.

        Args:
            json_string: Malformed JSON string
            error: Error message from initial parse attempt

        Returns:
            RepairResult with repair status and repaired JSON if successful
        """
        repair_methods = [
            ("trailing_comma", self._fix_trailing_commas),
            ("unquoted_keys", self._fix_unquoted_keys),
            ("single_quotes", self._fix_single_quotes),
            ("newline_in_string", self._fix_newlines_in_strings),
            ("missing_closing", self._fix_missing_closing),
            ("escape_sequences", self._fix_escape_sequences),
        ]

        for method_name, repair_func in repair_methods:
            try:
                repaired = repair_func(json_string)
                json.loads(repaired)
                return RepairResult(
                    success=True,
                    repaired_json=repaired,
                    original_error=error,
                    repair_method=method_name,
                )
            except (json.JSONDecodeError, Exception):
                continue

        return RepairResult(
            success=False,
            repaired_json=None,
            original_error=error,
            repair_method=None,
        )

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

    def _fix_trailing_commas(self, json_string: str) -> str:
        """Remove trailing commas before closing brackets."""
        # Remove trailing comma before }
        result = re.sub(r',\s*}', '}', json_string)
        # Remove trailing comma before ]
        result = re.sub(r',\s*]', ']', result)
        return result

    def _fix_unquoted_keys(self, json_string: str) -> str:
        """Add quotes around unquoted object keys."""
        # Match unquoted keys: word characters followed by :
        pattern = r'(?<=[{,\s])(\w+)(?=\s*:)'
        return re.sub(pattern, r'"\1"', json_string)

    def _fix_single_quotes(self, json_string: str) -> str:
        """Replace single quotes with double quotes."""
        # Simple replacement - may not work for all cases
        result = json_string.replace("'", '"')
        return result

    def _fix_newlines_in_strings(self, json_string: str) -> str:
        """Escape newlines inside string values."""
        # This is a simplified approach - proper handling would require parsing
        in_string = False
        result = []
        escape_next = False

        for char in json_string:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                continue

            if in_string and char == '\n':
                result.append('\\n')
            elif in_string and char == '\r':
                result.append('\\r')
            elif in_string and char == '\t':
                result.append('\\t')
            else:
                result.append(char)

        return ''.join(result)

    def _fix_missing_closing(self, json_string: str) -> str:
        """Add missing closing brackets."""
        open_braces = json_string.count('{')
        close_braces = json_string.count('}')
        open_brackets = json_string.count('[')
        close_brackets = json_string.count(']')

        result = json_string
        result += '}' * (open_braces - close_braces)
        result += ']' * (open_brackets - close_brackets)

        return result

    def _fix_escape_sequences(self, json_string: str) -> str:
        """Fix improperly escaped sequences."""
        # Fix common escape sequence issues
        result = json_string
        # Fix single backslash before quote
        result = re.sub(r'(?<!\\)\\(?!")', r'\\\\', result)
        return result


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
    elif result.repair_attempted:
        logger.info(
            f"Response from {provider} required repair "
            f"(success: {result.repair_successful})"
        )

    return result.valid, result.data, result.errors
