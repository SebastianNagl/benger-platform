"""Mutation-kill tests for response_parser.ResponseParser.

These complement the fuzz/round-trip invariants in
``test_response_parser_properties.py`` with HAND-COMPUTED exact-value
assertions. Every test below is written so that flipping a comparison
operator, changing a numeric/string constant, taking the wrong branch,
returning the wrong value, or mutating a regex in ``response_parser.py``
makes a concrete assertion FAIL.

Each test names — in its body or docstring — the exact branch / operator /
return / regex it pins, with the expected value derived by hand from the
source, not by running the parser first.

A note on parse-status precedence (``parse()``):
    1. ``_try_json_parse`` → if status == "success", return it.
    2. else ``_try_pattern_match`` → if status == "success", return it.
    3. else ``ParseResult(status="failed", ...)``.
``_try_json_parse`` itself can return success / validation_error / failed;
``_try_pattern_match`` returns success (always, via __response__ fallback) or
failed (only on an internal exception).
"""

import json
import os
import re
import sys

import pytest

# Make shared/annotation_utils importable (mounted at /shared in Docker).
# Mirrors the sys.path setup in test_response_parser.py.
_shared_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "shared",
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)
_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _workers_root not in sys.path:
    sys.path.insert(0, _workers_root)

from response_parser import (  # noqa: E402
    ParseResult,
    ResponseParser,
    find_prompt_structure,
    last_json_value,
    multi_choice_names,
)


# ---------------------------------------------------------------------------
# Reusable label configs (kept tiny + explicit so the expected values are
# trivially hand-derivable).
# ---------------------------------------------------------------------------

CHOICES_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <Choices name="sentiment" toName="text">
        <Choice value="positive"/>
        <Choice value="negative"/>
        <Choice value="neutral"/>
    </Choices>
</View>
"""

TEXTAREA_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <TextArea name="answer" toName="text"/>
</View>
"""

NUMBER_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <Number name="score" toName="text"/>
</View>
"""

RATING_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <Rating name="confidence" toName="text"/>
</View>
"""

LABELS_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <Labels name="entities" toName="text">
        <Label value="PERSON"/>
        <Label value="ORG"/>
    </Labels>
</View>
"""

LOESUNG_CONFIG = """
<View>
    <Text name="sachverhalt" value="$sachverhalt"/>
    <Loesung name="loesung" toName="sachverhalt"/>
</View>
"""

GLIEDERUNG_LOESUNG_CONFIG = """
<View>
    <Text name="sachverhalt" value="$sachverhalt"/>
    <Gliederung name="gliederung" toName="sachverhalt"/>
    <Loesung name="loesung" toName="sachverhalt"/>
