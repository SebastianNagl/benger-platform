"""Golden estimates and determinism.

``golden_estimates.json`` records every estimate of the synthetic role-swap
spec (all estimators, contrast kinds, scopes and family options) together with
the engine version, the spec hash and the frame hash. Any change to a number
fails :func:`test_estimates_equal_the_golden_file`: when the change is
intended, bump ``analysis.version.ENGINE_VERSION`` and regenerate with

    python services/workers/tests/analysis/test_analysis_golden.py

Reruns on one machine are bit-identical, which the determinism tests check
exactly. Across machines they are not: numpy's OpenBLAS picks its kernels by
CPU (an AVX-512 runner and an AVX2 desktop sum in different orders), which
moves the fitted quantities by a few units in the last place. The thread count
does not matter. The golden comparison therefore allows ``REL_TOL`` (1e-12)
of relative error, measured against what each field's rounding error scales
with rather than against the field itself (see :func:`_assert_close`):

* most floats are compared relative to their own value;
* an interval bound is ``estimate +- crit * std_error`` and cancels when the
  bound is near zero (``-26.39 + 26.37 = -0.02``), so its error scales with
  ``|estimate| + crit * std_error``, which is ``max(|ci_lower|, |ci_upper|)``;
* a tail p-value ``p = P(|T| > |t|)`` amplifies a relative error ``e`` of the
  statistic to about ``t**2 * e`` in ``p``, while ``log p`` (about
  ``-t**2 / 2``) keeps it near ``2 * e``, so p-values are compared on the log
  scale, relative to ``max(1, |log p|)``.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden_estimates.json")

if __name__ == "__main__":  # regeneration: make /shared and this folder importable
    sys.path[:0] = [HERE, os.path.normpath(os.path.join(HERE, "..", "..", "..", "shared"))]

from analysis.frame import build_frame, from_parquet, to_parquet  # noqa: E402
from analysis.observations import observations_from_records  # noqa: E402
from analysis.runner import run_spec  # noqa: E402
from analysis.spec import normalize_spec, spec_hash  # noqa: E402
from analysis.version import ENGINE_VERSION  # noqa: E402
from analysis_synthetic import role_swap_records, role_swap_spec  # noqa: E402


def _compute(records=None):
    spec = normalize_spec(role_swap_spec())
    built = build_frame(observations_from_records(records or role_swap_records()), spec)
    result = run_spec(built.frame, spec)
    return spec, built, result


def _bits(value):
    """A representation that differs for any two different floats."""
    if isinstance(value, float):
        return ("f", value.hex())
    if isinstance(value, dict):
        return {k: _bits(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_bits(v) for v in value]
    return value


REL_TOL = 1e-12
INTERVAL_KEYS = frozenset({"ci_lower", "ci_upper"})
P_VALUE_KEYS = frozenset({"p_value", "p_adjusted", "p_lower", "p_upper", "p_tost"})


def _floats(*values):
    return all(isinstance(v, float) and math.isfinite(v) for v in values)


def _assert_close(mine, golden, path="estimate"):
    """Compare an estimate row with its golden copy to ``REL_TOL``, scaled per
    field as the module docstring explains."""
    if isinstance(golden, float) and isinstance(mine, float):
        assert math.isclose(mine, golden, rel_tol=REL_TOL, abs_tol=1e-300), f"{path}: {mine!r} != {golden!r}"
    elif isinstance(golden, dict):
        assert isinstance(mine, dict) and set(mine) == set(golden), f"{path}: keys differ"
        bounds = [golden.get(k) for k in INTERVAL_KEYS]
        interval_scale = max(abs(b) for b in bounds) if _floats(*bounds) else None
        for k in golden:
            a, b, where = mine[k], golden[k], f"{path}.{k}"
            if k in INTERVAL_KEYS and interval_scale and _floats(a, b):
                assert math.isclose(a, b, rel_tol=REL_TOL, abs_tol=REL_TOL * interval_scale), f"{where}: {a!r} != {b!r}"
            elif k in P_VALUE_KEYS and _floats(a, b) and a > 0 and b > 0:
                ok = math.isclose(math.log(a), math.log(b), rel_tol=REL_TOL, abs_tol=REL_TOL)
                assert ok, f"{where}: {a!r} != {b!r} (compared as log p)"
            else:
                _assert_close(a, b, where)
    elif isinstance(golden, list):
        assert isinstance(mine, list) and len(mine) == len(golden), f"{path}: lengths differ"
        for i, (a, b) in enumerate(zip(mine, golden)):
            _assert_close(a, b, f"{path}[{i}]")
    else:
        assert mine == golden, f"{path}: {mine!r} != {golden!r}"


def test_estimates_equal_the_golden_file():
    with open(GOLDEN, encoding="utf-8") as fh:
        golden = json.load(fh)
    spec, built, result = _compute()
    assert golden["engine_version"] == ENGINE_VERSION, (
        "the golden file belongs to another engine version; regenerate it "
        "(see the module docstring) after reviewing the numeric change"
    )
    assert golden["spec_hash"] == spec_hash(spec)
    assert golden["frame_hash"] == built.hash
    assert len(result.estimates) == len(golden["estimates"])
    for mine, ref in zip(result.estimates, golden["estimates"]):
        _assert_close(json.loads(json.dumps(mine)), ref, f"estimate {ref['position']}")
    assert result.warnings == golden["warnings"]


def test_reruns_are_bit_identical():
    _, _, first = _compute()
    _, _, second = _compute()
    assert _bits(first.estimates) == _bits(second.estimates)
    assert first.fits == second.fits


def test_source_order_does_not_change_a_bit():
    _, _, reference = _compute()
    records = role_swap_records()
    random.Random(7).shuffle(records)
    _, _, shuffled = _compute(records)
    assert _bits(shuffled.estimates) == _bits(reference.estimates)


def test_the_stored_snapshot_reproduces_the_estimates_exactly():
    spec, built, reference = _compute()
    back = from_parquet(to_parquet(built.frame))
    again = run_spec(back, spec)
    assert _bits(again.estimates) == _bits(reference.estimates)


def test_the_golden_spec_covers_every_status_and_option():
    _, _, result = _compute()
    statuses = {r["status"] for r in result.estimates}
    assert {"ok"} <= statuses
    kinds = {r["kind"] for r in result.estimates}
    assert kinds == {"linear", "ratio"}
    estimators = {r["estimator"] for r in result.estimates}
    assert estimators == {"fe_ols", "mean_rate", "paired_within"}
    assert any(r["tost"] and len(r["tost"]) == 2 for r in result.estimates)
    assert any(r["family"] == "exploratory" for r in result.estimates)
    assert any(r["df"] for r in result.estimates)


def regenerate() -> None:
    spec, built, result = _compute()
    payload = {
        "engine_version": ENGINE_VERSION,
        "spec_hash": spec_hash(spec),
        "frame_hash": built.hash,
        "warnings": result.warnings,
        "estimates": json.loads(json.dumps(result.estimates)),
    }
    with open(GOLDEN, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {GOLDEN}: {len(result.estimates)} estimates")


if __name__ == "__main__":
    regenerate()
