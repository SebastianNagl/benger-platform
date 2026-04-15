"""Coverage tests for shared/annotation_utils.py.

Tests: _normalize_german, _extract_value, extract_field_value,
extract_all_field_values, extract_first_value, extract_first_text_value.
"""

import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
shared_root = os.path.join(os.path.dirname(workers_root), "shared")
sys.path.insert(0, workers_root)
if os.path.isdir(shared_root):
    sys.path.insert(0, shared_root)

from annotation_utils import (
    _normalize_german,
    _extract_value,
    extract_field_value,
    extract_all_field_values,
    extract_first_value,
    extract_first_text_value,
)


class TestNormalizeGerman:
    def test_lowercase(self):
        assert _normalize_german("ABC") == "abc"

    def test_umlaut_oe(self):
        assert _normalize_german("Lösung") == "loesung"

    def test_umlaut_ae(self):
        assert _normalize_german("Klärung") == "klaerung"

    def test_umlaut_ue(self):
        assert _normalize_german("Prüfung") == "pruefung"

    def test_eszett(self):
        assert _normalize_german("Straße") == "strasse"

    def test_combined(self):
        assert _normalize_german("Äußerung") == "aeusserung"

    def test_no_special_chars(self):
        assert _normalize_german("hello") == "hello"


class TestExtractValue:
    def test_text_list(self):
        result = {"value": {"text": ["Hello"]}, "type": "textarea"}
        assert _extract_value(result) == "Hello"

    def test_text_string(self):
        result = {"value": {"text": "Hello"}, "type": "textarea"}
        assert _extract_value(result) == "Hello"

    def test_text_empty_list(self):
        result = {"value": {"text": []}, "type": "textarea"}
        assert _extract_value(result) == []

    def test_markdown(self):
        result = {"value": {"markdown": "# Title"}, "type": "textarea"}
        assert _extract_value(result) == "# Title"

    def test_choices_single(self):
        result = {"value": {"choices": ["Yes"]}, "type": "choices"}
        assert _extract_value(result) == "Yes"

    def test_choices_empty(self):
        result = {"value": {"choices": []}, "type": "choices"}
        assert _extract_value(result) is None

    def test_choices_all(self):
        result = {"value": {"choices": ["A", "B"]}, "type": "choices"}
        assert _extract_value(result, return_first_choice=False) == ["A", "B"]

    def test_rating(self):
        result = {"value": {"rating": 5}, "type": "rating"}
        assert _extract_value(result) == "5"

    def test_number(self):
        result = {"value": {"number": 42}, "type": "number"}
        assert _extract_value(result) == "42"

    def test_labels_spans(self):
        spans = [{"start": 0, "end": 5, "labels": ["PER"]}]
        result = {"value": {"spans": spans}, "type": "labels"}
        assert _extract_value(result) == spans

    def test_empty_value(self):
        result = {"value": {}, "type": "unknown"}
        assert _extract_value(result) is None

    def test_missing_value_key(self):
        result = {"type": "textarea"}
        assert _extract_value(result) is None


class TestExtractFieldValue:
    def test_exact_match(self):
        results = [{"from_name": "answer", "type": "choices", "value": {"choices": ["Yes"]}}]
        assert extract_field_value(results, "answer") == "Yes"

    def test_case_insensitive_match(self):
        results = [{"from_name": "Answer", "type": "choices", "value": {"choices": ["Yes"]}}]
        assert extract_field_value(results, "answer") == "Yes"

    def test_umlaut_normalized_match(self):
        results = [{"from_name": "lösung", "type": "textarea", "value": {"text": ["Die Klage"]}}]
        assert extract_field_value(results, "loesung") == "Die Klage"

    def test_no_match(self):
        results = [{"from_name": "other", "type": "textarea", "value": {"text": ["X"]}}]
        assert extract_field_value(results, "answer") is None

    def test_empty_results(self):
        assert extract_field_value([], "answer") is None

    def test_none_results(self):
        assert extract_field_value(None, "answer") is None

    def test_non_list_results(self):
        assert extract_field_value("not a list", "answer") is None

    def test_normalize_umlauts_disabled(self):
        results = [{"from_name": "lösung", "type": "textarea", "value": {"text": ["X"]}}]
        # With normalization disabled, "loesung" won't match "lösung"
        assert extract_field_value(results, "loesung", normalize_umlauts=False) is None

    def test_return_all_choices(self):
        results = [{"from_name": "q", "type": "choices", "value": {"choices": ["A", "B"]}}]
        assert extract_field_value(results, "q", return_first_choice=False) == ["A", "B"]


