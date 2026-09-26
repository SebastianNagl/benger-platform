"""The Notenschlüssel audit trail helper.

``services/shared/grade_scale_history.py`` is the ONE place both writers of
``evaluation_config.grade_scale`` append through — the platform eval-config
PUT and the extended exam router. These tests pin the rules that make the
trail trustworthy: an entry only for a real change, newest last, a hard cap,
purity (the caller's document is never mutated), and the recompute stamp.
"""

import pytest

from grade_scale_history import (
    GRADE_SCALE_KEY,
    HISTORY_KEY,
    MAX_HISTORY_ENTRIES,
    append_grade_scale_change,
    apply_grade_scale_write,
    carry_grade_scale_history,
    grade_scale_changed,
    latest_grade_scale_change,
    mark_recomputed,
)


def _scale(preset="standard", pass_grade=4, thresholds=None):
    return {
        "unit": "percent",
        "preset": preset,
        "thresholds": thresholds or list(range(1, 19)),
        "rounding": "floor",
        "pass_grade": pass_grade,
    }


class TestAppendOnlyOnARealChange:
    def test_setting_a_key_on_a_default_project_records_from_null(self):
        out = append_grade_scale_change(
            {}, old=None, new=_scale(), actor_id="user-1"
        )
        entry = out[HISTORY_KEY][-1]
        assert entry["from"] is None
        assert entry["to"]["preset"] == "standard"
        assert entry["changed_by"] == "user-1"
        assert entry["recomputed"] is None
        assert entry["changed_at"]

    def test_clearing_the_key_records_to_null(self):
        out = append_grade_scale_change(
            {}, old=_scale(), new=None, actor_id="user-1"
        )
        entry = out[HISTORY_KEY][-1]
        assert entry["from"]["preset"] == "standard"
        assert entry["to"] is None

    def test_resaving_the_same_key_records_nothing(self):
        config = append_grade_scale_change(
            {}, old=None, new=_scale(), actor_id="user-1"
        )
        again = append_grade_scale_change(
            config, old=_scale(), new=_scale(), actor_id="user-2"
        )
        assert len(again[HISTORY_KEY]) == 1

    def test_a_saved_key_that_only_differs_in_number_type_is_not_a_change(self):
        ints = _scale(thresholds=[float(i) for i in range(1, 19)])
        floats = _scale(thresholds=list(range(1, 19)))
        assert append_grade_scale_change(
            {}, old=ints, new=floats, actor_id="u"
        ) == {}

    def test_a_project_that_never_had_a_key_keeps_a_clean_config(self):
        # Saving some OTHER evaluation setting must not plant an empty list.
        out = append_grade_scale_change(
            {"runs_per_task": 2}, old=None, new=None, actor_id="user-1"
        )
        assert out == {"runs_per_task": 2}
        assert HISTORY_KEY not in out

    def test_renaming_the_preset_is_a_change(self):
        # Same numbers, different policy label — the trail records it.
        out = append_grade_scale_change(
            {},
            old=_scale(preset="custom"),
            new=_scale(preset="standard"),
            actor_id="u",
        )
        assert out[HISTORY_KEY][-1]["from"]["preset"] == "custom"

    def test_a_changed_pass_grade_is_a_change(self):
        out = append_grade_scale_change(
            {}, old=_scale(pass_grade=4), new=_scale(pass_grade=5), actor_id="u"
        )
        assert len(out[HISTORY_KEY]) == 1

    def test_an_anonymous_actor_is_recorded_as_null(self):
        out = append_grade_scale_change({}, old=None, new=_scale(), actor_id=None)
        assert out[HISTORY_KEY][-1]["changed_by"] is None