</View>
"""

EMPTY_DISPLAY_CONFIG = "<View><Text name='t' value='$t'/></View>"


def _parser(label_config, gen_structure=None):
    return ResponseParser(
        generation_structure=gen_structure or {}, label_config=label_config
    )


# ===========================================================================
# ParseResult.__post_init__ — the `== None` default-init branch
# ===========================================================================

class TestParseResultPostInit:
    def test_none_field_values_becomes_empty_dict(self):
        # __post_init__: `if self.field_values == None: self.field_values = {}`.
        # Mutating `== None` to `!= None` would leave field_values as None here.
        r = ParseResult(status="success")
        assert r.field_values == {}
        assert r.field_values is not None

    def test_explicit_field_values_preserved_not_overwritten(self):
        # The `== None` guard must be FALSE for a non-None dict, so the supplied
        # dict survives. A flipped guard would clobber it with {}.
        fv = {"answer": "Ja"}
        r = ParseResult(status="success", field_values=fv)
        assert r.field_values is fv
        assert r.field_values == {"answer": "Ja"}


# ===========================================================================
# parse() — status precedence machine (JSON first, then pattern, then failed)
# ===========================================================================

class TestParseStatusPrecedence:
    def test_valid_json_returns_success_via_json_path(self):
        # parse(): _try_json_parse success short-circuits. Exact field_values.
        p = _parser(CHOICES_CONFIG)
        r = p.parse('{"sentiment": "positive"}')
        assert r.status == "success"
        assert r.field_values == {"sentiment": "positive"}

    def test_non_json_field_value_falls_to_pattern_success(self):
        # JSON parse fails -> pattern match extracts answer -> success.
        p = _parser(TEXTAREA_CONFIG)
        r = p.parse("answer: hello world")
        assert r.status == "success"
        assert r.field_values == {"answer": "hello world"}

    def test_unstructured_text_pattern_fallback_to_response_field(self):
        # No JSON, pattern extracts nothing for a Number-only config -> the
        # __response__ fallback success branch fires. status must be success,
        # NOT failed (kills a swap of the fallback's status constant).
        p = _parser(NUMBER_CONFIG)
        r = p.parse("Completely unrelated gibberish")
        assert r.status == "success"
        assert r.field_values == {"__response__": "Completely unrelated gibberish"}

    def test_failed_terminal_string_is_the_documented_value(self):
        # The only way to reach the terminal failed branch from parse() is if
        # both helpers return non-success. We force _try_json_parse->failed and
        # monkeypatch _try_pattern_match to also return failed.
        p = _parser(EMPTY_DISPLAY_CONFIG)
        p._try_pattern_match = lambda text: ParseResult(status="failed", error="x")
        r = p.parse("not json {")
        assert r.status == "failed"
        assert r.error == "Unable to parse response as JSON or structured text"


# ===========================================================================
# _try_json_parse — markdown fence extraction, array-wrap, validation, failure
# ===========================================================================

class TestTryJsonParse:
    def test_plain_json_success_exact_annotation(self):
        p = _parser(CHOICES_CONFIG)
        r = p._try_json_parse('{"sentiment": "neutral"}')
        assert r.status == "success"
        assert r.parsed_annotation == [
            {"from_name": "sentiment", "type": "choices",
             "value": {"choices": ["neutral"]}}
        ]

    def test_markdown_json_fence_recovered(self):
        # regex ```(?:json)?\s*\n(.*?)\n``` captures the inner JSON. Pins the
        # markdown branch (json_match truthy) vs the .strip() else-branch.
        p = _parser(CHOICES_CONFIG)
        r = p._try_json_parse('```json\n{"sentiment": "negative"}\n```')
        assert r.status == "success"
        assert r.field_values == {"sentiment": "negative"}

    def test_markdown_fence_without_json_word(self):
        # The `(?:json)?` group is optional — a bare ``` fence still matches.
        p = _parser(NUMBER_CONFIG)
        r = p._try_json_parse('```\n{"score": 7}\n```')
        assert r.status == "success"
        assert r.field_values == {"score": "7"}  # number extracted as str by util

    def test_plain_json_without_fence_uses_strip_branch(self):
        # No fence -> json_text = response_text.strip(). Leading/trailing
        # whitespace must be stripped for json.loads to succeed.
        p = _parser(NUMBER_CONFIG)
        r = p._try_json_parse('   {"score": 3}   ')
        assert r.status == "success"
        assert r.field_values == {"score": "3"}

    def test_broken_json_returns_failed_not_success(self):
        # json.JSONDecodeError branch -> status "failed". Killing the except
        # clause / wrong status constant fails here.
        p = _parser(TEXTAREA_CONFIG)
        r = p._try_json_parse("This is not JSON at all {broken")
        assert r.status == "failed"
        assert r.error.startswith("JSON parsing failed:")

    def test_schema_validation_error_for_bad_enum(self):
        # Choices enum is {positive,negative,neutral}; "maybe" violates it.
        # jsonschema.ValidationError branch -> status "validation_error",
        # distinct from both success and failed.
        p = _parser(CHOICES_CONFIG)
        r = p._try_json_parse('{"sentiment": "maybe"}')
        assert r.status == "validation_error"
        assert r.error.startswith("JSON schema validation failed:")

    def test_array_response_wrapped_for_labels_field(self):
        # Issue #964: a bare JSON array + a Labels field -> wrapped under the
        # Labels field name. Two spans in, two spans out, exact offsets.
        p = _parser(LABELS_CONFIG)
        raw = '[{"start": 0, "end": 5, "type": "PERSON", "text": "Alice"}, ' \
              '{"start": 6, "end": 10, "type": "ORG", "text": "Acme"}]'
        r = p._try_json_parse(raw)
        assert r.status == "success"
        spans = r.parsed_annotation[0]["value"]["spans"]
        assert [(s["start"], s["end"], s["labels"][0]) for s in spans] == [
            (0, 5, "PERSON"), (6, 10, "ORG")
        ]

    def test_array_response_not_wrapped_without_labels_field(self):
        # Same bare array but the config has NO Labels field -> the `if
        # labels_field:` wrap guard is FALSE, so parsed_data stays a list. The
        # auto-derived Choices schema is {"type": "object", ...}; a list is not
        # an object, so jsonschema validation fails -> validation_error (NOT
        # success). This pins the wrap guard: had the array been wrapped under
        # a field name it would have become a dict and validated differently.
        p = _parser(CHOICES_CONFIG)
        r = p._try_json_parse('[{"start": 0, "end": 5, "type": "PERSON"}]')
        assert r.status == "validation_error"

    def test_array_response_no_schema_no_labels_hits_broad_except(self):
        # No Labels field AND no schema (display-only config -> json_schema=={})
        # -> the array is neither wrapped nor validated, so it reaches
        # _transform_to_label_studio still a LIST. That function does
        # `parsed_data.items()`, which raises AttributeError on a list; the
        # broad `except Exception` branch catches it -> status "failed" with the
        # "Unexpected error" prefix (distinct from the JSONDecodeError "failed").
        # Pins (a) the wrap guard leaving a list untouched without a Labels
        # field, and (b) the broad-except -> failed return.
        p = _parser(EMPTY_DISPLAY_CONFIG)
        r = p._try_json_parse('[{"start": 0, "end": 5, "type": "PERSON"}]')
        assert r.status == "failed"
        assert r.error.startswith("Unexpected error in JSON parsing:")


# ===========================================================================
# _try_pattern_match — extraction regex, value cleanup, type conversion,
# the __response__ fallback, and the generation_structure-vs-label_config
# field-source precedence.
# ===========================================================================

class TestTryPatternMatch:
    def test_colon_separator_extracts_value(self):
        p = _parser(TEXTAREA_CONFIG)
        r = p._try_pattern_match("answer: The contract is valid")
        assert r.status == "success"
        assert r.field_values == {"answer": "The contract is valid"}

    def test_equals_separator_extracts_value(self):
        # Pattern is [:\=]; the '=' alternative must also match.
        p = _parser(TEXTAREA_CONFIG)
        r = p._try_pattern_match("answer = The contract is valid")
        assert r.status == "success"
        assert r.field_values == {"answer": "The contract is valid"}

    def test_value_whitespace_collapsed_and_quotes_stripped(self):
        # value cleanup: strip('"\'') then re.sub(r'\s+', ' '). Input value is
        #   "hello   world"   -> strip quotes -> hello   world -> collapse ->
        #   "hello world".
        p = _parser(TEXTAREA_CONFIG)
        r = p._try_pattern_match('answer: "hello   world"')
        assert r.field_values == {"answer": "hello world"}

    def test_multiline_lookahead_boundary_stops_at_next_field(self):
        # The lookahead (?=\n\w+\s*[:\=]|\Z) bounds the first field at the next
        # "word:" line. "answer" must capture only "first" not "second".
        config = """
        <View>
            <Text name='t' value='$t'/>
            <TextArea name='answer' toName='t'/>
            <TextArea name='reasoning' toName='t'/>
        </View>
        """
        p = _parser(config)
        r = p._try_pattern_match("answer: first\nreasoning: second part")
        assert r.field_values == {"answer": "first", "reasoning": "second part"}

    def test_choices_value_extracted_from_quotes(self):
        # field_type == "choices" path (lowercased from label_config). With a
        # quoted token, the inner regex ["']([^"']+)["'] extracts "positive".
        # We drive the generation_structure 'choices' branch directly.
        gs = {"fields": {"sentiment": {"type": "choices",
                                       "options": ["positive", "negative"]}}}
        p = _parser(CHOICES_CONFIG, gs)
        r = p._try_pattern_match('sentiment: I think "positive" fits')
        assert r.field_values == {"sentiment": "positive"}

    def test_number_field_converts_to_float(self):
        # field_type == "number" -> float(value). 42 -> 42.0, but the util
        # stringifies the stored number, so field_values is "42.0".
        gs = {"fields": {"score": {"type": "number"}}}
        p = _parser(NUMBER_CONFIG, gs)
        r = p._try_pattern_match("score: 42")
        assert r.field_values == {"score": "42.0"}

    def test_number_field_non_numeric_keeps_string(self):
        # float() raises ValueError -> the except branch keeps the raw string.
        gs = {"fields": {"score": {"type": "number"}}}
        p = _parser(NUMBER_CONFIG, gs)
        r = p._try_pattern_match("score: not_a_number")
        assert r.field_values == {"score": "not_a_number"}

    def test_no_fields_extracted_returns_response_fallback_exactly(self):
        # The `if not parsed_data:` branch builds a single __response__
        # textarea annotation with response_text.strip(). Exact shape pinned.
        p = _parser(NUMBER_CONFIG)
        r = p._try_pattern_match("   pure prose, no fields   ")
        assert r.status == "success"
        assert r.parsed_annotation == [{
            "from_name": "__response__",
            "type": "textarea",
            "value": {"text": ["pure prose, no fields"]},
        }]
        assert r.field_values == {"__response__": "pure prose, no fields"}

    def test_fields_source_prefers_generation_structure(self):
        # When generation_structure.fields exists it is used, NOT label_config.
        # gs declares 'answer'; we extract it.
        gs = {"fields": {"answer": {"type": "text"}}}
        p = _parser(TEXTAREA_CONFIG, gs)
        r = p._try_pattern_match("answer: from gen structure")
        assert r.field_values == {"answer": "from gen structure"}

    def test_fields_source_falls_back_to_label_config(self):
        # gs has no 'fields' -> the loop derives fields from label_config_map.
        # 'answer' (TextArea) is extracted.
        p = _parser(TEXTAREA_CONFIG)
        r = p._try_pattern_match("answer: from label config")
        assert r.field_values == {"answer": "from label config"}


# ===========================================================================
# _transform_to_label_studio — per-type dispatch + field-filtering
# ===========================================================================

class TestTransformDispatch:
    def test_choices_type_yields_choices_value_list(self):
        p = _parser(CHOICES_CONFIG)
        ann = p._transform_to_label_studio({"sentiment": "positive"})
        assert ann == [{"from_name": "sentiment", "type": "choices",
                        "value": {"choices": ["positive"]}}]

    def test_rating_type_yields_rating_value(self):
        # Rating branch: {"rating": value} with the raw value (int kept).
        p = _parser(RATING_CONFIG)
        ann = p._transform_to_label_studio({"confidence": 5})
        assert ann == [{"from_name": "confidence", "type": "rating",
                        "value": {"rating": 5}}]

    def test_number_type_yields_number_value(self):
        p = _parser(NUMBER_CONFIG)
        ann = p._transform_to_label_studio({"score": 42})
        assert ann == [{"from_name": "score", "type": "number",
                        "value": {"number": 42}}]

    def test_textarea_wraps_string_value_in_list(self):
        # default branch: text wrapped as [value] for a str.
        p = _parser(TEXTAREA_CONFIG)
        ann = p._transform_to_label_studio({"answer": "hi"})
        assert ann == [{"from_name": "answer", "type": "textarea",
                        "value": {"text": ["hi"]}}]

    def test_textarea_keeps_list_value_unwrapped(self):
        # default branch: a list value is NOT re-wrapped (isinstance str check).
        p = _parser(TEXTAREA_CONFIG)
        ann = p._transform_to_label_studio({"answer": ["a", "b"]})
        assert ann == [{"from_name": "answer", "type": "textarea",
                        "value": {"text": ["a", "b"]}}]

    def test_loesung_routes_to_textarea(self):
        # Gliederung/Loesung branch -> type "textarea", list-wrapped text.
        p = _parser(LOESUNG_CONFIG)
        ann = p._transform_to_label_studio({"loesung": "Antwort"})
        assert ann == [{"from_name": "loesung", "type": "textarea",
                        "value": {"text": ["Antwort"]}}]

    def test_gliederung_routes_to_textarea(self):
        p = _parser(GLIEDERUNG_LOESUNG_CONFIG)
        ann = p._transform_to_label_studio({"gliederung": "1. A 2. B"})
        assert ann == [{"from_name": "gliederung", "type": "textarea",
                        "value": {"text": ["1. A 2. B"]}}]

    def test_field_absent_from_label_config_is_skipped(self):
        # The `field_name not in self.label_config_map` continue-branch drops
        # unknown fields entirely.
        p = _parser(CHOICES_CONFIG)
        ann = p._transform_to_label_studio({"sentiment": "positive",
                                            "bogus": "x"})
        assert ann == [{"from_name": "sentiment", "type": "choices",
                        "value": {"choices": ["positive"]}}]

    def test_choices_non_string_value_passed_through(self):
        # Choices branch: `[value] if isinstance(value, str) else value`. A list
        # value is kept as-is (already a choices list).
        p = _parser(CHOICES_CONFIG)
        ann = p._transform_to_label_studio({"sentiment": ["positive", "neutral"]})
        assert ann == [{"from_name": "sentiment", "type": "choices",
                        "value": {"choices": ["positive", "neutral"]}}]


# ===========================================================================
# _build_json_schema — priority, type mapping, required list, empty schema
# ===========================================================================

class TestBuildJsonSchema:
    def test_priority1_generation_structure_choices_with_enum_and_required(self):
        gs = {"fields": {"answer": {"type": "choices",
                                    "options": ["Ja", "Nein"],
                                    "required": True}}}
        p = _parser(EMPTY_DISPLAY_CONFIG, gs)
        s = p.json_schema
        assert s["properties"]["answer"] == {"type": "string",
                                             "enum": ["Ja", "Nein"]}
        assert s["required"] == ["answer"]

    def test_priority1_number_maps_to_number(self):
        gs = {"fields": {"score": {"type": "number"}}}
        p = _parser(EMPTY_DISPLAY_CONFIG, gs)
        assert p.json_schema["properties"]["score"] == {"type": "number"}

    def test_priority1_text_maps_to_string_and_not_required(self):
        gs = {"fields": {"reasoning": {"type": "text"}}}
        p = _parser(EMPTY_DISPLAY_CONFIG, gs)
        s = p.json_schema
        assert s["properties"]["reasoning"] == {"type": "string"}
        # required defaults to False -> no "required" key emitted.
        assert "required" not in s

    def test_priority1_choices_without_options_has_no_enum(self):
        # The `if "options" in field_config` guard: absent options -> no enum.
        gs = {"fields": {"answer": {"type": "choices"}}}
        p = _parser(EMPTY_DISPLAY_CONFIG, gs)
        assert p.json_schema["properties"]["answer"] == {"type": "string"}

    def test_priority2_label_config_choices_enum(self):
        # No gs fields -> derive from label_config. Choices -> string + enum.
        p = _parser(CHOICES_CONFIG)
        s = p.json_schema
        assert s["properties"]["sentiment"]["type"] == "string"
        assert s["properties"]["sentiment"]["enum"] == [
            "positive", "negative", "neutral"
        ]

    def test_priority2_rating_maps_to_number(self):
        # Rating is grouped with Number -> {"type": "number"}.
        p = _parser(RATING_CONFIG)
        assert p.json_schema["properties"]["confidence"] == {"type": "number"}

    def test_priority2_labels_builds_array_span_schema(self):
        # Labels -> array of span objects; required keys are start/end/type and
        # the label enum is injected into properties.type.
        p = _parser(LABELS_CONFIG)
        prop = p.json_schema["properties"]["entities"]
        assert prop["type"] == "array"
        item = prop["items"]
        assert item["type"] == "object"
        assert item["required"] == ["start", "end", "type"]
        assert item["properties"]["start"] == {"type": "integer"}
        assert item["properties"]["type"]["enum"] == ["PERSON", "ORG"]

    def test_priority2_gliederung_and_loesung_map_to_string(self):
        p = _parser(GLIEDERUNG_LOESUNG_CONFIG)
        s = p.json_schema
        assert s["properties"]["gliederung"] == {"type": "string"}
        assert s["properties"]["loesung"] == {"type": "string"}

    def test_empty_schema_when_no_properties(self):
        # No gs fields, label_config has only a display Text -> {} (no schema,
        # no validation). Pins the `if not properties: return {}` branch.
        p = _parser(EMPTY_DISPLAY_CONFIG)
        assert p.json_schema == {}


# ===========================================================================
# _parse_label_config — tag inclusion, choices/labels extraction, required
# attr boolean parse, Text exclusion, invalid XML
# ===========================================================================

class TestParseLabelConfig:
    def test_choices_field_type_and_choice_values(self):
        p = _parser(CHOICES_CONFIG)
        cfg = p.label_config_map["sentiment"]
        assert cfg["type"] == "Choices"
        assert cfg["choices"] == ["positive", "negative", "neutral"]
        assert cfg["to_name"] == "text"

    def test_textarea_field_type(self):
        p = _parser(TEXTAREA_CONFIG)
        assert p.label_config_map["answer"]["type"] == "TextArea"

    def test_labels_field_extracts_label_values(self):
        p = _parser(LABELS_CONFIG)
        assert p.label_config_map["entities"]["labels"] == ["PERSON", "ORG"]

    def test_display_text_element_excluded(self):
        # "Text" is display-only and must NOT be in the answer-field map.
        p = _parser(CHOICES_CONFIG)
        assert "text" not in p.label_config_map

    def test_required_true_parsed_as_bool_true(self):
        # required attr "true".lower() == "true" -> True.
        config = """
        <View>
            <Text name='t' value='$t'/>
            <Choices name='a' toName='t' required='true'>
                <Choice value='Ja'/>
            </Choices>
        </View>
        """
        p = _parser(config)
        assert p.label_config_map["a"]["required"] is True

    def test_required_absent_defaults_false(self):
        # Missing required attr defaults to "false" -> False. Kills mutating the
        # default literal or the == "true" comparison.
        p = _parser(CHOICES_CONFIG)
        assert p.label_config_map["sentiment"]["required"] is False

    def test_required_uppercase_true_still_bool_true(self):
        # The .lower() normalizes "True"/"TRUE" -> "true" -> True.
        config = """
        <View>
            <TextArea name='a' toName='t' required='TRUE'/>
        </View>
        """
        p = _parser(config)
        assert p.label_config_map["a"]["required"] is True

    def test_invalid_xml_returns_empty_map(self):
        # ET.ParseError caught -> {} returned.
        p = _parser("<not valid xml")
        assert p.label_config_map == {}

    def test_element_without_name_is_skipped(self):
        # `if name:` guard — a control element with no name attr is not added.
        config = "<View><Choices toName='t'><Choice value='x'/></Choices></View>"
        p = _parser(config)
        assert p.label_config_map == {}

    def test_choices_without_choice_children_has_no_choices_key(self):
        # The `if choices:` guard — an empty Choices element gets no "choices".
        config = "<View><Choices name='a' toName='t'/></View>"
        p = _parser(config)
        assert "choices" not in p.label_config_map["a"]


# ===========================================================================
# _parse_span_value — list / JSON-string / inline / marked formats + offsets
# ===========================================================================

class TestParseSpanValue:
    def test_list_of_dicts_normalized_to_spans(self):
        p = _parser(LABELS_CONFIG)
        spans = p._parse_span_value(
            [{"start": 1, "end": 4, "type": "PERSON", "text": "Bob"}],
            {"labels": ["PERSON", "ORG"]},
        )
        assert len(spans) == 1
        assert (spans[0]["start"], spans[0]["end"]) == (1, 4)
        assert spans[0]["labels"] == ["PERSON"]
        assert spans[0]["text"] == "Bob"

    def test_json_string_array_parsed(self):
        p = _parser(LABELS_CONFIG)
        spans = p._parse_span_value(
            '[{"start": 0, "end": 3, "type": "ORG"}]', {"labels": ["ORG"]}
        )
        assert len(spans) == 1
        assert (spans[0]["start"], spans[0]["end"], spans[0]["labels"][0]) == (0, 3, "ORG")

    def test_inline_format_offsets_parsed_as_ints(self):
        # Pattern \[([A-Z_]+):\s*(\d+)-(\d+)\]\s*([^\[]+). start/end are int()'d;
        # text is .strip()'d (the regex captures the trailing space).
        p = _parser(LABELS_CONFIG)
        spans = p._parse_span_value("[PERSON: 0-5] Alice", {"labels": ["PERSON"]})
        assert len(spans) == 1
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 5
        assert spans[0]["text"] == "Alice"
        assert spans[0]["labels"] == ["PERSON"]

    def test_inline_two_spans_both_extracted(self):
        p = _parser(LABELS_CONFIG)
        spans = p._parse_span_value(
            "[PERSON: 0-5] Alice [ORG: 6-10] Acme",
            {"labels": ["PERSON", "ORG"]},
        )
        assert [(s["start"], s["end"], s["labels"][0], s["text"]) for s in spans] == [
            (0, 5, "PERSON", "Alice"), (6, 10, "ORG", "Acme")
        ]

    def test_inline_label_not_in_available_is_filtered(self):
        # `if not available_labels or label in available_labels` — a label
        # outside the configured set is dropped.
        p = _parser(LABELS_CONFIG)
        spans = p._parse_span_value("[GPE: 0-5] Paris", {"labels": ["PERSON"]})
        assert spans == []

    def test_marked_format_offsets_from_source_text(self):
        # <PERSON>John Smith</PERSON> with source 'The witness John Smith said.'
        # source.find('John Smith') == 12, end == 12 + 10 == 22.
        p = _parser(LABELS_CONFIG)
        p._source_text = "The witness John Smith said."
        spans = p._parse_span_value("<PERSON>John Smith</PERSON>",
                                    {"labels": ["PERSON"]})
        assert len(spans) == 1
        assert spans[0]["start"] == 12
        assert spans[0]["end"] == 22
        assert spans[0]["text"] == "John Smith"
        assert spans[0]["labels"] == ["PERSON"]

    def test_marked_format_text_not_in_source_raises(self):
        # find() == -1 -> ValueError ("not found in source"). The `>= 0` guard
        # must be a strict failure path, not a silent span.
        p = _parser(LABELS_CONFIG)
        p._source_text = "Totally different source."
        with pytest.raises(ValueError, match="not found in source"):
            p._parse_span_value("<PERSON>Ada Lovelace</PERSON>",
                                {"labels": ["PERSON"]})

    def test_marked_format_without_source_text_raises(self):
        # No _source_text -> the else-branch raises a ValueError demanding
        # source_text. Pins the hasattr/truthiness guard.
        p = _parser(LABELS_CONFIG)
        p._source_text = None
        with pytest.raises(ValueError, match="requires source_text"):
            p._parse_span_value("<PERSON>Ada</PERSON>", {"labels": ["PERSON"]})

    def test_non_list_non_string_value_returns_empty(self):
        # An int falls through both isinstance branches -> [].
        p = _parser(LABELS_CONFIG)
        assert p._parse_span_value(42, {"labels": ["PERSON"]}) == []

    def test_marked_offset_at_string_start_is_zero(self):
        # Boundary: text at index 0 of source -> start 0 (>= 0 accepted, not >).
        p = _parser(LABELS_CONFIG)
        p._source_text = "Alice met Bob."
        spans = p._parse_span_value("<PERSON>Alice</PERSON>", {"labels": ["PERSON"]})
        assert spans[0]["start"] == 0
        assert spans[0]["end"] == 5


# ===========================================================================
# _normalize_span — required-field guards, label validation, key alternatives
# ===========================================================================

class TestNormalizeSpan:
    def test_valid_span_exact_fields(self):
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span(
            {"start": 2, "end": 7, "type": "PERSON", "text": "Alice"},
            ["PERSON"],
        )
        assert span["start"] == 2
        assert span["end"] == 7
        assert span["text"] == "Alice"
        assert span["labels"] == ["PERSON"]

    def test_missing_start_returns_none(self):
        # `if start is None or ...` -> None. Mutating the OR to AND would let
        # this through.
        p = _parser(LABELS_CONFIG)
        assert p._normalize_span({"end": 5, "type": "PERSON"}, []) is None

    def test_missing_end_returns_none(self):
        p = _parser(LABELS_CONFIG)
        assert p._normalize_span({"start": 0, "type": "PERSON"}, []) is None

    def test_missing_type_returns_none(self):
        p = _parser(LABELS_CONFIG)
        assert p._normalize_span({"start": 0, "end": 5}, []) is None

    def test_zero_start_is_not_treated_as_missing(self):
        # start == 0 is falsy but `is None` must be used, not truthiness.
        # A `not start` mutation would wrongly reject start=0.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": 0, "end": 5, "type": "PERSON"}, [])
        assert span is not None
        assert span["start"] == 0

    def test_invalid_label_filtered_when_available_labels_present(self):
        # `if available_labels and label_type not in available_labels` -> None.
        p = _parser(LABELS_CONFIG)
        assert p._normalize_span(
            {"start": 0, "end": 5, "type": "ALIEN"}, ["PERSON", "ORG"]
        ) is None

    def test_any_label_allowed_when_no_available_labels(self):
        # Empty available_labels short-circuits the validation -> span accepted.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": 0, "end": 5, "type": "WHATEVER"}, [])
        assert span is not None
        assert span["labels"] == ["WHATEVER"]

    def test_label_key_used_when_type_absent(self):
        # `item.get("type") or item.get("label")` — fall back to 'label'.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": 0, "end": 5, "label": "ORG"}, [])
        assert span["labels"] == ["ORG"]

    def test_string_label_wrapped_in_list(self):
        # `[label_type] if isinstance(label_type, str) else label_type`.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": 1, "end": 2, "type": "ORG"}, [])
        assert span["labels"] == ["ORG"]

    def test_provided_id_is_preserved(self):
        # `item.get("id") or f"span-..."` — a supplied id wins over a fresh one.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span(
            {"id": "fixed-id", "start": 0, "end": 1, "type": "ORG"}, []
        )
        assert span["id"] == "fixed-id"

    def test_text_defaults_to_empty_string(self):
        # `item.get("text", "")` default.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": 0, "end": 1, "type": "ORG"}, [])
        assert span["text"] == ""

    def test_start_end_coerced_to_int(self):
        # int(start)/int(end) — string offsets become ints.
        p = _parser(LABELS_CONFIG)
        span = p._normalize_span({"start": "3", "end": "8", "type": "ORG"}, [])
        assert span["start"] == 3
        assert span["end"] == 8
        assert isinstance(span["start"], int)


# The Grundprinzipien project's label config: two German answer fields beside
# the display-only case text.
GERMAN_QA_CONFIG = """<View>
  <Text name="fall" value="$fall"/>
  <Text name="task" value="$task"/>
  <TextArea name="kurzantwort" toName="task" rows="1"/>
  <TextArea name="begruendung" toName="task" rows="3"/>
