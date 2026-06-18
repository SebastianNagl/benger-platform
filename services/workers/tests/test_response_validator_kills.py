"""Mutation-grade kills for the validation layer in
``services/shared/ai_services/response_validator.py``.

This module extracts JSON out of a (possibly markdown-wrapped) LLM response
and validates it against a schema *before* a benchmark score is parsed out of
it. ``validate_response`` is **fail-closed**: it extracts JSON, parses it, and
schema-validates it; a malformed, missing, or schema-violating response is
reported as ``valid=False`` rather than rewritten. There is **no repair pass**.

Historical note (kept for context): an earlier version carried JSON-"repair"
machinery -- an orchestrator plus a set of naive regex/string fix helpers.
That code was **dead** -- ``extract_json_from_text`` only ever returns a
candidate that already ``json.loads``-es, so the repair branch was
unreachable -- and was removed. For an academic benchmark fail-closed is also
the correct posture: a malformed provider response is surfaced as a failure,
not silently corrected into data of uncertain provenance. The fail-closed
behaviour for a string that *would* have been "repairable" (e.g.
``{"score":5,}``) is pinned in ``TestValidateResponse`` and
``TestFailClosedOnceRepairableInput``: extraction returns None, so
``validate_response`` exits at the extraction step with ``valid=False`` /
``data=None``.

Import note: the module under test lives in the ``ai_services`` package whose
``__init__`` eagerly imports every provider SDK (openai, anthropic,
google.genai, ...). We file-import ``response_validator.py`` directly via
``importlib.util.spec_from_file_location`` to avoid that cascade -- mirrors
``tests/test_ai_service_metadata.py``. The module itself only depends on
``json``, ``re``, ``dataclasses``, ``typing``, and ``jsonschema``.
"""

from __future__ import annotations

import importlib.util
import json
import os

# --- Direct file-import of the module under test (no SDK cascade) ----------
_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_rv_path = os.path.join(
    _services_root, "shared", "ai_services", "response_validator.py"
)
_spec = importlib.util.spec_from_file_location(
    "_response_validator_kills", _rv_path
)
_rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rv)

ResponseValidator = _rv.ResponseValidator
ValidationResult = _rv.ValidationResult
validate_structured_response = _rv.validate_structured_response


def _v(strict: bool = True) -> "ResponseValidator":
    return ResponseValidator(strict=strict)


# ===========================================================================
# extract_json_from_text
# ===========================================================================
class TestExtractJsonFromText:
    def test_returns_pure_json_unchanged(self):
        """Whole-string ``json.loads`` is tried FIRST; pure JSON (after
        strip) is returned verbatim before any pattern runs."""
        assert _v().extract_json_from_text('{"a":1}') == '{"a":1}'

    def test_strips_surrounding_whitespace_for_pure_json(self):
        """Leading/trailing whitespace is stripped before the whole-string
        parse, so the padded input round-trips to the trimmed JSON."""
        assert _v().extract_json_from_text('   {"a":1}   ') == '{"a":1}'

    def test_pulls_object_out_of_prose(self):
        """Prose with one object: the greedy ``(\\{[\\s\\S]*\\})`` pattern
        captures the object and ``json.loads`` accepts it."""
        out = _v().extract_json_from_text('Result: {"score": 5} done')
        assert out == '{"score": 5}'
        assert json.loads(out) == {"score": 5}

    def test_prefers_json_fence_over_bare_braces(self):
        """The ```json fence pattern is FIRST in JSON_PATTERNS, so a
        fenced block wins over a stray bare object earlier in the prose."""
        text = 'prelude {"wrong":0}\n```json\n{"right":1}\n```'
        assert json.loads(_v().extract_json_from_text(text)) == {"right": 1}

    def test_extracts_from_generic_code_fence(self):
        """A plain ``` fence (no language tag) is matched by the second
        pattern."""
        out = _v().extract_json_from_text('```\n{"x": 1}\n```')
        assert json.loads(out) == {"x": 1}

    def test_greedy_span_captures_nested_object_whole(self):
        """Greediness: from FIRST ``{`` to LAST ``}`` -- a nested object in
        prose is captured whole (outer + inner), not just the inner one."""
        out = _v().extract_json_from_text('x {"outer": {"inner": 1}} y')
        assert json.loads(out) == {"outer": {"inner": 1}}

    def test_two_separate_objects_in_prose_fail_to_extract(self):
        """The greedy span over two sibling objects swallows the junk
        between them (``{"a":1} junk {"b":2}``), which doesn't parse, and no
        narrower pattern matches -> None. Pins that the extractor is
        greedy-span, not first-object."""
        assert _v().extract_json_from_text('{"a":1} junk {"b":2}') is None

    def test_extracts_array_from_prose(self):
        """When no object pattern matches, the array pattern pulls a bare
        list out of prose."""
        out = _v().extract_json_from_text('data: [1,2,3] end')
        assert json.loads(out) == [1, 2, 3]

    def test_no_json_returns_none(self):
        assert _v().extract_json_from_text('there is no json here') is None

    def test_empty_string_returns_none(self):
        assert _v().extract_json_from_text('') is None

    def test_none_input_returns_none(self):
        """Falsy guard ``if not text`` covers None too."""
        assert _v().extract_json_from_text(None) is None

    def test_malformed_object_is_not_returned_by_extractor(self):
        """LOAD-BEARING: the extractor only returns a candidate that
        ALREADY ``json.loads`` -- a trailing-comma object never survives
        extraction. This is why ``validate_response`` is fail-closed for a
        once-"repairable" input (see TestValidateResponse /
        TestFailClosedOnceRepairableInput)."""
        assert _v().extract_json_from_text('{"a":1,}') is None


