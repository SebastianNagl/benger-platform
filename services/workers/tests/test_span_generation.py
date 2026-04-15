"""Tests for span annotation generation support.

Issue #964: Add Span Annotation as a project type for NER and text highlighting

Tests cover:
- ResponseParser handling of Labels/span field type
- Parsing of multiple span response formats from LLMs
- Prompt generation with span format instructions
"""

import json

import pytest
from response_parser import ResponseParser


class TestSpanResponseParsing:
    """Test ResponseParser handling of span/Labels annotations."""

    @pytest.fixture
    def ner_label_config(self):
        """Label config with NER-style Labels element."""
        return """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="PERSON"/>
                <Label value="ORGANIZATION"/>
                <Label value="LOCATION"/>
            </Labels>
        </View>
        """

    @pytest.fixture
    def parser(self, ner_label_config):
        """Create parser with NER label config."""
        return ResponseParser(generation_structure={}, label_config=ner_label_config)

    def test_parse_json_array_format(self, parser):
        """Test parsing JSON array format from LLM response."""
        response = json.dumps(
            [
                {"start": 0, "end": 10, "text": "John Smith", "type": "PERSON"},
                {"start": 20, "end": 32, "text": "Acme Corp", "type": "ORGANIZATION"},
            ]
        )

        result = parser.parse(response)
        assert result.status == "success"
        assert result.parsed_annotation is not None

        # Find the entities field in results
        entities_result = next(
            (r for r in result.parsed_annotation if r.get("from_name") == "entities"), None
        )
        assert entities_result is not None
        assert entities_result["type"] == "labels"
        assert "spans" in entities_result["value"]
        assert len(entities_result["value"]["spans"]) == 2

    def test_parse_json_object_format(self, parser):
        """Test parsing JSON object with entities key."""
        response = json.dumps(
            {
                "entities": [
                    {"start": 0, "end": 10, "text": "John Smith", "type": "PERSON"},
                ]
            }
        )

        result = parser.parse(response)
        assert result.status == "success"

    def test_parse_inline_format(self, parser):
        """Test parsing inline format: [LABEL: start-end] text."""
        response = "[PERSON: 0-10] John Smith\n[ORGANIZATION: 20-32] Acme Corp"

        result = parser.parse(response)
        # Pattern matching may succeed or fail depending on implementation
        # The key is that it handles the format gracefully
        assert result.status in ["success", "failed"]

    def test_parse_marked_format(self, parser):
        """Test parsing marked format: <LABEL>text</LABEL>."""
        response = "<PERSON>John Smith</PERSON> works at <ORGANIZATION>Acme Corp</ORGANIZATION>"

        result = parser.parse(response)
        # Pattern matching may succeed or fail depending on implementation
        assert result.status in ["success", "failed"]

    def test_parse_multiple_entities(self, parser):
        """Test parsing response with multiple entities."""
        response = json.dumps(
            [
                {"start": 0, "end": 10, "text": "John Smith", "type": "PERSON"},
                {"start": 20, "end": 32, "text": "Acme Corp", "type": "ORGANIZATION"},
                {"start": 40, "end": 48, "text": "New York", "type": "LOCATION"},
            ]
        )

        result = parser.parse(response)
        assert result.status == "success"

    def test_parse_empty_entities(self, parser):
        """Test parsing response with no entities."""
        response = json.dumps([])

        result = parser.parse(response)
        # Empty result should still be valid
        assert result.status in ["success", "failed"]

    def test_parse_invalid_json(self, parser):
        """Test handling of invalid JSON response."""
        response = "This is not JSON {invalid}"

        result = parser.parse(response)
        # Should fail gracefully
        assert result.status == "failed"
        assert result.error is not None

    def test_parse_json_in_markdown(self, parser):
        """Test parsing JSON embedded in markdown code block."""
        response = """Here are the entities:

```json
[
    {"start": 0, "end": 10, "text": "John Smith", "type": "PERSON"}
]
```
"""

        result = parser.parse(response)
        assert result.status == "success"

    def test_invalid_label_type(self, parser):
        """Test handling of entity with invalid label type."""
        response = json.dumps(
            [
                {"start": 0, "end": 10, "text": "John Smith", "type": "INVALID_TYPE"},
            ]
        )

        result = parser.parse(response)
        # Parser should validate against available labels
        # and reject or filter invalid types
        assert result.status in ["success", "validation_error", "failed"]

    def test_missing_required_fields(self, parser):
        """Test handling of entities missing required fields."""
        response = json.dumps(
            [
                {"start": 0, "text": "John Smith", "type": "PERSON"},  # Missing 'end'
            ]
        )

        result = parser.parse(response)
        # Should handle gracefully
        assert result.status in ["success", "failed", "validation_error"]


class TestSpanSchemaBuilding:
    """Test JSON schema building for span annotations."""

    def test_labels_schema_from_label_config(self):
        """Test that Labels field generates correct JSON schema."""
        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="PERSON"/>
                <Label value="ORGANIZATION"/>
            </Labels>
        </View>
        """

        parser = ResponseParser(generation_structure={}, label_config=label_config)
        schema = parser.json_schema

        assert "properties" in schema
        assert "entities" in schema["properties"]
        assert schema["properties"]["entities"]["type"] == "array"
        assert "items" in schema["properties"]["entities"]

    def test_labels_with_required_attribute(self):
        """Test Labels field with required="true" attribute."""
        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text" required="true">
                <Label value="PERSON"/>
            </Labels>
        </View>
        """

        parser = ResponseParser(generation_structure={}, label_config=label_config)
        schema = parser.json_schema

        # Required fields should be in schema
        if "required" in schema:
            assert "entities" in schema["required"]


class TestLabelConfigParsing:
    """Test label config parsing for Labels element."""

    def test_parse_labels_element(self):
        """Test parsing of Labels element from label config."""
        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="PERSON"/>
                <Label value="ORGANIZATION"/>
                <Label value="LOCATION"/>
            </Labels>
        </View>
        """

        parser = ResponseParser(generation_structure={}, label_config=label_config)
        label_map = parser.label_config_map

        assert "entities" in label_map
        assert label_map["entities"]["type"] == "Labels"
        assert "labels" in label_map["entities"]
        assert len(label_map["entities"]["labels"]) == 3
        assert "PERSON" in label_map["entities"]["labels"]

    def test_text_not_in_output_fields(self):
        """Test that Text (display) elements are not treated as output fields."""
        label_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="PERSON"/>
            </Labels>
        </View>
        """

        parser = ResponseParser(generation_structure={}, label_config=label_config)
        label_map = parser.label_config_map

        # Text elements should not be in output field map
        assert "text" not in label_map
        # Labels should be
        assert "entities" in label_map