</View>"""


def _fields(result):
    return {a["from_name"]: a["value"]["text"][0] for a in result.parsed_annotation}


class TestAnswerKeyMapping:
    """Kolibri-1 benchmark K9: answers following the prompt's English keys
    are read as the German schema fields."""

    def test_english_keys_map_to_the_german_fields(self):
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse('{"answer": "Ja", "reasoning": "§ 242 BGB, Verwirkung."}')
        assert r.status == "success"
        assert _fields(r) == {"kurzantwort": "Ja", "begruendung": "§ 242 BGB, Verwirkung."}
        assert r.mapped_keys == {"answer": "kurzantwort", "reasoning": "begruendung"}
        assert r.field_values == {
            "kurzantwort": "Ja",
            "begruendung": "§ 242 BGB, Verwirkung.",
        }

    def test_other_spellings_of_the_german_fields_are_not_mapped(self):
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse('{"Kurzantwort": "Nein", "begründung": "§ 311b BGB."}')
        assert r.mapped_keys == {}
        assert "kurzantwort" not in r.field_values
        assert "begruendung" not in r.field_values

    def test_english_keys_match_ignoring_case(self):
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse('{"Answer": "Ja", "REASONING": "Weil."}')
        assert _fields(r) == {"kurzantwort": "Ja", "begruendung": "Weil."}
        assert r.mapped_keys == {"Answer": "kurzantwort", "REASONING": "begruendung"}

    def test_exact_keys_are_not_reported_as_mapped(self):
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse('{"kurzantwort": "Ja", "begruendung": "Weil."}')
        assert _fields(r) == {"kurzantwort": "Ja", "begruendung": "Weil."}
        assert r.mapped_keys == {}

    def test_an_exact_field_wins_over_its_alias(self):
        # `target not in taken`: the German key is pre-taken, so the alias is
        # kept under its own name and dropped by the label-config filter.
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse(
            '{"reasoning": "englisch", "begruendung": "deutsch", "answer": "Nein",'
            ' "kurzantwort": "Ja"}'
        )
        assert _fields(r) == {"kurzantwort": "Ja", "begruendung": "deutsch"}
        assert r.mapped_keys == {}

    def test_first_of_two_alias_spellings_wins(self):
        p = _parser(GERMAN_QA_CONFIG)
        r = p.parse('{"answer": "Ja", "Reasoning": "erste", "reasoning": "zweite"}')
        assert _fields(r) == {"kurzantwort": "Ja", "begruendung": "erste"}
        assert r.mapped_keys == {"answer": "kurzantwort", "Reasoning": "begruendung"}

    def test_aliases_need_the_german_field_in_the_schema(self):
        # A schema with its own English fields reads them exactly.
        config = '<View><TextArea name="answer" toName="t"/><TextArea name="reasoning" toName="t"/></View>'
        p = _parser(config)
        r = p.parse('{"answer": "Ja", "reasoning": "Weil."}')
        assert _fields(r) == {"answer": "Ja", "reasoning": "Weil."}
        assert r.mapped_keys == {}

    def test_alias_ignored_when_its_target_is_not_a_field(self):
        # Only kurzantwort is a field: "reasoning" has no target and is dropped.
        config = '<View><TextArea name="kurzantwort" toName="t"/></View>'
        p = _parser(config)
        r = p.parse('{"answer": "Ja", "reasoning": "Weil."}')
        assert _fields(r) == {"kurzantwort": "Ja"}
        assert r.mapped_keys == {"answer": "kurzantwort"}

    def test_mapped_keys_are_validated_against_the_schema(self):
        # Mapping happens BEFORE schema validation: a required field supplied
        # under its alias passes.
        config = (
            '<View><TextArea name="kurzantwort" toName="t" required="true"/>'
            '<TextArea name="begruendung" toName="t"/></View>'
        )
        p = _parser(config)
        r = p.parse('{"answer": "Ja", "reasoning": "Weil."}')
        assert r.status == "success"
        assert _fields(r)["kurzantwort"] == "Ja"

    def test_generation_structure_fields_are_targets_too(self):
        p = ResponseParser(
            generation_structure={"fields": {"begruendung": {"type": "text"}}},
            label_config="",
        )
        mapped, keys = p._map_answer_keys({"reasoning": "Weil.", "other": 1})
        assert mapped == {"begruendung": "Weil.", "other": 1}
        assert keys == {"reasoning": "begruendung"}

    def test_non_dict_and_fieldless_input_pass_through(self):
        p = _parser(GERMAN_QA_CONFIG)
        assert p._map_answer_keys(["a"]) == (["a"], {})
        bare = ResponseParser(generation_structure={}, label_config="")
        assert bare._map_answer_keys({"answer": "Ja"}) == ({"answer": "Ja"}, {})

    def test_default_mapped_keys_is_an_empty_dict(self):
        assert ParseResult(status="failed").mapped_keys == {}


# ===========================================================================
# Kills for the parser paths added with per-item answers, answer-format
# options and the platform flags: prompt-structure lookup, multi-choice
# lists, JSON after prose, boolean choices, <Repeater> configs, answer keys
# from the structure's answer_schema, and the exact span/schema shapes.
# ===========================================================================

def _annotation(result):
    return {a["from_name"]: a["value"] for a in result.parsed_annotation}


class TestFindPromptStructure:
    def test_numeric_key_selects_the_entry_at_that_position(self):
        # `0 <= index` and `.get("structure", entry)`: position 0 is valid and
        # its inner structure (not the entry) is returned.
        config = {"prompt_structures": [{"structure": {"name": "first"}}]}
        assert find_prompt_structure(config, "0") == {"name": "first"}

    def test_position_past_the_end_is_none(self):
        # `index < len(structures)`: one entry, position 1 does not exist.
        config = {"prompt_structures": [{"structure": {"name": "first"}}]}
        assert find_prompt_structure(config, "1") is None

    def test_a_matching_key_with_an_empty_structure_stops_the_search(self):
        # `break`: the first entry with the key decides; a later entry with
        # the same key is not looked at.
        config = {
            "prompt_structures": [
                {"key": "a", "structure": {}},
                {"key": "a", "structure": {"name": "second"}},
            ]
        }
        assert find_prompt_structure(config, "a") is None


MULTI_CONFIG = """<View>
  <Text name="t" value="$t"/>
  <Choices name="tags" toName="t" choice="multiple">
    <Choice value="a"/><Choice value="b"/>
  </Choices>
  <Choices name="single" toName="t">
    <Choice value="x"/><Choice value="y"/>
  </Choices>
  <Choices toName="t" choice="multiple"><Choice value="z"/></Choices>
