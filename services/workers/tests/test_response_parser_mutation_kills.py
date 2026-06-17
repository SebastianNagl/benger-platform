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

import os
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

from response_parser import ParseResult, ResponseParser  # noqa: E402


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
