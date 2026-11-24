"""The pure rules of shared/grading_basis.py: fingerprints, stamps, verdicts."""

import copy

import pytest

import grading_basis as gb
from grading_basis import (
    FINGERPRINT_KEY,
    REASON_SCHEME,
    REASON_SHEET,
    metric_details,
    outdated_reason,
    register_grading_basis,
    scheme_fingerprint,
    scheme_keys_for,
    stamp_grading_basis,
    stamp_rows,
    unregister_grading_basis,
)


def _judge(**params):
    return {"id": "c1", "metric": "llm_judge_custom", "metric_parameters": params}


@pytest.fixture()
def registered():
    names = []

    def _register(metric, **kwargs):
        register_grading_basis(metric, **kwargs)
        names.append(metric)

    yield _register
    for name in names:
        unregister_grading_basis(name)


class TestSchemeFingerprint:
    def test_stable_and_blind_to_judge_settings(self):
        base = _judge(custom_criteria={"a": 1}, judge_model="gpt-4o", temperature=0)
        other_judge = _judge(custom_criteria={"a": 1}, judge_model="claude", seed=7, runs_per_judge=3)
        assert scheme_fingerprint(base) == scheme_fingerprint(other_judge)
        assert len(scheme_fingerprint(base)) == 32

    def test_changes_with_the_scheme(self):
        assert scheme_fingerprint(_judge(custom_criteria={"a": 1})) != scheme_fingerprint(
            _judge(custom_criteria={"a": 2})
        )
        assert scheme_fingerprint(_judge(custom_prompt_template="x")) != scheme_fingerprint(
            _judge(custom_prompt_template="y")
        )

    def test_unset_empty_and_default_values_are_the_same_scheme(self):
        plain = scheme_fingerprint(_judge())
        assert scheme_fingerprint(_judge(score_scale="1-5")) == plain
        assert scheme_fingerprint(_judge(custom_criteria=None, dimensions=[])) == plain
        assert scheme_fingerprint(_judge(use_task_rubric=False)) == plain
        assert scheme_fingerprint(_judge(score_scale="0-1")) != plain

    def test_metrics_without_a_scheme_have_no_fingerprint(self):
        assert scheme_keys_for("bleu") is None
        assert scheme_fingerprint({"id": "c", "metric": "bleu", "metric_parameters": {"x": 1}}) is None
        assert scheme_fingerprint({"id": "c", "metric": "korrektur_custom"}) is None
        assert scheme_fingerprint(None) is None

    def test_a_registered_metric_uses_its_own_keys(self, registered):
        registered("korrektur_custom", scheme_keys=("bareme",))
        registered("llm_judge_custom", scheme_keys=("bareme",))
        human = {"id": "h", "metric": "korrektur_custom", "metric_parameters": {"bareme": [1]}}
        assert scheme_fingerprint(human) is not None
        # The registration replaces the platform's judge keys.
        assert scheme_fingerprint(_judge(custom_criteria={"a": 1})) == scheme_fingerprint(_judge())

    def test_a_package_that_is_off_tracks_nothing(self, registered, monkeypatch):
        registered("llm_judge_custom", scheme_keys=("bareme",))
        monkeypatch.setitem(
            gb._SPECS, "llm_judge_custom",
            gb.GradingBasisSpec(scheme_keys=("bareme",), owner="some_overlay"),
        )
        monkeypatch.setattr(gb, "_owner_active", lambda owner: False)
        assert scheme_keys_for("llm_judge_custom") is None
        assert scheme_fingerprint(_judge()) is None


