"""The one current score per (subject, evaluation config, prediction field).

Covers ``services/shared/current_scores.py``: the cell key every view uses,
the newest-scored-row rule, the fallback for on-submit rows that carry a
model-side label, and the grade points reader.
"""

from datetime import datetime, timedelta, timezone

import pytest

import current_scores as cs

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
CFG = "llm_judge_custom-abc"
CONFIGS = {CFG: {"id": CFG, "prediction_fields": ["__all_model__", "human:loesung"]}}


def _row(id, *, field_name, ann="a1", gen=None, cfg=CFG, minutes=0, score=0.5, task="t1"):
    metrics = {"llm_judge_custom": {"value": score}} if score is not None else {
        "llm_judge_custom": {"value": None, "error": "judge failed"}
    }
    return {
        "id": id,
        "task_id": task,
        "annotation_id": ann,
        "generation_id": gen,
        "evaluation_config_id": cfg,
        "field_name": field_name,
        "metrics": metrics,
        "created_at": T0 + timedelta(minutes=minutes),
    }


class TestCellKey:
    def test_on_submit_and_batch_rows_share_a_cell(self):
        on_submit = _row("r1", field_name="human:loesung")
        batch = _row("r2", field_name=f"{CFG}|human:loesung|task.musterloesung")
        assert cs.cell_key(on_submit) == cs.cell_key(batch) == (
            "annotation", "a1", CFG, "loesung"
        )

    def test_reference_part_is_not_part_of_the_cell(self):
        a = _row("r1", field_name=f"{CFG}|human:loesung|task.musterloesung")
        b = _row("r2", field_name=f"{CFG}|human:loesung|task.bewertungsbogen")
        assert cs.cell_key(a) == cs.cell_key(b)

    def test_unprefixed_and_prefixed_fields_match(self):
        assert cs.cell_key(_row("r1", field_name="loesung")) == cs.cell_key(
            _row("r2", field_name="human:loesung")
        )

    def test_model_side_label_on_an_answer_resolves_through_the_config(self):
        mislabelled = _row("r1", field_name="__all_model__")
        batch = _row("r2", field_name=f"{CFG}|human:loesung|task.musterloesung")
        assert cs.cell_key(mislabelled, CONFIGS) == cs.cell_key(batch, CONFIGS)
        # Without the config the label cannot be resolved and stays its own cell.
        assert cs.cell_key(mislabelled) != cs.cell_key(batch)

    def test_model_side_label_on_a_generation_is_kept(self):
        row = _row("r1", field_name=f"{CFG}|__all_model__|task.x", ann=None, gen="g1")
        assert cs.cell_key(row, CONFIGS) == ("generation", "g1", CFG, "__all_model__")

    def test_config_from_the_field_name_when_the_column_is_empty(self):
        row = _row("r1", field_name="cfg-old|human:loesung|ref", cfg=None)
        assert cs.cell_key(row) == ("annotation", "a1", "cfg-old", "loesung")

    def test_distinct_configs_and_subjects_are_distinct_cells(self):
        assert cs.cell_key(_row("r1", field_name="loesung")) != cs.cell_key(
            _row("r2", field_name="loesung", cfg="other")
        )
        assert cs.cell_key(_row("r1", field_name="loesung")) != cs.cell_key(
            _row("r2", field_name="loesung", ann="a2")
        )

    def test_rows_without_a_subject_key_on_the_task(self):
        row = _row("r1", field_name="loesung", ann=None)
        assert cs.cell_subject(row) == ("task", "t1")


class TestPickCurrent:
    def test_newest_scored_row_wins_across_runs(self):
        """An on-submit row and a later forced re-run of the
        same config are one cell; the re-run is current, the first is history."""
        on_submit = _row("r1", field_name="human:loesung", minutes=0, score=0.75)
        rerun = _row("r2", field_name=f"{CFG}|human:loesung|task.musterloesung", minutes=20, score=0.82)
        assert cs.current_row_ids([on_submit, rerun]) == {"r2"}

    def test_a_failed_newer_row_does_not_replace_a_score(self):
        good = _row("r1", field_name="human:loesung", minutes=0, score=0.6)
        failed = _row("r2", field_name="human:loesung", minutes=5, score=None)
        assert cs.current_row_ids([good, failed]) == {"r1"}

    def test_only_failures_keep_the_newest_failure(self):
        a = _row("r1", field_name="human:loesung", minutes=0, score=None)
        b = _row("r2", field_name="human:loesung", minutes=5, score=None)
        assert cs.current_row_ids([a, b]) == {"r2"}

    def test_equal_timestamps_tie_break_on_id(self):
        a = _row("r1", field_name="human:loesung")
        b = _row("r2", field_name="human:loesung")
        assert cs.current_row_ids([b, a]) == {"r2"}
        assert cs.current_row_ids([a, b]) == {"r2"}

    def test_one_current_row_per_cell(self):
        rows = [
            _row("r1", field_name="human:loesung", minutes=0),
            _row("r2", field_name="human:loesung", minutes=1),
            _row("r3", field_name="human:loesung", ann="a2"),
            _row("r4", field_name="human:loesung", cfg="other"),
        ]
        assert cs.current_row_ids(rows) == {"r2", "r3", "r4"}

    def test_naive_timestamps_compare(self):
        a = _row("r1", field_name="human:loesung")
        a["created_at"] = datetime(2026, 1, 1)
        b = _row("r2", field_name="human:loesung")
        assert cs.current_row_ids([a, b]) == {"r2"}

    def test_works_on_objects(self):
        class Row:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        rows = [Row(**_row("r1", field_name="loesung")), Row(**_row("r2", field_name="loesung", minutes=1))]
        assert cs.current_row_ids(rows) == {"r2"}

    def test_legacy_korrektur_blob_counts_as_scored(self):
        legacy = _row("r1", field_name="human:loesung", minutes=0)
        legacy["metrics"] = {"korrektur_falloesung": {"total_score": 51.5}}
        failed = _row("r2", field_name="human:loesung", minutes=5, score=None)
        assert cs.current_row_ids([legacy, failed]) == {"r1"}


class TestRowHasScore:
    @pytest.mark.parametrize(
        "metrics, expected",
        [
            ({"bleu": 0.4}, True),
            ({"m": {"value": 0.4}}, True),
            ({"m": {"value": None, "error": "x"}}, False),
            ({"m_response": {"score": 4}}, False),
            ({}, False),
            (None, False),
            ("not a dict", False),
        ],
    )
    def test_cases(self, metrics, expected):
        assert cs.row_has_score(metrics) is expected


class TestGradePoints:
    def test_top_level_key(self):
        assert cs.extract_grade_points({"llm_judge_custom": 0.8, "llm_judge_custom_grade_points": 14}) == 14

    def test_details(self):
        assert cs.extract_grade_points(
            {"llm_judge_falloesung": {"value": 0.7, "details": {"grade_points": 12}}}
        ) == 12

    def test_none(self):
        assert cs.extract_grade_points({"bleu": 0.3}) is None
        assert cs.extract_grade_points(None) is None


def test_configs_by_id_reads_the_stored_config():
    stored = {"evaluation_configs": [{"id": "a", "metric": "bleu"}, {"metric": "no-id"}, "junk"]}
    assert cs.configs_by_id(stored) == {"a": {"id": "a", "metric": "bleu"}}
    assert cs.configs_by_id(None) == {}


def test_split_field_name():
    assert cs.split_field_name("cfg|human:x|ref") == ("cfg", "human:x")
    assert cs.split_field_name("loesung") == ("", "loesung")
    assert cs.split_field_name(None) == ("", "")