# ===========================================================================
# validate_response -- top level
# ===========================================================================
_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}},
    "required": ["score"],
}


class TestValidateResponse:
    def test_valid_json_passes(self):
        res = _v().validate_response('{"score": 5}', _SCHEMA)
        assert isinstance(res, ValidationResult)
        assert res.valid is True
        assert res.data == {"score": 5}
        assert res.extracted_json == '{"score": 5}'
        assert res.errors == []

    def test_valid_json_embedded_in_prose_passes(self):
        res = _v().validate_response('Here you go: {"score": 8}', _SCHEMA)
        assert res.valid is True
        assert res.data == {"score": 8}

    def test_schema_violation_returns_data_but_not_valid(self):
        """A string where the schema demands an integer: valid=False but
        ``data`` is still populated with the parsed object, and an error
        names the offending path."""
        res = _v().validate_response('{"score": "high"}', _SCHEMA)
        assert res.valid is False
        assert res.data == {"score": "high"}
        assert any("score" in e for e in res.errors)

    def test_missing_required_field_fails_schema(self):
        res = _v().validate_response('{"other": 1}', _SCHEMA)
        assert res.valid is False
        assert res.data == {"other": 1}
        assert any("required" in e.lower() or "score" in e for e in res.errors)

    def test_no_extractable_json_returns_clean_failure(self):
        res = _v().validate_response('absolutely no json', _SCHEMA)
        assert res.valid is False
        assert res.data is None
        assert res.extracted_json is None
        assert res.errors == ["Could not extract JSON from response"]

    def test_strict_flag_is_stored_on_constructor(self):
        """The constructor records strict; pin both states. (Current schema
        path uses Draft7Validator the same way for both, but the flag is the
        documented knob and its storage must not silently break.)"""
        assert _v(strict=True).strict is True
        assert _v(strict=False).strict is False


# ===========================================================================
# Fail-closed behaviour for a malformed-but-once-"repairable" input.
#
# A trailing-comma object (``{"score":5,}``) is the canonical "trivially
# repairable in principle" case. validate_response does NOT repair it: the
# extractor only returns candidates that already json.loads, so extraction
# returns None and validate_response exits at the extraction step with
# valid=False / data=None. This is the fail-closed contract -- pinned without
# reference to any (removed) repair machinery.
# ===========================================================================
class TestFailClosedOnceRepairableInput:
    def test_trailing_comma_object_fails_closed(self):
        res = _v().validate_response('{"score": 5,}', _SCHEMA)
        assert res.valid is False
        assert res.data is None
        assert res.extracted_json is None
        assert res.errors == ["Could not extract JSON from response"]

    def test_unquoted_key_fails_closed(self):
        """``{score: 5}`` (bare key) is also not returned by the extractor
        -> fail-closed, not silently fixed."""
        res = _v().validate_response('{score: 5}', _SCHEMA)
        assert res.valid is False
        assert res.data is None
        assert res.extracted_json is None

    def test_single_quoted_object_fails_closed(self):
        """``{'score': 5}`` is invalid JSON; not extracted -> fail-closed."""
        res = _v().validate_response("{'score': 5}", _SCHEMA)
        assert res.valid is False
        assert res.data is None
        assert res.extracted_json is None

    def test_unclosed_object_fails_closed(self):
        """``{"score": 5`` (missing closer) is not extractable -> fail-closed."""
        res = _v().validate_response('{"score": 5', _SCHEMA)
        assert res.valid is False
        assert res.data is None
        assert res.extracted_json is None


