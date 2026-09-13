"""Unit suite for ``services.grade_scale_recompute`` — the rewrite that
brings stored Notenpunkte onto a changed Notenschlüssel.

Everything here exercises the PURE planner ``_plan_row`` (no DB): it decides,
for one ``TaskEvaluation.metrics`` blob, whether the row is in scope, what the
rewritten document looks like, and what the row-level pass flag becomes. The
endpoint + persistence side lives in
``tests/integration/test_grade_scale_recompute_endpoints.py``.

Pinned here:
  * both stored lane shapes (``total_score``/``total_max`` vs a bare 0–100
    ``raw_score``)
  * rows without ``details.grade_points`` are never given one
  * ``judge_response`` (and the rest of the evidence) survives untouched
  * the ``<metric>_grade_points`` / ``<metric>_passed`` siblings are refreshed
    when present and never invented when absent
  * the row-level pass flag follows the recomputed grade
  * a rubric-level Notenschlüssel beats the default, and the exam key beats
    the rubric's
  * idempotence, and "already correct" counting as NOT stale
"""

import copy
from types import SimpleNamespace

import pytest

from rubric_structure import GRADE_SCALE_PRESETS, PERCENT_GRADE_UNIT
from services.grade_scale_recompute import (
    DEFAULT_TOTAL_POINTS,
    _blob_points_and_total,
    _plan_row,
    _row_grade_key,
    _scale_source,
    _Scan,
)

pytestmark = pytest.mark.unit


def _percent_key(preset: str):
    return {
        "unit": PERCENT_GRADE_UNIT,
        "preset": preset,
        "thresholds": list(GRADE_SCALE_PRESETS[preset]),
        "rounding": "floor",
        "pass_grade": 4,
    }


UEBUNGSKLAUSUR = {"grade_scale": _percent_key("uebungsklausur")}
STANDARD = {"grade_scale": _percent_key("standard")}

# An absolute (unit BE) per-sheet key on a 50-point Bewertungsbogen. 25 of 50
# points reach Notenpunkt 9 here — against Notenpunkt 4 under the platform
# default and Notenpunkt 6 under the Übungsklausur key, so which key won is
# readable straight off the number.
LEGACY_BE_KEY = {
    "unit": "BE",
    "thresholds": [2, 4, 6, 8, 10, 12, 14, 16, 18, 28, 30, 32, 34, 36, 38, 40, 42, 44],
    "rounding": "floor",
    "pass_grade": 4,
}


def _rubric(rubric_id="r1", total_points=100.0, grade_scale=None):
    return SimpleNamespace(id=rubric_id, total_points=total_points, grade_scale=grade_scale)


def _rubric_lane(grade_points=10, **details):
    """A stored ``llm_judge_rubric`` / ``korrektur_custom`` blob: 73.5 of 100."""
    blob_details = {
        "scores": {"a": 40.0, "b": 33.5},
        "rubric_id": "r1",
        "total_max": 100.0,
        "total_score": 73.5,
        "raw_output": "<the judge's verbatim answer>",
        "grade_points": grade_points,
        "passed": True,
    }
    blob_details.update(details)
    return {
        "llm_judge_rubric": {
            "value": 0.735,
            "method": "llm_judge_rubric",
            "details": blob_details,
            "error": None,
        },
        "raw_score": 0.735,
    }


def _falloesung_lane(grade_points=6, **details):
    """A stored ``llm_judge_falloesung`` blob: raw_score 58.5 on a 0–100 scale."""
    blob_details = {
        "passed": True,
        "raw_score": 58.5,
        "raw_output": "{...}",
        "grade_points": grade_points,
        "call_metadata": {"latency_ms": 1200},
        "judge_response": {"score": 58.5, "reasoning": "Aufbau überzeugt."},
    }
    blob_details.update(details)
    return {
        "llm_judge_falloesung": {
            "value": 0.585,
            "method": "llm_judge_falloesung",
            "details": blob_details,
            "error": None,
        }
    }


