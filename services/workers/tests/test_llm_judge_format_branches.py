"""Residual branch coverage for ml_evaluation/llm_judge_evaluator.py value
formatting and response parsing.

test_ml_evaluation_deep_coverage.py::TestLLMJudgeDeepCoverage already covers
the bulk of ``_format_value`` / ``_format_value_by_type`` / ``_format_spans``
and test_llm_judge_evaluator_more.py covers the ``_parse_evaluation_response``
score-regex fallbacks. This file fills the specific intra-method branches
those suites skip, each confirmed UNREACHED by them via grep:

  * ``_format_value_by_type`` text-type with a *truthy, non-str, non-dict*
    value (a number / a non-empty list) -> the final ``return str(value)``
    fall-through (the existing text tests only pass str / dict / empty-str).
  * text-type with a *falsy* non-str value ([] / 0) -> the ``"(empty)"`` arm
    of that same fall-through.
  * choices-type dict carrying the ``"selected"`` key (not ``"choices"``) ->
    the ``value.get("choices", value.get("selected", []))`` second-default arm.
  * span_selection dispatched *through* ``_format_value`` (existing span tests
    call ``_format_spans`` directly, never via the answer_type dispatch at
    line 1372-1373).
  * rating/numeric dict carrying only the ``"value"`` key -> the third
    ``or value.get("value")`` arm; and a rating dict whose recognised keys are
    all missing -> the ``f"Value: {value}"`` whole-dict fall-through.
  * ``_format_spans`` given ``{"spans": []}`` -> the dict-unwrap yields an
    empty list, hitting the ``len(spans) == 0`` guard *after* extraction
    (existing empty test passes a bare ``[]`` / ``None``, not a wrapper dict).
  * ``_parse_evaluation_response`` with a fenced ```json block whose body is
    invalid JSON -> the fenced ``except json.JSONDecodeError: pass`` arm; and a
    bare ``{"preference": ...}`` object that is invalid JSON -> the
    preference-regex ``except: pass`` arm.

All behavioral: craft an input, assert the returned string / dict. AI service
is a MagicMock; no provider call is made. Mirrors the ``_make_evaluator``
helper idiom from test_llm_judge_evaluator_more.py.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import LLMJudgeEvaluator  # noqa: E402


def _make_evaluator(**kwargs):
    defaults = {"ai_service": MagicMock(), "judge_model": "test-model"}
    defaults.update(kwargs)
    return LLMJudgeEvaluator(**defaults)


# ============================================================================
# _format_value_by_type — text-type non-str fall-through (line ~1358)
# ============================================================================


class TestFormatTextNonStringFallThrough:
    def test_text_type_number_value_stringifies(self):
        """answer_type=text + an int value: not str, not dict -> str(value)."""
        ev = _make_evaluator(answer_type="text")
        assert ev._format_value(42) == "42"

    def test_text_type_nonempty_list_value_stringifies(self):
        """answer_type=text + a non-empty list: not str, not dict -> str(list)."""
        ev = _make_evaluator(answer_type="long_text")
        result = ev._format_value(["a", "b"])
        # str() of the list, not JSON — text branch falls to str(value).
        assert result == "['a', 'b']"

    def test_text_type_falsy_nonstring_value_is_empty_marker(self):
        """answer_type=text + an empty list ([]): falsy non-str -> '(empty)'."""
        ev = _make_evaluator(answer_type="short_text")
        assert ev._format_value([]) == "(empty)"

    def test_text_type_zero_value_is_empty_marker(self):
        """answer_type=text + 0: falsy non-str/non-dict -> '(empty)'."""
        ev = _make_evaluator(answer_type="text")
        assert ev._format_value(0) == "(empty)"

    def test_text_type_dict_without_text_key_stringifies(self):
        """answer_type=text + dict lacking a 'text' key: the inner dict block
        finds no text_val, so control reaches the final str(value) line."""
        ev = _make_evaluator(answer_type="text")
        result = ev._format_value({"other": "x"})
        assert result == "{'other': 'x'}"


# ============================================================================
# _format_value_by_type — choices 'selected' key default (line ~1365)
# ============================================================================


class TestFormatChoicesSelectedKey:
    def test_choices_dict_uses_selected_key_fallback(self):
        """A choices dict with no 'choices' key but a 'selected' key uses the
        second default in value.get('choices', value.get('selected', []))."""
        ev = _make_evaluator(answer_type="multiple_choice")
        result = ev._format_value({"selected": ["X", "Y"]})
        assert result == "Selected: [X, Y]"

    def test_choices_dict_without_any_known_key_is_none(self):
        """No 'choices' and no 'selected' -> the [] default -> 'Selected: [none]'."""
        ev = _make_evaluator(answer_type="binary")
        result = ev._format_value({"unrelated": 1})
        assert result == "Selected: [none]"


# ============================================================================
# _format_value_by_type — span_selection dispatch via _format_value (line 1372-1373)
# ============================================================================


class TestFormatValueSpanSelectionDispatch:
    def test_format_value_dispatches_spans_to_format_spans(self):
        """answer_type=span_selection routed through the public _format_value
        path reaches the span_selection branch that calls _format_spans."""
        ev = _make_evaluator(answer_type="span_selection")
        spans = [{"text": "Berlin", "start": 0, "end": 6, "labels": ["LOC"]}]
        result = ev._format_value(spans)
        assert "Berlin" in result
        assert "LOC" in result
        assert "chars 0-6" in result


# ============================================================================
# _format_value_by_type — rating/numeric 'value' key + dict fall-through (1376-1382)
# ============================================================================


class TestFormatRatingValueKey:
    def test_rating_dict_uses_value_key(self):
        """A rating dict with only a 'value' key uses the third or-arm:
        rating or number or value."""
        ev = _make_evaluator(answer_type="rating")
        result = ev._format_value({"value": 7})
        assert result == "Value: 7"

    def test_rating_dict_without_known_keys_formats_whole_dict(self):
        """A rating dict where rating/number/value are all absent: num_val is
        None, so the 'if num_val is not None' guard is False and control
        reaches the final f'Value: {value}' with the whole dict."""
        ev = _make_evaluator(answer_type="numeric")
        result = ev._format_value({"foo": "bar"})
        assert result == "Value: {'foo': 'bar'}"


# ============================================================================
# _format_spans — empty list AFTER dict unwrap (line ~1413)
# ============================================================================


class TestFormatSpansEmptyAfterUnwrap:
    def test_spans_wrapper_dict_with_empty_list(self):
        """{'spans': []} unwraps to [] which is a list, so the not-a-list guard
        is skipped and the len == 0 check (post-extraction) returns the
        no-spans marker."""
        ev = _make_evaluator(answer_type="span_selection")
        assert ev._format_spans({"spans": []}) == "(no spans annotated)"

    def test_labels_wrapper_dict_with_empty_list(self):
        """{'labels': []} unwraps via the second .get default to [] -> same
        post-extraction empty-list guard."""
        ev = _make_evaluator(answer_type="span_selection")
        assert ev._format_spans({"labels": []}) == "(no spans annotated)"


# ============================================================================
# _parse_evaluation_response — fenced-invalid + preference-invalid (1053-54/1068-69)
# ============================================================================


class TestParseEvaluationResponseInnerExcepts:
    def test_fenced_block_invalid_json_falls_through(self):
        """A ```json fence whose body is not valid JSON trips the fenced
        except-pass; with no recoverable bare-object after it, returns None."""
        ev = _make_evaluator()
        content = "preamble\n```json\n{not valid json here}\n```\ntail"
        assert ev._parse_evaluation_response(content) is None

    def test_fenced_invalid_then_bare_score_recovers(self):
        """Fenced body is invalid (inner except-pass), but a later bare
        {\"score\": ...} object is recovered by the score regex stage."""
        ev = _make_evaluator()
        content = '```json\n{broken}\n``` then {"score": 3, "justification": "ok"}'
        out = ev._parse_evaluation_response(content)
        assert out is not None
        assert out["score"] == 3

    def test_malformed_preference_object_returns_none(self):
        """A bare object containing the substring 'preference' but with invalid
        JSON trips the preference-regex except-pass arm -> None. (The score
        regex doesn't match because there's no 'score' substring.)"""
        ev = _make_evaluator()
        out = ev._parse_evaluation_response('{"preference": not-valid-json}')
        assert out is None