# ===========================================================================
# _validate_against_schema
# ===========================================================================
class TestValidateAgainstSchema:
    def test_valid_data_yields_no_errors(self):
        errs = _v()._validate_against_schema({"score": 1}, _SCHEMA)
        assert errs == []

    def test_type_violation_yields_pathed_error(self):
        errs = _v()._validate_against_schema({"score": "x"}, _SCHEMA)
        assert len(errs) == 1
        assert errs[0].startswith("Schema error at score:")

    def test_missing_required_uses_root_path(self):
        """A missing required key has an empty error.path, so the helper
        labels it ``root``."""
        errs = _v()._validate_against_schema({}, _SCHEMA)
        assert len(errs) == 1
        assert "root" in errs[0]

    def test_malformed_schema_is_caught_and_reported(self):
        """A schema that itself blows up Draft7Validator is caught by the
        broad except and surfaced as a 'Schema validation error' string
        rather than raising."""
        bad_schema = {"type": "not-a-real-type"}
        errs = _v()._validate_against_schema({"a": 1}, bad_schema)
        assert len(errs) == 1
        assert "Schema validation error" in errs[0] or "Schema error" in errs[0]


# ===========================================================================
# validate_structured_response  (module-level convenience fn)
# ===========================================================================
class TestValidateStructuredResponse:
    def test_returns_tuple_for_valid_input(self):
        ok, data, errs = validate_structured_response(
            '{"score": 9}', _SCHEMA, "google"
        )
        assert ok is True
        assert data == {"score": 9}
        assert errs == []

    def test_returns_failure_tuple_for_no_json(self):
        ok, data, errs = validate_structured_response(
            'nope', _SCHEMA, "google"
        )
        assert ok is False
        assert data is None
        assert errs == ["Could not extract JSON from response"]

    def test_schema_violation_tuple_carries_data(self):
        """Mirrors validate_response: invalid but data present."""
        ok, data, errs = validate_structured_response(
            '{"score": "x"}', _SCHEMA, "google"
        )
        assert ok is False
        assert data == {"score": "x"}
        assert errs and any("score" in e for e in errs)

    def test_strict_flag_is_forwarded(self):
        """strict=False is passed through to the constructor; happy path
        still validates."""
        ok, data, errs = validate_structured_response(
            '{"score": 2}', _SCHEMA, "google", strict=False
        )
        assert ok is True
        assert data == {"score": 2}


# ===========================================================================
# End-to-end guard: a VALID response -- even one whose string values contain
# commas/braces/apostrophes/colons -- parses on the FIRST json.loads try (via
# extract_json_from_text) and is returned unchanged. There is no _fix_* helper
# to fool: validate_response never rewrites a response. These pin that a valid
# response carrying "dangerous" punctuation in string values survives intact.
# ===========================================================================
class TestEndToEndNeverCorruptsValidJson:
    _OPEN_SCHEMA = {"type": "object"}

    def _check_unchanged(self, raw):
        res = _v().validate_response(raw, self._OPEN_SCHEMA)
        assert res.valid is True, res.errors
        assert res.data == json.loads(raw)
        assert res.extracted_json == raw

    def test_value_with_comma_and_brace_survives(self):
        """``{"a":"x,}"}`` has the literal substring ``,}`` inside a string
        value, but it is valid JSON -> parses first try, returned untouched."""
        self._check_unchanged('{"a":"x,}"}')

    def test_value_with_apostrophe_survives(self):
        """``{"a":"it's"}`` is valid JSON -> the apostrophe is preserved."""
        self._check_unchanged('{"a":"it\'s"}')

    def test_value_with_space_word_colon_survives(self):
        """``{"a":"x y:z"}`` parses first try and is returned with its
        meaning intact."""
        self._check_unchanged('{"a":"x y:z"}')

    def test_value_with_url_colon_survives(self):
        self._check_unchanged('{"url":"http://example.com/a,b"}')

    def test_value_with_escaped_quote_survives(self):
        """``{"a":"x\\"y"}`` (value ``x"y``) is valid and returned unchanged."""
        self._check_unchanged('{"a":"x\\"y"}')
