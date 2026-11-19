"""Golden estimates and determinism of the estimator extensions.

``golden_estimates_extensions.json`` records every estimate of the specs
below (logit with marginal effects, Bradley-Terry, Plackett-Luce, the rank-1
conditional logit, Spearman, joint tests, lookups and a cross-project slot
frame) with the engine version and the spec and frame hashes, like
``golden_estimates.json`` does for the core estimators. MixedLM is left out:
its variance component comes from statsmodels' optimizer, whose stopping
point may move with the CPU's floating-point kernels (the reference tests
cover it). Regenerate after an intended numeric change (bump
``ENGINE_VERSION``) with

    python services/workers/tests/analysis/test_analysis_golden_extensions.py
"""

from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden_estimates_extensions.json")

if __name__ == "__main__":  # regeneration: make /shared and this folder importable
    sys.path[:0] = [HERE, os.path.normpath(os.path.join(HERE, "..", "..", "..", "shared"))]

from analysis.frame import build_frame, from_parquet, to_parquet  # noqa: E402
from analysis.observations import observations_from_records  # noqa: E402
from analysis.runner import run_spec  # noqa: E402
from analysis.spec import normalize_spec, spec_hash  # noqa: E402
from analysis.version import ENGINE_VERSION  # noqa: E402
from analysis_synthetic import MEASURES, role_swap_records  # noqa: E402
from estimator_synthetic import (  # noqa: E402
    SECOND_PROJECT_SEED,
    congruence_lookup,
    docket_records,
    pairs_records,
    single_records,
)
from test_analysis_golden import _assert_close, _bits  # noqa: E402

GROUP = {"dummies": "group", "reference": "ref"}
GENDER = {"dummies": "gender", "reference": "f"}


def _docket_records():
    first = [dict(r, project_id="proj_a") for r in docket_records(dockets=60, controls=6)]
    second = []
    for r in docket_records(dockets=40, controls=0, seed=SECOND_PROJECT_SEED):
        second.append(dict(r, project_id="proj_b", generation_id="b_" + r["generation_id"], task_id="b_" + r["task_id"]))
    return first + second


SPECS = {
    "docket": (
        _docket_records,
        {
            "spec_version": 1,
            "name": "docket",
            "inputs": {"designs": ["docket"], "projects": [{"project_id": "proj_b", "designs": ["docket"]}]},
            "frame": {"unit": "slot"},
            "lookups": [{"id": "cong", "rows": congruence_lookup(), "keys": {"system": "model", "fact": "fact", "group": "group"},
                         "columns": {"cong": "cong"}, "fill": {"cong": 0}}],
            "measures": {
                "rank": {"kind": "field", "field": "rank_{idx}"},
                "risk": {"kind": "field", "field": "risk_{idx}"},
                "rank_valid": {"kind": "slot_aggregate", "field": "rank_{idx}", "function": "is_ranking"},
            },
            "estimands": [
                {"id": "pl", "estimator": "plackett_luce", "outcome": "rank", "stages": 3,
                 "terms": [GROUP, {"dummies": "pos", "reference": 1}], "subset": "kind == 'docket' and rank_valid == 1",
                 "vcov": {"type": "cluster", "by": ["unit"]}, "scopes": ["pooled", {"by": ["project_id"]}],
                 "joint_tests": [{"id": "groups", "parameters": ["group[*]"]}]},
                {"id": "first", "estimator": "clogit_rank1", "outcome": "rank", "terms": [GROUP],
                 "subset": "kind == 'docket' and rank_valid == 1", "conventions": {"inference": "t"}},
                {"id": "ols", "estimator": "fe_ols", "outcome": "risk", "terms": ["cong", GROUP],
                 "fixed_effects": [["unit", "system"]], "vcov": {"type": "cluster", "by": ["unit", "name_id"]},
                 "contrasts": [{"id": "cong", "weights": {"cong": 1}, "tost": {"margin": 3}}],
                 "joint_tests": [{"id": "groups", "parameters": ["group[*]"]}]},
            ],
            "families": [{"id": "pl_groups", "method": "holm", "members": [{"estimand": "pl", "scope": "pooled"}]}],
        },
    ),
    "pairs": (
        lambda: pairs_records(units=80),
        {
            "spec_version": 1,
            "name": "pairs",
            "inputs": {"designs": ["pairs"]},
            "measures": {
                "choice": {"kind": "field", "field": "choice"},
                "first_wins": {"kind": "expression", "expr": "1 * (choice == 1)"},
                "g1": {"kind": "slot_factor", "factor": "group", "slot": 1},
                "g2": {"kind": "slot_factor", "factor": "group", "slot": 2},
            },
            "estimands": [
                {"id": f"bt_{link}", "estimator": "bradley_terry", "outcome": "first_wins", "players": ["g1", "g2"],
                 "reference": "ref", "link": link, "fixed_effects": [["system", "case"]],
                 "vcov": {"type": "cluster", "by": ["unit"]}, "joint_tests": [{"id": "all", "parameters": ["strength[*]"]}]}
                for link in ("logit", "linear")
            ],
        },
    ),
    "single": (
        lambda: single_records(names_per_group=4, reps=3),
        {
            "spec_version": 1,
            "name": "single",
            "inputs": {"designs": ["single"]},
            "measures": {"probation": {"kind": "field", "field": "probation"}, "months": {"kind": "field", "field": "months"}},
            "estimands": [
                {"id": "logit", "estimator": "logit", "outcome": "probation",
                 "terms": [GROUP, GENDER, {"interact": [GROUP, GENDER]}],
                 "vcov": {"type": "cluster", "by": ["name_id"]}, "conventions": {"inference": "t"},
                 "contrasts": [{"id": g, "kind": "ame", "column": "group", "level": g, "reference": "ref", "scale": 100,
                                "tost": {"margin": 5}} for g in ("a", "b", "control")]
                 + [{"id": "a_logodds", "weights": {"group[a]": 1, "group[a]:gender[m]": 0.5}}],
                 "joint_tests": [{"id": "ames", "contrasts": ["a", "b", "control"]}]},
                {"id": "rho", "estimator": "spearman", "outcome": "months", "x": "probation", "scopes": [{"by": ["system"]}]},
            ],
        },
    ),
    "spearman": (
        role_swap_records,
        {
            "spec_version": 1,
            "name": "spearman",
            "inputs": {"designs": ["role_swap"]},
            "measures": MEASURES,
            "estimands": [{"id": "rho", "estimator": "spearman", "outcome": "share_x", "x": "level",
                           "scopes": ["pooled", {"by": ["system", "x_role"]}]}],
        },
    ),
}


