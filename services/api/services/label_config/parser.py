"""
Label Config Parser Service

Parses Label Studio XML configurations to extract field metadata,
attributes, and options. Supports multiple field types including
Choices, TextArea, Rating, Number, Text, and DateTime.

Issue #798: Label config parsing coverage
XSS Prevention: All extracted field metadata is sanitized before returning
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from label_config_sanitizer import LabelConfigSanitizer


class LabelConfigParser:
    """Parser for Label Studio XML configurations"""

    # Supported field types
    SUPPORTED_FIELD_TYPES = [
        "Choices",
        "TextArea",
        "Rating",
        "Number",
        "Text",
        "DateTime",
    ]

    @staticmethod
    def extract_fields(label_config: str, sanitize: bool = True) -> List[Dict]:
        """
        Extract all fields with full metadata from label config.

        Args:
            label_config: Label Studio XML configuration string
            sanitize: Whether to sanitize field metadata (default: True)
                     XSS Prevention: Sanitization prevents stored XSS attacks

        Returns:
            List of field dictionaries with metadata (sanitized by default)

        Example:
            >>> xml = '<View><Choices name="label" toName="text"><Choice value="A"/></Choices></View>'
            >>> fields = LabelConfigParser.extract_fields(xml)
            >>> fields[0]['name']
            'label'
            >>> fields[0]['type']
            'Choices'
        """
        if not label_config:
            return []

        try:
            root = ET.fromstring(label_config)
            fields = []

            for elem in root.iter():
                if elem.tag in LabelConfigParser.SUPPORTED_FIELD_TYPES:
                    field = LabelConfigParser._parse_field_element(elem)
                    if field:
                        # XSS Prevention: Sanitize field metadata before returning
                        if sanitize:
                            field = LabelConfigSanitizer.sanitize_field(field)
                        fields.append(field)

            return fields
        except ET.ParseError:
            return []

    @staticmethod
    def extract_field_names(label_config: str) -> List[str]:
        """
        Extract only field names from label config.

        Args:
            label_config: Label Studio XML configuration string

        Returns:
            List of field names
        """
        fields = LabelConfigParser.extract_fields(label_config)
        return [field["name"] for field in fields]

    @staticmethod
    def get_field_by_name(label_config: str, name: str) -> Optional[Dict]:
        """
        Get a specific field by name.

        Args:
            label_config: Label Studio XML configuration string
            name: Field name to retrieve

        Returns:
            Field dictionary or None if not found
        """
        fields = LabelConfigParser.extract_fields(label_config)
        for field in fields:
            if field["name"] == name:
                return field
        return None

    @staticmethod
    def _parse_field_element(elem: ET.Element) -> Optional[Dict]:
        """
        Parse a single field element into a dictionary.

        Args:
            elem: XML Element to parse

        Returns:
            Field dictionary or None if element has no name
        """
        name = elem.get("name")
        if not name:
            return None

        field = {
            "name": name,
            "type": elem.tag,
            "attributes": dict(elem.attrib),
        }

        # Add toName reference if present
        to_name = elem.get("toName")
        if to_name:
            field["toName"] = to_name

        # Extract type-specific metadata
        if elem.tag == "Choices":
            field["options"] = LabelConfigParser._extract_choice_options(elem)
        elif elem.tag == "Rating":
            max_rating = elem.get("maxRating")
            if max_rating:
                field["maxRating"] = int(max_rating)
        elif elem.tag == "Number":
            # Extract min/max if present
            min_val = elem.get("min")
            max_val = elem.get("max")
            if min_val:
                field["min"] = float(min_val)
            if max_val:
                field["max"] = float(max_val)
        return field

    @staticmethod
    def _extract_choice_options(choices_elem: ET.Element) -> List[str]:
        """
        Extract choice options from a Choices element.

        Args:
            choices_elem: Choices XML element

        Returns:
            List of choice values
        """
        options = []
        for choice in choices_elem.findall("Choice"):
            value = choice.get("value")
            if value:
                options.append(value)
        return options

    @staticmethod
    def parse_field_attributes(label_config: str, field_name: str) -> Dict:
        """
        Get all attributes for a specific field.

        Args:
            label_config: Label Studio XML configuration string
            field_name: Name of field to get attributes for

        Returns:
            Dictionary of attributes or empty dict if field not found
        """
        field = LabelConfigParser.get_field_by_name(label_config, field_name)
        if field:
            return field.get("attributes", {})
        return {}

    @staticmethod
    def validate_config(label_config: str) -> Dict:
        """
        Validate a label config and return validation results.

        Args:
            label_config: Label Studio XML configuration string

        Returns:
            Dictionary with validation results
        """
        if not label_config:
            return {
                "valid": False,
                "error": "Empty configuration",
            }

        try:
            ET.fromstring(label_config)
            fields = LabelConfigParser.extract_fields(label_config)

            if not fields:
                return {
                    "valid": False,
                    "error": "No valid fields found",
                }

            # Check for duplicate field names
            field_names = [f["name"] for f in fields]
            duplicates = [name for name in field_names if field_names.count(name) > 1]
            if duplicates:
                return {
                    "valid": False,
                    "error": f"Duplicate field names: {', '.join(set(duplicates))}",
                }

            return {
                "valid": True,
                "field_count": len(fields),
                "field_types": list(set(f["type"] for f in fields)),
            }
        except ET.ParseError as e:
            return {
                "valid": False,
                "error": f"Invalid XML: {str(e)}",
            }
