"""Property-based tests for response_parser.ResponseParser (hypothesis).

The headline invariant is the classic parser fuzz: parse(text) must return a
ParseResult and NEVER raise for arbitrary input (control chars, broken JSON,
huge whitespace, unicode). That single property kills the most mutants, because
any operator/boundary mutant that makes the parser throw on some input gets
caught regardless of the exact output value.

Invariants covered:
  * robustness/fuzz: parse(arbitrary text) returns a ParseResult with a valid
    status and never raises (for textarea, choices, number, and labels/NER
    configs).
  * determinism: same input => same status (and same field_values).
  * status domain: status is always one of the three documented values.
  * span invariants: every extracted NER span has start <= end and offsets
    within len(source_text) when source_text is provided.
  * round-trip: a valid JSON dict for a textarea field round-trips so the field
    value is recovered in field_values (extract ∘ transform == identity on the
    value).
"""

import json
import os
import sys

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from response_parser import ParseResult, ResponseParser  # noqa: E402

_VALID_STATUSES = {"success", "failed", "validation_error"}

TEXTAREA_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <TextArea name="answer" toName="text"/>
</View>
"""

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

NUMBER_CONFIG = """
<View>
    <Text name="text" value="$text"/>
    <Number name="score" toName="text"/>
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


def _make_parser(label_config, fields=None):
    structure = {"fields": fields} if fields else {}
    return ResponseParser(generation_structure=structure, label_config=label_config)


# Free-form text including control chars, unicode, and broken-JSON-looking
# strings. This is the fuzz corpus.
_arbitrary_text = st.text(
    alphabet=st.characters(min_codepoint=0, max_codepoint=0x10FFFF),
    max_size=400,
)

# A grab-bag of JSON-ish fragments to stress the JSON branch specifically.
_jsonish = st.one_of(
    _arbitrary_text,
    st.builds(lambda d: json.dumps(d), st.dictionaries(st.text(max_size=8), st.integers(), max_size=5)),
    st.sampled_from(
        [
            "{",
            "}",
            "[",
            "]",
            "{\"a\":}",
            "```json\n{bad}\n```",
            "```\n[1,2,3]\n```",
            "null",
            "true",
            "[]",
            "{}",
            "   \n\t   ",
            "answer: hello",
            "answer = world",
            '{"answer": "ja"}',
            "<PERSON>John</PERSON>",
            "[PERSON: 0-4] John",
        ]
    ),
)

_settings = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class TestFuzzNeverRaises:
    """The key invariant: parse never raises and always returns a ParseResult."""

    @_settings
    @given(text=_jsonish)
    def test_textarea_config_never_raises(self, text):
        parser = _make_parser(TEXTAREA_CONFIG)
        result = parser.parse(text)
        assert isinstance(result, ParseResult)
        assert result.status in _VALID_STATUSES

    @_settings
    @given(text=_jsonish)
    def test_choices_config_never_raises(self, text):
        parser = _make_parser(CHOICES_CONFIG)
        result = parser.parse(text)
        assert isinstance(result, ParseResult)
        assert result.status in _VALID_STATUSES

    @_settings
    @given(text=_jsonish)
    def test_number_config_never_raises(self, text):
        parser = _make_parser(NUMBER_CONFIG)
        result = parser.parse(text)
        assert isinstance(result, ParseResult)
        assert result.status in _VALID_STATUSES

    @_settings
    @given(text=_jsonish, source=st.text(max_size=200))
    def test_labels_config_never_raises(self, text, source):
        # NER/labels config exercises the span-parsing path; with a source_text
        # the marked/inline span branches run. Must never raise.
        parser = _make_parser(LABELS_CONFIG)
        result = parser.parse(text, source_text=source)
        assert isinstance(result, ParseResult)
        assert result.status in _VALID_STATUSES

    @_settings
    @given(text=_arbitrary_text)
    def test_empty_structure_config_never_raises(self, text):
        # No label_config at all — degenerate but must still parse safely.
        parser = ResponseParser(generation_structure={}, label_config="")
        result = parser.parse(text)
        assert isinstance(result, ParseResult)
        assert result.status in _VALID_STATUSES


class TestDeterminism:
    @_settings
    @given(text=_jsonish)
    def test_same_input_same_status(self, text):
        parser = _make_parser(TEXTAREA_CONFIG)
        a = parser.parse(text)
        b = parser.parse(text)
        assert a.status == b.status
        assert a.field_values == b.field_values


class TestSpanInvariants:
    @_settings
    @given(
        prefix=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=40),
        entity=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12),
        suffix=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=40),
    )
    def test_extracted_spans_have_valid_offsets(self, prefix, entity, suffix):
        # Build a JSON span array; positions must satisfy start <= end and be
        # within the source text length once parsed/normalized.
        source = f"{prefix}{entity}{suffix}"
        start = len(prefix)
        end = start + len(entity)
        response = json.dumps(
            {"entities": [{"start": start, "end": end, "text": entity, "type": "PERSON"}]}
        )
        parser = _make_parser(LABELS_CONFIG)
        result = parser.parse(response, source_text=source)
        assert isinstance(result, ParseResult)
        if result.status == "success" and result.parsed_annotation:
            for ann in result.parsed_annotation:
                for span in ann.get("value", {}).get("spans", []):
                    s, e = span["start"], span["end"]
                    assert s <= e
                    assert 0 <= s <= len(source)
                    assert 0 <= e <= len(source)

    @_settings
    @given(
        spans=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=50),
                st.integers(min_value=0, max_value=50),
            ),
            min_size=1,
            max_size=6,
        )
    )
    def test_json_span_offsets_preserve_ordering(self, spans):
        # Spans supplied as JSON with start <= end stay start <= end after parse.
        normalized = [{"start": min(a, b), "end": max(a, b), "type": "ORG"} for a, b in spans]
        response = json.dumps({"entities": normalized})
        parser = _make_parser(LABELS_CONFIG)
        result = parser.parse(response)
        assert isinstance(result, ParseResult)
        if result.status == "success" and result.parsed_annotation:
            for ann in result.parsed_annotation:
                for span in ann.get("value", {}).get("spans", []):
                    assert span["start"] <= span["end"]


class TestRoundTrip:
    @_settings
    @given(
        value=st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=1,
            max_size=60,
        ).filter(lambda s: s.strip() != "")
    )
    def test_textarea_value_round_trips(self, value):
        # A valid JSON dict for the answer field should transform to LS format
        # then be recovered in field_values: extract ∘ transform == identity on
        # the value. The parser collapses internal whitespace runs for the
        # pattern path, but the JSON path keeps the value intact.
        parser = _make_parser(TEXTAREA_CONFIG)
        response = json.dumps({"answer": value})
        result = parser.parse(response)
        assert result.status == "success"
        assert result.field_values.get("answer") == value

    @_settings
    @given(choice=st.sampled_from(["positive", "negative", "neutral"]))
    def test_choices_value_round_trips(self, choice):
        parser = _make_parser(CHOICES_CONFIG)
        response = json.dumps({"sentiment": choice})
        result = parser.parse(response)
        assert result.status == "success"
        assert result.field_values.get("sentiment") == choice
