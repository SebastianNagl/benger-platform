"""Tests for response_parser.py covering uncovered branches.

Covers: _parse_label_config, _build_json_schema, _transform_to_label_studio,
_parse_span_value, _normalize_span, parse, _try_json_parse, _try_pattern_match.
"""

import json
import pytest

import sys
import os
workers_root = os.path.dirname(os.path.dirname(__file__))
shared_root = os.path.join(os.path.dirname(workers_root), "shared")
sys.path.insert(0, workers_root)
if os.path.isdir(shared_root):
    sys.path.insert(0, shared_root)

from response_parser import ResponseParser, ParseResult


# ============================================================
# ParseResult dataclass
# ============================================================

class TestParseResult:
    def test_default_field_values(self):
        r = ParseResult(status="success")
        assert r.field_values == {}

    def test_explicit_field_values(self):
        r = ParseResult(status="success", field_values={"a": 1})
        assert r.field_values == {"a": 1}

    def test_error_field(self):
        r = ParseResult(status="failed", error="oops")
        assert r.error == "oops"


# ============================================================
# _parse_label_config
# ============================================================

class TestParseLabelConfig:
    def test_empty_config(self):
        parser = ResponseParser({}, "<View></View>")
        assert parser.label_config_map == {}

    def test_choices_field(self):
        config = '<View><Choices name="answer" toName="text"><Choice value="Yes"/><Choice value="No"/></Choices></View>'
        parser = ResponseParser({}, config)
        assert "answer" in parser.label_config_map
        assert parser.label_config_map["answer"]["type"] == "Choices"
        assert parser.label_config_map["answer"]["choices"] == ["Yes", "No"]

    def test_textarea_field(self):
        config = '<View><TextArea name="comment" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert "comment" in parser.label_config_map
        assert parser.label_config_map["comment"]["type"] == "TextArea"

    def test_rating_field(self):
        config = '<View><Rating name="score" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert "score" in parser.label_config_map
        assert parser.label_config_map["score"]["type"] == "Rating"

    def test_number_field(self):
        config = '<View><Number name="count" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert "count" in parser.label_config_map
        assert parser.label_config_map["count"]["type"] == "Number"

    def test_labels_field(self):
        config = '<View><Labels name="ner" toName="text"><Label value="PER"/><Label value="ORG"/></Labels></View>'
        parser = ResponseParser({}, config)
        assert "ner" in parser.label_config_map
        assert parser.label_config_map["ner"]["type"] == "Labels"
        assert parser.label_config_map["ner"]["labels"] == ["PER", "ORG"]

    def test_gliederung_field(self):
        config = '<View><Gliederung name="outline" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert "outline" in parser.label_config_map
        assert parser.label_config_map["outline"]["type"] == "Gliederung"

    def test_loesung_field(self):
        config = '<View><Loesung name="solution" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert "solution" in parser.label_config_map
        assert parser.label_config_map["solution"]["type"] == "Loesung"

    def test_required_field(self):
        config = '<View><TextArea name="x" toName="text" required="true"/></View>'
        parser = ResponseParser({}, config)
        assert parser.label_config_map["x"]["required"] is True

    def test_not_required_field(self):
        config = '<View><TextArea name="x" toName="text"/></View>'
        parser = ResponseParser({}, config)
        assert parser.label_config_map["x"]["required"] is False

    def test_invalid_xml(self):
        parser = ResponseParser({}, "<<not xml>>")
        assert parser.label_config_map == {}

    def test_text_element_is_ignored(self):
        """Text elements are display-only, not answer fields."""
        config = '<View><Text name="display" value="$text"/><Choices name="answer" toName="display"><Choice value="A"/></Choices></View>'
        parser = ResponseParser({}, config)
        assert "display" not in parser.label_config_map
        assert "answer" in parser.label_config_map

    def test_no_name_attribute(self):
        config = '<View><Choices toName="text"><Choice value="A"/></Choices></View>'
        parser = ResponseParser({}, config)
        assert len(parser.label_config_map) == 0

    def test_choices_without_choice_children(self):
        config = '<View><Choices name="q" toName="text"></Choices></View>'
        parser = ResponseParser({}, config)
        assert "q" in parser.label_config_map
        assert "choices" not in parser.label_config_map["q"]

    def test_labels_without_label_children(self):
        config = '<View><Labels name="ner" toName="text"></Labels></View>'
        parser = ResponseParser({}, config)
        assert "ner" in parser.label_config_map
        assert "labels" not in parser.label_config_map["ner"]


# ============================================================
# _build_json_schema
# ============================================================

