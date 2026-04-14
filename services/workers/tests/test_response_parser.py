"""Tests for response_parser.py - LLM response parsing and Label Studio transformation.

Covers:
- ParseResult dataclass
- JSON parsing (plain, markdown-wrapped, array wrapping)
- Pattern matching fallback
- Label Studio annotation transformation
- JSON schema building from generation_structure and label_config
- Label config XML parsing
- Span normalization
"""

import json
import os
import sys

import pytest

# Make shared/annotation_utils importable (mounted at /shared in Docker)
_shared_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared")
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

from response_parser import ParseResult, ResponseParser


# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------

class TestParseResult:
    """Tests for the ParseResult dataclass."""

    def test_default_field_values(self):
        result = ParseResult(status="success")
        assert result.field_values == {}
        assert result.parsed_annotation is None
        assert result.error is None

    def test_explicit_field_values(self):
        fv = {"answer": "Ja"}
        result = ParseResult(status="success", field_values=fv)
        assert result.field_values is fv

    def test_error_result(self):
        result = ParseResult(status="failed", error="something went wrong")
        assert result.status == "failed"
        assert result.error == "something went wrong"
        assert result.parsed_annotation is None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def choices_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <Choices name="sentiment" toName="text">
            <Choice value="positive"/>
            <Choice value="negative"/>
            <Choice value="neutral"/>
        </Choices>
    </View>
    """


@pytest.fixture
def textarea_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <TextArea name="answer" toName="text"/>
    </View>
    """