class TestStamp:
    def test_unified_blob_gets_the_fingerprint_in_its_details(self):
        config = _judge(custom_criteria={"a": 1})
        metrics = {"llm_judge_custom": {"value": 0.7, "details": {"rubric_id": "r1"}}}
        before = copy.deepcopy(metrics)

        out = stamp_grading_basis(metrics, config)

        assert metrics == before  # the input is never changed
        details = out["llm_judge_custom"]["details"]
        assert details == {"rubric_id": "r1", FINGERPRINT_KEY: scheme_fingerprint(config)}
        assert "review" not in details

    def test_flat_row_gets_a_details_sibling(self):
        config = _judge()
        out = stamp_grading_basis({"llm_judge_custom": 0.5, "raw_score": 0.5}, config)
        assert out["llm_judge_custom"] == 0.5
        assert out["llm_judge_custom_details"] == {FINGERPRINT_KEY: scheme_fingerprint(config)}
        assert metric_details(out, "llm_judge_custom")[FINGERPRINT_KEY]

    def test_regrade_writes_a_draft_except_on_a_failed_result(self):
        config = _judge()
        good = stamp_grading_basis({"llm_judge_custom": {"value": 0.5}}, config, regrade=True)
        assert good["llm_judge_custom"]["details"]["review"] == {"status": "draft", "reason": "regrade"}
        failed = stamp_grading_basis(
            {"llm_judge_custom": {"value": None, "error": "boom"}}, config, regrade=True
        )
        assert "review" not in failed["llm_judge_custom"]["details"]
        flat_failed = stamp_grading_basis({"llm_judge_custom": None}, config, regrade=True)
        assert "review" not in flat_failed["llm_judge_custom_details"]

    def test_regrade_replaces_a_release_the_judge_wrote(self):
        config = {"id": "f", "metric": "llm_judge_feedback", "metric_parameters": {}}
        metrics = {"llm_judge_feedback": {"value": None, "details": {
            "feedback_only": True, "review": {"status": "released", "released_by": "judge"}}}}
        out = stamp_grading_basis(metrics, config, regrade=True)
        assert out["llm_judge_feedback"]["details"]["review"] == {"status": "draft", "reason": "regrade"}

    def test_nothing_to_stamp_returns_the_same_object(self):
        metrics = {"bleu": {"value": 0.4}}
        assert stamp_grading_basis(metrics, {"id": "b", "metric": "bleu"}) is metrics
        empty = {}
        assert stamp_grading_basis(empty, _judge()) is empty

    def test_only_answer_rows_become_drafts(self):
        config = _judge()
        rows = [
            {"evaluation_config_id": "c1", "annotation_id": "a", "metrics": {"llm_judge_custom": {"value": 1.0}}},
            {"evaluation_config_id": "c1", "generation_id": "g", "metrics": {"llm_judge_custom": {"value": 1.0}}},
            {"evaluation_config_id": "other", "annotation_id": "a", "metrics": {"llm_judge_custom": {"value": 1.0}}},
        ]
        stamp_rows(rows, [config], regrade=True)
        answer, model, unknown = (r["metrics"]["llm_judge_custom"] for r in rows)
        assert answer["details"]["review"]["status"] == "draft"
        assert "review" not in model["details"] and model["details"][FINGERPRINT_KEY]
        assert "details" not in unknown


class TestOutdatedReason:
    def test_another_sheet_now(self):
        stored = {"rubric_id": "old", FINGERPRINT_KEY: "fp"}
        assert outdated_reason(stored, _judge(), current_rubric_id="new", current_fingerprint="fp") == REASON_SHEET
        assert outdated_reason(stored, _judge(), current_rubric_id="old", current_fingerprint="fp") is None
        # No usable sheet now: nothing to re-grade along.
        assert outdated_reason(stored, _judge(), current_rubric_id=None, current_fingerprint="fp") is None

    def test_another_scheme_now(self):
        stored = {FINGERPRINT_KEY: "old"}
        assert outdated_reason(stored, _judge(), current_rubric_id=None, current_fingerprint="new") == REASON_SCHEME
        assert outdated_reason(stored, _judge(), current_rubric_id=None, current_fingerprint="old") is None
        # A metric that is not tracked now cannot be compared.
        assert outdated_reason(stored, _judge(), current_rubric_id=None, current_fingerprint=None) is None

    def test_rows_without_a_fingerprint_ask_the_owning_package(self, registered):
        config = {"id": "f", "metric": "llm_judge_feedback", "metric_parameters": {"bareme": [2]}}
        assert outdated_reason({}, config, current_rubric_id=None, current_fingerprint="x") is None

        seen = []

        def legacy(stored, cfg):
            seen.append(stored)
            return stored["bareme"] != cfg["metric_parameters"]["bareme"]

        registered("llm_judge_feedback", scheme_keys=("bareme",), legacy_keys=("bareme",),
                   legacy_outdated=legacy)
        stale = {"bareme": [1], "noise": "x"}
        assert outdated_reason(stale, config, current_rubric_id=None, current_fingerprint="x") == REASON_SCHEME
        assert seen == [{"bareme": [1]}]  # only the declared keys reach it
        assert outdated_reason({"bareme": [2]}, config, current_rubric_id=None, current_fingerprint="x") is None

    def test_a_failing_legacy_check_counts_as_current(self, registered):
        def broken(stored, cfg):
            raise RuntimeError("boom")

        registered("llm_judge_feedback", scheme_keys=(), legacy_outdated=broken)
        config = {"id": "f", "metric": "llm_judge_feedback"}
        assert outdated_reason({}, config, current_rubric_id=None, current_fingerprint="x") is None