class TestBuildJsonSchema:
    def test_schema_from_generation_structure_choices(self):
        gen_struct = {"fields": {"q": {"type": "choices", "options": ["A", "B"]}}}
        parser = ResponseParser(gen_struct, "<View></View>")
        assert parser.json_schema["properties"]["q"]["enum"] == ["A", "B"]

    def test_schema_from_generation_structure_number(self):
        gen_struct = {"fields": {"n": {"type": "number"}}}
        parser = ResponseParser(gen_struct, "<View></View>")
        assert parser.json_schema["properties"]["n"]["type"] == "number"

    def test_schema_from_generation_structure_text(self):
        gen_struct = {"fields": {"t": {"type": "text"}}}
        parser = ResponseParser(gen_struct, "<View></View>")
        assert parser.json_schema["properties"]["t"]["type"] == "string"

    def test_schema_from_generation_structure_required(self):
        gen_struct = {"fields": {"t": {"type": "text", "required": True}}}
        parser = ResponseParser(gen_struct, "<View></View>")
        assert "t" in parser.json_schema["required"]

    def test_schema_from_label_config_choices(self):
        config = '<View><Choices name="q" toName="t"><Choice value="A"/></Choices></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["q"]["enum"] == ["A"]

    def test_schema_from_label_config_number(self):
        config = '<View><Number name="n" toName="t"/></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["n"]["type"] == "number"

    def test_schema_from_label_config_rating(self):
        config = '<View><Rating name="r" toName="t"/></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["r"]["type"] == "number"

    def test_schema_from_label_config_textarea(self):
        config = '<View><TextArea name="c" toName="t"/></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["c"]["type"] == "string"

    def test_schema_from_label_config_labels(self):
        config = '<View><Labels name="ner" toName="t"><Label value="PER"/></Labels></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["ner"]["type"] == "array"
        assert parser.json_schema["properties"]["ner"]["items"]["properties"]["type"]["enum"] == ["PER"]

    def test_schema_from_label_config_gliederung(self):
        config = '<View><Gliederung name="g" toName="t"/></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["g"]["type"] == "string"

    def test_schema_from_label_config_loesung(self):
        config = '<View><Loesung name="l" toName="t"/></View>'
        parser = ResponseParser({}, config)
        assert parser.json_schema["properties"]["l"]["type"] == "string"

    def test_empty_schema_when_no_fields(self):
        parser = ResponseParser({}, "<View></View>")
        assert parser.json_schema == {}


# ============================================================
# _transform_to_label_studio
# ============================================================

class TestTransformToLabelStudio:
    def test_choices_string_value(self):
        config = '<View><Choices name="q" toName="t"><Choice value="Yes"/></Choices></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"q": "Yes"})
        assert result[0]["type"] == "choices"
        assert result[0]["value"]["choices"] == ["Yes"]

    def test_choices_list_value(self):
        config = '<View><Choices name="q" toName="t"><Choice value="A"/><Choice value="B"/></Choices></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"q": ["A", "B"]})
        assert result[0]["value"]["choices"] == ["A", "B"]

    def test_rating_value(self):
        config = '<View><Rating name="r" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"r": 5})
        assert result[0]["type"] == "rating"
        assert result[0]["value"]["rating"] == 5

    def test_number_value(self):
        config = '<View><Number name="n" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"n": 42})
        assert result[0]["type"] == "number"
        assert result[0]["value"]["number"] == 42

    def test_gliederung_value(self):
        config = '<View><Gliederung name="g" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"g": "I. Einleitung"})
        assert result[0]["type"] == "textarea"
        assert result[0]["value"]["text"] == ["I. Einleitung"]

    def test_loesung_value(self):
        config = '<View><Loesung name="l" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"l": "Die Klage ist begründet."})
        assert result[0]["type"] == "textarea"
        assert result[0]["value"]["text"] == ["Die Klage ist begründet."]

    def test_textarea_value(self):
        config = '<View><TextArea name="c" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"c": "Hello"})
        assert result[0]["type"] == "textarea"
        assert result[0]["value"]["text"] == ["Hello"]

    def test_textarea_list_value(self):
        config = '<View><TextArea name="c" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"c": ["a", "b"]})
        assert result[0]["value"]["text"] == ["a", "b"]

    def test_unknown_field_skipped(self):
        config = '<View><TextArea name="c" toName="t"/></View>'
        parser = ResponseParser({}, config)
        result = parser._transform_to_label_studio({"unknown": "value", "c": "hello"})
        assert len(result) == 1
        assert result[0]["from_name"] == "c"

    def test_labels_value(self):
        config = '<View><Labels name="ner" toName="t"><Label value="PER"/></Labels></View>'
        parser = ResponseParser({}, config)
        spans = [{"start": 0, "end": 5, "type": "PER", "text": "Hello"}]
        result = parser._transform_to_label_studio({"ner": spans})
        assert result[0]["type"] == "labels"
        assert "spans" in result[0]["value"]