</View>"""


class TestMultiChoiceNames:
    def test_only_named_multi_choice_controls(self):
        # Pins the "name", "Choices" and `and` of the comprehension: the single
        # choice and the nameless multi choice are not listed.
        assert multi_choice_names(MULTI_CONFIG) == ["tags"]

    def test_no_config_and_bad_xml(self):
        assert multi_choice_names(None) == []
        assert multi_choice_names("") == []
        assert multi_choice_names("<View>") == []

    def test_multi_choice_answer_takes_a_list(self):
        # `name in self.label_config_map` keeps "tags" a multi-choice field,
        # so the schema takes a list of its values.
        r = _parser(MULTI_CONFIG).parse('{"tags": ["a", "b"], "single": "x"}')
        assert r.status == "success"
        assert _annotation(r) == {"tags": {"choices": ["a", "b"]}, "single": {"choices": ["x"]}}


class TestChoiceListSchema:
    def test_multi_choice_property_widened_exactly(self):
        p = _parser(MULTI_CONFIG)
        single = {"type": "string", "enum": ["a", "b"]}
        assert p._validation_schema == {
            "type": "object",
            "properties": {
                "tags": {"anyOf": [single, {"type": "array", "items": single}]},
                "single": {"type": "string", "enum": ["x", "y"]},
            },
        }
        # The widening copies: the plain schema keeps the single-value form.
        assert p.json_schema["properties"]["tags"] == single

    def test_schema_without_multi_choice_is_returned_as_is(self):
        p = _parser(CHOICES_CONFIG)
        assert p._validation_schema is p.json_schema
        assert p._with_choice_lists({}) == {}

    def test_list_item_outside_the_choices_is_rejected(self):
        p = _parser(MULTI_CONFIG)
        r = p._parse_decoded({"tags": ["a", "c"]})
        assert r.status == "validation_error"

    def test_flag_off_keeps_the_single_value_schema(self):
        p = ResponseParser({}, MULTI_CONFIG, variant_experiments=False)
        assert p._validation_schema is p.json_schema
        assert p._parse_decoded({"tags": ["a"]}).status == "validation_error"


class TestLastJsonValue:
    def test_object_after_prose_and_trailing_whitespace(self):
        assert last_json_value('Here is my answer: {"a": 1}  \n') == {"a": 1}
        assert last_json_value('{"a": 1}') == {"a": 1}
        assert last_json_value('List: [1, 2]') == [1, 2]

    def test_empty_and_non_json_endings(self):
        assert last_json_value("") is None
        assert last_json_value("   ") is None
        assert last_json_value("no json here") is None
        assert last_json_value('{"a": 1} trailing') is None

    def test_uppercase_x_in_prose_is_no_bracket(self):
        assert last_json_value('eXample {"a": 1}') == {"a": 1}

    def test_closed_bracket_pair_before_the_value(self):
        # "{ }" decodes but does not reach the end; depth returns to 0 at its
        # "}" (depth - 1, clamped at 0), so the final object is found.
        assert last_json_value('first { } then {"a": 1}') == {"a": 1}

    def test_unclosed_bracket_before_the_value_blocks_it(self):
        # Two opens and one close leave depth 1: the final object is nested in
        # an unclosed draft and is not promoted.
        assert last_json_value('draft {{ } {"a": 1}') is None
        assert last_json_value('draft {{ X } {"a": 1}') is None
        assert last_json_value('draft [[ ] {"a": 1}') is None

    def test_truncated_final_value(self):
        assert last_json_value('{"a": 1} {"b": ') is None
        assert last_json_value('x {"a": {"b": 1}') is None


class TestJsonAfterProse:
    def test_json_after_prose_answers_a_known_field(self):
        p = _parser(TEXTAREA_CONFIG)
        assert p.variant_experiments is True
        r = p.parse('My reply follows {"answer": "x"}')
        assert r.status == "success"
        assert r.parsed_annotation == [
            {"from_name": "answer", "type": "textarea", "value": {"text": ["x"]}}
        ]

    def test_json_after_prose_without_a_known_field_is_free_text(self):
        # Decodes and validates, but answers no field: the pattern fallback
        # reads the whole text (not a failed JSON parse, not an empty answer).
        text = 'Note: {"other": 1}'
        r = _parser(TEXTAREA_CONFIG).parse(text)
        assert r.status == "success"
        assert r.parsed_annotation == [
            {"from_name": "__response__", "type": "textarea", "value": {"text": [text]}}
        ]

    def test_flag_off_does_not_look_for_json_after_prose(self):
        text = 'My reply follows {"answer": "x"}'
        p = ResponseParser({}, TEXTAREA_CONFIG, variant_experiments=False)
        r = p.parse(text)
        assert r.status == "success"
        assert [a["from_name"] for a in r.parsed_annotation] == ["__response__"]

    def test_unexpected_error_in_json_parse(self):
        r = _parser(TEXTAREA_CONFIG)._try_json_parse(None)
        assert r.status == "failed"
        assert r.error.startswith("Unexpected error in JSON parsing: ")

    def test_pattern_match_failure(self):
        r = _parser(TEXTAREA_CONFIG)._try_pattern_match(None)
        assert r.status == "failed"
        assert r.error.startswith("Pattern matching failed: ")


BOOL_CONFIG = """<View>
  <Text name="t" value="$t"/>
  <TextArea name="note" toName="t"/>
  <Choices name="flag" toName="t"><Choice value="True"/><Choice value="False"/></Choices>
  <Choices name="flags" toName="t" choice="multiple">
    <Choice value="true"/><Choice value="false"/><Choice value="maybe"/>
  </Choices>
  <Choices name="empty" toName="t"/>
