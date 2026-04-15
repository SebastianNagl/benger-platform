"""
Unit tests for import/export helper functions.

Targets: routers/projects/import_export.py — 26.60% coverage (454 uncovered lines)
Tests span conversion, format handling, etc.
"""

import uuid

import pytest


class TestConvertToLabelStudioFormat:
    """Test convert_to_label_studio_format."""

    def test_none_input(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format(None) is None

    def test_empty_list(self):
        from routers.projects.import_export import convert_to_label_studio_format
        assert convert_to_label_studio_format([]) == []

    def test_non_span_result_passes_through(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"from_name": "label", "to_name": "text", "type": "choices",
             "value": {"choices": ["A"]}}
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1
        assert output[0]["type"] == "choices"

    def test_span_flattening(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 10, "text": "hello", "labels": ["PER"]},
                        {"id": "s2", "start": 15, "end": 20, "text": "world", "labels": ["LOC"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["type"] == "labels"
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 15

    def test_labels_without_spans_passes_through(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 0, "end": 5, "labels": ["PER"]}}
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 1

    def test_mixed_types(self):
        from routers.projects.import_export import convert_to_label_studio_format
        results = [
            {"from_name": "choice", "type": "choices", "value": {"choices": ["Yes"]}},
            {
                "from_name": "label", "to_name": "text", "type": "labels",
                "value": {"spans": [{"id": "s1", "start": 0, "end": 5, "text": "hi", "labels": ["X"]}]},
            },
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["type"] == "choices"
        assert output[1]["type"] == "labels"


class TestConvertFromLabelStudioFormat:
    """Test convert_from_label_studio_format."""

    def test_none_input(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format(None) is None

    def test_empty_list(self):
        from routers.projects.import_export import convert_from_label_studio_format
        assert convert_from_label_studio_format([]) == []

    def test_non_labels_type_passes_through(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"from_name": "choice", "type": "choices", "value": {"choices": ["A"]}}
        ]
        output = convert_from_label_studio_format(results)
        assert len(output) == 1

    def test_labels_are_grouped_into_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format
        results = [
            {"id": "s1", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 0, "end": 5, "text": "hello", "labels": ["PER"]}},
            {"id": "s2", "from_name": "label", "to_name": "text", "type": "labels",
             "value": {"start": 10, "end": 15, "text": "world", "labels": ["LOC"]}},
        ]
        output = convert_from_label_studio_format(results)
        # Should group them into a single result with spans array
        assert len(output) == 1
        assert output[0]["type"] == "labels"
        assert "spans" in output[0]["value"]
        assert len(output[0]["value"]["spans"]) == 2


class TestImportExportRouterExists:
    """Verify router structure."""

    def test_import_export_router_importable(self):
        from routers.projects.import_export import router
        assert router is not None

    def test_import_export_has_routes(self):
        from routers.projects.import_export import router
        routes = [r.path for r in router.routes]
        assert len(routes) >= 2  # At least import and export
