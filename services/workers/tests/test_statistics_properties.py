"""Property-based tests for ml_evaluation.statistics (hypothesis).

These assert mathematical INVARIANTS that hold for all inputs, not hand-picked
examples — which is what kills the off-by-one / wrong-operator / boundary mutants
that example tests miss (the mutation co-gate, issue: meaningful-coverage program).

Invariants covered:
  * bootstrap_confidence_interval (mean): ci_lower <= ci_upper, both within the
    data range, std_error >= 0, point_estimate == mean, deterministic (seeded).
  * cohens_d: reflexivity d(x,x)==0, antisymmetry d(a,b)==-d(b,a), pooled_std>=0.
  * cliffs_delta: bounded in [-1, 1], antisymmetry, reflexivity == 0.
  * aggregate_with_statistics: min<=mean<=max, std>=0, constant-list collapse,
    metric-name passthrough, empty-input -> None.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ml_evaluation.statistics import (
    aggregate_with_statistics,
    bootstrap_confidence_interval,
    cliffs_delta,
    cohens_d,
)

# Finite, moderately-bounded floats — avoids numpy overflow / precision noise
# while still exercising negatives, zeros, and a wide magnitude range.
_finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_scores = st.lists(_finite, min_size=2, max_size=40)


class TestBootstrapCI:
    @settings(max_examples=60, deadline=None)
    @given(data=_scores)
    def test_mean_ci_is_bounded_and_ordered(self, data):
        r = bootstrap_confidence_interval(data, statistic="mean")
        lo, hi = min(data), max(data)
        # A mean of resampled-from-data values can never leave the data range.
        assert lo - 1e-6 <= r["ci_lower"] <= r["ci_upper"] <= hi + 1e-6
        assert r["std_error"] >= 0.0
        assert lo - 1e-6 <= r["point_estimate"] <= hi + 1e-6
        assert r["point_estimate"] == pytest.approx(sum(data) / len(data), rel=1e-6, abs=1e-6)

    @settings(max_examples=30, deadline=None)
    @given(data=_scores)
    def test_seeded_bootstrap_is_deterministic(self, data):
        # Same default random_state -> byte-identical CI (guards against an
        # un-seeded RNG mutant making results irreproducible).
        a = bootstrap_confidence_interval(data, statistic="mean")
        b = bootstrap_confidence_interval(data, statistic="mean")
        assert a == b


class TestCohensD:
    @settings(max_examples=60, deadline=None)
    @given(data=_scores)
    def test_reflexivity_zero_effect(self, data):
        # Identical distributions => zero effect size.
        assert cohens_d(data, data)["cohens_d"] == pytest.approx(0.0, abs=1e-9)

    @settings(max_examples=60, deadline=None)
    @given(a=_scores, b=_scores)
    def test_antisymmetry_and_nonneg_pooled_std(self, a, b):
        d_ab = cohens_d(a, b)
        d_ba = cohens_d(b, a)
        assert d_ab["pooled_std"] >= 0.0
        # Swapping the arguments negates the effect size.
        assert d_ab["cohens_d"] == pytest.approx(-d_ba["cohens_d"], rel=1e-6, abs=1e-9)


class TestCliffsDelta:
    @settings(max_examples=60, deadline=None)
    @given(a=_scores, b=_scores)
    def test_bounded_and_antisymmetric(self, a, b):
        delta_ab = cliffs_delta(a, b)["cliffs_delta"]
        delta_ba = cliffs_delta(b, a)["cliffs_delta"]
        assert -1.0 <= delta_ab <= 1.0
        assert delta_ab == pytest.approx(-delta_ba, abs=1e-9)

    @settings(max_examples=40, deadline=None)
    @given(data=_scores)
    def test_reflexivity_zero(self, data):
        assert cliffs_delta(data, data)["cliffs_delta"] == pytest.approx(0.0, abs=1e-9)


class TestAggregateWithStatistics:
    @settings(max_examples=60, deadline=None)
    @given(data=_scores, name=st.text(min_size=1, max_size=20))
    def test_central_tendency_within_range_and_passthrough(self, data, name):
        r = aggregate_with_statistics(data, name)
        assert r["metric"] == name
        assert r["n_samples"] == len(data)
        assert r["min"] <= r["mean"] <= r["max"]
        assert r["min"] <= r["median"] <= r["max"]
        assert r["std"] >= 0.0

    @settings(max_examples=40, deadline=None)
    @given(c=_finite, n=st.integers(min_value=2, max_value=30), name=st.text(max_size=10))
    def test_constant_list_collapses(self, c, n, name):
        # All-equal scores => zero spread, CI collapses to the constant.
        r = aggregate_with_statistics([c] * n, name)
        assert r["mean"] == pytest.approx(c, abs=1e-6)
        assert r["std"] == pytest.approx(0.0, abs=1e-6)
        assert r["ci_lower"] == pytest.approx(c, abs=1e-6)
        assert r["ci_upper"] == pytest.approx(c, abs=1e-6)

    def test_empty_input_returns_none(self):
        r = aggregate_with_statistics([], "metric")
        assert r["mean"] is None and r["n_samples"] == 0

    @settings(max_examples=30, deadline=None)
    @given(data=_scores)
    def test_no_nan_in_outputs(self, data):
        r = aggregate_with_statistics(data, "m")
        for key in ("mean", "median", "std", "min", "max"):
            assert not math.isnan(r[key])