</View>"""


class TestBooleanChoices:
    def test_json_booleans_read_as_the_matching_choice(self):
        r = _parser(BOOL_CONFIG).parse(
            '{"note": "n", "flag": true, "flags": [false, "maybe"]}'
        )
        assert r.status == "success"
        assert _annotation(r) == {
            "note": {"text": ["n"]},
            "flag": {"choices": ["True"]},
            "flags": {"choices": ["false", "maybe"]},
        }

    def test_false_reads_as_false(self):
        p = _parser(BOOL_CONFIG)
        assert p._coerce_boolean_choices({"flag": False}) == {"flag": "False"}

    def test_non_choice_and_choiceless_fields_are_left_alone(self):
        p = _parser(BOOL_CONFIG)
        assert p._coerce_boolean_choices({"note": True, "empty": True, "x": True}) == {
            "note": True,
            "empty": True,
            "x": True,
        }

    def test_flag_off_does_not_coerce(self):
        p = ResponseParser({}, BOOL_CONFIG, variant_experiments=False)
        assert p._coerce_boolean_choices({"flag": True}) == {"flag": True}


class TestAnswerKeyExactFieldNotAliased:
    def test_a_field_named_like_an_alias_keeps_its_own_value(self):
        # `key not in fields and ...`: "answer" is itself a field here, so it
        # is not read as kurzantwort.
        config = (
            '<View><TextArea name="answer" toName="t"/>'
            '<TextArea name="kurzantwort" toName="t"/></View>'
        )
        r = _parser(config).parse('{"answer": "A"}')
        assert _annotation(r) == {"answer": {"text": ["A"]}}
        assert r.mapped_keys == {}


class _StubAnswerKeys:
    """Stands in for generation_fidelity.AnswerKeys."""

    def map_answer(self, parsed):
        data = {("answer" if k == "Antwort" else k): v for k, v in parsed.items()}
        return data, {"Antwort": "answer"}, {"answer": {"J": "Ja"}}


class TestStructureAnswerKeys:
    def test_answer_keys_rename_and_report(self):
        p = ResponseParser({}, TEXTAREA_CONFIG, answer_keys=_StubAnswerKeys())
        r = p.parse('{"Antwort": "Ja"}')
        assert r.status == "success"
        assert _annotation(r) == {"answer": {"text": ["Ja"]}}
        assert r.mapped_keys == {"Antwort": "answer"}
        assert r.mapped_values == {"answer": {"J": "Ja"}}

    def test_mapped_values_default_and_explicit(self):
        assert ParseResult(status="failed").mapped_values == {}
        assert ParseResult(status="success", mapped_values={"f": {"a": "b"}}).mapped_values == {
            "f": {"a": "b"}
        }


REPEATER_CONFIG = """<View>
  <Repeater on="$cases" indexFlag="{{idx}}" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}"/>
  </Repeater>
