"""Tests for span annotation export/import format conversion.

Issue #964: Add Span Annotation as a project type for NER and text highlighting

Tests cover:
- Conversion from BenGER format to Label Studio format (export)
- Conversion from Label Studio format to BenGER format (import)
- Round-trip conversion preservation
- Edge cases (empty spans, multiple spans, mixed annotations)
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from routers.projects.import_export import (
    convert_from_label_studio_format,
    convert_to_label_studio_format,
)


class TestConvertToLabelStudioFormat:
    """Test BenGER to Label Studio format conversion (export)."""

    def test_single_span_conversion(self):
        """Test converting a single span annotation."""
        benger_format = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        }
                    ]
                },
            }
        ]

        result = convert_to_label_studio_format(benger_format)

        assert len(result) == 1
        assert result[0]["id"] == "span-1"
        assert result[0]["from_name"] == "entities"
        assert result[0]["to_name"] == "text"
        assert result[0]["type"] == "labels"
        assert result[0]["value"]["start"] == 0
        assert result[0]["value"]["end"] == 10
        assert result[0]["value"]["text"] == "John Smith"
        assert result[0]["value"]["labels"] == ["PERSON"]

    def test_multiple_spans_conversion(self):
        """Test converting multiple spans in one annotation."""
        benger_format = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        },
                        {
                            "id": "span-2",
                            "start": 20,
                            "end": 30,
                            "text": "Acme Corp",
                            "labels": ["ORGANIZATION"],
                        },
                    ]
                },
            }
        ]

        result = convert_to_label_studio_format(benger_format)

        assert len(result) == 2
        assert result[0]["id"] == "span-1"
        assert result[1]["id"] == "span-2"

    def test_empty_spans_array(self):
        """Test handling of empty spans array."""
        benger_format = [
            {"from_name": "entities", "to_name": "text", "type": "labels", "value": {"spans": []}}
        ]

        result = convert_to_label_studio_format(benger_format)

        # Should pass through as-is when no spans
        assert len(result) == 1
        assert result[0]["value"]["spans"] == []

    def test_non_span_annotations_passthrough(self):
        """Test that non-span annotations pass through unchanged."""
        input_format = [
            {
                "from_name": "answer",
                "to_name": "text",
                "type": "textarea",
                "value": {"text": ["Some answer"]},
            },
            {
                "from_name": "sentiment",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["positive"]},
            },
        ]

        result = convert_to_label_studio_format(input_format)

        assert len(result) == 2
        assert result[0]["type"] == "textarea"
        assert result[1]["type"] == "choices"

    def test_mixed_annotations(self):
        """Test conversion with both span and non-span annotations."""
        input_format = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        }
                    ]
                },
            },
            {
                "from_name": "sentiment",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["positive"]},
            },
        ]

        result = convert_to_label_studio_format(input_format)

        assert len(result) == 2
        # Span annotation flattened
        span_result = next(r for r in result if r["type"] == "labels")
        assert "start" in span_result["value"]
        # Choice annotation unchanged
        choice_result = next(r for r in result if r["type"] == "choices")
        assert choice_result["value"]["choices"] == ["positive"]

    def test_none_input(self):
        """Test handling of None input."""
        result = convert_to_label_studio_format(None)
        assert result is None

    def test_empty_list_input(self):
        """Test handling of empty list input."""
        result = convert_to_label_studio_format([])
        assert result == []


class TestConvertFromLabelStudioFormat:
    """Test Label Studio to BenGER format conversion (import)."""

    def test_single_span_conversion(self):
        """Test converting a single Label Studio span."""
        ls_format = [
            {
                "id": "span-1",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 0,
                    "end": 10,
                    "text": "John Smith",
                    "labels": ["PERSON"],
                },
            }
        ]

        result = convert_from_label_studio_format(ls_format)

        assert len(result) == 1
        assert result[0]["from_name"] == "entities"
        assert result[0]["to_name"] == "text"
        assert result[0]["type"] == "labels"
        assert "spans" in result[0]["value"]
        assert len(result[0]["value"]["spans"]) == 1
        assert result[0]["value"]["spans"][0]["start"] == 0
        assert result[0]["value"]["spans"][0]["end"] == 10

    def test_multiple_spans_consolidation(self):
        """Test consolidating multiple Label Studio spans into one."""
        ls_format = [
            {
                "id": "span-1",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 0,
                    "end": 10,
                    "text": "John Smith",
                    "labels": ["PERSON"],
                },
            },
            {
                "id": "span-2",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 20,
                    "end": 30,
                    "text": "Acme Corp",
                    "labels": ["ORGANIZATION"],
                },
            },
        ]

        result = convert_from_label_studio_format(ls_format)

        # Should consolidate to one annotation with two spans
        assert len(result) == 1
        assert result[0]["from_name"] == "entities"
        assert len(result[0]["value"]["spans"]) == 2

    def test_different_from_names_stay_separate(self):
        """Test that spans with different from_names stay separate."""
        ls_format = [
            {
                "id": "span-1",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 0,
                    "end": 10,
                    "text": "John Smith",
                    "labels": ["PERSON"],
                },
            },
            {
                "id": "span-2",
                "from_name": "keywords",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 20,
                    "end": 30,
                    "text": "important",
                    "labels": ["KEYWORD"],
                },
            },
        ]

        result = convert_from_label_studio_format(ls_format)

        # Should have two separate annotations
        assert len(result) == 2

    def test_benger_format_passthrough(self):
        """Test that already-BenGER-format annotations pass through."""
        benger_format = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        }
                    ]
                },
            }
        ]

        result = convert_from_label_studio_format(benger_format)

        assert len(result) == 1
        assert "spans" in result[0]["value"]

    def test_non_span_annotations_passthrough(self):
        """Test that non-span annotations pass through unchanged."""
        input_format = [
            {
                "from_name": "answer",
                "to_name": "text",
                "type": "textarea",
                "value": {"text": ["Some answer"]},
            }
        ]

        result = convert_from_label_studio_format(input_format)

        assert len(result) == 1
        assert result[0]["type"] == "textarea"
        assert result[0]["value"]["text"] == ["Some answer"]

    def test_none_input(self):
        """Test handling of None input."""
        result = convert_from_label_studio_format(None)
        assert result is None

    def test_empty_list_input(self):
        """Test handling of empty list input."""
        result = convert_from_label_studio_format([])
        assert result == []


class TestRoundTrip:
    """Test round-trip conversion preservation."""

    def test_export_import_roundtrip(self):
        """Test that export then import preserves data."""
        original_benger = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        },
                        {
                            "id": "span-2",
                            "start": 20,
                            "end": 30,
                            "text": "Acme Corp",
                            "labels": ["ORGANIZATION"],
                        },
                    ]
                },
            }
        ]

        # Export (BenGER -> Label Studio)
        exported = convert_to_label_studio_format(original_benger)
        assert len(exported) == 2  # Flattened to 2 results

        # Import (Label Studio -> BenGER)
        imported = convert_from_label_studio_format(exported)
        assert len(imported) == 1  # Consolidated back to 1 result

        # Verify data preserved
        assert imported[0]["from_name"] == "entities"
        assert len(imported[0]["value"]["spans"]) == 2

        spans = imported[0]["value"]["spans"]
        span_ids = [s["id"] for s in spans]
        assert "span-1" in span_ids
        assert "span-2" in span_ids

    def test_import_export_roundtrip(self):
        """Test that import then export preserves data."""
        original_ls = [
            {
                "id": "span-1",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 0,
                    "end": 10,
                    "text": "John Smith",
                    "labels": ["PERSON"],
                },
            },
            {
                "id": "span-2",
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "start": 20,
                    "end": 30,
                    "text": "Acme Corp",
                    "labels": ["ORGANIZATION"],
                },
            },
        ]

        # Import (Label Studio -> BenGER)
        imported = convert_from_label_studio_format(original_ls)
        assert len(imported) == 1

        # Export (BenGER -> Label Studio)
        exported = convert_to_label_studio_format(imported)
        assert len(exported) == 2

        # Verify data preserved
        for span in exported:
            assert span["from_name"] == "entities"
            assert span["type"] == "labels"
            assert "start" in span["value"]
            assert "end" in span["value"]

    def test_mixed_annotations_roundtrip(self):
        """Test round-trip with mixed annotation types."""
        original_benger = [
            {
                "from_name": "entities",
                "to_name": "text",
                "type": "labels",
                "value": {
                    "spans": [
                        {
                            "id": "span-1",
                            "start": 0,
                            "end": 10,
                            "text": "John Smith",
                            "labels": ["PERSON"],
                        }
                    ]
                },
            },
            {
                "from_name": "sentiment",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": ["positive"]},
            },
        ]

        # Export
        exported = convert_to_label_studio_format(original_benger)

        # Import
        imported = convert_from_label_studio_format(exported)

        # Should have 2 annotations
        assert len(imported) == 2

        # Find each type
        span_ann = next((r for r in imported if r["type"] == "labels"), None)
        choice_ann = next((r for r in imported if r["type"] == "choices"), None)

        assert span_ann is not None
        assert choice_ann is not None
        assert "spans" in span_ann["value"]
        assert choice_ann["value"]["choices"] == ["positive"]
