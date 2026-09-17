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
    gradable_configs,
    parse_annotation_results,
    resolve_human_prediction,
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


def _cfg(*fields, metric="llm_judge_falloesung"):
    return {"id": f"{metric}-1", "metric": metric, "prediction_fields": list(fields)}


class TestResolveHumanPrediction:
    """The one resolver the worker and the dispatcher share (prod: the sweep
    re-dispatched 14 annotations every hour because the worker skipped every
    config while the dispatcher did not know it would)."""

    def test_bare_and_prefixed_field(self):
        results = {"loesung": "Antwort"}
        assert resolve_human_prediction(_cfg("loesung"), results) == "Antwort"
        assert resolve_human_prediction(_cfg("human:loesung"), results) == "Antwort"

    def test_empty_and_whitespace_text_is_no_answer(self):
        assert resolve_human_prediction(_cfg("human:loesung"), {"loesung": ""}) is None
        assert resolve_human_prediction(_cfg("human:loesung"), {"loesung": " \n "}) is None

    def test_missing_field_is_no_answer(self):
        results = {"notizen": "x", "gliederung": "y"}
        assert resolve_human_prediction(_cfg("human:loesung"), results) is None

    def test_model_selectors_never_resolve(self):
        # Prod "Test" project: a real answer under `answer`, but every config
        # reads `__all_model__` only.
        results = {"answer": "Nein, belastendes Gewohnheitsrecht ..."}
        assert resolve_human_prediction(_cfg("__all_model__"), results) is None
        assert resolve_human_prediction(_cfg("model:answer"), results) is None

    def test_first_field_with_an_answer_wins(self):
        cfg = _cfg("__all_model__", "human:loesung")
        assert resolve_human_prediction(cfg, {"loesung": "L"}) == "L"
        cfg = _cfg("human:leer", "human:loesung")
        assert resolve_human_prediction(cfg, {"leer": "", "loesung": "L"}) == "L"

    def test_all_human_joins_non_empty_fields(self):
        cfg = _cfg("__all_human__")
        assert resolve_human_prediction(cfg, {"a": "x", "b": "", "c": "y"}) == "a: x\n\nc: y"
        assert resolve_human_prediction(cfg, {"a": "", "b": "  "}) is None
        assert resolve_human_prediction(cfg, {}) is None

    def test_rating_zero_is_an_answer_but_bool_and_empty_list_are_not(self):
        assert resolve_human_prediction(_cfg("r"), {"r": 0}) == 0
        assert resolve_human_prediction(_cfg("r"), {"r": False}) is None
        assert resolve_human_prediction(_cfg("r"), {"r": []}) is None
        assert resolve_human_prediction(_cfg("r"), {"r": ["a", "b"]}) == ["a", "b"]

    def test_tolerates_missing_or_odd_fields(self):
        assert resolve_human_prediction({"metric": "x"}, {"a": "b"}) is None
        assert resolve_human_prediction({"prediction_fields": None}, {"a": "b"}) is None
        assert resolve_human_prediction(_cfg("a"), None) is None


class TestGradableConfigs:
    def test_keeps_only_configs_with_an_answer(self):
        with_answer = _cfg("human:loesung")
        model_only = _cfg("__all_model__", metric="llm_judge_lexam")
        other_field = _cfg("human:gliederung", metric="rouge")
        results = {"loesung": "L", "gliederung": ""}
        assert gradable_configs([with_answer, model_only, other_field], results) == [
            with_answer
        ]

    def test_prod_shapes_have_nothing_to_grade(self):
        cfgs = [_cfg("human:loesung"), _cfg("loesung"), _cfg("__all_model__")]
        for result in (
            [],
            [{"type": "textarea", "value": "", "to_name": "text", "from_name": "loesung"}],
            [{"type": "textarea", "value": "", "to_name": "text", "from_name": "notizen"}],
        ):
            ann = SimpleNamespace(result=result)
            assert gradable_configs(cfgs, parse_annotation_results(ann)) == []

    def test_empty_inputs(self):
        assert gradable_configs([], {"a": "b"}) == []
        assert gradable_configs(None, {"a": "b"}) == []