# ============================================================
# _normalize_span
# ============================================================

class TestNormalizeSpan:
    def _get_parser(self):
        config = '<View><Labels name="ner" toName="t"><Label value="PER"/></Labels></View>'
        return ResponseParser({}, config)

    def test_valid_span(self):
        p = self._get_parser()
        span = p._normalize_span({"start": 0, "end": 5, "type": "PER", "text": "Hello"}, ["PER"])
        assert span["start"] == 0
        assert span["end"] == 5
        assert span["labels"] == ["PER"]

    def test_span_missing_start(self):
        p = self._get_parser()
        assert p._normalize_span({"end": 5, "type": "PER"}, []) is None

    def test_span_missing_end(self):
        p = self._get_parser()
        assert p._normalize_span({"start": 0, "type": "PER"}, []) is None

    def test_span_missing_type(self):
        p = self._get_parser()
        assert p._normalize_span({"start": 0, "end": 5}, []) is None

    def test_span_with_label_key(self):
        p = self._get_parser()
        span = p._normalize_span({"start": 0, "end": 5, "label": "PER"}, [])
        assert span is not None
        assert span["labels"] == ["PER"]

    def test_span_invalid_label(self):
        p = self._get_parser()
        assert p._normalize_span({"start": 0, "end": 5, "type": "XXX"}, ["PER"]) is None

    def test_span_no_available_labels(self):
        p = self._get_parser()
        span = p._normalize_span({"start": 0, "end": 5, "type": "ANY"}, [])
        assert span is not None

    def test_span_preserves_existing_id(self):
        p = self._get_parser()
        span = p._normalize_span({"start": 0, "end": 5, "type": "PER", "id": "my-id"}, [])
        assert span["id"] == "my-id"


# ============================================================
# _parse_span_value
# ============================================================

class TestParseSpanValue:
    def _get_parser(self):
        config = '<View><Labels name="ner" toName="t"><Label value="PER"/><Label value="ORG"/></Labels></View>'
        return ResponseParser({}, config)

    def test_list_of_dicts(self):
        p = self._get_parser()
        spans = p._parse_span_value(
            [{"start": 0, "end": 5, "type": "PER"}],
            {"labels": ["PER"]},
        )
        assert len(spans) == 1
        assert spans[0]["labels"] == ["PER"]

    def test_json_string(self):
        p = self._get_parser()
        json_str = json.dumps([{"start": 0, "end": 5, "type": "PER"}])
        spans = p._parse_span_value(json_str, {"labels": ["PER"]})
        assert len(spans) == 1

    def test_inline_format(self):
        p = self._get_parser()
        text = "[PER: 0-5] John"
        spans = p._parse_span_value(text, {"labels": ["PER"]})
        assert len(spans) == 1
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 5
        assert spans[0]["labels"] == ["PER"]

    def test_marked_format_with_source(self):
        p = self._get_parser()
        p._source_text = "John Smith works at Acme"
        text = "<PER>John Smith</PER>"
        spans = p._parse_span_value(text, {"labels": ["PER"]})
        assert len(spans) == 1
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 10

    def test_marked_format_text_not_found(self):
        p = self._get_parser()
        p._source_text = "different text"
        text = "<PER>nonexistent</PER>"
        with pytest.raises(ValueError, match="not found in source text"):
            p._parse_span_value(text, {"labels": ["PER"]})

    def test_marked_format_no_source_text(self):
        p = self._get_parser()
        p._source_text = None
        text = "<PER>John</PER>"
        with pytest.raises(ValueError, match="requires source_text"):
            p._parse_span_value(text, {"labels": ["PER"]})

    def test_empty_list(self):
        p = self._get_parser()
        spans = p._parse_span_value([], {})
        assert spans == []

    def test_non_matching_string(self):
        p = self._get_parser()
        spans = p._parse_span_value("no spans here", {})
        assert spans == []

    def test_invalid_json_string(self):
        p = self._get_parser()
        spans = p._parse_span_value("{invalid json", {})
        assert spans == []


# ============================================================
# Full parse() method
# ============================================================