class TestOrderAndCap:
    def test_newest_is_last(self):
        config = {}
        for grade in range(0, 5):
            config = append_grade_scale_change(
                config,
                old=_scale(pass_grade=grade),
                new=_scale(pass_grade=grade + 1),
                actor_id=f"u{grade}",
            )
        assert [e["changed_by"] for e in config[HISTORY_KEY]] == [
            "u0", "u1", "u2", "u3", "u4"
        ]

    def test_the_list_is_capped_and_drops_from_the_front(self):
        config = {}
        for grade in range(0, MAX_HISTORY_ENTRIES + 5):
            config = append_grade_scale_change(
                config,
                old=_scale(thresholds=[grade + 1] * 18),
                new=_scale(thresholds=[grade + 2] * 18),
                actor_id=f"u{grade}",
            )
        entries = config[HISTORY_KEY]
        assert len(entries) == MAX_HISTORY_ENTRIES
        assert entries[0]["changed_by"] == "u5"
        assert entries[-1]["changed_by"] == f"u{MAX_HISTORY_ENTRIES + 4}"


class TestPurity:
    def test_the_input_document_is_never_mutated(self):
        config = {"grade_scale": _scale()}
        snapshot = {"grade_scale": _scale()}
        out = append_grade_scale_change(
            config, old=None, new=_scale(), actor_id="u"
        )
        assert config == snapshot
        assert out is not config

    def test_the_existing_history_is_not_mutated_in_place(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        before = list(config[HISTORY_KEY])
        mark_recomputed(config, 7)
        assert config[HISTORY_KEY] == before

    def test_a_none_config_is_accepted(self):
        out = append_grade_scale_change(None, old=None, new=_scale(), actor_id="u")
        assert len(out[HISTORY_KEY]) == 1


class TestMarkRecomputed:
    def test_stamps_the_newest_entry(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        stamped = mark_recomputed(config, 13)
        assert stamped[HISTORY_KEY][-1]["recomputed"] == 13

    def test_only_the_newest_entry_is_stamped(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u1")
        config = append_grade_scale_change(
            config, old=_scale(), new=_scale(pass_grade=5), actor_id="u2"
        )
        stamped = mark_recomputed(config, 4)
        assert [e["recomputed"] for e in stamped[HISTORY_KEY]] == [None, 4]

    def test_a_second_run_accumulates_onto_the_same_entry(self):
        # "how many grades has this key change moved so far" — a second,
        # idempotent run must not overwrite the first run's count with 0.
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        config = mark_recomputed(config, 13)
        config = mark_recomputed(config, 0)
        assert config[HISTORY_KEY][-1]["recomputed"] == 13
        config = mark_recomputed(config, 2)
        assert config[HISTORY_KEY][-1]["recomputed"] == 15

    def test_a_run_that_moved_nothing_still_records_that_it_ran(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        assert mark_recomputed(config, 0)[HISTORY_KEY][-1]["recomputed"] == 0

    def test_a_project_without_history_is_left_alone(self):
        assert mark_recomputed({"runs_per_task": 1}, 5) == {"runs_per_task": 1}
        assert mark_recomputed(None, 5) == {}

    @pytest.mark.parametrize("count", [None, "nonsense", -3])
    def test_a_broken_count_never_corrupts_the_entry(self, count):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        assert mark_recomputed(config, count)[HISTORY_KEY][-1]["recomputed"] == 0


class TestLatest:
    def test_returns_the_newest_entry(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u1")
        config = append_grade_scale_change(
            config, old=_scale(), new=_scale(pass_grade=5), actor_id="u2"
        )
        assert latest_grade_scale_change(config)["changed_by"] == "u2"

    def test_none_for_an_untouched_project(self):
        assert latest_grade_scale_change({}) is None
        assert latest_grade_scale_change(None) is None
        assert latest_grade_scale_change({HISTORY_KEY: "not a list"}) is None

    def test_the_returned_entry_is_a_copy(self):
        config = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        latest_grade_scale_change(config)["changed_by"] = "tampered"
        assert config[HISTORY_KEY][-1]["changed_by"] == "u"


class TestCarryAcrossARebuild:
    def test_a_rebuilt_document_keeps_the_trail(self):
        # The extended exam editor replaces evaluation_config wholesale when
        # the grading MODE changes; the audit must survive that.
        old_config = append_grade_scale_change(
            {"evaluation_configs": ["falloesung pair"]},
            old=None,
            new=_scale(),
            actor_id="u",
        )
        rebuilt = carry_grade_scale_history(
            {"evaluation_configs": ["rubric pair"]}, old_config
        )
        assert rebuilt["evaluation_configs"] == ["rubric pair"]
        assert len(rebuilt[HISTORY_KEY]) == 1

    def test_carrying_nothing_leaves_no_empty_list(self):
        rebuilt = carry_grade_scale_history({"evaluation_configs": []}, {})
        assert HISTORY_KEY not in rebuilt


class TestGradeScaleChanged:
    """The one test of "the key moved" the writers gate their follow-ups on
    (the history entry, the re-rendered task-data mirrors)."""

    def test_same_key_is_no_change(self):
        assert not grade_scale_changed(_scale(), _scale())

    def test_number_type_and_stray_fields_are_no_change(self):
        ints = _scale(thresholds=[float(i) for i in range(1, 19)])
        assert not grade_scale_changed(ints, {**_scale(), "note": "x"})

    def test_no_key_on_both_sides_is_no_change(self):
        assert not grade_scale_changed(None, None)
        assert not grade_scale_changed(None, {"thresholds": "broken"})

    @pytest.mark.parametrize(
        "old,new",
        [
            (None, _scale()),
            (_scale(), None),
            (_scale(preset="custom"), _scale(preset="standard")),
            (_scale(pass_grade=4), _scale(pass_grade=5)),
            (_scale(), _scale(thresholds=list(range(2, 20)))),
        ],
    )
    def test_a_real_change(self, old, new):
        assert grade_scale_changed(old, new)


class TestApplyGradeScaleWrite:
    """What both platform writers (eval-config PUT, project PATCH) store."""

    def test_a_key_change_is_appended(self):
        stored = {"runs_per_task": 2}
        written = {"runs_per_task": 2, GRADE_SCALE_KEY: _scale()}
        out = apply_grade_scale_write(stored, written, actor_id="u")
        assert out[GRADE_SCALE_KEY] == _scale()
        assert len(out[HISTORY_KEY]) == 1
        assert out[HISTORY_KEY][0]["from"] is None
        assert out[HISTORY_KEY][0]["changed_by"] == "u"

    def test_an_unrelated_write_adds_nothing(self):
        stored = append_grade_scale_change(
            {GRADE_SCALE_KEY: _scale()}, old=None, new=_scale(), actor_id="u"
        )
        written = {**stored, "runs_per_task": 3}
        out = apply_grade_scale_write(stored, written, actor_id="v")
        assert out[HISTORY_KEY] == stored[HISTORY_KEY]
        assert out["runs_per_task"] == 3

    def test_the_trail_is_server_owned(self):
        stored = append_grade_scale_change({}, old=None, new=_scale(), actor_id="u")
        forged = [{"changed_at": "1999-01-01T00:00:00+00:00", "changed_by": "x"}]
        out = apply_grade_scale_write(
            stored, {**stored, HISTORY_KEY: forged}, actor_id="v"
        )
        assert out[HISTORY_KEY] == stored[HISTORY_KEY]
        # A write that deleted the list does not erase it either.
        dropped = {k: v for k, v in stored.items() if k != HISTORY_KEY}
        assert apply_grade_scale_write(stored, dropped, actor_id="v")[HISTORY_KEY] == (
            stored[HISTORY_KEY]
        )

    def test_a_forged_trail_on_a_project_without_one_is_dropped(self):
        out = apply_grade_scale_write({}, {HISTORY_KEY: [{"changed_by": "x"}]}, actor_id="v")
        assert HISTORY_KEY not in out

    def test_inputs_are_not_mutated(self):
        stored = {GRADE_SCALE_KEY: _scale(preset="custom")}
        written = {GRADE_SCALE_KEY: _scale()}
        stored_before, written_before = dict(stored), dict(written)
        apply_grade_scale_write(stored, written, actor_id="u")
        assert stored == stored_before and written == written_before

    def test_none_documents_are_accepted(self):
        assert apply_grade_scale_write(None, None, actor_id="u") == {}
