"""Why a run that dispatched no cell says what it says.

Background
----------
An evaluation run that matched nothing used to be stored exactly like a run
that had nothing left to do: ``completed``, zero samples, and
``has_sample_results`` set to True. In the UI both rendered as "no results for
this configuration". A production Bewertungsbogen run therefore graded nothing
and reported success, and the cause took a manual database trawl to find.

``_classify_config_match`` turns "0 cells" into one whitelisted reason, and
``_summarize_config_match`` decides whether those reasons should fail the run.
The split that matters is benign versus blocking: "everything was already
graded" must stay ``completed``, everything else must fail loudly.

Pure functions, no DB - the orchestrator paths that feed them are covered in
``tests/integration/test_orchestration_branches_e2e.py``.
"""

import pytest
from tasks import (
    _BENIGN_MATCH_REASONS,
    _CONFIG_MATCH_REASONS,
    _classify_config_match,
    _summarize_config_match,
)


def side(metric="exact_match", human=(), llm=(), config_id="cfg1", name=None):
    return {
        "config_id": config_id,
        "metric": metric,
        "display_name": name,
        "human_fields": list(human),
        "llm_fields": list(llm),
    }


def classify(cfg, **over):
    base = {
        "gen_cells": [],
        "ann_cells": [],
        "gen_pool_scoped": 0,
        "gen_pool_raw": 0,
        "ann_pool_scoped": 0,
        "ann_pool_raw": 0,
        "ann_pre_filter": 0,
        "missing_only": True,
        "generation_filters_active": False,
        "annotator_filter_active": False,
        "classifier_unavailable": False,
    }
    base.update(over)
    return _classify_config_match(cfg, **base)


class TestMatched:
    def test_a_config_that_produced_generation_cells_has_no_reason(self):
        assert classify(side(llm=["__all_model__"]), gen_cells=[("t", "g", [])]) is None

    def test_a_config_that_produced_annotation_cells_has_no_reason(self):
        assert classify(side(human=["loesung"]), ann_cells=[("t", "a", [])]) is None

    def test_a_both_sided_config_matches_if_either_side_did(self):
        cfg = side(human=["human:a"], llm=["model:b"])
        assert classify(cfg, ann_cells=[("t", "a", [])]) is None
        assert classify(cfg, gen_cells=[("t", "g", [])]) is None


class TestTheProductionCase:
    def test_model_side_config_in_a_project_with_only_annotations(self):
        """The exact shape that shipped: the judge was pointed at model
        generations an exam never has."""
        reason = classify(side(llm=["__all_model__"]), ann_pool_scoped=1)
        assert reason == "no_generations"

    def test_that_reason_is_blocking(self):
        assert "no_generations" not in _BENIGN_MATCH_REASONS


class TestGenerationSide:
    def test_subjects_existed_and_were_all_already_graded(self):
        assert (
            classify(side(llm=["__all_model__"]), gen_pool_scoped=3)
            == "all_cells_already_evaluated"
        )

    def test_filters_excluded_every_generation(self):
        assert (
            classify(
                side(llm=["__all_model__"]),
                gen_pool_raw=5,
                generation_filters_active=True,
            )
            == "generation_filters_excluded_all"
        )


class TestAnnotationSide:
    def test_no_annotations_at_all(self):
        assert classify(side(human=["loesung"])) == "no_annotations"

    def test_every_annotation_cancelled(self):
        assert (
            classify(side(human=["loesung"]), ann_pool_raw=2)
            == "all_annotations_cancelled"
        )

    def test_annotator_filter_excluded_everyone(self):
        assert (
            classify(
                side(human=["loesung"]),
                ann_pre_filter=4,
                annotator_filter_active=True,
            )
            == "annotator_filter_excluded_all"
        )


class TestForceRerunSemantics:
    def test_already_evaluated_requires_missing_only(self):
        """Under a forced rerun no skip set is built, so subjects that exist
        with no cells cannot mean "already graded" - it is a real mismatch and
        must not be excused as benign."""
        cfg = side(llm=["__all_model__"])
        assert classify(cfg, gen_pool_scoped=3, missing_only=True) == (
            "all_cells_already_evaluated"
        )
        assert classify(cfg, gen_pool_scoped=3, missing_only=False) == "other"


class TestBenignAndDefensive:
    def test_human_graded_metrics_are_never_dispatched(self):
        assert classify(side(metric="korrektur_custom")) == "manual_metric"
        assert "manual_metric" in _BENIGN_MATCH_REASONS

    def test_a_config_with_no_prediction_fields(self):
        assert classify(side()) == "no_prediction_fields"

    def test_a_worker_that_cannot_classify_says_so(self):
        """This used to silently skip the whole annotation pass."""
        assert (
            classify(side(human=["loesung"]), classifier_unavailable=True)
            == "classifier_unavailable"
        )


