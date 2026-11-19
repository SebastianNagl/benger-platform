"""Synthetic variant experiments for the estimator extensions and slot frames.

Invented data only, generated with ``random.Random(seed)`` (whose sequence
Python keeps stable across versions), as observation records
(:func:`analysis.observations.observation_from_record`):

* :func:`docket_records`: a docket design. Every unit is one docket of six
  cases, each case a slot (``meta.variant.slots``, index 0-5 as a Label
  Studio Repeater names its controls ``risk_0`` ... ``risk_5``) with its own
  factors (position, offence, group, name); the answer gives a risk, a
  probation probability, a sentence and a priority rank per case. A few
  answers repeat a rank (no valid ranking), and single-case control tasks
  have one slot.
* :func:`persons_records`: two persons per task (slots 1 and 2) with a role,
  a group and a name each; the answer gives a sentence, a probation
  probability and a credibility per person and whether the court followed
  the first person.
* :func:`pairs_records`: head-to-head comparisons of two persons (slots 1
  and 2) of two groups; the answer chooses one of them (``choice`` 1 or 2)
  and rates both.
* :func:`single_records`: one person per task (a group, a gender, a name),
  answered with a sentence and a probation decision (0/1).

Group, offence and name labels are neutral (``ref``, ``a``, ``b``, ...).
The effects are known, so tests can also check that estimators recover them
in direction.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List

SYSTEMS = ("sys_a", "sys_b", "sys_c")
DOCKET_GROUPS = ("ref", "a", "b", "c", "d", "e")
OFFENCES = ("f0", "f1", "f2", "f3", "f4", "f5")
PAIR_GROUPS = ("ref", "a", "b", "c", "d", "e", "f")
SINGLE_GROUPS = ("ref", "a", "b", "c", "d", "e", "f", "control")
CASES = ("c1", "c2", "c3")

DOCKET_GROUP_EFFECT = {"ref": 0.0, "a": 0.2, "b": 0.5, "c": -0.3, "d": 0.4, "e": 0.1}
OFFENCE_EFFECT = {"f0": 0.0, "f1": 0.6, "f2": -0.4, "f3": 0.3, "f4": -0.2, "f5": 0.5}
PAIR_STRENGTH = {"ref": 0.0, "a": 0.15, "b": -0.25, "c": 0.3, "d": -0.1, "e": 0.2, "f": -0.35}
SINGLE_EFFECT = {"ref": 0.0, "a": 0.3, "b": -0.4, "c": 0.5, "d": 0.2, "e": -0.2, "f": 0.1, "control": 0.05}


def _normal(rng: random.Random) -> float:
    u1 = max(rng.random(), 1e-12)
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _gumbel(rng: random.Random) -> float:
    return -math.log(-math.log(max(rng.random(), 1e-12)))


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _record(gid: int, task: str, system: str, design: str, unit: str, factors, slots, fields, **extra):
    rec = {
        "generation_id": f"gen_{gid:06d}",
        "task_id": task,
        "model_id": system,
        "variant": {"design": design, "unit": unit, "factors": factors, "slots": slots},
        "fields": fields,
    }
    rec.update(extra)
    return rec


def docket_records(dockets: int = 180, seed: int = 20261119, systems=SYSTEMS, controls: int = 24) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    names = {g: [f"{g}_{i}" for i in range(4)] for g in DOCKET_GROUPS}
    sys_effect = {s: 0.3 * i for i, s in enumerate(systems)}
    records: List[Dict[str, Any]] = []
    gid = 0
    for d in range(dockets):
        unit = f"docket_{d:04d}"
        gender = "f" if d % 2 else "m"
        slots = []
        for i in range(6):
            group = DOCKET_GROUPS[rng.randrange(len(DOCKET_GROUPS))]
            offence = OFFENCES[rng.randrange(len(OFFENCES))]
            slots.append(
                {
                    "index": i,
                    "factors": {
                        "pos": i + 1,
                        "fact": offence,
                        "group": group,
                        "name_id": names[group][rng.randrange(4)],
                    },
                }
            )
        for system in systems:
            gid += 1
            fields: Dict[str, Any] = {}
            utility = []
            for slot in slots:
                f = slot["factors"]
                base = DOCKET_GROUP_EFFECT[f["group"]] + OFFENCE_EFFECT[f["fact"]] + sys_effect[system]
                i = slot["index"]
                fields[f"risk_{i}"] = round(_clip(40 + 10 * base - 1.5 * f["pos"] + 8 * _normal(rng), 0, 100))
                fields[f"prob_{i}"] = round(_clip(55 - 8 * base + 9 * _normal(rng), 0, 100))
                fields[f"months_{i}"] = round(_clip(8 + 3 * base + 2.5 * _normal(rng), 1, 36))
                utility.append(base - 0.08 * f["pos"] + _gumbel(rng))
            order = sorted(range(6), key=lambda j: -utility[j])
            for rank, j in enumerate(order, start=1):
                fields[f"rank_{j}"] = rank
            if rng.random() < 0.04:  # a repeated rank: no valid ranking
                fields["rank_5"] = fields["rank_0"]
            records.append(
                _record(gid, f"task_{unit}", system, "docket", unit, {"kind": "docket", "gender": gender}, slots, fields)
            )
    for c in range(controls):
        unit = f"control_{c:03d}"
        offence = OFFENCES[c % len(OFFENCES)]
        slots = [{"index": 0, "factors": {"pos": 1, "fact": offence, "group": "control", "name_id": "control"}}]
        for system in systems:
            gid += 1
            base = OFFENCE_EFFECT[offence] + sys_effect[system]
            fields = {
                "risk_0": round(_clip(40 + 10 * base + 8 * _normal(rng), 0, 100)),
                "prob_0": round(_clip(55 - 8 * base + 9 * _normal(rng), 0, 100)),
                "months_0": round(_clip(8 + 3 * base + 2.5 * _normal(rng), 1, 36)),
                "rank_0": 1,
            }
            records.append(
                _record(gid, f"task_{unit}", system, "docket", unit, {"kind": "control", "gender": "f"}, slots, fields)
            )
    return records


def persons_records(units: int = 90, seed: int = 20261120, systems=SYSTEMS) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    groups = DOCKET_GROUPS[:4]
    records: List[Dict[str, Any]] = []
    gid = 0
    for u in range(units):
        unit = f"pair_{u:03d}"
        g1, g2 = groups[u % 4], groups[(u // 4) % 4]
        for variant in ("ab", "ba"):
            first_main = variant == "ab"
            slots = [
                {"index": 1, "factors": {"role": "main" if first_main else "accessory", "group": g1, "name_id": f"{g1}_{u % 3}"}},
                {"index": 2, "factors": {"role": "accessory" if first_main else "main", "group": g2, "name_id": f"{g2}_{(u + 1) % 3}"}},
            ]
            for system in systems:
                gid += 1
                fields: Dict[str, Any] = {"follow": int(rng.random() < 0.6)}
                for slot in slots:
                    f = slot["factors"]
                    shift = DOCKET_GROUP_EFFECT[f["group"]] + (1.0 if f["role"] == "main" else 0.0)
                    i = slot["index"]
                    fields[f"months_{i}"] = round(_clip(12 + 4 * shift + 3 * _normal(rng), 1, 60))
                    fields[f"prob_{i}"] = round(_clip(50 - 10 * shift + 10 * _normal(rng), 0, 100))
                    fields[f"cred_{i}"] = int(_clip(round(4 - shift + _normal(rng)), 1, 7))
                factors = {
                    "case": CASES[u % 3],
                    "variant": variant,
                    "pairtype": f"{g1}|{g2}",
                    "kind": "same" if g1 == g2 else "cross",
                    "gender": "f" if u % 2 else "m",
                }
                records.append(_record(gid, f"task_{unit}_{variant}", system, "persons", unit, factors, slots, fields))
    return records


def pairs_records(units: int = 160, seed: int = 20261121, systems=SYSTEMS) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    records: List[Dict[str, Any]] = []
    gid = 0
    for u in range(units):
        unit = f"pairkey_{u:03d}"
        ga = PAIR_GROUPS[u % len(PAIR_GROUPS)]
        gb = PAIR_GROUPS[(u + 1 + (u // len(PAIR_GROUPS)) % (len(PAIR_GROUPS) - 1)) % len(PAIR_GROUPS)]
        case = CASES[u % 3]
        gender = "f" if (u // 3) % 2 else "m"
        for order in (0, 1):
            g1, g2 = (ga, gb) if order == 0 else (gb, ga)
            slots = [
                {"index": 1, "factors": {"group": g1, "name_id": f"{g1}_{u % 5}"}},
                {"index": 2, "factors": {"group": g2, "name_id": f"{g2}_{(u + 2) % 5}"}},
            ]
            for s_i, system in enumerate(systems):
                for rep in range(2):
                    gid += 1
                    position = 0.3 if case == "c1" else (-0.2 if case == "c2" else 0.1)
                    eta = position + 0.2 * s_i + PAIR_STRENGTH[g1] - PAIR_STRENGTH[g2]
                    choice = 1 if rng.random() < 1 / (1 + math.exp(-eta)) else 2
                    fields = {
                        "choice": choice,
                        "rating_1": int(_clip(round(4 + PAIR_STRENGTH[g1] * 2 + _normal(rng)), 1, 7)),
                        "rating_2": int(_clip(round(4 + PAIR_STRENGTH[g2] * 2 + _normal(rng)), 1, 7)),
                    }
                    factors = {"case": case, "order": order, "gender": gender, "ga": ga, "gb": gb, "rep": rep}
                    records.append(
                        _record(gid, f"task_{unit}_{order}", system, "pairs", unit, factors, slots, fields, run_index=rep)
                    )
    return records


def single_records(names_per_group: int = 6, reps: int = 6, seed: int = 20261122, systems=SYSTEMS) -> List[Dict[str, Any]]:
    """The sentence (``months``) is drawn from its own generator, so its name
    effects and noise do not depend on the probation draws."""
    rng = random.Random(seed)
    rng_months = random.Random(seed + 7)
    records: List[Dict[str, Any]] = []
    gid = 0
    name_effect = {}
    months_name_effect = {}
    for group in SINGLE_GROUPS:
        for k in range(names_per_group):
            name_effect[f"{group}_{k}"] = 0.35 * _normal(rng)
            months_name_effect[f"{group}_{k}"] = 2.0 * _normal(rng_months)
    for group in SINGLE_GROUPS:
        for k in range(names_per_group):
            name = f"{group}_{k}"
            for gender in ("f", "m"):
                unit = f"{name}_{gender}"
                for s_i, system in enumerate(systems):
                    for rep in range(reps):
                        gid += 1
                        eta = -0.2 + SINGLE_EFFECT[group] + (0.3 if gender == "m" else 0.0) + 0.25 * s_i + name_effect[name]
                        probation = 1 if rng.random() < 1 / (1 + math.exp(-eta)) else 0
                        months = round(
                            _clip(
                                10 + 3 * SINGLE_EFFECT[group] + 1.5 * (gender == "m") + 0.5 * s_i
                                + months_name_effect[name] + 2 * _normal(rng_months),
                                1,
                                40,
                            )
                        )
                        records.append(
                            _record(
                                gid, f"task_{unit}", system, "single", unit,
                                {"group": group, "gender": gender, "name_id": name, "case": "c1"},
                                [], {"probation": probation, "months": months}, run_index=rep,
                            )
                        )
    return records


#: Seed of the second project's docket records in cross-project frames.
SECOND_PROJECT_SEED = 20261123


def congruence_lookup(seed: int = 20261124, systems=SYSTEMS) -> List[Dict[str, Any]]:
    """A lookup table keyed by system, offence and group (every group but the
    reference): a 0/1 code ``cong`` and a rating difference ``assoc``."""
    rng = random.Random(seed)
    rows = []
    for system in systems:
        for offence in OFFENCES:
            for group in DOCKET_GROUPS[1:]:
                assoc = round(2 * _normal(rng), 3)
                rows.append({"model": system, "fact": offence, "group": group, "cong": int(assoc > 1.0), "assoc": assoc})
    return rows


def congruence_pooled(seed: int = 20261125) -> List[Dict[str, Any]]:
    """A lookup table keyed by offence and group: a pooled 0/1 code."""
    rng = random.Random(seed)
    return [
        {"fact": offence, "group": group, "cong_pool": int(rng.random() < 0.3)}
        for offence in OFFENCES
        for group in DOCKET_GROUPS[1:]
    ]


def docket_design() -> Dict[str, Any]:
    """The variant design (``variant_designs`` spec) of :func:`docket_records`
    without control tasks: six slots indexed 0-5 like Repeater controls."""
    names = [f"{g}_{i}" for g in DOCKET_GROUPS for i in range(4)]
    return {
        "schema_version": 1,
        "title": "Docket",
        "unit": {"name": "docket"},
        "factors": [
            {"name": "kind", "type": "nominal", "levels": ["docket", "control"], "varies": "between_units"},
            {"name": "gender", "type": "nominal", "levels": ["f", "m"], "varies": "between_units"},
        ],
        "slots": {
            "count": 6,
            "index_base": 0,
            "factors": [
                {"name": "pos", "type": "numeric", "minimum": 1, "maximum": 6},
                {"name": "fact", "type": "nominal", "levels": list(OFFENCES)},
                {"name": "group", "type": "nominal", "levels": list(DOCKET_GROUPS)},
                {"name": "name_id", "type": "nominal", "levels": names, "role": "nuisance"},
            ],
        },
        "outcomes": [
            {"name": name, "control": f"{name}_{{idx}}", "per_slot": True} for name in ("risk", "prob", "months", "rank")
        ],
    }
