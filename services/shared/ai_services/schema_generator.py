"""
Schema Generator for Structured LLM Output

Converts Label Studio label_config XML to JSON Schema for use with
LLM structured output APIs (OpenAI JSON mode, Anthropic tool_use, etc.)

This enables LLM responses to match the annotation schema defined in projects,
allowing direct comparison between human annotations and LLM outputs.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from label_config_repeater import (
    REPEATER_TAG,
    repeater_answer_schema,
    repeater_blocks,
)


def generate_json_schema_from_label_config(
    label_config: str,
    include_descriptions: bool = True,
    strict_mode: bool = True,
    task_data: Any = None,
) -> Dict[str, Any]:
    """
    Convert Label Studio label_config XML to JSON Schema.

    Args:
        label_config: XML string defining the annotation interface
        include_descriptions: Whether to add field descriptions from placeholders
        strict_mode: If True, generates schema compatible with OpenAI strict mode
        task_data: The task's data. A <Repeater> block becomes one array
            property (named after the last segment of its ``on`` binding)
            holding one object per item, keyed by each control's answer key;
            with ``task_data`` its length is pinned to the task's item count.
            Configs without a Repeater ignore it.

    Returns:
        JSON Schema dict compatible with OpenAI/Anthropic structured output

    Example:
        Input XML:
        <View>
          <TextArea name="answer" toName="task" placeholder="Enter answer..." required="true"/>
          <Choices name="verdict" toName="task">
            <Choice value="Ja"/>
            <Choice value="Nein"/>
          </Choices>
        </View>

        Output Schema:
        {
          "type": "object",
          "properties": {
            "answer": {"type": "string", "description": "Enter answer..."},
            "verdict": {"type": "string", "enum": ["Ja", "Nein"]}
          },
          "required": ["answer"],
          "additionalProperties": false
        }
    """
    if not label_config or not label_config.strip():
        return _empty_schema()

    try:
        root = ET.fromstring(label_config)
    except ET.ParseError:
        return _empty_schema()

    properties = {}
    required = []

    blocks = iter(repeater_blocks(label_config))
    inside_repeater = {
        id(child)
        for repeater in root.iter(REPEATER_TAG)
        for child in repeater.iter()
        if child is not repeater
    }

    def _control_schema(element: ET.Element):
        info = _parse_element(element, include_descriptions)
        return None if info is None else (info[1], info[2])

    # Find all annotation control elements
    for elem in root.iter():
        if elem.tag == REPEATER_TAG:
            block = next(blocks)
            if not block.controls:
                continue
            properties[block.answer_property] = repeater_answer_schema(
                block, _control_schema, task_data=task_data, strict_mode=strict_mode
            )
            required.append(block.answer_property)
            continue
        if id(elem) in inside_repeater:
            continue
        field_info = _parse_element(elem, include_descriptions)
        if field_info:
            name, prop_schema, is_required = field_info
            properties[name] = prop_schema
            if is_required:
                required.append(name)

    if not properties:
        return _empty_schema()

    schema = {
        "type": "object",
        "properties": properties,
    }

    # OpenAI strict mode requires ALL properties to be in required array
    if strict_mode:
        schema["required"] = list(properties.keys())
        schema["additionalProperties"] = False
    elif required:
        schema["required"] = required

    return schema


def _parse_element(elem: ET.Element, include_descriptions: bool) -> Optional[Tuple[str, Dict, bool]]:
    """
    Parse a single XML element into JSON Schema property.

    Returns:
        Tuple of (field_name, schema_dict, is_required) or None if not an annotation element
    """
    tag = elem.tag
    name = elem.get("name")

    if not name:
        return None

    # Map Label Studio types to JSON Schema
    # Note: "Text" elements are display-only (show task data with value="$..."), NOT answer fields
    if tag == "TextArea":
        schema = {"type": "string"}
        placeholder = elem.get("placeholder")
        if include_descriptions and placeholder:
            schema["description"] = placeholder
        is_required = elem.get("required", "").lower() == "true"
        return (name, schema, is_required)

    elif tag == "Choices":
        choices = [choice.get("value") for choice in elem.findall("Choice") if choice.get("value")]
        if choices:
            schema = {"type": "string", "enum": choices}
        else:
            schema = {"type": "string"}
        is_required = elem.get("required", "").lower() == "true"
        return (name, schema, is_required)

    elif tag == "Rating":
        max_rating = int(elem.get("maxRating", 5))
        schema = {
            "type": "integer",
            "minimum": 1,
            "maximum": max_rating
        }
        is_required = elem.get("required", "").lower() == "true"
        return (name, schema, is_required)

    elif tag == "Number":
        schema = {"type": "number"}
        min_val = elem.get("min")
        max_val = elem.get("max")
        if min_val is not None:
            schema["minimum"] = float(min_val)
        if max_val is not None:
            schema["maximum"] = float(max_val)
        is_required = elem.get("required", "").lower() == "true"
        return (name, schema, is_required)

    return None


def _empty_schema() -> Dict[str, Any]:
    """Return an empty but valid JSON schema."""
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True
    }


def generate_format_instructions(
    label_config: str,
    include_example: bool = True,
    task_data: Any = None,
) -> str:
    """
    Generate human-readable format instructions for prompt injection.

    Used for providers that don't support native structured output (DeepInfra).

    Args:
        label_config: XML string defining the annotation interface
        include_example: Whether to include an example JSON response

    Returns:
        Markdown-formatted instructions string
    """
    schema = generate_json_schema_from_label_config(
        label_config, include_descriptions=True, task_data=task_data
    )

    if not schema.get("properties"):
        return ""

    lines = ["## Output Format", "", "Respond with a JSON object containing these fields:", ""]

    for field_name, field_schema in schema["properties"].items():
        field_type = field_schema.get("type", "string")
        description = field_schema.get("description", "")
        enum_values = field_schema.get("enum")

        if enum_values:
            type_hint = f"one of: {', '.join(enum_values)}"
        elif field_type == "array" and isinstance(field_schema.get("items"), dict):
            keys = ", ".join(field_schema["items"].get("properties", {}))
            type_hint = f"list with one object per item (keys: {keys})"
        elif field_type == "integer":
            min_val = field_schema.get("minimum", 1)
            max_val = field_schema.get("maximum", 5)
            type_hint = f"integer ({min_val}-{max_val})"
        elif field_type == "number":
            type_hint = "number"
        else:
            type_hint = "string"

        required_marker = " (required)" if field_name in schema.get("required", []) else ""

        if description:
            lines.append(f"- **{field_name}**: {type_hint}{required_marker} - {description}")
        else:
            lines.append(f"- **{field_name}**: {type_hint}{required_marker}")

    if include_example:
        lines.append("")
        lines.append("**Example response:**")
        lines.append("```json")
        lines.append(json.dumps(_generate_example(schema), indent=2, ensure_ascii=False))
        lines.append("```")

    lines.append("")
    lines.append("Respond ONLY with valid JSON, no other text.")

    return "\n".join(lines)


def _generate_example(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an example JSON object from schema."""
    example = {}

    for field_name, field_schema in schema.get("properties", {}).items():
        field_type = field_schema.get("type", "string")
        enum_values = field_schema.get("enum")

        if enum_values:
            example[field_name] = enum_values[0]
        elif field_type == "array" and isinstance(field_schema.get("items"), dict):
            # One example object per item (one when the count is open).
            count = max(field_schema.get("minItems", 1), 1)
            items = [_generate_example(field_schema["items"]) for _ in range(count)]
            # An item-number key spanning exactly the items counts up.
            for key, prop in field_schema["items"].get("properties", {}).items():
                low, high = prop.get("minimum"), prop.get("maximum")
                if prop.get("type") == "integer" and low is not None and high is not None:
                    if high - low + 1 == count:
                        for position, item in enumerate(items):
                            item[key] = int(low) + position
            example[field_name] = items
        elif field_type == "integer":
            example[field_name] = field_schema.get("minimum", 1)
        elif field_type == "number":
            # Respect the schema's minimum (mirror the integer branch): a constant
            # 0.0 violates a field with a positive `minimum`, and this example is
            # injected into the prompt as the canonical sample for providers without
            # native structured output — teaching the model an out-of-range value.
            example[field_name] = field_schema.get("minimum", 0.0)
        else:
            example[field_name] = "..."

    return example


def extract_field_names(label_config: str) -> List[str]:
    """
    Extract just the field names from label_config.

    Args:
        label_config: XML string defining the annotation interface

    Returns:
        List of field names that can receive annotations
    """
    schema = generate_json_schema_from_label_config(label_config)
    return list(schema.get("properties", {}).keys())
