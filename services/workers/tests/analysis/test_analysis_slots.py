"""Slot frames, slot measures, lookup joins and cross-project frames.

The acceptance check of per-slot frames: a per-slot design unpivots to one
row per generation and slot whose columns are exactly the expected set (the
engine's base columns stand for the system, the unit and the generation):

* a six-case docket answered through a Label Studio Repeater (indexed
  controls ``risk_0`` ... ``risk_5``): system, docket, task factors, slot
  factors (position, offence, group, name), the four per-case answers and
  the cross-slot rank validity;
* two persons per answer: each person's own answers, the other person's
  answers and group, and a generation-level answer;
* the same two-person design as one row per generation, with the persons'
  factors and answers by slot index.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.frame import FrameError, build_frame, from_parquet, to_parquet
from analysis.measures import slot_field_name
from analysis.observations import observations_from_records
from analysis.spec import BASE_COLUMNS, normalize_spec
from estimator_synthetic import docket_records, persons_records
from label_config_repeater import derive_slot_map

DOCKETS, CONTROLS, SYSTEMS = 180, 24, 3


def _spec(design, measures, unit="slot", **extra):
    spec = {
        "spec_version": 1,
        "name": "frame",
        "inputs": {"designs": [design]},
        "measures": measures,
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": next(iter(measures))}],
        **extra,
    }
    if unit:
        spec["frame"] = {"unit": unit}
    return normalize_spec(spec)


def _added(frame, slot_frame=True):
    """The columns beyond the base columns (and the slot index)."""
    base = list(BASE_COLUMNS) + (["slot"] if slot_frame else [])
    assert list(frame.columns[: len(base)]) == base
    return set(frame.columns[len(base):])


DOCKET_MEASURES = {
    "risk": {"kind": "field", "field": "risk_{idx}"},
    "prob": {"kind": "field", "field": "prob_{idx}"},
    "months": {"kind": "field", "field": "months_{idx}"},
    "rank": {"kind": "field", "field": "rank_{idx}"},
    "rank_valid": {"kind": "slot_aggregate", "field": "rank_{idx}", "function": "is_ranking"},
}


@pytest.fixture(scope="module")
def docket():
    records = docket_records()
    return records, build_frame(observations_from_records(records), _spec("docket", DOCKET_MEASURES))


def test_docket_slot_frame_has_the_expected_columns(docket):
    _, built = docket
    frame = built.frame
    # model -> system, docket_id -> unit; everything else by name
    expected = {"kind", "gender", "pos", "fact", "group", "name_id", "risk", "prob", "months", "rank", "rank_valid"}
    assert _added(frame) == expected
    assert len(frame) == (DOCKETS * 6 + CONTROLS) * SYSTEMS
    assert built.counts["observations"] == (DOCKETS + CONTROLS) * SYSTEMS
    assert built.counts["rows"] == len(frame)
    assert frame["slot"].dtype == np.int64 and frame["pos"].dtype == float
    assert set(frame["slot"]) == set(range(6))
    assert (frame["pos"] == frame["slot"] + 1).all()
    assert set(frame["kind"]) == {"docket", "control"}


def test_docket_slot_rows_carry_their_own_answers(docket):
    records, built = docket
    frame = built.frame
    by_gen = {r["generation_id"]: r for r in records}
    for row in frame.sample(200, random_state=3).itertuples():
        rec = by_gen[row.generation_id]
        slot = next(s for s in rec["variant"]["slots"] if s["index"] == row.slot)
        assert row.risk == rec["fields"][f"risk_{row.slot}"]
        assert row.rank == rec["fields"][f"rank_{row.slot}"]
        assert row.group == slot["factors"]["group"] and row.name_id == slot["factors"]["name_id"]
        ranks = sorted(rec["fields"][f"rank_{s['index']}"] for s in rec["variant"]["slots"])
        assert row.rank_valid == float(ranks == list(range(1, len(ranks) + 1)))
    # rank validity is constant within a generation and some answers repeat a rank
    per_gen = frame.groupby("generation_id")["rank_valid"].nunique()
    assert (per_gen == 1).all()
    assert 0 < (frame.drop_duplicates("generation_id")["rank_valid"] == 0).sum() < DOCKETS


def test_per_slot_names_follow_the_repeater_slot_map():
    config = (
        '<View><Repeater on="$cases" indexFlag="{{idx}}">'
        '<Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>'
        '<Number name="risk_{{idx}}" toName="case_{{idx}}"/>'
        '<Number name="rank_{{idx}}" toName="case_{{idx}}"/>'
        "</Repeater></View>"
    )
    task_data = {"cases": [{"text": f"case {i}"} for i in range(6)]}
    group = derive_slot_map(config, task_data)[0]
    assert [s["index"] for s in group["slots"]] == list(range(6))
    for slot in group["slots"]:
        assert slot_field_name("risk_{idx}", slot["index"]) == slot["controls"]["risk"]
        assert slot_field_name("rank_{idx}", slot["index"]) == slot["controls"]["rank"]


PERSON_MEASURES = {
    "months": {"kind": "field", "field": "months_{idx}"},
    "prob": {"kind": "field", "field": "prob_{idx}"},
    "cred": {"kind": "field", "field": "cred_{idx}"},
    "months_other": {"kind": "field", "field": "months_{idx}", "slot": "other"},
    "prob_other": {"kind": "field", "field": "prob_{idx}", "slot": "other"},
    "cred_other": {"kind": "field", "field": "cred_{idx}", "slot": "other"},
    "partner": {"kind": "slot_factor", "factor": "group", "slot": "other"},
    "follow": {"kind": "field", "field": "follow"},
}


def test_two_person_slot_frame_has_own_and_other_columns():
    records = persons_records()
    built = build_frame(observations_from_records(records), _spec("persons", PERSON_MEASURES))
    frame = built.frame
    # job_id -> generation_id, model -> system, unit_id -> unit
    expected = {
        "case", "variant", "pairtype", "kind", "gender", "role", "group", "partner", "name_id",
        "months", "prob", "cred", "months_other", "prob_other", "cred_other", "follow",
    }
    assert _added(frame) == expected
    assert len(frame) == 2 * len(records)
    by_gen = {r["generation_id"]: r for r in records}
    for row in frame.itertuples():
        rec = by_gen[row.generation_id]
        other = 3 - row.slot
        assert row.months == rec["fields"][f"months_{row.slot}"]
        assert row.months_other == rec["fields"][f"months_{other}"]
        assert row.cred_other == rec["fields"][f"cred_{other}"]
        assert row.partner == rec["variant"]["slots"][other - 1]["factors"]["group"]
        assert row.follow == rec["fields"]["follow"]
    assert not built.warnings


def test_two_person_generation_frame_reads_slots_by_index():
    measures = {
        "cred_first": {"kind": "field", "field": "cred_{idx}", "slot": 1},
        "cred_second": {"kind": "field", "field": "cred_{idx}", "slot": 2},
        "group_first": {"kind": "slot_factor", "factor": "group", "slot": 1},
        "group_second": {"kind": "slot_factor", "factor": "group", "slot": 2},
        "id_first": {"kind": "slot_factor", "factor": "name_id", "slot": 1},
        "id_second": {"kind": "slot_factor", "factor": "name_id", "slot": 2},
        "follow": {"kind": "field", "field": "follow"},
        "cred_diff": {"kind": "expression", "expr": "cred_first - cred_second"},
    }
    records = persons_records()
    built = build_frame(observations_from_records(records), _spec("persons", measures, unit=None))
    frame = built.frame
    assert _added(frame, slot_frame=False) == {"case", "variant", "pairtype", "kind", "gender"} | set(measures)
    assert len(frame) == len(records)
    rec = {r["generation_id"]: r for r in records}[frame.generation_id[0]]
    assert frame.group_second[0] == rec["variant"]["slots"][1]["factors"]["group"]
    assert frame.cred_diff[0] == rec["fields"]["cred_1"] - rec["fields"]["cred_2"]


def test_the_slot_frame_snapshot_round_trips(docket):
    _, built = docket
    back = from_parquet(to_parquet(built.frame))
    assert list(back.columns) == list(built.frame.columns)
    assert back["slot"].dtype == np.int64
    from analysis.frame import frame_hash

    assert frame_hash(back) == built.hash


def _rec(gid, slots, fields, factors=None, design="d", project=None):
    rec = {
        "generation_id": gid,
        "task_id": "t" + gid,
        "model_id": "m",
        "variant": {"design": design, "unit": "u" + gid, "factors": factors or {}, "slots": slots},
        "fields": fields,
    }
    if project:
        rec["project_id"] = project
    return rec


def _slots(*groups):
    return [{"index": i + 1, "factors": {"g": g}} for i, g in enumerate(groups)]


def test_slot_frames_leave_out_tasks_without_slots_and_warn():
    records = [_rec("1", _slots("a", "b"), {"y_1": 1, "y_2": 2}), _rec("2", [], {"y_1": 5})]
    built = build_frame(observations_from_records(records), _spec("d", {"y": {"kind": "field", "field": "y_{idx}"}}))
    assert list(built.frame["y"]) == [1.0, 2.0]
    assert built.counts["generations_without_slots"] == 1
    assert any("without slots" in w for w in built.warnings)


def test_other_needs_exactly_two_slots():
    records = [_rec("1", _slots("a", "b", "c"), {"y_1": 1, "y_2": 2, "y_3": 3}), _rec("2", _slots("a", "b"), {"y_1": 4, "y_2": 6})]
    measures = {"y": {"kind": "field", "field": "y_{idx}"}, "other": {"kind": "field", "field": "y_{idx}", "slot": "other"},
                "partner": {"kind": "slot_factor", "factor": "g", "slot": "other"}}
    built = build_frame(observations_from_records(records), _spec("d", measures))
    frame = built.frame
    assert np.isnan(frame["other"][:3]).all() and list(frame["other"][3:]) == [6.0, 4.0]
    assert list(frame["partner"]) == [None, None, None, "b", "a"]
    assert sum("have no slot 'other'" in w for w in built.warnings) == 2


def test_slot_aggregates():
    records = [
        _rec("1", _slots("a", "b", "c"), {"r_1": 2, "r_2": 3, "r_3": 1}),
        _rec("2", _slots("a", "b", "c"), {"r_1": 1, "r_2": 1, "r_3": 2}),
        _rec("3", _slots("a", "b", "c"), {"r_1": 1, "r_2": None, "r_3": 3}),
    ]
    measures = {f: {"kind": "slot_aggregate", "field": "r_{idx}", "function": f}
                for f in ("is_ranking", "mean", "sum", "min", "max", "sd", "count")}
    frame = build_frame(observations_from_records(records), _spec("d", measures, unit=None)).frame
    assert list(frame["is_ranking"]) == [1.0, 0.0, 0.0]
    assert list(frame["mean"]) == [2.0, pytest.approx(4 / 3), 2.0]
    assert list(frame["sum"]) == [6.0, 4.0, 4.0]
    assert list(frame["min"]) == [1.0, 1.0, 1.0] and list(frame["max"]) == [3.0, 2.0, 3.0]
    assert frame["sd"][0] == 1.0 and frame["sd"][2] == pytest.approx(math.sqrt(2))
    assert list(frame["count"]) == [3.0, 3.0, 2.0]


def test_slot_factor_names_must_not_collide():
    records = [_rec("1", [{"index": 1, "factors": {"g": "a"}}], {"y_1": 1}, factors={"g": "x"})]
    with pytest.raises(FrameError, match="both a task factor and a slot factor"):
        build_frame(observations_from_records(records), _spec("d", {"y": {"kind": "field", "field": "y_{idx}"}}))
    records = [_rec("1", [{"index": 1, "factors": {"y": "a"}}], {"y_1": 1})]
    with pytest.raises(FrameError, match="collide"):
        build_frame(observations_from_records(records), _spec("d", {"y": {"kind": "field", "field": "y_{idx}"}}))


def _lookup_spec(lookups, measures=None):
    return _spec("d", measures or {"y": {"kind": "field", "field": "y"}}, unit=None, lookups=lookups)


def test_lookups_join_by_canonical_text_and_fill():
    records = [
        _rec("1", [], {"y": 1}, factors={"k": "a", "level": 1}),
        _rec("2", [], {"y": 2}, factors={"k": "b", "level": 2.0}),
        _rec("3", [], {"y": 3}, factors={"k": "c", "level": 3}),
    ]
    lookups = [{"id": "tab", "keys": {"k": "key", "level": "lv"}, "columns": {"code": "code", "label": "label"},
                "rows": [{"key": "a", "lv": 1.0, "code": 7, "label": "x"}, {"key": "b", "lv": 2, "code": 8, "label": 1}],
                "fill": {"code": 0}}]
    built = build_frame(observations_from_records(records), _lookup_spec(lookups))
    frame = built.frame
    assert list(frame["code"]) == [7.0, 8.0, 0.0]
    assert list(frame["label"]) == ["x", "1", None]
    assert any("1 row(s) without a matching lookup row" in w for w in built.warnings)
    assert list(frame.columns[-3:]) == ["code", "label", "y"]


def test_lookup_errors():
    records = [_rec("1", [], {"y": 1}, factors={"k": "a"})]
    dup = [{"id": "tab", "keys": {"k": "key"}, "columns": {"c": "c"}, "rows": [{"key": "a", "c": 1}, {"key": "a", "c": 2}]}]
    with pytest.raises(FrameError, match="more than one row"):
        build_frame(observations_from_records(records), _lookup_spec(dup))
    unknown = [{"id": "tab", "keys": {"zz": "key"}, "columns": {"c": "c"}, "rows": [{"key": "a", "c": 1}]}]
    with pytest.raises(FrameError, match="unknown key column 'zz'"):
        build_frame(observations_from_records(records), _lookup_spec(unknown))
    stored = [{"id": "tab", "keys": {"k": "key"}, "columns": {"c": "c"}, "table": {"name": "t", "version": 1}}]
    with pytest.raises(FrameError, match="was not loaded"):
        build_frame(observations_from_records(records), _lookup_spec(stored))
    built = build_frame(
        observations_from_records(records), _lookup_spec(stored), lookup_tables={"tab": [{"key": "a", "c": 5}]}
    )
    assert list(built.frame["c"]) == [5.0]
    missing = [{"id": "tab", "keys": {"k": "key"}, "columns": {"c": "nope"}, "table": {"name": "t", "version": 1}}]
    with pytest.raises(FrameError, match="no column"):
        build_frame(observations_from_records(records), _lookup_spec(missing), lookup_tables={"tab": [{"key": "a"}]})


def test_cross_project_frames_select_each_projects_designs():
    records = [
        _rec("1", [], {"y": 1}, design="d", project="home"),
        _rec("2", [], {"y": 2}, design="other", project="home"),
        _rec("3", [], {"y": 3}, design="e", project="p2"),
        _rec("4", [], {"y": 4}, design="d", project="p2"),
        _rec("5", [], {"y": 5}, design="e", project="p3"),
    ]
    spec = _spec("d", {"y": {"kind": "field", "field": "y"}}, unit=None)
    spec["inputs"]["projects"] = [{"project_id": "p2", "designs": ["e"]}]
    built = build_frame(observations_from_records(records), spec, home_project="home")
    frame = built.frame
    assert list(zip(frame["project_id"], frame["y"])) == [("home", 1.0), ("p2", 3.0)]
    assert built.counts["projects"] == 2 and built.counts["designs"] == 2
