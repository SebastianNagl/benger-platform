"""Mutation-grade kills for the JSON-repair + validation layer in
``services/shared/ai_services/response_validator.py``.

This module repairs malformed LLM JSON *before* a benchmark score is parsed
out of it. A repair that corrupts VALID JSON, or mis-fixes malformed JSON,
silently produces wrong parsed data -> a wrong benchmark score. The whole
file had no dedicated test; this file pins every repair helper, the
extractor, the orchestrator, and the two public entry points.

The most load-bearing assertions are the ANTI-CORRUPTION ones: each naive
``_fix_*`` helper, applied to already-valid JSON, must (where it is honest
about its own limitations) leave the parsed meaning unchanged. Several of
the helpers are deliberately naive regex/string rewrites; where they DO
over-match valid JSON we pin the *actual* observed behaviour and document
in the docstring that (a) it is a known limitation of the isolated helper
and (b) why it is end-to-end-safe (see ``TestEndToEndNeverCorruptsValidJson``):
the helpers are private and only ever invoked via ``attempt_repair``, which
is only ever invoked on a string that already FAILED ``json.loads``. Valid
JSON is therefore never fed to a ``_fix_*`` helper in production.

Import note: the helpers under test live in the ``ai_services`` package
whose ``__init__`` eagerly imports every provider SDK (openai, anthropic,
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
RepairResult = _rv.RepairResult
validate_structured_response = _rv.validate_structured_response


def _v(strict: bool = True) -> "ResponseValidator":
    return ResponseValidator(strict=strict)


# ===========================================================================
# _fix_trailing_commas  (line 267)
#   re.sub(r',\s*}', '}', s) then re.sub(r',\s*]', ']', s)
# ===========================================================================
class TestFixTrailingCommas:
    def test_removes_trailing_comma_before_brace(self):
        """MUST-fix: object trailing comma. ``{"a":1,}`` is invalid JSON;
        the helper strips the ``,`` before ``}`` so the result parses."""
        out = _v()._fix_trailing_commas('{"a":1,}')
        assert out == '{"a":1}'
        assert json.loads(out) == {"a": 1}

    def test_removes_trailing_comma_before_bracket(self):
        """MUST-fix: array trailing comma ``[1,2,]`` -> ``[1,2]``."""
        out = _v()._fix_trailing_commas("[1,2,]")
        assert out == "[1,2]"
        assert json.loads(out) == [1, 2]

    def test_removes_trailing_comma_with_whitespace(self):
        r"""``\s*`` in the pattern means whitespace/newlines between the
        comma and the closer are also consumed (pretty-printed trailing
        comma)."""
        out = _v()._fix_trailing_commas('{"a":1 ,\n  }')
        assert json.loads(out) == {"a": 1}

    def test_does_not_remove_legitimate_separator_comma(self):
        """ANTI-CORRUPTION: a comma that separates two members is NOT
        followed by a closer, so the pattern ``,\\s*}`` cannot match it.
        Valid two-key object must be byte-identical out."""
        src = '{"a":1, "b":2}'
        out = _v()._fix_trailing_commas(src)
        assert out == src
        assert json.loads(out) == {"a": 1, "b": 2}

    def test_does_not_touch_plain_comma_inside_string_value(self):
        """ANTI-CORRUPTION: a comma inside a string value (``"hello,
        world"``) is not followed by a closer, so it is untouched -- the
        common, safe case."""
        src = '{"a":"hello, world"}'
        out = _v()._fix_trailing_commas(src)
        assert out == src
        assert json.loads(out) == {"a": "hello, world"}

    def test_comma_then_brace_inside_string_is_a_known_helper_limitation(self):
        r"""TRICKY / known naive-regex limitation. The VALID input
        ``{"a":"x,}"}`` has the literal substring ``,}`` *inside* the
        string value ``"x,}"``. The regex ``,\s*}`` is string-blind, so it
        rewrites that to ``}``, producing ``{"a":"x}"}`` whose value is now
        ``"x}"`` -- a corruption of valid JSON IN ISOLATION.

        We pin the actual behaviour (not the ideal one) so a mutation that
        flips the regex is still caught, and document that this is harmless
        end-to-end: ``_fix_trailing_commas`` is only reached from
        ``attempt_repair``, which is only called after ``json.loads`` has
        already failed -- valid JSON never enters here. See
        ``TestEndToEndNeverCorruptsValidJson``.
        """
        src = '{"a":"x,}"}'
        assert json.loads(src) == {"a": "x,}"}  # source is valid
        out = _v()._fix_trailing_commas(src)
        assert out == '{"a":"x}"}'  # naive over-match
        assert json.loads(out) == {"a": "x}"}  # meaning changed in isolation


# ===========================================================================
# _fix_unquoted_keys  (line 275)
#   re.sub(r'(?<=[{,\s])(\w+)(?=\s*:)', r'"\1"', s)
# ===========================================================================
class TestFixUnquotedKeys:
    def test_quotes_a_bare_key(self):
        """MUST-fix: ``{a:1}`` -> ``{"a":1}``. The key ``a`` is preceded by
        ``{`` (lookbehind) and followed by ``:`` (lookahead)."""
        out = _v()._fix_unquoted_keys("{a:1}")
        assert out == '{"a":1}'
        assert json.loads(out) == {"a": 1}

    def test_quotes_multiple_bare_keys(self):
        """Second key ``b`` is preceded by the space after the comma, which
        the ``\\s`` arm of the lookbehind matches."""
        out = _v()._fix_unquoted_keys("{a:1, b:2}")
        assert out == '{"a":1, "b":2}'
        assert json.loads(out) == {"a": 1, "b": 2}

    def test_does_not_double_quote_an_already_quoted_key(self):
        """ANTI-CORRUPTION: an already-quoted key ``"a"`` -- the inner word
        ``a`` is preceded by ``"`` (not in ``[{,\\s]``), so the lookbehind
        fails and nothing is added. Valid input stays byte-identical."""
        src = '{"a":1}'
        out = _v()._fix_unquoted_keys(src)
        assert out == src
        assert json.loads(out) == {"a": 1}

    def test_does_not_quote_colon_inside_url_string_value(self):
        """ANTI-CORRUPTION (the named danger): a ``://`` inside a string
        value. ``url`` is preceded by ``"`` so it is not a key; the ``http``
        before ``://`` is preceded by ``"`` too -> no match. Untouched."""
        src = '{"url":"http://example.com"}'
        out = _v()._fix_unquoted_keys(src)
        assert out == src
        assert json.loads(out) == {"url": "http://example.com"}

    def test_does_not_quote_word_colon_inside_string_value(self):
        """ANTI-CORRUPTION: ``{"a":"key:val"}`` -- ``key`` is preceded by
        ``"``, so the lookbehind fails and the string value is untouched."""
        src = '{"a":"key:val"}'
        out = _v()._fix_unquoted_keys(src)
        assert out == src
        assert json.loads(out) == {"a": "key:val"}

    def test_space_word_colon_inside_string_is_a_known_helper_limitation(self):
        r"""TRICKY / known naive-regex limitation. In the VALID input
        ``{"a":"x y:z"}`` the substring ``y:`` sits inside the string value,
        preceded by a space. The ``\s`` arm of the lookbehind matches that
        space and the lookahead matches ``:``, so ``y`` gets wrapped:
        ``{"a":"x "y":z"}`` -- now INVALID JSON.

        Pinned as actual behaviour + documented as a helper-in-isolation
        limitation that is end-to-end-safe (valid JSON never reaches here)."""
        src = '{"a":"x y:z"}'
        assert json.loads(src) == {"a": "x y:z"}  # source valid
        out = _v()._fix_unquoted_keys(src)
        assert out == '{"a":"x "y":z"}'  # naive over-match
        # And the over-matched result no longer parses:
        try:
            json.loads(out)
            raise AssertionError("expected corrupted output to be invalid")
        except json.JSONDecodeError:
            pass


# ===========================================================================
# _fix_single_quotes  (line 281)
#   s.replace("'", '"')
# ===========================================================================
class TestFixSingleQuotes:
    def test_converts_single_quoted_object(self):
        """MUST-fix: ``{'a':'b'}`` -> ``{"a":"b"}``."""
        out = _v()._fix_single_quotes("{'a':'b'}")
        assert out == '{"a":"b"}'
        assert json.loads(out) == {"a": "b"}

    def test_double_quoted_input_without_apostrophes_is_unchanged(self):
        """ANTI-CORRUPTION: valid JSON with no apostrophes contains no
        ``'`` to replace, so it is byte-identical out."""
        src = '{"a":"b","c":1}'
        out = _v()._fix_single_quotes(src)
        assert out == src
        assert json.loads(out) == {"a": "b", "c": 1}

    def test_apostrophe_in_value_is_the_named_danger_and_is_corrupted(self):
        r"""TRICKY / the explicitly-named dangerous case. The VALID input
        ``{"a":"it's"}`` carries an apostrophe inside the string value.
        The blind ``replace("'", '"')`` turns it into ``{"a":"it"s"}``,
        which is now INVALID JSON (the apostrophe became a closing quote).

        This is the canonical reason ``_fix_single_quotes`` must never be
        run on valid JSON. Pinned as actual behaviour; documented as
        end-to-end-safe because the helper only runs after ``json.loads``
        has already failed on the (malformed) string."""
        src = '{"a":"it\'s"}'
        assert json.loads(src) == {"a": "it's"}  # source valid
        out = _v()._fix_single_quotes(src)
        assert out == '{"a":"it"s"}'  # apostrophe became a quote
        try:
            json.loads(out)
            raise AssertionError("expected corrupted output to be invalid")
        except json.JSONDecodeError:
            pass


# ===========================================================================
# _fix_newlines_in_strings  (line 287)
#   stateful scanner: escapes \n \r \t only while inside a "..." string
# ===========================================================================
class TestFixNewlinesInStrings:
    def test_escapes_literal_newline_inside_string_value(self):
        r"""MUST-fix: a literal newline inside a string value is an invalid
        control char in JSON. ``{"a":"line1<LF>line2"}`` -> the scanner is
        ``in_string`` at the LF and emits the two chars ``\n`` so the
        result is ``{"a":"line1\nline2"}`` which parses to the string
        ``line1\nline2``."""
        src = '{"a":"line1\nline2"}'
        # Source has a raw control char -> invalid JSON:
        try:
            json.loads(src)
            raise AssertionError("source should be invalid (raw newline)")
        except json.JSONDecodeError:
            pass
        out = _v()._fix_newlines_in_strings(src)
        assert out == '{"a":"line1\\nline2"}'
        assert json.loads(out) == {"a": "line1\nline2"}

    def test_escapes_literal_tab_and_cr_inside_string(self):
        r"""MUST-fix companions: raw tab -> ``\t`` and raw CR -> ``\r``."""
        out = _v()._fix_newlines_in_strings('{"a":"x\ty\rz"}')
        assert out == '{"a":"x\\ty\\rz"}'
        assert json.loads(out) == {"a": "x\ty\rz"}

    def test_does_not_touch_newlines_between_tokens(self):
        """ANTI-CORRUPTION: a pretty-printed object's newlines sit OUTSIDE
        any string (``in_string`` is False there), so they are emitted
        verbatim. The structural newlines survive untouched."""
        src = '{\n  "a": 1\n}'
        out = _v()._fix_newlines_in_strings(src)
        assert out == src
        assert json.loads(out) == {"a": 1}

    def test_does_not_re_escape_an_already_escaped_newline(self):
        r"""ANTI-CORRUPTION: an already-escaped ``\n`` is two chars
        ``\`` + ``n``. The scanner sees ``\``, sets ``escape_next``, and
        passes the ``n`` through untouched -- it does NOT double-escape.
        Valid input stays byte-identical and keeps its meaning."""
        src = '{"a":"line1\\nline2"}'
        assert json.loads(src) == {"a": "line1\nline2"}
        out = _v()._fix_newlines_in_strings(src)
        assert out == src
        assert json.loads(out) == {"a": "line1\nline2"}


# ===========================================================================
# _fix_missing_closing  (line 321)
#   append '}'*(open{-close}) then ']'*(open[-close])
# ===========================================================================
class TestFixMissingClosing:
    def test_closes_a_single_unclosed_object(self):
        """MUST-fix: ``{"a":1`` has 1 ``{`` and 0 ``}`` -> append one ``}``
        giving ``{"a":1}``."""
        out = _v()._fix_missing_closing('{"a":1')
        assert out == '{"a":1}'
        assert json.loads(out) == {"a": 1}

    def test_does_not_over_close_already_balanced_json(self):
        """ANTI-CORRUPTION: balanced ``{"a":1}`` has equal counts -> append
        zero braces. Byte-identical out, never over-closed."""
        src = '{"a":1}'
        out = _v()._fix_missing_closing(src)
        assert out == src
        assert json.loads(out) == {"a": 1}

    def test_balanced_array_is_untouched(self):
        """ANTI-CORRUPTION: ``[1,2]`` balanced -> unchanged."""
        src = "[1,2]"
        out = _v()._fix_missing_closing(src)
        assert out == src
        assert json.loads(out) == [1, 2]

    def test_extra_closer_yields_negative_count_and_appends_nothing(self):
        """TRICKY (no over-close on negatives): valid ``{"a":"}"}`` counts
        the ``}`` inside the string too -> 1 open, 2 close. ``'}' * (1-2)``
        is ``'}' * -1 == ''`` in Python, so nothing is appended and the
        already-valid string is returned byte-identical. Pins that a
        negative multiplier can't corrupt valid input."""
        src = '{"a":"}"}'
        assert json.loads(src) == {"a": "}"}
        out = _v()._fix_missing_closing(src)
        assert out == src
        assert json.loads(out) == {"a": "}"}

    def test_nested_array_in_object_appends_in_wrong_order(self):
        """TRICKY / known ordering limitation. ``{"a":[1,2`` is missing one
        ``]`` then one ``}``. The helper appends ALL ``}`` FIRST, then ALL
        ``]`` -> ``{"a":[1,2}]`` which is still INVALID (closers in the
        wrong order). Pinned so a mutation that 'accidentally fixes' the
        order is still observable; documents that this nested-missing-close
        case is NOT actually repaired by this helper."""
        out = _v()._fix_missing_closing('{"a":[1,2')
        assert out == '{"a":[1,2}]'
        try:
            json.loads(out)
            raise AssertionError("nested wrong-order close should not parse")
        except json.JSONDecodeError:
            pass


# ===========================================================================
# _fix_escape_sequences  (line 334)
#   re.sub(r'(?<!\\)\\(?!")', r'\\\\', s)
#   -> double any backslash that is NOT preceded by '\' and NOT followed by '"'
# ===========================================================================
class TestFixEscapeSequences:
    def test_doubles_a_lone_invalid_escape_backslash(self):
        r"""MUST-fix: ``{"a":"50\% done"}`` -- ``\%`` is an invalid JSON
        escape. The lone ``\`` is not preceded by ``\`` and not followed by
        ``"``, so it is doubled to ``\\`` giving ``{"a":"50\\% done"}``,
        which parses to the literal string ``50\% done``."""
        src = '{"a":"50\\% done"}'  # python str: 50<backslash>% done
        # invalid because \% is not a legal JSON escape
        try:
            json.loads(src)
            raise AssertionError("source should be invalid (\\% escape)")
        except json.JSONDecodeError:
            pass
        out = _v()._fix_escape_sequences(src)
        assert out == '{"a":"50\\\\% done"}'
        assert json.loads(out) == {"a": "50\\% done"}

    def test_does_not_touch_an_escaped_quote(self):
        r"""ANTI-CORRUPTION: ``\"`` is excluded by the negative lookahead
        ``(?!")``. Valid ``{"a":"x\"y"}`` (value ``x"y``) is left
        byte-identical and keeps its meaning -- the escaped quote that makes
        the JSON valid is NOT mangled."""
        src = '{"a":"x\\"y"}'
        assert json.loads(src) == {"a": 'x"y'}
        out = _v()._fix_escape_sequences(src)
        assert out == src
        assert json.loads(out) == {"a": 'x"y'}

    def test_does_not_touch_an_already_doubled_backslash_pair(self):
        r"""ANTI-CORRUPTION: in ``\\`` the second ``\`` IS preceded by a
        ``\`` (lookbehind fails) and the first ``\`` is followed by ``\``
        (not ``"``) but... the regex matches non-overlapping left-to-right:
        the first ``\`` matches ``(?<!\\)\\(?!")`` ONLY if the char before
        it isn't ``\`` -- here it isn't, and the char after is ``\`` not
        ``"`` -> the FIRST backslash of the pair IS matched and doubled.

        So the helper does NOT preserve a literal ``\\``; it expands
        ``{"a":"x\\y"}`` (value ``x\y``) to three backslashes
        ``{"a":"x\\\y"}`` which is INVALID. Pinned as actual behaviour:
        this helper is only sound for the lone-invalid-escape case and is
        end-to-end-safe because it only ever runs on already-malformed
        input."""
        src = '{"a":"x\\\\y"}'  # value is x<backslash>y, source is valid
        assert json.loads(src) == {"a": "x\\y"}
        out = _v()._fix_escape_sequences(src)
        assert out == '{"a":"x\\\\\\y"}'
        try:
            json.loads(out)
            raise AssertionError("over-doubled backslash should be invalid")
        except json.JSONDecodeError:
            pass


# ===========================================================================
# extract_json_from_text  (line 164)
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
        extraction. (This is why repair is effectively dead on the
        validate_response path; see TestValidateResponse.)"""
        assert _v().extract_json_from_text('{"a":1,}') is None


# ===========================================================================
# attempt_repair  (line 200)
# ===========================================================================
class TestAttemptRepair:
    def test_trailing_comma_repaired_first(self):
        """Repairable + the trailing_comma method is FIRST in the list, so
        it's the one credited for ``{"a":1,}``."""
        r = _v().attempt_repair('{"a":1,}', "err")
        assert isinstance(r, RepairResult)
        assert r.success is True
        assert r.repair_method == "trailing_comma"
        assert json.loads(r.repaired_json) == {"a": 1}
        assert r.original_error == "err"

    def test_unquoted_key_repaired(self):
        """``{a:1}`` -- trailing_comma leaves it unchanged (still invalid),
        so the loop falls through to ``unquoted_keys``."""
        r = _v().attempt_repair('{a:1}', "err")
        assert r.success is True
        assert r.repair_method == "unquoted_keys"
        assert json.loads(r.repaired_json) == {"a": 1}

    def test_single_quotes_repaired(self):
        r = _v().attempt_repair("{'a':'b'}", "err")
        assert r.success is True
        assert r.repair_method == "single_quotes"
        assert json.loads(r.repaired_json) == {"a": "b"}

    def test_missing_closing_repaired(self):
        """``{"a":1`` falls through the earlier methods (each leaves it
        invalid) to ``missing_closing``."""
        r = _v().attempt_repair('{"a":1', "err")
        assert r.success is True
        assert r.repair_method == "missing_closing"
        assert json.loads(r.repaired_json) == {"a": 1}

    def test_unrepairable_gibberish_returns_failure(self):
        """No method makes ``not json at all !!!`` parse -> success False,
        repaired_json None, repair_method None, error preserved."""
        r = _v().attempt_repair('not json at all !!!', "boom")
        assert r.success is False
        assert r.repaired_json is None
        assert r.repair_method is None
        assert r.original_error == "boom"

    def test_first_succeeding_method_wins_ordering(self):
        """A trailing comma is fixable by trailing_comma; even though later
        methods might also coincidentally produce valid JSON, the FIRST
        method that yields a json.loads-able string short-circuits the loop.
        Pins the ordering contract."""
        r = _v().attempt_repair('{"a":1,}', "err")
        assert r.repair_method == "trailing_comma"


# ===========================================================================
# validate_response  (line 71) -- top level
# ===========================================================================
_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}},
    "required": ["score"],
}


