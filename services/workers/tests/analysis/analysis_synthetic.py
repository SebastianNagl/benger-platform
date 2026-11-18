"""Synthetic variant experiments for the analysis engine tests.

Invented data only. :func:`role_swap_records` builds a counterfactual
role-swap design: every unit is one case rendered four times (the party of
interest X as claimant or respondent, X's account printed first or second),
answered by several systems; the answer is X's opponent's share ``share_p``
in steps of 5. The generator uses ``random.Random(seed).random()`` only,
whose sequence Python keeps stable across versions, so the records (and the
golden estimates computed from them) do not depend on numpy's generators.
"""

from __future__ import annotations

import copy
import math
import random
from typing import Any, Dict, List

SYSTEMS = ("sys_a", "sys_b", "sys_c")
ROLE_EFFECT = {"sys_a": -12.0, "sys_b": -3.0, "sys_c": 0.0}
SLOPE = {"sys_a": 0.6, "sys_b": 0.3, "sys_c": 0.0}
LEVELS = (0, 25, 50, 75, 100)


def _normal(rng: random.Random) -> float:
    """Box-Muller from two uniforms (deterministic given the uniforms)."""
    u1 = max(rng.random(), 1e-12)
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def role_swap_records(units: int = 48, seed: int = 20261118, systems=SYSTEMS) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    names = [f"name_{i:02d}" for i in range(11)]
    records: List[Dict[str, Any]] = []
    gid = 0
    for u in range(units):
        unit = f"case_{u:03d}"
        level = LEVELS[u % len(LEVELS)]
        name = names[(u * 7) % len(names)]
        scenario = f"sc_{u % 6}"
        for system in systems:
            unit_effect = 6.0 * _normal(rng)
            for role in ("P", "D"):
                for first in ("P", "D"):
                    x_p = 1.0 if role == "P" else 0.0
                    first_x = 1.0 if role == first else 0.0
                    share_x = (
                        50.0
                        + SLOPE[system] * (level - 50)
                        + ROLE_EFFECT[system] * (x_p - 0.5)
                        + 1.5 * (first_x - 0.5)
                        + unit_effect
                        + 8.0 * _normal(rng)
                    )
                    share_x = min(100.0, max(0.0, round(share_x / 5.0) * 5.0))
                    share_p = share_x if role == "P" else 100.0 - share_x
                    credible = ("P", "D", "E")[int(rng.random() * 3)]
                    gid += 1
                    parse_ok = rng.random() > 0.02
                    records.append(
                        {
                            "generation_id": f"gen_{gid:05d}",
                            "task_id": f"task_{u:03d}_{role}{first}",
                            "model_id": system,
                            "variant": {
                                "design": "role_swap",
                                "unit": unit,
                                "factors": {
                                    "x_role": role,
                                    "first": first,
                                    "level": level,
                                    "scenario": scenario,
                                    "name_id": name,
                                },
                            },
                            "fields": (
                                {"share_p": share_p, "credible": credible} if parse_ok else {}
                            ),
                            "parse_ok": parse_ok,
                            "task_data": {"gold": {"low": max(0, level - 10), "high": min(100, level + 10)}},
                        }
                    )
    return records


MEASURES: Dict[str, Any] = {
    "share_p": {"kind": "field", "field": "share_p"},
    "credible": {"kind": "field", "field": "credible", "type": "text"},
    "x_p": {"kind": "expression", "expr": "1 * (x_role == 'P')"},
    "first_x": {"kind": "expression", "expr": "1 * (x_role == first)"},
    "share_x": {"kind": "expression", "expr": "if(x_p == 1, share_p, 100 - share_p)"},
    "gold_low": {"kind": "gold", "path": "gold.low"},
    "gold_high": {"kind": "gold", "path": "gold.high"},
    "in_gold": {"kind": "expression", "expr": "100 * (share_x >= gold_low and share_x <= gold_high)"},
    "fifty": {"kind": "expression", "expr": "100 * (share_p == 50)"},
    "wrong": {"kind": "expression", "expr": "if(level in (0, 100), 100 * (if(level > 50, share_x, 100 - share_x) < 50), null)"},
    "fault_p": {"kind": "expression", "expr": "if(level != 50, if(level > 50, x_p, 1 - x_p), null)"},
}

TWO_WAY = {"type": "cluster", "by": ["unit", "name_id"]}
UNIT_SYSTEM = [["unit", "system"]]


