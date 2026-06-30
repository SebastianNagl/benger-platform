"""Pure-function unit tests for the shared immediate-eval dispatch helpers.

Covers the DB-free logic of ``services/shared/immediate_eval_dispatch.py`` —
annotation-result parsing, eligibility filtering, and the real-score detector.
The DB-backed entry points (``ensure_immediate_evaluation``, ``scan_ungraded``)
are exercised by the worker/integration suites; here we lock the pure helpers
that every trigger (hook, worker, endpoint, sweep, CLI) shares.
"""

from types import SimpleNamespace

import pytest

from immediate_eval_dispatch import (
    eligible_configs,
    eligible_metrics,
    parse_annotation_results,
    row_has_real_score_for,
)

pytestmark = pytest.mark.unit


class TestParseAnnotationResults:
    def test_textarea_and_string_and_choices(self):
        ann = SimpleNamespace(
            result=[
                {"from_name": "loesung", "type": "textarea", "value": {"text": ["A", "B"]}},
                {"from_name": "note", "value": "plain"},
                {"from_name": "pick", "type": "choices", "value": {"choices": ["x"]}},
                {"from_name": "md", "value": {"markdown": "# H"}},
            ]
        )
        out = parse_annotation_results(ann)
        assert out["loesung"] == "A\nB"
        assert out["note"] == "plain"
        assert out["pick"] == "x"
        assert out["md"] == "# H"

    def test_empty_or_non_list_result(self):
        assert parse_annotation_results(SimpleNamespace(result=[])) == {}
        assert parse_annotation_results(SimpleNamespace(result=None)) == {}

    def test_skips_regions_without_from_name(self):
        ann = SimpleNamespace(result=[{"type": "textarea", "value": {"text": ["x"]}}])
        assert parse_annotation_results(ann) == {}


class TestRowHasRealScoreFor:
    def test_value_dict_counts(self):
        assert row_has_real_score_for(
            {"llm_judge_falloesung": {"value": 0.43}}, {"llm_judge_falloesung"}
        )

    def test_error_dict_does_not_count(self):
        assert not row_has_real_score_for(
            {"llm_judge_falloesung": {"error": "boom", "value": None}},
            {"llm_judge_falloesung"},
        )

    def test_bare_float_counts(self):
        assert row_has_real_score_for({"exact_match": 1.0}, {"exact_match"})

    def test_bool_does_not_count_as_numeric(self):
        assert not row_has_real_score_for({"exact_match": True}, {"exact_match"})

    def test_missing_metric_and_non_dict(self):
        assert not row_has_real_score_for({"other": 0.5}, {"exact_match"})
        assert not row_has_real_score_for(None, {"exact_match"})


class TestEligibleConfigs:
    def test_filters_disabled_and_human_graded(self):
        project = SimpleNamespace(
            evaluation_config={
                "evaluation_configs": [
                    {"metric": "llm_judge_falloesung", "enabled": True},
                    {"metric": "korrektur_falloesung", "enabled": True},   # human-graded → excluded
                    {"metric": "exact_match", "enabled": False},           # disabled → excluded
                    {"metric": "exact_match", "enabled": True},            # eligible
                ]
            }
        )
        cfgs = eligible_configs(project)
        metrics = eligible_metrics(cfgs)
        assert metrics == {"llm_judge_falloesung", "exact_match"}

    def test_reads_legacy_multi_field_key(self):
        project = SimpleNamespace(
            evaluation_config={
                "multi_field_evaluations": [
                    {"metric": "llm_judge_falloesung", "enabled": True},
                ]
            }
        )
        assert eligible_metrics(eligible_configs(project)) == {"llm_judge_falloesung"}

    def test_no_config_returns_empty(self):
        assert eligible_configs(SimpleNamespace(evaluation_config=None)) == []
        assert eligible_configs(SimpleNamespace(evaluation_config={})) == []