class TestValidateResponse:
    def test_valid_json_passes_without_repair(self):
        res = _v().validate_response('{"score": 5}', _SCHEMA)
        assert isinstance(res, ValidationResult)
        assert res.valid is True
        assert res.data == {"score": 5}
        assert res.repair_attempted is False
        assert res.repair_successful is False
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
        assert res.repair_attempted is False
        assert res.errors == ["Could not extract JSON from response"]

    def test_trailing_comma_response_is_not_repaired_end_to_end(self):
        """LOAD-BEARING characterization. A trailing-comma response is
        malformed-but-trivially-repairable in principle, BUT
        ``extract_json_from_text`` returns None for it (it only returns
        candidates that already json.loads). So ``validate_response`` exits
        at the extraction step: valid=False, repair_attempted=False, and the
        only error is the extraction failure. The repair machinery is never
        engaged on this path. Pinned so nobody assumes repair runs here."""
        res = _v().validate_response('{"score": 5,}', _SCHEMA)
        assert res.valid is False
        assert res.repair_attempted is False
        assert res.repair_successful is False
        assert res.extracted_json is None
        assert res.errors == ["Could not extract JSON from response"]

    def test_strict_flag_is_stored_on_constructor(self):
        """The constructor records strict; pin both states. (Current schema
        path uses Draft7Validator the same way for both, but the flag is the
        documented knob and its storage must not silently break.)"""
        assert _v(strict=True).strict is True
        assert _v(strict=False).strict is False

    def test_attempt_repair_flag_false_skips_repair_branch(self):
        """When attempt_repair=False is passed and the extracted JSON fails
        to parse, the repair branch is skipped. (We construct a case that
        survives extraction yet... cannot, since extraction gates on
        json.loads. So with valid JSON the flag is simply a no-op.) Pin that
        passing the flag does not break the happy path."""
        res = _v().validate_response('{"score": 3}', _SCHEMA, attempt_repair=False)
        assert res.valid is True
        assert res.data == {"score": 3}


