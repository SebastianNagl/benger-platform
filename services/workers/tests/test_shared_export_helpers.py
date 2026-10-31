"""Helpers the worker reaches through /shared (audit finding A3).

``coerce_metric_value`` (used by report_service) and
``convert_to_label_studio_format`` (used by the Label Studio export
generator) used to live in API routers, which the worker image does not
carry. Both now live in /shared; these tests pin their behaviour from the
worker side.
"""

from export_stream import convert_to_label_studio_format
from metric_values import coerce_metric_value


class TestCoerceMetricValue:
    def test_none_and_bool_are_not_numbers(self):
        assert coerce_metric_value(None) is None
        assert coerce_metric_value(True) is None
        assert coerce_metric_value(False) is None

    def test_bare_numbers(self):
        assert coerce_metric_value(3) == 3.0
        assert isinstance(coerce_metric_value(3), float)
        assert coerce_metric_value(0.25) == 0.25

    def test_value_details_shape(self):
        assert coerce_metric_value({"value": 0.8, "details": {}}) == 0.8
        assert coerce_metric_value({"value": True}) is None

    def test_multi_output_uses_primary_key_then_first(self):
        inner = {"precision": 0.5, "recall": 0.7}
        assert coerce_metric_value({"value": inner, "primary_metric_key": "recall"}) == 0.7
        assert coerce_metric_value({"value": inner}) == 0.5

    def test_legacy_korrektur_shape(self):
        assert coerce_metric_value({"total_score": 51.5, "score": 3}) == 51.5
        assert coerce_metric_value({"score": 12}) == 12.0

    def test_strings_and_unknown_shapes(self):
        # Unlike aggregate_summaries._coerce_metric_value, strings are not parsed.
        assert coerce_metric_value("0.5") is None
        assert coerce_metric_value({"foo": 1}) is None
        assert coerce_metric_value([1, 2]) is None


class TestConvertToLabelStudioFormat:
    def test_passthrough_for_empty_or_non_list(self):
        assert convert_to_label_studio_format(None) is None
        assert convert_to_label_studio_format([]) == []
        assert convert_to_label_studio_format("x") == "x"

    def test_flattens_spans_and_keeps_other_results(self):
        results = [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {"spans": [
                    {"id": "a", "start": 0, "end": 3, "text": "abc", "labels": ["X"]},
                    {"start": 4, "end": 5},
                ]},
            },
            {"type": "labels", "value": {"start": 1, "end": 2}},
            {"type": "choices", "value": {"choices": ["Ja"]}},
        ]
        out = convert_to_label_studio_format(results)
        assert len(out) == 4
        assert out[0] == {
            "id": "a",
            "from_name": "label",
            "to_name": "text",
            "type": "labels",
            "value": {"start": 0, "end": 3, "text": "abc", "labels": ["X"]},
        }
        # A span without id gets a generated one and default text/labels.
        assert out[1]["id"]
        assert out[1]["value"] == {"start": 4, "end": 5, "text": "", "labels": []}
        # A labels result without a spans array and a non-span result pass through.
        assert out[2] is results[1]
        assert out[3] is results[2]
