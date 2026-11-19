"""The frame builder: observations, measures, canonical order, hash, Parquet."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from analysis.frame import FrameError, build_frame, frame_hash, frame_models, from_parquet, to_parquet
from analysis.measures import coerce, lookup_path
from analysis.observations import (
    ObservationError,
    observation_from_record,
    observations_from_records,
    typed_field_values,
    variant_of_task_meta,
)
from analysis.spec import BASE_COLUMNS, normalize_spec
from analysis_synthetic import role_swap_records, role_swap_spec


@pytest.fixture(scope="module")
def built():
    spec = normalize_spec(role_swap_spec())
    return build_frame(observations_from_records(role_swap_records()), spec)


def test_columns_types_and_counts(built):
    frame = built.frame
    assert list(frame.columns[: len(BASE_COLUMNS)]) == list(BASE_COLUMNS)
    assert built.factors == ["first", "level", "name_id", "scenario", "x_role"]
    assert frame["level"].dtype == np.float64 and frame["x_role"].dtype == object
    assert frame["run_index"].dtype == np.int64
    assert built.counts["observations"] == len(frame) == 48 * 3 * 4
    assert built.counts["units"] == 48 and built.counts["systems"] == 3
    assert built.counts["parse_failures"] == int((frame["parse_ok"] == 0).sum()) > 0


def test_measures_reproduce_the_coding_by_hand(built):
    f = built.frame
    ok = f["parse_ok"] == 1
    xp = (f["x_role"] == "P").astype(float)
    share_x = np.where(xp == 1, f["share_p"], 100 - f["share_p"])
    assert np.array_equal(f["x_p"].to_numpy(), xp.to_numpy())
    assert np.allclose(f["share_x"][ok], share_x[ok]) and f["share_x"][~ok].isna().all()
    assert np.array_equal(f["gold_low"].to_numpy(), np.maximum(0, f["level"] - 10).to_numpy())
    fifty = f["fifty"][ok]
    assert set(fifty.unique()) <= {0.0, 100.0}
    assert f["wrong"][~f["level"].isin([0, 100])].isna().all()
    assert f["credible"][~ok].isna().all()


def test_order_and_hash_do_not_depend_on_the_source_order(built):
    records = role_swap_records()
    random.Random(1).shuffle(records)
    again = build_frame(observations_from_records(records), normalize_spec(role_swap_spec()))
    assert again.hash == built.hash
    assert again.frame.equals(built.frame)


def test_hash_changes_with_any_value(built):
    frame = built.frame.copy()
    frame.loc[0, "share_x"] = frame.loc[0, "share_x"] + 1e-9
    assert frame_hash(frame) != built.hash


def test_hash_treats_negative_zero_and_nan_payloads_as_equal(built):
    frame = built.frame.copy()
    frame["zero"] = [0.0] * len(frame)
    other = frame.copy()
    other["zero"] = [-0.0] * len(frame)
    assert frame_hash(frame) == frame_hash(other)


def test_parquet_round_trip_keeps_the_hash(built):
    data = to_parquet(built.frame, metadata={"benger.spec_hash": "x"})
    back = from_parquet(data)
    assert frame_hash(back) == built.hash
    import pyarrow.parquet as pq
    import io

    meta = pq.read_schema(io.BytesIO(data)).metadata
    assert meta[b"benger.frame_hash"].decode() == built.hash
    assert meta[b"benger.spec_hash"] == b"x"


def test_inputs_select_designs_systems_and_structures():
    records = role_swap_records(units=5)
    records[0]["variant"]["design"] = "other"
    records[1]["structure_key"] = "s2"
    spec = normalize_spec(
        {**role_swap_spec(), "inputs": {"designs": ["role_swap"], "systems": ["sys_a", "sys_b"]}}
    )
    built = build_frame(observations_from_records(records), spec)
    assert set(built.frame["system"]) == {"sys_a", "sys_b"}
    assert "gen_00001" not in set(built.frame["generation_id"])
    spec["inputs"]["structures"] = ["s2"]
    assert list(build_frame(observations_from_records(records), spec).frame["generation_id"]) == ["gen_00002"]


def test_duplicate_generations_are_ignored_with_a_warning():
    records = role_swap_records(units=2)
    records.append(dict(records[0]))
    built = build_frame(observations_from_records(records), normalize_spec(role_swap_spec()))
    assert len(built.frame) == len(records) - 1
    assert any("duplicate generation" in w for w in built.warnings)


def test_role_dependent_field_and_declared_factor_types():
    records = [
        {"generation_id": "g1", "task_id": "t1", "model_id": "m", "variant": {"design": "d", "unit": "u", "factors": {"role": "P", "level": "25"}},
         "fields": {"own": 30, "other": 70}},
        {"generation_id": "g2", "task_id": "t2", "model_id": "m", "variant": {"design": "d", "unit": "u", "factors": {"role": "D", "level": "x"}},
         "fields": {"own": 40, "other": 60}},
    ]
    spec = normalize_spec({
        "spec_version": 1, "name": "x", "inputs": {"designs": ["d"], "factor_types": {"level": "number"}},
        "measures": {"share": {"kind": "field", "by": "role", "fields": {"P": "own", "D": "other"}},
                     "missing": {"kind": "field", "field": "absent"}},
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "share"}],
    })
    built = build_frame(observations_from_records(records), spec)
    assert list(built.frame["share"]) == [30.0, 60.0]
    assert built.frame["level"].iloc[0] == 25.0 and math.isnan(built.frame["level"].iloc[1])
    assert any("not number" in w for w in built.warnings)
    assert any("no answer has the field 'absent'" in w for w in built.warnings)


def test_non_finite_measures_become_missing_with_a_warning():
    records = [{"generation_id": f"g{i}", "task_id": "t", "model_id": "m", "variant": {"design": "d", "unit": "u", "factors": {}},
                "fields": {"amount": a}} for i, a in enumerate([0, 10])]
    spec = normalize_spec({
        "spec_version": 1, "name": "x", "inputs": {"designs": ["d"]},
        "measures": {"amount": {"kind": "field", "field": "amount"}, "lg": {"kind": "expression", "expr": "log(amount)"}},
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "lg"}],
    })
    built = build_frame(observations_from_records(records), spec)
    assert math.isnan(built.frame["lg"].iloc[0])
    assert any("non-finite" in w for w in built.warnings)


def test_frame_errors():
    base = {"generation_id": "g", "task_id": "t", "model_id": "m", "fields": {}}
    spec = normalize_spec({
        "spec_version": 1, "name": "x", "inputs": {"designs": ["d"]},
        "measures": {"y": {"kind": "expression", "expr": "nope + 1"}},
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "y"}],
    })
    with pytest.raises(FrameError, match="unknown column"):
        build_frame(observations_from_records([{**base, "variant": {"design": "d", "unit": "u", "factors": {}}}]), spec)
    with pytest.raises(FrameError, match="collide"):
        build_frame(observations_from_records([{**base, "variant": {"design": "d", "unit": "u", "factors": {"system": "x"}}}]), spec)


def test_typed_field_values_keep_types():
    results = [
        {"from_name": "n", "type": "number", "value": {"number": 7}},
        {"from_name": "r", "type": "rating", "value": {"rating": 4}},
        {"from_name": "c", "type": "choices", "value": {"choices": ["P"]}},
        {"from_name": "t", "type": "textarea", "value": {"text": ["first", "second"]}},
        {"from_name": "l", "type": "labels", "value": {"spans": [{"start": 0, "end": 1}]}},
        {"from_name": "n", "type": "number", "value": {"number": 8}},
        {"from_name": "m", "type": "textarea", "value": {"markdown": "**x**"}},
        {"from_name": "o", "type": "x", "value": {"other": 1}},
        {"from_name": "s", "value": "plain"},
        {"type": "number", "value": {"number": 1}},
        "not a result",
    ]
    assert typed_field_values(results) == {
        "n": 7, "r": 4, "c": ["P"], "t": "first", "l": [{"start": 0, "end": 1}],
        "m": "**x**", "o": {"other": 1}, "s": "plain",
    }
    assert typed_field_values(None) == {}


def test_variant_of_task_meta():
    assert variant_of_task_meta({"benger_variant": {"design": "d", "unit": 3, "factors": {"a": 1}}}) == {
        "design": "d", "unit": "3", "factors": {"a": 1}, "slots": ()}
    assert variant_of_task_meta({"benger_variant": {"design": "d"}}) is None
    assert variant_of_task_meta({"tags": []}) is None
    assert variant_of_task_meta(None) is None
    assert variant_of_task_meta({"benger_variant": {"design": "d", "unit": "u", "factors": "x"}})["factors"] == {}


def test_observation_records_are_checked():
    ok = {"generation_id": "g", "task_id": "t", "model_id": "m", "design": "d", "unit": "u", "factors": {},
          "parsed_annotation": [{"from_name": "y", "type": "number", "value": {"number": 2}}], "run_index": 2.0}
    obs = observation_from_record(ok)
    assert obs.fields == {"y": 2} and obs.run_index == 2 and obs.system == "m"
    for bad, message in [
        ({**ok, "design": None}, "no variant design"),
        ({**ok, "model_id": ""}, "missing 'model_id'"),
        ({**ok, "fields": []}, "'fields' must be an object"),
        ({**ok, "run_index": 1.5}, "whole number"),
        ({**ok, "task_data": []}, "'task_data' must be an object"),
    ]:
        with pytest.raises(ObservationError, match=message):
            observation_from_record(bad)
    with pytest.raises(ObservationError):
        observation_from_record(["not", "a", "dict"])


@pytest.mark.parametrize(
    "value, kind, expected",
    [
        (True, "number", 1.0), ("2,5", "number", 2.5), ([3], "number", 3.0), ([1, 2], "number", math.nan),
        ("x", "number", math.nan), (float("inf"), "number", math.nan), ({"a": 1}, "number", math.nan),
        (50.0, "text", "50"), (2.5, "text", "2.5"), (False, "text", "false"), ([], "text", None),
        ("TRUE", "bool", 1.0), (0, "bool", 0.0), (2, "bool", math.nan), (None, "bool", math.nan),
    ],
)
def test_coercion(value, kind, expected):
    out = coerce(value, kind)
    if isinstance(expected, float) and math.isnan(expected):
        assert isinstance(out, float) and math.isnan(out)
    else:
        assert out == expected


NUMBER_TEXTS = [
    # (text, value, ambiguous): a dot is the decimal mark; one comma without a
    # dot is the decimal mark unless three digits follow; the two grouped
    # forms; everything else of digits and separators is ambiguous
    ("2.5", 2.5, False), ("-3", -3.0, False), (" 1e3 ", 1000.0, False), ("1.000", 1.0, False),
    ("1,5", 1.5, False), ("12,25", 12.25, False), ("-0,25", -0.25, False),
    ("1.000,50", 1000.5, False), ("1,000.50", 1000.5, False), ("12.345.678,9", 12345678.9, False),
    ("1,000", math.nan, True), ("1,2,3", math.nan, True), ("1.000.000,5,5", math.nan, True),
    ("1.000.000", math.nan, True), ("1,00.5", math.nan, True), ("1.00,5", math.nan, True),
    ("n/a", math.nan, False), ("", math.nan, False), ("inf", math.nan, False),
]


@pytest.mark.parametrize("text, value, is_ambiguous", NUMBER_TEXTS)
def test_number_text_never_guesses_the_separator(text, value, is_ambiguous):
    ambiguous = []
    out = coerce(text, "number", ambiguous)
    if math.isnan(value):
        assert isinstance(out, float) and math.isnan(out)
    else:
        assert out == value
    assert ambiguous == ([text] if is_ambiguous else [])


def test_ambiguous_number_texts_are_missing_with_a_warning_per_measure():
    amounts = ["1,000", "1,5", "1.000.000", "1,000.50", "x"]
    records = [{"generation_id": f"g{i}", "task_id": f"t{i}", "model_id": "m",
                "variant": {"design": "d", "unit": "u", "factors": {}},
                "fields": {"amount": a, "label": a}, "task_data": {"gold": {"amount": a}}}
               for i, a in enumerate(amounts)]
    spec = normalize_spec({
        "spec_version": 1, "name": "x", "inputs": {"designs": ["d"]},
        "measures": {"amount": {"kind": "field", "field": "amount"},
                     "gold_amount": {"kind": "gold", "path": "gold.amount"},
                     "label": {"kind": "field", "field": "label", "type": "text"},
                     "parsed": {"kind": "expression", "expr": "number(label)"}},
        "estimands": [{"id": "m", "estimator": "mean_rate", "outcome": "amount"}],
    })
    built = build_frame(observations_from_records(records), spec)
    by_text = dict(zip(built.frame["label"], built.frame["parsed"]))
    assert by_text["1,5"] == 1.5 and by_text["1,000.50"] == 1000.5
    assert all(math.isnan(by_text[t]) for t in ("1,000", "1.000.000", "x"))
    for name in ("amount", "gold_amount", "parsed"):
        assert f"measure {name!r}: 2 number text(s) with an ambiguous separator set to missing" in built.warnings
    assert not any(w.startswith("measure 'label'") for w in built.warnings)


def test_lookup_path():
    data = {"gold": {"range": [10, 20]}, "x": None}
    assert lookup_path(data, "gold.range.1") == 20
    assert lookup_path(data, "gold.range.5") is None
    assert lookup_path(data, "gold.range.a") is None
    assert lookup_path(data, "x.y") is None


def test_frame_models_lists_every_model_once():
    import pandas as pd

    # The model part of a system key is the text before "@" (profile hash).
    frame = pd.DataFrame({"model_id": ["m2", "m1", None, "m1"], "system": ["m2@p1", "m3@p9", None, "m1"]})
    assert frame_models(frame) == ["m1", "m2", "m3"]
    assert frame_models(pd.DataFrame({"x": [1]})) == []