@pytest.fixture
def multi_field_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <Choices name="sentiment" toName="text">
            <Choice value="positive"/>
            <Choice value="negative"/>
        </Choices>
        <TextArea name="reasoning" toName="text"/>
        <Rating name="confidence" toName="text"/>
    </View>
    """


@pytest.fixture
def number_label_config():
    return """
    <View>
        <Text name="text" value="$text"/>
        <Number name="score" toName="text"/>
    </View>
    """


@pytest.fixture
def loesung_label_config():
    """German legal annotation config with Loesung field."""
    return """
    <View>
        <Text name="sachverhalt" value="$sachverhalt"/>
        <Loesung name="loesung" toName="sachverhalt"/>
    </View>
    """


@pytest.fixture
def gliederung_loesung_label_config():
    """Config with both Gliederung and Loesung."""
    return """
    <View>
        <Text name="sachverhalt" value="$sachverhalt"/>
        <Gliederung name="gliederung" toName="sachverhalt"/>
        <Loesung name="loesung" toName="sachverhalt"/>
    </View>
    """


# ---------------------------------------------------------------------------
# Label config parsing
# ---------------------------------------------------------------------------

class TestLabelConfigParsing:
    """Test _parse_label_config for various element types."""

    def test_choices_parsed(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        assert "sentiment" in parser.label_config_map
        cfg = parser.label_config_map["sentiment"]
        assert cfg["type"] == "Choices"
        assert set(cfg["choices"]) == {"positive", "negative", "neutral"}

    def test_textarea_parsed(self, textarea_label_config):
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        assert "answer" in parser.label_config_map
        assert parser.label_config_map["answer"]["type"] == "TextArea"

    def test_rating_parsed(self, multi_field_label_config):
        parser = ResponseParser(generation_structure={}, label_config=multi_field_label_config)
        assert "confidence" in parser.label_config_map
        assert parser.label_config_map["confidence"]["type"] == "Rating"

    def test_number_parsed(self, number_label_config):
        parser = ResponseParser(generation_structure={}, label_config=number_label_config)
        assert "score" in parser.label_config_map
        assert parser.label_config_map["score"]["type"] == "Number"

    def test_display_text_excluded(self, choices_label_config):
        """Text elements (display-only) must not appear in the output field map."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        assert "text" not in parser.label_config_map

    def test_loesung_parsed(self, loesung_label_config):
        parser = ResponseParser(generation_structure={}, label_config=loesung_label_config)
        assert "loesung" in parser.label_config_map
        assert parser.label_config_map["loesung"]["type"] == "Loesung"

    def test_gliederung_parsed(self, gliederung_loesung_label_config):
        parser = ResponseParser(generation_structure={}, label_config=gliederung_loesung_label_config)
        assert "gliederung" in parser.label_config_map
        assert parser.label_config_map["gliederung"]["type"] == "Gliederung"

    def test_invalid_xml_returns_empty(self):
        parser = ResponseParser(generation_structure={}, label_config="<not valid xml")
        assert parser.label_config_map == {}

    def test_required_attribute(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="answer" toName="text" required="true">
                <Choice value="Ja"/>
                <Choice value="Nein"/>
            </Choices>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        assert parser.label_config_map["answer"]["required"] is True


# ---------------------------------------------------------------------------
# JSON schema building
# ---------------------------------------------------------------------------

class TestBuildJsonSchema:
    """Test _build_json_schema from generation_structure and label_config."""

    def test_schema_from_generation_structure_choices(self):
        gs = {
            "fields": {
                "answer": {"type": "choices", "options": ["Ja", "Nein"], "required": True}
            }
        }
        parser = ResponseParser(
            generation_structure=gs,
            label_config="<View><Text name='t' value='$t'/></View>",
        )
        schema = parser.json_schema
        assert schema["properties"]["answer"]["type"] == "string"
        assert schema["properties"]["answer"]["enum"] == ["Ja", "Nein"]
        assert "answer" in schema["required"]

    def test_schema_from_generation_structure_number(self):
        gs = {"fields": {"score": {"type": "number"}}}
        parser = ResponseParser(
            generation_structure=gs,
            label_config="<View><Text name='t' value='$t'/></View>",
        )
        assert parser.json_schema["properties"]["score"]["type"] == "number"

    def test_schema_from_generation_structure_text(self):
        gs = {"fields": {"reasoning": {"type": "text"}}}
        parser = ResponseParser(
            generation_structure=gs,
            label_config="<View><Text name='t' value='$t'/></View>",
        )
        assert parser.json_schema["properties"]["reasoning"]["type"] == "string"

    def test_schema_auto_derived_from_label_config(self, choices_label_config):
        """When generation_structure has no fields, schema comes from label_config."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        schema = parser.json_schema
        assert "sentiment" in schema["properties"]
        assert schema["properties"]["sentiment"]["type"] == "string"
        assert set(schema["properties"]["sentiment"]["enum"]) == {"positive", "negative", "neutral"}

    def test_schema_number_from_label_config(self, number_label_config):
        parser = ResponseParser(generation_structure={}, label_config=number_label_config)
        assert parser.json_schema["properties"]["score"]["type"] == "number"

    def test_empty_schema_when_no_fields(self):
        parser = ResponseParser(
            generation_structure={},
            label_config="<View><Text name='t' value='$t'/></View>",
        )
        assert parser.json_schema == {}

    def test_schema_from_label_config_gliederung(self, gliederung_loesung_label_config):
        parser = ResponseParser(generation_structure={}, label_config=gliederung_loesung_label_config)
        schema = parser.json_schema
        assert schema["properties"]["gliederung"]["type"] == "string"
        assert schema["properties"]["loesung"]["type"] == "string"


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

class TestJsonParsing:
    """Test _try_json_parse and the full parse() path for JSON inputs."""

    def test_parse_plain_json_choices(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        result = parser.parse('{"sentiment": "positive"}')
        assert result.status == "success"
        annotation = result.parsed_annotation
        assert any(a["from_name"] == "sentiment" for a in annotation)

    def test_parse_json_in_markdown_block(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        response = '```json\n{"sentiment": "negative"}\n```'
        result = parser.parse(response)
        assert result.status == "success"

    def test_parse_json_validation_error_via_try_json(self, choices_label_config):
        """_try_json_parse returns validation_error for invalid enum values."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        result = parser._try_json_parse('{"sentiment": "invalid_value"}')
        assert result.status == "validation_error"
        assert "validation" in result.error.lower()

    def test_parse_invalid_enum_value_top_level(self, choices_label_config):
        """Top-level parse() fails when JSON has invalid enum and pattern match also fails."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        result = parser.parse('{"sentiment": "invalid_value"}')
        # JSON validation fails, pattern match also fails -> "failed"
        assert result.status == "failed"

    def test_parse_invalid_json_falls_through(self, textarea_label_config):
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        result = parser._try_json_parse("This is not JSON at all {broken")
        assert result.status == "failed"

    def test_parse_json_textarea(self, textarea_label_config):
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        result = parser.parse('{"answer": "This is my analysis."}')
        assert result.status == "success"
        ann = next(a for a in result.parsed_annotation if a["from_name"] == "answer")
        assert ann["type"] == "textarea"
        assert ann["value"]["text"] == ["This is my analysis."]

    def test_parse_json_number(self, number_label_config):
        parser = ResponseParser(generation_structure={}, label_config=number_label_config)
        result = parser.parse('{"score": 42}')
        assert result.status == "success"
        ann = next(a for a in result.parsed_annotation if a["from_name"] == "score")
        assert ann["type"] == "number"
        assert ann["value"]["number"] == 42

    def test_parse_multi_field_json(self, multi_field_label_config):
        parser = ResponseParser(generation_structure={}, label_config=multi_field_label_config)
        response = json.dumps({
            "sentiment": "positive",
            "reasoning": "Good text",
            "confidence": 4,
        })
        result = parser.parse(response)
        assert result.status == "success"
        assert len(result.parsed_annotation) == 3

    def test_extra_fields_filtered_out(self, choices_label_config):
        """Fields not in label_config should be dropped from the annotation."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        response = json.dumps({"sentiment": "positive", "extra_field": "should be ignored"})
        result = parser.parse(response)
        assert result.status == "success"
        field_names = [a["from_name"] for a in result.parsed_annotation]
        assert "extra_field" not in field_names


# ---------------------------------------------------------------------------
# Pattern matching fallback
# ---------------------------------------------------------------------------

class TestPatternMatching:
    """Test _try_pattern_match for non-JSON LLM outputs."""

    def test_colon_separated_fields(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        response = "sentiment: positive"
        result = parser._try_pattern_match(response)
        assert result.status == "success"

    def test_equals_separated_fields(self, textarea_label_config):
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        response = "answer = This is my response."
        result = parser._try_pattern_match(response)
        assert result.status == "success"

    def test_pattern_match_no_fields(self):
        """Completely unstructured text with no matching fields."""
        config = "<View><Text name='t' value='$t'/><Number name='score' toName='t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        result = parser._try_pattern_match("Random text with no structure")
        assert result.status == "failed"

    def test_pattern_match_from_generation_structure(self):
        gs = {"fields": {"answer": {"type": "text"}}}
        config = "<View><Text name='t' value='$t'/><TextArea name='answer' toName='t'/></View>"
        parser = ResponseParser(generation_structure=gs, label_config=config)
        response = "answer: My detailed analysis"
        result = parser._try_pattern_match(response)
        assert result.status == "success"

    def test_freeform_text_single_loesung(self, loesung_label_config):
        """Free-form text should map to a single Loesung field."""
        parser = ResponseParser(generation_structure={}, label_config=loesung_label_config)
        response = "Dies ist eine detaillierte Loesung des Falles."
        result = parser._try_pattern_match(response)
        assert result.status == "success"

    def test_freeform_text_multi_fields_prioritizes_loesung(self, gliederung_loesung_label_config):
        """With multiple text fields, Loesung should be prioritized for free-form text."""
        parser = ResponseParser(generation_structure={}, label_config=gliederung_loesung_label_config)
        response = "Dies ist die gesamte Antwort."
        result = parser._try_pattern_match(response)
        assert result.status == "success"
        ann = next(a for a in result.parsed_annotation if a["from_name"] == "loesung")
        assert ann["value"]["text"] == ["Dies ist die gesamte Antwort."]


# ---------------------------------------------------------------------------
# Full parse() integration
# ---------------------------------------------------------------------------

class TestParseIntegration:
    """Test the top-level parse() method end-to-end."""

    def test_json_preferred_over_pattern(self, choices_label_config):
        """JSON parsing should be attempted first."""
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        result = parser.parse('{"sentiment": "positive"}')
        assert result.status == "success"

    def test_fallback_to_pattern_match(self, textarea_label_config):
        """When JSON fails, pattern matching kicks in."""
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        result = parser.parse("answer: This is my analysis of the case.")
        assert result.status == "success"

    def test_both_fail(self):
        """When both JSON and pattern matching fail."""
        config = "<View><Text name='t' value='$t'/><Number name='score' toName='t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        result = parser.parse("Completely unrelated gibberish")
        assert result.status == "failed"
        assert "Unable to parse" in result.error


# ---------------------------------------------------------------------------
# Transform to Label Studio
# ---------------------------------------------------------------------------

class TestTransformToLabelStudio:
    """Test _transform_to_label_studio for each annotation type."""

    def test_choices_transform(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        annotation = parser._transform_to_label_studio({"sentiment": "positive"})
        assert len(annotation) == 1
        assert annotation[0]["type"] == "choices"
        assert annotation[0]["value"]["choices"] == ["positive"]

    def test_textarea_transform(self, textarea_label_config):
        parser = ResponseParser(generation_structure={}, label_config=textarea_label_config)
        annotation = parser._transform_to_label_studio({"answer": "My answer"})
        assert annotation[0]["type"] == "textarea"
        assert annotation[0]["value"]["text"] == ["My answer"]

    def test_rating_transform(self, multi_field_label_config):
        parser = ResponseParser(generation_structure={}, label_config=multi_field_label_config)
        annotation = parser._transform_to_label_studio({"confidence": 5})
        ann = next(a for a in annotation if a["from_name"] == "confidence")
        assert ann["type"] == "rating"
        assert ann["value"]["rating"] == 5

    def test_number_transform(self, number_label_config):
        parser = ResponseParser(generation_structure={}, label_config=number_label_config)
        annotation = parser._transform_to_label_studio({"score": 42})
        assert annotation[0]["type"] == "number"
        assert annotation[0]["value"]["number"] == 42

    def test_loesung_transform(self, loesung_label_config):
        parser = ResponseParser(generation_structure={}, label_config=loesung_label_config)
        annotation = parser._transform_to_label_studio({"loesung": "Antwort"})
        assert annotation[0]["type"] == "textarea"
        assert annotation[0]["value"]["text"] == ["Antwort"]

    def test_unknown_field_skipped(self, choices_label_config):
        parser = ResponseParser(generation_structure={}, label_config=choices_label_config)
        annotation = parser._transform_to_label_studio({"unknown_field": "value"})
        assert len(annotation) == 0


# ---------------------------------------------------------------------------
# Span normalization
# ---------------------------------------------------------------------------

class TestNormalizeSpan:
    """Test _normalize_span helper."""

    def test_valid_span(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="PERSON"/>
            </Labels>
        </View>
        """
        parser = ResponseParser(generation_structure={}, label_config=config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "type": "PERSON", "text": "Alice"},
            available_labels=["PERSON"],
        )
        assert span is not None
        assert span["start"] == 0
        assert span["end"] == 5
        assert span["labels"] == ["PERSON"]

    def test_missing_start_returns_none(self):
        config = "<View><Text name='t' value='$t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        span = parser._normalize_span(
            {"end": 5, "type": "PERSON"},
            available_labels=[],
        )
        assert span is None

    def test_missing_type_returns_none(self):
        config = "<View><Text name='t' value='$t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        span = parser._normalize_span(
            {"start": 0, "end": 5},
            available_labels=[],
        )
        assert span is None

    def test_invalid_label_filtered(self):
        config = "<View><Text name='t' value='$t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "type": "INVALID"},
            available_labels=["PERSON", "ORG"],
        )
        assert span is None

    def test_label_key_alternative(self):
        """Accepts 'label' key as alternative to 'type'."""
        config = "<View><Text name='t' value='$t'/></View>"
        parser = ResponseParser(generation_structure={}, label_config=config)
        span = parser._normalize_span(
            {"start": 0, "end": 5, "label": "PERSON"},
            available_labels=[],
        )
        assert span is not None
        assert span["labels"] == ["PERSON"]