@pytest.mark.parametrize(
    "cfg,over",
    [
        (side(llm=["__all_model__"]), {}),
        (side(human=["loesung"]), {}),
        (side(metric="korrektur_custom"), {}),
        (side(), {}),
        (side(llm=["x"]), {"gen_pool_scoped": 2}),
        (side(human=["y"]), {"ann_pool_raw": 2}),
        (side(llm=["x"]), {"classifier_unavailable": True}),
    ],
)
def test_every_emitted_reason_is_whitelisted(cfg, over):
    """Same discipline as the failure buckets: an unrecognised situation must
    land in `other`, never grow the metadata with free text."""
    reason = classify(cfg, **over)
    assert reason is None or reason in _CONFIG_MATCH_REASONS


class TestSummary:
    def test_benign_reasons_do_not_fail_the_run(self):
        records = [
            {**side(config_id="a"), "reason": "all_cells_already_evaluated"},
            {**side(config_id="b", metric="korrektur_custom"), "reason": "manual_metric"},
        ]
        should_fail, message = _summarize_config_match(records)
        assert should_fail is False
        assert message == ""

    def test_one_blocking_reason_fails_and_explains(self):
        records = [
            {
                **side(config_id="c1", metric="llm_judge_rubric", llm=["__all_model__"],
                       name="Bewertungsbogen (gpt-5-mini)"),
                "reason": "no_generations",
            }
        ]
        should_fail, message = _summarize_config_match(records)
        assert should_fail is True
        # Names the config, the metric, the reason, the offending selector,
        # and what to do about it.
        assert "Bewertungsbogen (gpt-5-mini)" in message
        assert "llm_judge_rubric" in message
        assert "no_generations" in message
        assert "__all_model__" in message
        assert "human:" in message

    def test_a_partially_matched_run_still_reports_the_unmatched_one(self):
        records = [
            {**side(config_id="ok", llm=["__all_model__"]), "reason": None},
            {**side(config_id="bad", human=["loesung"]), "reason": "no_annotations"},
        ]
        should_fail, message = _summarize_config_match(records)
        assert should_fail is True
        assert "1 of 2 configs matched" in message

    def test_the_message_stays_bounded(self):
        records = [
            {**side(config_id=f"c{i}", llm=["__all_model__"]), "reason": "no_generations"}
            for i in range(6)
        ]
        should_fail, message = _summarize_config_match(records)
        assert should_fail is True
        assert len(message) <= 500
        assert "[+4 more]" in message


class TestTheMessageNamesTheOtherSide:
    """The side-mismatch reasons say what the other side holds and which
    selector would grade it. On prod an exam's judge aimed at '__all_model__'
    was told only that there were no generations, never that the exam had
    submitted answers it could have graded."""

    @staticmethod
    def _model_side_rubric():
        return [
            {
                **side(config_id="c1", metric="llm_judge_rubric",
                       llm=["__all_model__"], name="Bewertungsbogen"),
                "reason": "no_generations",
            }
        ]

    @staticmethod
    def _human_side_config():
        return [{**side(config_id="h1", human=["loesung"]), "reason": "no_annotations"}]

    def test_a_model_side_config_in_a_project_with_answers(self):
        should_fail, message = _summarize_config_match(
            self._model_side_rubric(), subject_counts={"generations": 0, "answers": 3}
        )
        assert should_fail is True
        assert "3 submitted answer(s)" in message
        assert "'human:loesung'" in message
        assert "'__all_human__'" in message

    def test_a_model_side_config_in_a_project_with_nothing_yet(self):
        _, message = _summarize_config_match(
            self._model_side_rubric(), subject_counts={"generations": 0, "answers": 0}
        )
        assert "nothing to grade on either side" in message
        assert "submitted answer(s):" not in message

    def test_a_human_side_config_in_a_project_with_generations(self):
        _, message = _summarize_config_match(
            self._human_side_config(), subject_counts={"generations": 2, "answers": 0}
        )
        assert "2 model generation(s)" in message
        assert "'model:<field>'" in message
        assert "'__all_model__'" in message

    def test_a_human_side_config_in_a_project_with_nothing_yet(self):
        _, message = _summarize_config_match(
            self._human_side_config(), subject_counts={"generations": 0, "answers": 0}
        )
        assert "nothing to grade on either side" in message
        assert "model generation(s):" not in message

    def test_without_counts_the_general_advice_stays(self):
        _, message = _summarize_config_match(self._model_side_rubric())
        assert "Generate responses first" in message
        assert "human:" in message

    def test_other_reasons_ignore_the_counts(self):
        records = [
            {**side(config_id="f1", llm=["__all_model__"]),
             "reason": "generation_filters_excluded_all"},
        ]
        _, message = _summarize_config_match(
            records, subject_counts={"generations": 5, "answers": 7}
        )
        assert "filters excluded every one of them" in message
        assert "submitted answer" not in message

    def test_the_message_stays_bounded_with_counts(self):
        records = [
            {**side(config_id=f"c{i}", llm=["__all_model__"],
                    name="A rather long evaluation display name"),
             "reason": "no_generations"}
            for i in range(4)
        ]
        should_fail, message = _summarize_config_match(
            records, subject_counts={"generations": 0, "answers": 12}
        )
        assert should_fail is True
        assert len(message) <= 500