</View>"""

TWO_CASES = {"cases": [{"text": "a"}, {"text": "b"}]}


class TestRepeaterParsing:
    def test_array_answer_maps_onto_indexed_names(self):
        p = ResponseParser({}, REPEATER_CONFIG)
        r = p.parse('[{"case": 1, "risk": 10}, {"case": 2, "risk": 20}]', task_data=TWO_CASES)
        assert r.status == "success"
        assert r.parsed_annotation == [
            {"from_name": "risk_0", "type": "number", "value": {"number": 10}},
            {"from_name": "risk_1", "type": "number", "value": {"number": 20}},
        ]

    def test_without_task_data_the_parse_fails_with_the_reason(self):
        r = ResponseParser({}, REPEATER_CONFIG).parse('[{"case": 1, "risk": 10}]')
        assert r.status == "failed"
        assert r.error == "The label config has a <Repeater>; parsing needs the task's data"

    def test_wrong_item_count_is_a_validation_error(self):
        # The count comes from the task (2 items), not from the answer.
        r = ResponseParser({}, REPEATER_CONFIG).parse('[{"case": 1, "risk": 10}]', task_data=TWO_CASES)
        assert r.status == "validation_error"
        assert r.error == "'cases' has 1 objects, the task has 2 items"
        assert r.parsed_annotation is None

    def test_task_parsers_are_cached_per_item_count(self):
        p = ResponseParser({}, REPEATER_CONFIG)
        three = {"cases": [{}, {}, {}]}
        assert p._for_task(TWO_CASES) is p._for_task({"cases": [{"text": "c"}, {}]})
        assert p._for_task(three) is not p._for_task(TWO_CASES)
        assert set(p._task_parsers) == {(2,), (3,)}
        r = p.parse(json.dumps([{"risk": i} for i in range(3)]), task_data=three)
        assert [a["from_name"] for a in r.parsed_annotation] == ["risk_0", "risk_1", "risk_2"]

    def test_answer_controls(self):
        p = ResponseParser({}, REPEATER_CONFIG)
        assert p.answer_controls(TWO_CASES) == ["risk_0", "risk_1"]
        assert p.answer_controls() == []
        assert _parser(TEXTAREA_CONFIG).answer_controls(TWO_CASES) == ["answer"]


TWO_LABELS_CONFIG = """<View>
  <Text name="text" value="$text"/>
  <Labels name="ner1" toName="text"><Label value="PERSON"/></Labels>
  <Labels name="ner2" toName="text"><Label value="PERSON"/></Labels>
