"""
Unit tests for routers/projects/import_export.py — targets span conversion functions
and other pure functions at the top of the file (lines 28-125+).
"""

import pytest


class TestConvertToLabelStudioFormat:
    """Tests for convert_to_label_studio_format."""

    def test_none_input(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format(None) is None

    def test_empty_list(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format([]) == []

    def test_not_a_list(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format("not a list") == "not a list"

    def test_non_labels_type_passthrough(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [{"type": "choices", "value": {"choices": ["A"]}}]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_labels_without_spans_passthrough(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [{"type": "labels", "value": {"text": "hello"}}]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1

    def test_labels_with_empty_spans(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [{"type": "labels", "value": {"spans": []}}]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1  # passthrough since spans is empty

    def test_labels_with_spans_flattened(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 10, "labels": ["PER"]},
                        {"id": "s2", "start": 20, "end": 30, "labels": ["ORG"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["id"] == "s1"
        assert output[0]["type"] == "labels"
        assert output[0]["from_name"] == "label"
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["end"] == 30

    def test_mixed_types(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"type": "choices", "value": {"choices": ["B"]}},
            {
                "type": "labels",
                "from_name": "ner",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"start": 5, "end": 15, "labels": ["LOC"]},
                    ]
                },
            },
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["type"] == "choices"
        assert output[1]["type"] == "labels"


class TestConvertFromLabelStudioFormat:
    """Tests for convert_from_label_studio_format."""

    def test_none_input(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format(None) is None

    def test_empty_list(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format([]) == []

    def test_not_a_list(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format("not a list") == "not a list"

    def test_non_labels_passthrough(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [{"type": "choices", "value": {"choices": ["A"]}}]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_labels_collapsed_to_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 10, "labels": ["PER"]},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 20, "end": 30, "labels": ["ORG"]},
            },
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "labels"
        assert len(output[0]["value"]["spans"]) == 2
        assert output[0]["value"]["spans"][0]["id"] == "s1"

    def test_labels_with_different_from_name_not_collapsed(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label1",
                "to_name": "text",
                "value": {"start": 0, "end": 10},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "label2",
                "to_name": "text",
                "value": {"start": 20, "end": 30},
            },
        ]
        output = convert_from_label_studio_format(results)
        # Should create separate entries since from_name differs
        assert len(output) == 2


class TestSpanIdGeneration:
    """Tests for edge cases in span conversion."""

    def test_span_without_id_gets_uuid(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"start": 0, "end": 5, "labels": ["PER"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["id"] is not None
        assert len(output[0]["id"]) > 0

    def test_labels_type_without_value_dict(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [{"type": "labels", "value": "not_a_dict"}]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "labels"

    def test_labels_with_spans_not_list(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [{"type": "labels", "value": {"spans": "not_a_list"}}]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