class TestBlobPointsAndTotal:
    def test_rubric_lane_uses_total_score_and_total_max(self):
        assert _blob_points_and_total({"total_score": 73.5, "total_max": 90.0}) == (73.5, 90.0)

    def test_falloesung_lane_falls_back_to_raw_score_on_100(self):
        assert _blob_points_and_total({"raw_score": 58.5}) == (58.5, DEFAULT_TOTAL_POINTS)

    def test_zero_or_broken_total_falls_back_to_100(self):
        assert _blob_points_and_total({"total_score": 40, "total_max": 0}) == (40.0, 100.0)
        assert _blob_points_and_total({"total_score": 40, "total_max": "90"}) == (40.0, 100.0)

    def test_no_points_at_all_is_not_measurable(self):
        assert _blob_points_and_total({"grade_points": 5}) is None
        # A bool is not a score.
        assert _blob_points_and_total({"total_score": True}) is None


class TestRowGradeKey:
    def test_known_metrics_follow_the_headline_precedence(self):
        assert _row_grade_key(["korrektur_custom", "llm_judge_falloesung"]) == (
            "llm_judge_falloesung"
        )

    def test_unknown_metrics_sort_after_known_ones_alphabetically(self):
        assert _row_grade_key(["zzz_metric", "llm_judge_rubric"]) == "llm_judge_rubric"
        assert _row_grade_key(["bbb", "aaa"]) == "aaa"


class TestRubricLane:
    def test_recomputes_a_stale_grade_against_the_exam_key(self):
        """The live dev case: 73.5 of 100 BE stored as 10, but the exam runs
        the Übungsklausur key, where 73 points are 12 Notenpunkte."""
        metrics = _rubric_lane(grade_points=10)
        in_scope, updated, row_passed, sources = _plan_row(
            metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()}
        )
        assert in_scope is True
        assert updated is not None
        assert updated["llm_judge_rubric"]["details"]["grade_points"] == 12
        assert updated["llm_judge_rubric"]["details"]["passed"] is True
        assert row_passed is True
        assert sources == {"project"}

    def test_a_correct_grade_is_not_stale(self):
        metrics = _rubric_lane(grade_points=12)
        in_scope, updated, row_passed, _ = _plan_row(
            metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()}
        )
        assert in_scope is True
        assert updated is None and row_passed is None

    def test_evidence_and_untouched_keys_survive_the_rewrite(self):
        metrics = _rubric_lane(grade_points=10)
        before = copy.deepcopy(metrics)
        _, updated, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        # The input document is never mutated in place.
        assert metrics == before
        details = updated["llm_judge_rubric"]["details"]
        assert details["scores"] == before["llm_judge_rubric"]["details"]["scores"]
        assert details["raw_output"] == "<the judge's verbatim answer>"
        assert details["total_score"] == 73.5 and details["total_max"] == 100.0
        assert updated["raw_score"] == 0.735
        assert updated["llm_judge_rubric"]["value"] == 0.735

    def test_idempotent_second_pass_changes_nothing(self):
        metrics = _rubric_lane(grade_points=10)
        _, once, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        in_scope, twice, row_passed, _ = _plan_row(
            once, True, UEBUNGSKLAUSUR, {"r1": _rubric()}
        )
        assert in_scope is True
        assert twice is None and row_passed is None


class TestFalloesungLane:
    def test_raw_score_without_a_total_grades_on_100(self):
        """58.5 → floor 58 → Notenpunkt 8 under the Übungsklausur key
        (stored 6 under the standard one)."""
        in_scope, updated, row_passed, sources = _plan_row(
            _falloesung_lane(grade_points=6), True, UEBUNGSKLAUSUR, {}
        )
        assert in_scope is True
        assert updated["llm_judge_falloesung"]["details"]["grade_points"] == 8
        assert row_passed is True
        assert sources == {"project"}

    def test_judge_response_is_evidence_and_is_never_touched(self):
        metrics = _falloesung_lane(grade_points=6)
        original = copy.deepcopy(metrics["llm_judge_falloesung"]["details"]["judge_response"])
        _, updated, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {})
        assert updated["llm_judge_falloesung"]["details"]["judge_response"] == original
        assert updated["llm_judge_falloesung"]["details"]["call_metadata"] == {
            "latency_ms": 1200
        }

    def test_a_grade_below_the_pass_mark_flips_the_row(self):
        """22.5 raw → floor 22 → Notenpunkt 1 on the standard key: below the
        pass mark of 4, so blob AND row are marked failed."""
        metrics = _falloesung_lane(grade_points=6, raw_score=22.5)
        in_scope, updated, row_passed, _ = _plan_row(metrics, True, STANDARD, {})
        assert in_scope is True
        assert updated["llm_judge_falloesung"]["details"]["grade_points"] == 1
        assert updated["llm_judge_falloesung"]["details"]["passed"] is False
        assert row_passed is False