class TestParse:
    def test_parse_json_success(self):
        config = '<View><Choices name="answer" toName="text"><Choice value="Yes"/></Choices></View>'
        parser = ResponseParser({}, config)
        result = parser.parse('{"answer": "Yes"}')
        assert result.status == "success"

    def test_parse_json_in_markdown(self):
        config = '<View><Choices name="answer" toName="text"><Choice value="Yes"/></Choices></View>'
        parser = ResponseParser({}, config)
        result = parser.parse('```json\n{"answer": "Yes"}\n```')
        assert result.status == "success"

    def test_parse_pattern_fallback(self):
        config = '<View><TextArea name="comment" toName="text"/></View>'
        gen_struct = {"fields": {"comment": {"type": "text"}}}
        parser = ResponseParser(gen_struct, config)
        result = parser.parse("comment: This is a test")
        assert result.status == "success"

    def test_parse_both_fail(self):
        config = '<View><Choices name="q" toName="t"><Choice value="A"/></Choices></View>'
        gen_struct = {"fields": {"q": {"type": "choices", "options": ["A"]}}}
        parser = ResponseParser(gen_struct, config)
        # Random gibberish that can't be parsed
        result = parser.parse("@#$%^&*")
        assert result.status in ("failed", "validation_error")

    def test_parse_json_validation_error(self):
        """Validation error from _try_json_parse is visible in the direct call."""
        config = '<View><Choices name="q" toName="t"><Choice value="A"/></Choices></View>'
        gen_struct = {"fields": {"q": {"type": "choices", "options": ["A"], "required": True}}}
        parser = ResponseParser(gen_struct, config)
        result = parser._try_json_parse('{"q": 12345}')
        assert result.status == "validation_error"

    def test_parse_array_response_for_labels(self):
        config = '<View><Labels name="ner" toName="t"><Label value="PER"/></Labels></View>'
        parser = ResponseParser({}, config)
        response = json.dumps([{"start": 0, "end": 5, "type": "PER"}])
        result = parser.parse(response)
        assert result.status == "success"


# ============================================================
# _try_pattern_match specifics
# ============================================================

class TestTryPatternMatch:
    def test_choices_extraction(self):
        gen_struct = {"fields": {"q": {"type": "choices"}}}
        config = '<View><Choices name="q" toName="t"><Choice value="A"/></Choices></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match('q: "A"')
        assert result.status == "success"

    def test_number_extraction_valid(self):
        gen_struct = {"fields": {"n": {"type": "number"}}}
        config = '<View><Number name="n" toName="t"/></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match("n: 42.5")
        assert result.status == "success"

    def test_number_extraction_invalid(self):
        gen_struct = {"fields": {"n": {"type": "number"}}}
        config = '<View><Number name="n" toName="t"/></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match("n: not-a-number")
        assert result.status == "success"  # Falls back to string

    def test_text_extraction(self):
        gen_struct = {"fields": {"t": {"type": "text"}}}
        config = '<View><TextArea name="t" toName="x"/></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match("t: Hello world")
        assert result.status == "success"

    def test_no_fields_extracted(self):
        gen_struct = {"fields": {"xyz": {"type": "text"}}}
        config = '<View></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match("abc: something")
        assert result.status == "failed"

    def test_freeform_text_single_text_field(self):
        """Test fallback for German legal text fields when no structured data found."""
        config = '<View><Loesung name="loesung" toName="text"/></View>'
        parser = ResponseParser({}, config)
        result = parser._try_pattern_match("Die Klage ist begründet, weil...")
        assert result.status == "success"

    def test_freeform_text_multiple_text_fields_loesung(self):
        """When multiple text fields, prioritize Loesung."""
        config = '<View><Gliederung name="gliederung" toName="text"/><Loesung name="loesung" toName="text"/></View>'
        parser = ResponseParser({}, config)
        result = parser._try_pattern_match("Die Klage ist begründet, weil...")
        assert result.status == "success"

    def test_freeform_text_multiple_text_fields_no_loesung(self):
        """Multiple text fields but no Loesung -> nothing extracted."""
        config = '<View><Gliederung name="gliederung" toName="text"/><TextArea name="comment" toName="text"/></View>'
        parser = ResponseParser({}, config)
        result = parser._try_pattern_match("Some random text")
        assert result.status == "failed"

    def test_pattern_match_equals_sign(self):
        gen_struct = {"fields": {"answer": {"type": "text"}}}
        config = '<View><TextArea name="answer" toName="text"/></View>'
        parser = ResponseParser(gen_struct, config)
        result = parser._try_pattern_match("answer = This is the answer")
        assert result.status == "success"

    def test_fallback_to_label_config_fields(self):
        """When generation_structure has no fields, fall back to label_config."""
        config = '<View><TextArea name="answer" toName="text"/></View>'
        parser = ResponseParser({}, config)
        result = parser._try_pattern_match("answer: My response here")
        assert result.status == "success"