# ===========================================================================
# _validate_against_schema  (line 240)
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
# validate_structured_response  (line 343, module-level convenience fn)
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
# End-to-end anti-corruption guard: the reason the in-isolation helper
# corruptions above are harmless. validate_response tries json.loads FIRST
# (via extract_json_from_text) and only ever invokes attempt_repair on a
# string that already failed to parse. So a VALID response -- even one whose
# string values contain commas/braces/apostrophes/colons that would fool a
# naive _fix_* helper -- is returned unchanged, repair never engaged.
# ===========================================================================
class TestEndToEndNeverCorruptsValidJson:
    _OPEN_SCHEMA = {"type": "object"}

    def _check_unchanged(self, raw):
        res = _v().validate_response(raw, self._OPEN_SCHEMA)
        assert res.valid is True, res.errors
        assert res.repair_attempted is False
        assert res.data == json.loads(raw)

    def test_value_with_comma_and_brace_survives(self):
        """``{"a":"x,}"}`` would be corrupted by _fix_trailing_commas in
        isolation, but end-to-end it parses on the first try -> untouched."""
        self._check_unchanged('{"a":"x,}"}')

    def test_value_with_apostrophe_survives(self):
        """``{"a":"it's"}`` -- the _fix_single_quotes landmine -- is valid
        JSON, so repair is never reached and the apostrophe is preserved."""
        self._check_unchanged('{"a":"it\'s"}')

    def test_value_with_space_word_colon_survives(self):
        """``{"a":"x y:z"}`` -- the _fix_unquoted_keys landmine -- parses
        first try and is returned with its meaning intact."""
        self._check_unchanged('{"a":"x y:z"}')

    def test_value_with_url_colon_survives(self):
        self._check_unchanged('{"url":"http://example.com/a,b"}')

    def test_value_with_escaped_quote_survives(self):
        """``{"a":"x\\"y"}`` -- the _fix_escape_sequences territory -- is
        valid and returned unchanged."""
        self._check_unchanged('{"a":"x\\"y"}')