class TestOutOfScopeRows:
    def test_a_blob_without_grade_points_is_never_given_one(self):
        """Legacy ``llm_judge_custom``: totals, but nobody ever turned them
        into Notenpunkte. Minting a grade here would invent an assessment."""
        metrics = {
            "llm_judge_custom": {
                "value": 0.4,
                "method": "llm_judge_custom",
                "details": {"total_score": 40.0, "total_max": 100.0, "scores": {}},
                "error": None,
            },
            "raw_score": 0.4,
        }
        in_scope, updated, row_passed, sources = _plan_row(metrics, False, UEBUNGSKLAUSUR, {})
        assert in_scope is False
        assert updated is None and row_passed is None and sources == set()

    def test_rows_without_object_metrics_are_skipped(self):
        for metrics in (None, [], "nope", 3):
            assert _plan_row(metrics, True, UEBUNGSKLAUSUR, {}) == (False, None, None, set())

    def test_deterministic_metrics_are_untouched(self):
        metrics = {"bleu": {"value": 0.3, "method": "bleu", "details": {}, "error": None}}
        assert _plan_row(metrics, True, UEBUNGSKLAUSUR, {})[0] is False

    def test_a_graded_blob_without_points_counts_as_graded_but_cannot_move(self):
        metrics = {
            "korrektur_falloesung": {
                "value": 0.5,
                "method": "korrektur_falloesung",
                "details": {"grade_points": 9, "passed": True},
                "error": None,
            }
        }
        in_scope, updated, row_passed, sources = _plan_row(metrics, True, UEBUNGSKLAUSUR, {})
        assert in_scope is True
        assert updated is None and row_passed is None and sources == set()


class TestSiblingMetrics:
    def test_siblings_are_refreshed_when_the_writer_put_them_there(self):
        metrics = _rubric_lane(grade_points=10)
        metrics["llm_judge_rubric_grade_points"] = 10.0
        metrics["llm_judge_rubric_passed"] = 1.0
        _, updated, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert updated["llm_judge_rubric_grade_points"] == 12.0
        assert updated["llm_judge_rubric_passed"] == 1.0

    def test_the_passed_sibling_follows_a_failing_grade(self):
        metrics = _rubric_lane(grade_points=12, total_score=5.0)
        metrics["llm_judge_rubric_grade_points"] = 12.0
        metrics["llm_judge_rubric_passed"] = 1.0
        _, updated, row_passed, _ = _plan_row(
            metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()}
        )
        assert updated["llm_judge_rubric_grade_points"] == 0.0
        assert updated["llm_judge_rubric_passed"] == 0.0
        assert row_passed is False

    def test_siblings_are_not_invented_where_they_do_not_exist(self):
        metrics = _rubric_lane(grade_points=10)
        _, updated, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert "llm_judge_rubric_grade_points" not in updated
        assert "llm_judge_rubric_passed" not in updated

    def test_a_sibling_only_stale_value_makes_the_row_stale(self):
        """The grade itself is right but the flat sibling lagged behind —
        readers that prefer the sibling would still show the old number."""
        metrics = _rubric_lane(grade_points=12)
        metrics["llm_judge_rubric_grade_points"] = 10.0
        _, updated, _, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert updated is not None
        assert updated["llm_judge_rubric_grade_points"] == 12.0