class TestExtractAllFieldValues:
    def test_multiple_fields(self):
        results = [
            {"from_name": "answer", "type": "choices", "value": {"choices": ["Yes"]}},
            {"from_name": "comment", "type": "textarea", "value": {"text": ["Good"]}},
        ]
        vals = extract_all_field_values(results)
        assert vals["answer"] == "Yes"
        assert vals["comment"] == "Good"

    def test_skip_none_values(self):
        results = [
            {"from_name": "empty", "type": "unknown", "value": {}},
        ]
        vals = extract_all_field_values(results)
        assert "empty" not in vals

    def test_skip_no_from_name(self):
        results = [{"type": "textarea", "value": {"text": ["X"]}}]
        vals = extract_all_field_values(results)
        assert vals == {}

    def test_empty_results(self):
        assert extract_all_field_values([]) == {}

    def test_none_results(self):
        assert extract_all_field_values(None) == {}


class TestExtractFirstValue:
    def test_finds_first(self):
        results = [
            {"from_name": "a", "type": "textarea", "value": {"text": ["First"]}},
            {"from_name": "b", "type": "textarea", "value": {"text": ["Second"]}},
        ]
        assert extract_first_value(results) == "First"

    def test_skips_empty(self):
        results = [
            {"from_name": "a", "type": "unknown", "value": {}},
            {"from_name": "b", "type": "textarea", "value": {"text": ["Found"]}},
        ]
        assert extract_first_value(results) == "Found"

    def test_empty_results(self):
        assert extract_first_value([]) is None

    def test_none_results(self):
        assert extract_first_value(None) is None

    def test_all_empty(self):
        results = [{"from_name": "a", "type": "unknown", "value": {}}]
        assert extract_first_value(results) is None


class TestExtractFirstTextValue:
    def test_finds_text(self):
        results = [{"from_name": "a", "type": "textarea", "value": {"text": ["Hello"]}}]
        assert extract_first_text_value(results) == "Hello"

    def test_finds_markdown(self):
        results = [{"from_name": "a", "type": "other", "value": {"markdown": "# Title"}}]
        assert extract_first_text_value(results) == "# Title"

    def test_skips_choices(self):
        results = [
            {"from_name": "a", "type": "choices", "value": {"choices": ["A"]}},
            {"from_name": "b", "type": "textarea", "value": {"text": ["Found"]}},
        ]
        assert extract_first_text_value(results) == "Found"

    def test_text_as_string(self):
        results = [{"from_name": "a", "type": "text", "value": {"text": "Direct string"}}]
        assert extract_first_text_value(results) == "Direct string"

    def test_empty_text_list(self):
        results = [
            {"from_name": "a", "type": "textarea", "value": {"text": []}},
            {"from_name": "b", "type": "textarea", "value": {"text": ["Found"]}},
        ]
        assert extract_first_text_value(results) == "Found"

    def test_empty_markdown(self):
        results = [{"from_name": "a", "type": "other", "value": {"markdown": ""}}]
        # Empty markdown is falsy so it's skipped
        assert extract_first_text_value(results) is None

    def test_none_results(self):
        assert extract_first_text_value(None) is None

    def test_empty_results(self):
        assert extract_first_text_value([]) is None