def _compute(name, records=None):
    make, raw = SPECS[name]
    spec = normalize_spec(raw)
    built = build_frame(observations_from_records(records or make()), spec, home_project="proj_a")
    return spec, built, run_spec(built.frame, spec)


def test_estimates_equal_the_golden_file():
    with open(GOLDEN, encoding="utf-8") as fh:
        golden = json.load(fh)
    assert golden["engine_version"] == ENGINE_VERSION, "regenerate the golden file (see the module docstring)"
    assert set(golden["specs"]) == set(SPECS)
    for name in SPECS:
        spec, built, result = _compute(name)
        ref = golden["specs"][name]
        assert ref["spec_hash"] == spec_hash(spec), name
        assert ref["frame_hash"] == built.hash, name
        assert len(result.estimates) == len(ref["estimates"]), name
        for mine, row in zip(result.estimates, ref["estimates"]):
            _assert_close(json.loads(json.dumps(mine)), row, f"{name} estimate {row['position']}")
        assert result.warnings == ref["warnings"], name


def test_reruns_and_source_order_are_bit_identical():
    for name, (make, _) in SPECS.items():
        _, _, first = _compute(name)
        records = make()
        random.Random(11).shuffle(records)
        _, _, shuffled = _compute(name, records)
        assert _bits(first.estimates) == _bits(shuffled.estimates), name
        assert first.fits == shuffled.fits, name


def test_the_stored_snapshot_reproduces_the_estimates_exactly():
    for name in SPECS:
        spec, built, reference = _compute(name)
        again = run_spec(from_parquet(to_parquet(built.frame)), spec)
        assert _bits(again.estimates) == _bits(reference.estimates), name


def test_the_golden_specs_cover_the_extensions():
    kinds, estimators, statuses = set(), set(), set()
    for name in SPECS:
        _, _, result = _compute(name)
        kinds |= {r["kind"] for r in result.estimates}
        estimators |= {r["estimator"] for r in result.estimates}
        statuses |= {r["status"] for r in result.estimates}
    assert kinds == {"linear", "ame", "wald"}
    assert estimators == {"plackett_luce", "clogit_rank1", "fe_ols", "bradley_terry", "logit", "spearman"}
    assert "ok" in statuses


def regenerate() -> None:
    payload = {"engine_version": ENGINE_VERSION, "specs": {}}
    for name in SPECS:
        spec, built, result = _compute(name)
        payload["specs"][name] = {
            "spec_hash": spec_hash(spec),
            "frame_hash": built.hash,
            "warnings": result.warnings,
            "estimates": json.loads(json.dumps(result.estimates)),
        }
    with open(GOLDEN, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    regenerate()