class TestGradeScaleSource:
    def test_a_rubric_key_beats_the_platform_default(self):
        """No exam key: the sheet's own absolute (BE) Notenschlüssel governs.
        25 of 50 is Notenpunkt 9 there, 4 under the default table."""
        metrics = _rubric_lane(grade_points=4, total_score=25.0, total_max=50.0)
        rubric = _rubric(total_points=50.0, grade_scale=LEGACY_BE_KEY)
        in_scope, updated, _, sources = _plan_row(metrics, True, {}, {"r1": rubric})
        assert in_scope is True
        assert updated["llm_judge_rubric"]["details"]["grade_points"] == 9
        assert sources == {"rubric"}

    def test_the_exam_key_beats_the_sheets_own(self):
        metrics = _rubric_lane(grade_points=9, total_score=25.0, total_max=50.0)
        rubric = _rubric(total_points=50.0, grade_scale=LEGACY_BE_KEY)
        # 25 of 50 = 50 % → Notenpunkt 6 on the Übungsklausur key.
        _, updated, _, sources = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": rubric})
        assert updated["llm_judge_rubric"]["details"]["grade_points"] == 6
        assert sources == {"project"}

    def test_without_any_key_the_default_table_applies(self):
        metrics = _rubric_lane(grade_points=4, total_score=25.0, total_max=50.0)
        _, updated, _, sources = _plan_row(metrics, True, {}, {"r1": _rubric(total_points=50.0)})
        assert updated is None  # 25 of 50 already IS Notenpunkt 4 by default
        assert sources == {"default"}

    def test_the_stored_source_label_is_refreshed_but_never_invented(self):
        with_label = _rubric_lane(grade_points=10, grade_scale_source="default")
        _, updated, _, _ = _plan_row(with_label, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert updated["llm_judge_rubric"]["details"]["grade_scale_source"] == "project"

        without_label = _rubric_lane(grade_points=10)
        _, updated2, _, _ = _plan_row(without_label, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert "grade_scale_source" not in updated2["llm_judge_rubric"]["details"]


class TestRowLevelPassed:
    def test_the_row_flag_follows_the_grade_even_when_the_grade_is_right(self):
        metrics = _rubric_lane(grade_points=12)
        in_scope, updated, row_passed, _ = _plan_row(
            metrics, False, UEBUNGSKLAUSUR, {"r1": _rubric()}
        )
        assert in_scope is True
        assert row_passed is True
        # The blob's own numbers are already correct; only the row flag moved.
        assert updated["llm_judge_rubric"]["details"]["grade_points"] == 12

    def test_the_headline_metric_decides_when_a_row_carries_several(self):
        metrics = _falloesung_lane(grade_points=6)
        metrics.update(_rubric_lane(grade_points=12))
        _, _, row_passed, _ = _plan_row(metrics, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        # llm_judge_falloesung outranks llm_judge_rubric; 58.5 → NP 8 → passed.
        assert row_passed is True

    def test_a_blob_passed_flag_is_added_only_when_the_grade_moves(self):
        moved = _rubric_lane(grade_points=10)
        del moved["llm_judge_rubric"]["details"]["passed"]
        _, updated, _, _ = _plan_row(moved, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert updated["llm_judge_rubric"]["details"]["passed"] is True

        steady = _rubric_lane(grade_points=12)
        del steady["llm_judge_rubric"]["details"]["passed"]
        _, updated2, _, _ = _plan_row(steady, True, UEBUNGSKLAUSUR, {"r1": _rubric()})
        assert updated2 is None


class TestScaleSourceReport:
    def test_an_exam_key_always_reports_project(self):
        project = SimpleNamespace(id="p", evaluation_config=dict(UEBUNGSKLAUSUR))
        assert _scale_source(project, _Scan(sources={"rubric"})) == "project"

    def test_a_sheet_key_reports_rubric(self):
        project = SimpleNamespace(id="p", evaluation_config={})
        assert _scale_source(project, _Scan(sources={"rubric", "default"})) == "rubric"

    def test_nothing_stored_reports_default(self):
        project = SimpleNamespace(id="p", evaluation_config=None)
        assert _scale_source(project, _Scan(sources={"default"})) == "default"
        assert _scale_source(project, _Scan()) == "default"
