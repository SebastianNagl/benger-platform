"""Response parser for LLM generation outputs.

This module parses LLM responses according to generation structures and transforms
them into Label Studio annotation format.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import jsonschema
from jsonschema import validate


@dataclass
class ParseResult:
    """Result of parsing an LLM response."""

    status: str  # success/failed/validation_error
    parsed_annotation: Optional[List[Dict]] = None  # Label Studio JSONB format
    error: Optional[str] = None
    field_values: Dict[str, Any] = None

    def __post_init__(self):
        if self.field_values is None:
            self.field_values = {}


class ResponseParser:
    """Parser for LLM generation responses with Label Studio transformation."""

    def __init__(self, generation_structure: Dict, label_config: str):
        """Initialize parser with generation structure and label config.

        Args:
            generation_structure: Dict defining expected response structure
            label_config: XML string of Label Studio configuration
        """
        self.generation_structure = generation_structure
        self.label_config = label_config
        # Parse label_config FIRST since _build_json_schema may reference it
        self.label_config_map = self._parse_label_config(label_config)
        self.json_schema = self._build_json_schema(generation_structure)

    def parse(self, response_text: str, source_text: str = None) -> ParseResult:
        """Parse LLM response text.

        Args:
            response_text: Raw LLM response text
            source_text: Optional source text for calculating span positions
                        (required for marked format <LABEL>text</LABEL>)

        Returns:
            ParseResult with status and parsed data or error
        """
        self._source_text = source_text  # Store for use in _parse_span_value

        # Try JSON parsing first
        result = self._try_json_parse(response_text)
        if result.status == "success":
            return result

        # Try pattern matching as fallback
        result = self._try_pattern_match(response_text)
        if result.status == "success":
            return result

        # Both approaches failed
        return ParseResult(
            status="failed", error="Unable to parse response as JSON or structured text"
        )

    def _try_json_parse(self, response_text: str) -> ParseResult:
        """Attempt to parse response as JSON with schema validation.

        Args:
            response_text: Raw response text

        Returns:
            ParseResult indicating success or failure
        """
        try:
            # Extract JSON if embedded in markdown code blocks
            json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                json_text = response_text.strip()

            # Parse JSON
            parsed_data = json.loads(json_text)

            # Handle array response for NER/Labels fields (Issue #964)
            # If the response is a direct array and we have a Labels field, wrap it
            if isinstance(parsed_data, list) and self.label_config_map:
                # Find the Labels field name
                labels_field = None
                for field_name, config in self.label_config_map.items():
                    if config.get("type") == "Labels":
                        labels_field = field_name
                        break

                # Wrap the array with the field name
                if labels_field:
                    parsed_data = {labels_field: parsed_data}

            # Validate against schema if available
            if self.json_schema:
                try:
                    validate(instance=parsed_data, schema=self.json_schema)
                except jsonschema.ValidationError as e:
                    return ParseResult(
                        status="validation_error", error=f"JSON schema validation failed: {str(e)}"
                    )

            # Transform to Label Studio format
            ls_annotation = self._transform_to_label_studio(parsed_data)
            field_values = self._extract_field_values(ls_annotation)

            return ParseResult(
                status="success", parsed_annotation=ls_annotation, field_values=field_values
            )

        except json.JSONDecodeError as e:
            return ParseResult(status="failed", error=f"JSON parsing failed: {str(e)}")
        except Exception as e:
            return ParseResult(status="failed", error=f"Unexpected error in JSON parsing: {str(e)}")

    def _try_pattern_match(self, response_text: str) -> ParseResult:
        """Attempt to parse response using regex pattern matching.

        Args:
            response_text: Raw response text

        Returns:
            ParseResult indicating success or failure
        """
        try:
            parsed_data = {}

            # Determine which fields to extract - prefer generation_structure, fall back to label_config
            fields_to_extract = self.generation_structure.get("fields", {})
            if not fields_to_extract and self.label_config_map:
                # Use label_config fields when generation_structure doesn't define output fields
                fields_to_extract = {
                    name: {"type": config.get("type", "text").lower()}
                    for name, config in self.label_config_map.items()
                }

            # Extract fields based on field definitions
            for field_name, field_config in fields_to_extract.items():
                field_type = field_config.get("type", "text")

                # Pattern: field_name: value or field_name = value
                pattern = rf'{re.escape(field_name)}\s*[:\=]\s*(.+?)(?=\n\w+\s*[:\=]|\Z)'
                match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)

                if match:
                    value = match.group(1).strip()

                    # Clean up value
                    value = value.strip('"\'')
                    value = re.sub(r'\s+', ' ', value)

                    # Type conversion based on field type
                    if field_type == "choices":
                        # Extract choice from quotes or clean text
                        choice_match = re.search(r'["\']([^"\']+)["\']', value)
                        parsed_data[field_name] = choice_match.group(1) if choice_match else value
                    elif field_type == "number":
                        try:
                            parsed_data[field_name] = float(value)
                        except ValueError:
                            parsed_data[field_name] = value
                    else:
                        parsed_data[field_name] = value

            # Check if we extracted any fields
            if not parsed_data:
                # Fallback for free-form text responses (German legal projects - Issue #1041)
                # If we have a Loesung/loesung field and no structured data, use entire response
                text_fields = []
                for name, config in self.label_config_map.items():
                    field_type = config.get("type", "")
                    # Gliederung, Loesung, TextArea are text-based answer fields
                    if field_type in ["Gliederung", "Loesung", "TextArea"]:
                        text_fields.append((name, field_type))

                # If there's a single primary text field, use the entire response for it
                if len(text_fields) == 1:
                    field_name, _ = text_fields[0]
                    parsed_data[field_name] = response_text.strip()
                elif len(text_fields) > 1:
                    # Multiple text fields - prioritize Loesung (solution) for the full response
                    loesung_field = next(
                        (name for name, ft in text_fields if ft == "Loesung"), None
                    )
                    if loesung_field:
                        parsed_data[loesung_field] = response_text.strip()

            # Check if we extracted any fields
            if not parsed_data:
                return ParseResult(status="failed", error="No fields could be extracted from text")

            # Transform to Label Studio format
            ls_annotation = self._transform_to_label_studio(parsed_data)
            field_values = self._extract_field_values(ls_annotation)

            return ParseResult(
                status="success", parsed_annotation=ls_annotation, field_values=field_values
            )

        except Exception as e:
            return ParseResult(status="failed", error=f"Pattern matching failed: {str(e)}")

    def _transform_to_label_studio(self, parsed_data: Dict) -> List[Dict]:
        """Transform parsed data to Label Studio annotation format.

        Args:
            parsed_data: Dictionary of field names to values

        Returns:
            List of Label Studio annotation objects
        """
        ls_annotation = []

        for field_name, value in parsed_data.items():
            # Only include fields that are defined as answer fields in label_config
            # Skip any extra fields the LLM might have generated (like display-only fields)
            if self.label_config_map and field_name not in self.label_config_map:
                continue

            # Get field configuration from label config
            field_config = self.label_config_map.get(field_name, {})
            field_type = field_config.get("type", "textarea")

            # Build annotation based on type
            if field_type == "Choices":
                ls_annotation.append(
                    {
                        "from_name": field_name,
                        "type": "choices",
                        "value": {"choices": [value] if isinstance(value, str) else value},
                    }
                )
            elif field_type == "Rating":
                ls_annotation.append(
                    {"from_name": field_name, "type": "rating", "value": {"rating": value}}
                )
            elif field_type == "Number":
                ls_annotation.append(
                    {"from_name": field_name, "type": "number", "value": {"number": value}}
                )
            elif field_type == "Labels":
                # Handle NER/span annotation type (Issue #964)
                spans = self._parse_span_value(value, field_config)
                ls_annotation.append(
                    {
                        "from_name": field_name,
                        "type": "labels",
                        "value": {"spans": spans},
                    }
                )
            elif field_type in ["Gliederung", "Loesung"]:
                # German legal annotation fields (Issue #1041) - use textarea format
                ls_annotation.append(
                    {
                        "from_name": field_name,
                        "type": "textarea",
                        "value": {"text": [value] if isinstance(value, str) else value},
                    }
                )
            else:  # Default to textarea for text fields
                ls_annotation.append(
                    {
                        "from_name": field_name,
                        "type": "textarea",
                        "value": {"text": [value] if isinstance(value, str) else value},
                    }
                )

        return ls_annotation

    def _extract_field_values(self, ls_annotation: List[Dict]) -> Dict[str, Any]:
        """Extract field values from Label Studio annotation."""
        from annotation_utils import extract_all_field_values
        return extract_all_field_values(ls_annotation)

    def _build_json_schema(self, generation_structure: Dict) -> Dict:
        """Build JSON schema from generation structure or label_config.

        If generation_structure["fields"] is provided, use it for validation.
        Otherwise, automatically derive schema from label_config fields.

        Args:
            generation_structure: Dict defining expected response structure

        Returns:
            JSON schema dictionary
        """
        properties = {}
        required = []

        # Priority 1: Use explicitly defined fields from generation_structure
        if generation_structure and "fields" in generation_structure:
            for field_name, field_config in generation_structure["fields"].items():
                field_type = field_config.get("type", "text")
                is_required = field_config.get("required", False)

                # Map field types to JSON schema types
                if field_type == "choices":
                    properties[field_name] = {"type": "string"}
                    if "options" in field_config:
                        properties[field_name]["enum"] = field_config["options"]
                elif field_type == "number":
                    properties[field_name] = {"type": "number"}
                else:  # text/textarea
                    properties[field_name] = {"type": "string"}

                if is_required:
                    required.append(field_name)

        # Priority 2: Auto-generate schema from label_config if no explicit fields
        elif self.label_config_map:
            for field_name, field_config in self.label_config_map.items():
                field_type = field_config.get("type", "TextArea")
                is_required = field_config.get("required", False)

                # Map Label Studio types to JSON schema types
                if field_type == "Choices":
                    properties[field_name] = {"type": "string"}
                    if "choices" in field_config:
                        properties[field_name]["enum"] = field_config["choices"]
                elif field_type in ["Number", "Rating"]:
                    properties[field_name] = {"type": "number"}
                elif field_type == "Labels":
                    # NER/span annotation schema (Issue #964)
                    span_schema = {
                        "type": "object",
                        "properties": {
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                            "text": {"type": "string"},
                            "type": {"type": "string"},
                        },
                        "required": ["start", "end", "type"],
                    }
                    # Add label enum if available
                    if "labels" in field_config:
                        span_schema["properties"]["type"]["enum"] = field_config["labels"]
                    properties[field_name] = {"type": "array", "items": span_schema}
                else:  # TextArea, Text, Gliederung, Loesung (Issue #1041)
                    properties[field_name] = {"type": "string"}

                if is_required:
                    required.append(field_name)

        # If no fields found, return empty schema (no validation)
        if not properties:
            return {}

        schema = {"type": "object", "properties": properties}

        if required:
            schema["required"] = required

        return schema

    def _parse_label_config(self, label_config: str) -> Dict[str, Dict]:
        """Parse Label Studio XML configuration to extract field types.

        Args:
            label_config: XML string of Label Studio configuration

        Returns:
            Dictionary mapping field names to their configurations
        """
        field_map = {}

        try:
            root = ET.fromstring(label_config)

            # Find all annotation control elements (answer fields only, not display fields)
            # Note: "Text" elements are display-only fields (show task data), NOT answer fields
            # Include German legal annotation elements (Issue #1041)
            for elem in root.iter():
                if elem.tag in [
                    "Choices",
                    "TextArea",
                    "Rating",
                    "Number",
                    "Labels",
                    "Gliederung",
                    "Loesung",
                ]:
                    name = elem.get("name")
                    if name:
                        field_map[name] = {
                            "type": elem.tag,
                            "to_name": elem.get("toName"),
                            "required": elem.get("required", "false").lower() == "true",
                        }

                        # Extract choices if available
                        if elem.tag == "Choices":
                            choices = []
                            for choice in elem.findall("Choice"):
                                choice_value = choice.get("value")
                                if choice_value:
                                    choices.append(choice_value)
                            if choices:
                                field_map[name]["choices"] = choices

                        # Extract labels for NER/span annotation (Issue #964)
                        if elem.tag == "Labels":
                            labels = []
                            for label in elem.findall("Label"):
                                label_value = label.get("value")
                                if label_value:
                                    labels.append(label_value)
                            if labels:
                                field_map[name]["labels"] = labels

        except ET.ParseError:
            # Return empty map if parsing fails
            pass

        return field_map

    def _parse_span_value(self, value: Any, field_config: Dict) -> List[Dict]:
        """Parse span annotation value from LLM response (Issue #964).

        Supports multiple formats:
        1. JSON array: [{"start": 0, "end": 10, "text": "...", "type": "PERSON"}]
        2. Inline format: [PERSON: 0-10] John Smith
        3. Marked format: <PERSON>John Smith</PERSON>
        4. Simple text list: PERSON: John Smith, ORGANIZATION: Acme Corp

        Args:
            value: Raw value from LLM response
            field_config: Field configuration including available labels

        Returns:
            List of span dictionaries with id, start, end, text, labels
        """
        import uuid

        spans = []
        available_labels = field_config.get("labels", [])

        # If already a list of dicts, validate and normalize
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    span = self._normalize_span(item, available_labels)
                    if span:
                        spans.append(span)
            return spans

        # If string, try to parse it
        if isinstance(value, str):
            # Try JSON format first
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            span = self._normalize_span(item, available_labels)
                            if span:
                                spans.append(span)
                    return spans
            except json.JSONDecodeError:
                pass

            # Try inline format: [LABEL: start-end] text
            inline_pattern = r'\[([A-Z_]+):\s*(\d+)-(\d+)\]\s*([^\[]+)'
            for match in re.finditer(inline_pattern, value):
                label, start, end, text = match.groups()
                if not available_labels or label in available_labels:
                    spans.append(
                        {
                            "id": f"span-{uuid.uuid4().hex[:8]}",
                            "start": int(start),
                            "end": int(end),
                            "text": text.strip(),
                            "labels": [label],
                        }
                    )

            if spans:
                return spans

            # Try marked format: <LABEL>text</LABEL>
            marked_pattern = r'<([A-Z_]+)>([^<]+)</\1>'
            for match in re.finditer(marked_pattern, value):
                label, text = match.groups()
                if not available_labels or label in available_labels:
                    extracted_text = text.strip()
                    # Calculate real positions from source text if available
                    if hasattr(self, '_source_text') and self._source_text:
                        start_pos = self._source_text.find(extracted_text)
                        if start_pos >= 0:
                            spans.append(
                                {
                                    "id": f"span-{uuid.uuid4().hex[:8]}",
                                    "start": start_pos,
                                    "end": start_pos + len(extracted_text),
                                    "text": extracted_text,
                                    "labels": [label],
                                }
                            )
                        else:
                            # Text not found in source - raise error for scientific rigor
                            raise ValueError(
                                f"Span text '{extracted_text}' not found in source text. "
                                "Cannot calculate accurate position offsets."
                            )
                    else:
                        # No source text provided - raise error for scientific rigor
                        raise ValueError(
                            f"Marked format <{label}>{extracted_text}</{label}> requires source_text "
                            "parameter to calculate accurate position offsets. "
                            "Pass source_text to parse() method."
                        )

            if spans:
                return spans

        return spans

    def _normalize_span(self, item: Dict, available_labels: List[str]) -> Optional[Dict]:
        """Normalize a span dictionary to standard format.

        Args:
            item: Raw span dictionary from LLM
            available_labels: List of valid label values

        Returns:
            Normalized span dict or None if invalid
        """
        import uuid

        # Required fields
        start = item.get("start")
        end = item.get("end")
        label_type = item.get("type") or item.get("label")

        if start is None or end is None or not label_type:
            return None

        # Validate label if we have a list
        if available_labels and label_type not in available_labels:
            return None

        return {
            "id": item.get("id") or f"span-{uuid.uuid4().hex[:8]}",
            "start": int(start),
            "end": int(end),
            "text": item.get("text", ""),
            "labels": [label_type] if isinstance(label_type, str) else label_type,
        }
