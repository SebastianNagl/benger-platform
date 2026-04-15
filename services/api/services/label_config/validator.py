"""
Label Config Validation Service

Validates Label Studio XML configurations for security and correctness.
Implements Issue #798: Critical gap in label config validation

Security Features:
- XXE (XML External Entity) attack prevention
- Billion Laughs (entity expansion) attack prevention
- Script injection prevention
- Invalid character detection

Validation Features:
- XML well-formedness
- Required attribute validation
- Field type validation
- Duplicate name detection
"""

import re
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET


class LabelConfigValidator:
    """
    Validator for Label Studio XML configuration

    Provides comprehensive validation including:
    - XML parsing and well-formedness
    - Security checks (XXE, entity expansion, injection)
    - Field type and attribute validation
    - Duplicate field name detection
    """

    # Supported Label Studio field types
    SUPPORTED_FIELD_TYPES = {
        'Choices',
        'Choice',
        'TextArea',
        'Rating',
        'Text',
        'Header',
        'View',
        'Label',
        'Labels',  # NER-style span annotation (Issue #964)
        'Checkbox',
        'Radio',
        'Number',
        'DateTime',
        'Taxonomy',
        'Polygon',
        'Rectangle',
        'KeyPoint',
        'Brush',
        'AudioPlus',
        'VideoPlus',
        'Image',
        'Audio',
        'Video',
        'HyperText',
        'TimeSeriesLabels',
        'Ranker',
        'Pairwise',
        'Style',
        'Filter',
        'List',
    }

    # Field types that require a 'name' attribute
    NAMED_FIELD_TYPES = {
        'Choices',
        'TextArea',
        'Rating',
        'Text',
        'Labels',  # NER-style span annotation (Issue #964)
        'Checkbox',
        'Radio',
        'Number',
        'DateTime',
        'Taxonomy',
        'Polygon',
        'Rectangle',
        'KeyPoint',
        'Brush',
        'AudioPlus',
        'VideoPlus',
        'Image',
        'Audio',
        'Video',
        'HyperText',
        'TimeSeriesLabels',
        'Ranker',
        'Pairwise',
        'List',
    }

    # Maximum config size (10KB)
    MAX_CONFIG_SIZE = 10 * 1024

    @classmethod
    def validate(cls, label_config: Optional[str]) -> Tuple[bool, List[str]]:
        """
        Validate label configuration

        Args:
            label_config: XML configuration string

        Returns:
            Tuple of (is_valid, errors)
            - is_valid: True if config is valid
            - errors: List of error messages (empty if valid)
        """
        errors = []

        # Check None
        if label_config is None:
            errors.append("Label config cannot be None")
            return False, errors

        # Check empty
        if not label_config or not label_config.strip():
            errors.append("Label config cannot be empty")
            return False, errors

        # Check size
        if len(label_config) > cls.MAX_CONFIG_SIZE:
            errors.append(f"Label config exceeds maximum size of {cls.MAX_CONFIG_SIZE} bytes")
            return False, errors

        # Security checks
        security_errors = cls._check_security(label_config)
        if security_errors:
            errors.extend(security_errors)
            return False, errors

        # Parse XML
        try:
            root = cls._safe_parse_xml(label_config)
        except Exception as e:
            errors.append(f"XML parsing failed: {str(e)}")
            return False, errors

        # Validate structure
        structure_errors = cls._validate_structure(root)
        if structure_errors:
            errors.extend(structure_errors)

        # Validate attributes
        attribute_errors = cls._validate_attributes(root)
        if attribute_errors:
            errors.extend(attribute_errors)

        # Return result
        is_valid = len(errors) == 0
        return is_valid, errors

    @classmethod
    def _safe_parse_xml(cls, xml_string: str) -> ET.Element:
        """
        Safely parse XML with security restrictions

        Args:
            xml_string: XML string to parse

        Returns:
            Parsed XML root element

        Raises:
            Exception: If parsing fails
        """
        # Remove XML declaration if present
        xml_string = re.sub(r'<\?xml[^>]+\?>', '', xml_string).strip()

        # Parse with standard ElementTree (secure by default in Python 3.8+)
        # Python's ET.fromstring is safe against XXE by default
        root = ET.fromstring(xml_string)
        return root

    @classmethod
    def _check_security(cls, xml_string: str) -> List[str]:
        """
        Check for security vulnerabilities

        Args:
            xml_string: XML string to check

        Returns:
            List of security error messages
        """
        errors = []

        # Check for external entity references (XXE)
        if '<!ENTITY' in xml_string or '<!DOCTYPE' in xml_string:
            errors.append("External entity references are not allowed")

        # Check for system entity references
        if 'SYSTEM' in xml_string or 'PUBLIC' in xml_string:
            errors.append("System and public entity references are not allowed")

        # Check for script tags
        if re.search(r'<script[^>]*>', xml_string, re.IGNORECASE):
            errors.append("Script tags are not allowed in label config")

        # Check for on* event handlers
        if re.search(r'\bon\w+\s*=', xml_string, re.IGNORECASE):
            errors.append("Event handlers (onclick, onload, etc.) are not allowed")

        # Check for javascript: protocol
        if re.search(r'javascript:', xml_string, re.IGNORECASE):
            errors.append("JavaScript protocol is not allowed")

        # Check for excessive entity expansion (billion laughs pattern)
        entity_count = xml_string.count('&') + xml_string.count(';')
        if entity_count > 50:
            errors.append("Excessive entity references detected (possible billion laughs attack)")

        return errors

    @classmethod
    def _validate_structure(cls, root: ET.Element) -> List[str]:
        """
        Validate XML structure and field types

        Args:
            root: Parsed XML root element

        Returns:
            List of validation error messages
        """
        errors = []

        # Check root tag
        if root.tag != 'View':
            errors.append(f"Root element must be <View>, found <{root.tag}>")

        # Collect all field names for duplicate checking
        field_names = []

        # Recursively validate all elements
        cls._validate_element(root, errors, field_names)

        # Check for duplicate field names
        seen_names = set()
        for name in field_names:
            if name in seen_names:
                errors.append(f"Duplicate field name found: '{name}'")
            seen_names.add(name)

        return errors

    @classmethod
    def _validate_element(
        cls, element: ET.Element, errors: List[str], field_names: List[str]
    ) -> None:
        """
        Recursively validate an XML element

        Args:
            element: Element to validate
            errors: List to append errors to
            field_names: List to append field names to
        """
        # Check if field type is supported
        if element.tag not in cls.SUPPORTED_FIELD_TYPES:
            errors.append(f"Unsupported field type: '{element.tag}'")

        # Check required 'name' attribute
        if element.tag in cls.NAMED_FIELD_TYPES:
            name = element.get('name')
            if not name:
                errors.append(f"Field type '{element.tag}' requires a 'name' attribute")
            elif name:
                # Validate name format (supports Unicode letters including German umlauts)
                if not name.isidentifier():
                    errors.append(
                        f"Invalid field name '{name}': must be a valid identifier "
                        "(start with a letter or underscore, followed by letters, digits, "
                        "or underscores). Unicode letters like German umlauts (ö, ü, ä) are supported."
                    )
                field_names.append(name)

        # Recursively validate children
        for child in element:
            cls._validate_element(child, errors, field_names)

    @classmethod
    def _validate_attributes(cls, root: ET.Element) -> List[str]:
        """
        Validate element attributes

        Args:
            root: Parsed XML root element

        Returns:
            List of validation error messages
        """
        errors = []

        # Recursively check all elements
        cls._validate_element_attributes(root, errors)

        return errors

    @classmethod
    def _validate_element_attributes(cls, element: ET.Element, errors: List[str]) -> None:
        """
        Recursively validate element attributes

        Args:
            element: Element to validate
            errors: List to append errors to
        """
        # Check for invalid attribute values (basic checks)
        for attr_name, attr_value in element.attrib.items():
            # Check for empty attribute values where it doesn't make sense
            if attr_name in ['name', 'toName', 'value'] and not attr_value.strip():
                errors.append(f"Attribute '{attr_name}' on <{element.tag}> cannot be empty")

        # Recursively validate children
        for child in element:
            cls._validate_element_attributes(child, errors)