</View>"""

SPAN_ID = re.compile(r"span-[0-9a-f]{8}")


class TestLabelsAnswers:
    def test_object_answer_for_a_labels_field_is_not_rewrapped(self):
        r = _parser(LABELS_CONFIG).parse(
            '{"entities": [{"start": 0, "end": 3, "type": "ORG", "text": "Acm", "id": "s1"}]}'
        )
        assert r.status == "success"
        assert r.parsed_annotation == [
            {
                "from_name": "entities",
                "type": "labels",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 3, "text": "Acm", "labels": ["ORG"]}
                    ]
                },
            }
        ]

    def test_bare_list_goes_to_the_first_labels_field(self):
        r = _parser(TWO_LABELS_CONFIG).parse('[{"start": 0, "end": 3, "type": "PERSON"}]')
        assert r.status == "success"
        assert [a["from_name"] for a in r.parsed_annotation] == ["ner1"]

    def test_labels_span_schema_exactly(self):
        assert _parser(LABELS_CONFIG).json_schema == {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                            "text": {"type": "string"},
                            "type": {"type": "string", "enum": ["PERSON", "ORG"]},
                        },
                        "required": ["start", "end", "type"],
                    },
                }
            },
        }

    def test_generated_span_ids(self):
        p = _parser(LABELS_CONFIG)
        inline = p._parse_span_value("[ORG: 0-4] Acme", {"labels": ["ORG"]})
        assert SPAN_ID.fullmatch(inline[0]["id"])
        p._source_text = "Ann works at Acme."
        marked = p._parse_span_value("<ORG>Acme</ORG>", {"labels": ["ORG"]})
        assert SPAN_ID.fullmatch(marked[0]["id"])
        assert marked[0]["start"] == 13
        normalized = p._normalize_span({"start": 0, "end": 3, "type": "ORG"}, [])
        assert SPAN_ID.fullmatch(normalized["id"])

    def test_marked_label_outside_the_labels_is_dropped(self):
        p = _parser(LABELS_CONFIG)
        p._source_text = "Ann lives in Berlin."
        assert p._parse_span_value("<LOC>Berlin</LOC>", {"labels": ["PERSON", "ORG"]}) == []

    def test_marked_text_not_in_source_message(self):
        p = _parser(LABELS_CONFIG)
        p._source_text = "Ann lives in Berlin."
        with pytest.raises(ValueError) as exc:
            p._parse_span_value("<ORG>Acme</ORG>", {"labels": ["ORG"]})
        assert str(exc.value) == (
            "Span text 'Acme' not found in source text. "
            "Cannot calculate accurate position offsets."
        )

    def test_marked_without_source_text_message(self):
        p = _parser(LABELS_CONFIG)
        p._source_text = None
        with pytest.raises(ValueError) as exc:
            p._parse_span_value("<ORG>Acme</ORG>", {"labels": ["ORG"]})
        assert str(exc.value) == (
            "Marked format <ORG>Acme</ORG> requires source_text "
            "parameter to calculate accurate position offsets. "
            "Pass source_text to parse() method."
        )


class TestPatternMatchSources:
    def test_generation_structure_fields_without_label_config(self):
        p = ResponseParser({"fields": {"summary": {"type": "text"}}}, "")
        r = p._try_pattern_match("summary: hello")
        assert r.parsed_annotation == [
            {"from_name": "summary", "type": "textarea", "value": {"text": ["hello"]}}
        ]

    def test_generation_structure_types_win_over_label_config(self):
        # Number from the structure (float), not TextArea text from the config.
        p = ResponseParser({"fields": {"answer": {"type": "number"}}}, TEXTAREA_CONFIG)
        r = p._try_pattern_match("answer: 42")
        answer = r.field_values["answer"]
        assert isinstance(answer, float)
        assert answer == 42.0

    def test_label_config_choices_type_extracts_the_quoted_choice(self):
        r = _parser(CHOICES_CONFIG)._try_pattern_match("sentiment: I pick 'positive' here")
        assert r.parsed_annotation == [
            {"from_name": "sentiment", "type": "choices", "value": {"choices": ["positive"]}}
        ]

    def test_field_name_ignores_case_and_value_spans_lines(self):
        r = _parser(TEXTAREA_CONFIG)._try_pattern_match("Answer: first line\nsecond line")
        assert _annotation(r) == {"answer": {"text": ["first line second line"]}}

    def test_only_quotes_are_stripped_from_the_value(self):
        r = _parser(TEXTAREA_CONFIG)._try_pattern_match('answer: "Xylophone X"')
        assert _annotation(r) == {"answer": {"text": ["Xylophone X"]}}


class TestSchemaWithoutStructureFields:
    def test_structure_without_fields_uses_the_label_config(self):
        p = ResponseParser({"system_prompt": "x"}, TEXTAREA_CONFIG)
        assert p.json_schema == {"type": "object", "properties": {"answer": {"type": "string"}}}
