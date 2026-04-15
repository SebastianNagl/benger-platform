"""Extended tests for response_parser.py - additional coverage for spans and edge cases.

Covers:
- _parse_span_value with various formats
- Array response wrapping for NER
- JSON in markdown blocks
- Schema validation edge cases
- Labels in label_config
- Span inline format parsing
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

_shared_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared")
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from response_parser import ParseResult, ResponseParser


@pytest.fixture
def ner_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <Labels name="entities" toName="text">
            <Label value="PERSON"/>
            <Label value="ORG"/>
            <Label value="LOC"/>
        </Labels>
    </View>
    """


@pytest.fixture
def rating_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <Rating name="quality" toName="text"/>
    </View>
    """


# ---------------------------------------------------------------------------
# NER/Labels config parsing
# ---------------------------------------------------------------------------

class TestNERConfigParsing:

    def test_labels_parsed_with_values(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        assert "entities" in parser.label_config_map
        cfg = parser.label_config_map["entities"]
        assert cfg["type"] == "Labels"
        assert set(cfg["labels"]) == {"PERSON", "ORG", "LOC"}

    def test_schema_for_labels_is_array(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        schema = parser.json_schema
        assert schema["properties"]["entities"]["type"] == "array"
        assert schema["properties"]["entities"]["items"]["type"] == "object"

    def test_schema_labels_enum(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        schema = parser.json_schema
        items = schema["properties"]["entities"]["items"]
        assert set(items["properties"]["type"]["enum"]) == {"PERSON", "ORG", "LOC"}


# ---------------------------------------------------------------------------
# Array wrapping for NER
# ---------------------------------------------------------------------------

class TestArrayWrapping:

    def test_direct_array_wrapped_for_labels(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        response = json.dumps([
            {"start": 0, "end": 5, "type": "PERSON", "text": "Alice"},
        ])
        result = parser.parse(response)
        assert result.status == "success"

    def test_direct_array_not_wrapped_without_labels(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <TextArea name="answer" toName="text"/>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        # A JSON array won't match the expected object schema
        result = parser._try_json_parse('[1, 2, 3]')
        # Without Labels field, array is not wrapped so schema validation should fail
        assert result.status in ("failed", "validation_error")


# ---------------------------------------------------------------------------
# Span parsing
# ---------------------------------------------------------------------------

class TestSpanParsing:

    def test_parse_span_list_of_dicts(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        value = [
            {"start": 0, "end": 5, "type": "PERSON", "text": "Alice"},
            {"start": 10, "end": 15, "type": "ORG", "text": "ACME"},
        ]
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value(value, field_config)
        assert len(spans) == 2
        assert spans[0]["labels"] == ["PERSON"]
        assert spans[1]["labels"] == ["ORG"]

    def test_parse_span_json_string(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        value = json.dumps([
            {"start": 0, "end": 5, "type": "PERSON", "text": "Alice"},
        ])
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value(value, field_config)
        assert len(spans) == 1

    def test_parse_span_inline_format(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        value = "[PERSON: 0-5] Alice [ORG: 10-14] ACME"
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value(value, field_config)
        assert len(spans) == 2
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 5
        assert spans[0]["labels"] == ["PERSON"]

    def test_parse_span_marked_format_with_source(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        parser._source_text = "Alice went to Berlin"
        value = "<PERSON>Alice</PERSON>"
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value(value, field_config)
        assert len(spans) == 1
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 5
        assert spans[0]["text"] == "Alice"

    def test_parse_span_marked_format_without_source_raises(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        parser._source_text = None
        value = "<PERSON>Alice</PERSON>"
        field_config = parser.label_config_map["entities"]
        with pytest.raises(ValueError, match="requires source_text"):
            parser._parse_span_value(value, field_config)

    def test_parse_span_marked_text_not_in_source_raises(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        parser._source_text = "Bob went to Berlin"
        value = "<PERSON>Alice</PERSON>"
        field_config = parser.label_config_map["entities"]
        with pytest.raises(ValueError, match="not found in source text"):
            parser._parse_span_value(value, field_config)

    def test_parse_span_empty_list(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value([], field_config)
        assert spans == []

    def test_parse_span_invalid_dict_skipped(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        value = [{"not_a_span": True}]
        field_config = parser.label_config_map["entities"]
        spans = parser._parse_span_value(value, field_config)
        assert spans == []

    def test_normalize_span_with_label_key(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "label": "PERSON"},
            available_labels=["PERSON", "ORG"],
        )
        assert span is not None
        assert span["labels"] == ["PERSON"]

    def test_normalize_span_preserves_id(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "type": "PERSON", "id": "custom-id"},
            available_labels=[],
        )
        assert span["id"] == "custom-id"

    def test_normalize_span_generates_id(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "type": "PERSON"},
            available_labels=[],
        )
        assert span["id"].startswith("span-")


# ---------------------------------------------------------------------------
# Labels transform
# ---------------------------------------------------------------------------

class TestLabelsTransform:

    def test_labels_transform_to_label_studio(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        parsed_data = {
            "entities": [
                {"start": 0, "end": 5, "type": "PERSON", "text": "Alice"},
            ]
        }
        annotation = parser._transform_to_label_studio(parsed_data)
        assert len(annotation) == 1
        assert annotation[0]["type"] == "labels"
        assert "spans" in annotation[0]["value"]


# ---------------------------------------------------------------------------
# Rating parsing
# ---------------------------------------------------------------------------

class TestRatingParsing:

    def test_parse_rating_json(self, rating_label_config):
        parser = ResponseParser(generation_structure={}, label_config=rating_label_config)
        result = parser.parse('{"quality": 4}')
        assert result.status == "success"
        ann = result.parsed_annotation[0]
        assert ann["type"] == "rating"
        assert ann["value"]["rating"] == 4


# ---------------------------------------------------------------------------
# Schema required fields
# ---------------------------------------------------------------------------

class TestSchemaRequired:

    def test_required_fields_in_generation_structure(self):
        gs = {
            "fields": {
                "answer": {"type": "choices", "required": True},
                "comment": {"type": "text", "required": False},
            }
        }
        config = "<View><Text name='t' value='$t'/></View>"
        parser = ResponseParser(generation_structure=gs, label_config=config)
        assert "answer" in parser.json_schema["required"]
        assert "comment" not in parser.json_schema.get("required", [])

    def test_required_from_label_config(self):
        config = """
        <View>
            <Text name="t" value="$t"/>
            <TextArea name="answer" toName="t" required="true"/>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        assert "answer" in parser.json_schema.get("required", [])


# ---------------------------------------------------------------------------
# Choices list value
# ---------------------------------------------------------------------------

class TestChoicesListValue:

    def test_choices_list_wraps_to_array(self):
        config = """
        <View>
            <Text name="t" value="$t"/>
            <Choices name="answer" toName="t">
                <Choice value="yes"/>
                <Choice value="no"/>
            </Choices>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        annotation = parser._transform_to_label_studio({"answer": "yes"})
        assert annotation[0]["value"]["choices"] == ["yes"]

    def test_choices_already_list(self):
        config = """
        <View>
            <Text name="t" value="$t"/>
            <Choices name="answer" toName="t">
                <Choice value="a"/>
                <Choice value="b"/>
            </Choices>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        annotation = parser._transform_to_label_studio({"answer": ["a", "b"]})
        assert annotation[0]["value"]["choices"] == ["a", "b"]


# ---------------------------------------------------------------------------
# Parse with source_text
# ---------------------------------------------------------------------------

class TestParseWithSourceText:

    def test_parse_stores_source_text(self, ner_label_config):
        parser = ResponseParser(generation_structure={}, label_config=ner_label_config)
        parser.parse('{"entities": []}', source_text="Some text here")
        assert parser._source_text == "Some text here"
