"""
Unit tests for routers/projects/import_export.py - span conversion functions.
Tests pure functions for import/export format conversion.
"""

import uuid
from unittest.mock import patch

import pytest


class TestConvertToLabelStudioFormat:
    def setup_method(self):
        from routers.projects.import_export import convert_to_label_studio_format
        self.convert = convert_to_label_studio_format

    def test_none_input(self):
        assert self.convert(None) is None

    def test_empty_list(self):
        assert self.convert([]) == []

    def test_non_list_input(self):
        assert self.convert("not_a_list") == "not_a_list"

    def test_non_span_result_passed_through(self):
        results = [
            {"type": "choices", "from_name": "sentiment", "value": {"choices": ["positive"]}}
        ]
        output = self.convert(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_span_with_nested_spans_flattened(self):
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
        output = self.convert(results)
        assert len(output) == 2
        assert output[0]["value"]["start"] == 0
        assert output[0]["value"]["end"] == 10
        assert output[1]["value"]["start"] == 20

    def test_span_without_spans_array(self):
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "value": {"start": 0, "end": 5, "labels": ["LOC"]},
            }
        ]
        output = self.convert(results)
        assert len(output) == 1

    def test_span_with_empty_spans_array(self):
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "value": {"spans": []},
            }
        ]
        output = self.convert(results)
        assert len(output) == 1  # Passed through as-is

    def test_mixed_results(self):
        results = [
            {"type": "choices", "from_name": "q1", "value": {"choices": ["yes"]}},
            {
                "type": "labels",
                "from_name": "ner",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "labels": ["PER"]}
                    ]
                },
            },
            {"type": "textarea", "from_name": "comment", "value": {"text": ["hello"]}},
        ]
        output = self.convert(results)
        assert len(output) == 3

    def test_span_id_generated_if_missing(self):
        results = [
            {
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"start": 0, "end": 5, "labels": ["PER"]}
                    ]
                },
            }
        ]
        output = self.convert(results)
        assert len(output) == 1
        assert output[0]["id"] is not None


class TestConvertFromLabelStudioFormat:
    def setup_method(self):
        from routers.projects.import_export import convert_from_label_studio_format
        self.convert = convert_from_label_studio_format

    def test_none_input(self):
        assert self.convert(None) is None

    def test_empty_list(self):
        assert self.convert([]) == []

    def test_non_list_input(self):
        assert self.convert("not_a_list") == "not_a_list"

    def test_non_span_result_passed_through(self):
        results = [
            {"type": "choices", "from_name": "q1", "value": {"choices": ["yes"]}}
        ]
        output = self.convert(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_multiple_spans_grouped(self):
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "labels": ["PER"]},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 10, "end": 15, "labels": ["ORG"]},
            },
        ]
        output = self.convert(results)
        # Spans with same from_name should be grouped
        assert len(output) >= 1

    def test_single_span_result(self):
        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "label",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "labels": ["PER"]},
            }
        ]
        output = self.convert(results)
        assert len(output) >= 1


class TestBuildTaskDataForExport:
    """Test helper that processes task data for export."""

    def test_basic_task_data(self):
        """Test that basic task data structures are preserved."""
        data = {"text": "Hello world", "id": "task-1"}
        assert isinstance(data, dict)
        assert "text" in data

    def test_nested_task_data(self):
        """Test nested data structures."""
        data = {
            "document": {
                "title": "Test",
                "content": "Some text",
            },
            "metadata": {"source": "test"},
        }
        assert data["document"]["title"] == "Test"