def role_swap_spec() -> Dict[str, Any]:
    """A spec exercising every estimator, contrast kind and family option."""
    scopes = ["pooled", {"by": ["system"]}]
    return {
        "spec_version": 1,
        "name": "role swap",
        "inputs": {"designs": ["role_swap"]},
        "measures": copy.deepcopy(MEASURES),
        "conventions": {"ci_critical": 1.96, "degenerate_p": "null_match"},
        "estimands": [
            {
                "id": "role",
                "estimator": "fe_ols",
                "outcome": "share_x",
                "terms": ["x_p", "first_x"],
                "fixed_effects": UNIT_SYSTEM,
                "vcov": TWO_WAY,
                "scopes": scopes,
                "contrasts": [
                    {"id": "role", "weights": {"x_p": 1}, "tost": [{"margin": 3}, {"margin": 2}]},
                    {"id": "order", "weights": {"first_x": 1}},
                ],
            },
            {
                "id": "slope",
                "estimator": "fe_ols",
                "outcome": "share_x",
                "terms": ["level", "x_p", "first_x"],
                "fixed_effects": [["scenario", "system"]],
                "vcov": TWO_WAY,
                "scopes": scopes,
                "contrasts": [{"id": "slope", "weights": {"level": 1}, "null": 1}],
            },
            {
                "id": "role_by_system",
                "estimator": "fe_ols",
                "outcome": "share_x",
                "terms": [
                    "x_p",
                    {"interact": ["x_p", {"dummies": "system", "reference": "sys_c"}]},
                    "first_x",
                ],
                "fixed_effects": UNIT_SYSTEM,
                "vcov": {"type": "cluster", "by": ["unit"]},
                "contrasts": [
                    {"id": "did sys_a", "weights": {"x_p:system[sys_a]": 1}},
                    {"id": "did sys_b", "weights": {"x_p:system[sys_b]": 1}},
                    {
                        "id": "share removed sys_a",
                        "kind": "ratio",
                        "numerator": {"weights": {"x_p:system[sys_a]": 1}},
                        "denominator": {"weights": {"x_p": 1}},
                        "scale": -1,
                        "min_abs_denominator": 0.5,
                    },
                ],
            },
            {
                "id": "wrong_side",
                "estimator": "fe_ols",
                "outcome": "wrong",
                "subset": "level in (0, 100)",
                "terms": ["fault_p", "first_x"],
                "fixed_effects": UNIT_SYSTEM,
                "vcov": TWO_WAY,
                "scopes": scopes,
                "contrasts": [{"id": "wrong side", "weights": {"fault_p": 1}, "tost": {"margin": 5}}],
            },
            {
                "id": "credible_claimant",
                "estimator": "fe_ols",
                "outcome": "share_x",
                "subset": "credible in ('P', 'D')",
                "terms": [{"dummies": "credible", "reference": "D"}],
                "vcov": {"type": "hc1"},
                "contrasts": "terms",
            },
            {
                "id": "fifty_rate",
                "estimator": "mean_rate",
                "outcome": "fifty",
                "scopes": scopes,
                "contrasts": [{"id": "rate", "weights": {"(mean)": 1}, "mde": {"tests": 3}}],
            },
            {
                "id": "role_pairs",
                "estimator": "paired_within",
                "outcome": "share_x",
                "pair_by": ["unit", "system"],
                "treatment": {"factor": "x_role", "level": "P", "reference": "D"},
                "vcov": {"type": "cluster", "by": ["unit"]},
                "min_n": 10,
            },
            {
                "id": "in_gold",
                "estimator": "fe_ols",
                "outcome": "in_gold",
                "terms": [{"dummies": "system", "reference": "sys_a"}],
                "vcov": {"type": "cluster", "by": ["unit"]},
                "conventions": {"inference": "t", "ci_critical": "exact"},
                "contrasts": "terms",
            },
        ],
        "families": [
            {
                "id": "primary",
                "method": "holm",
                "members": [
                    {"estimand": "role", "contrast": "role", "scope": "pooled"},
                    {"estimand": "slope", "scope": "pooled"},
                    {"estimand": "wrong_side", "scope": "pooled"},
                ],
                "mde": {"power": 0.8},
            },
            {
                "id": "per_system",
                "method": "holm",
                "members": [
                    {"estimand": "role", "contrast": "role", "scope": "by:system"},
                    {"estimand": "wrong_side", "scope": "by:system"},
                ],
                "split_by": ["estimand"],
                "missing_p": "count",
            },
            {
                "id": "exploratory",
                "method": "bh",
                "exploratory": True,
                "members": [{"estimand": "role_by_system"}, {"estimand": "in_gold"}],
            },
        ],
    }
