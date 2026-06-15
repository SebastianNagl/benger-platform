"""Hand-computed kill tests for the LEADERBOARD aggregation logic.

`shared/aggregate_summaries.py` computes the leaderboard scores + project
summary statistics that users see and cite. A wrong operator, constant,
comparison, rounding, sort-direction, or filter boundary here mis-ranks
published results. These tests pin the PURE aggregation helpers to
KNOWN-input -> HAND-COMPUTED-output so any such mutation fails.

Pure helpers under test (deterministic, no DB):
  * _period_cutoff          — period -> time-window cutoff
  * _coerce_metric_value    — JSON metric value -> float | None
  * _confidence_interval    — sample -> 95% t-CI of the mean
  * metric_key_is_real      — the noise filter that decides which metric
                              keys count toward an aggregate (re-exported by
                              this module from metric_filters)

The mean/sum + round(...,4) rollup and the leaderboard tie-break SORT live
inside the DB-bound functions (`_aggregate_leaderboard_rows`,
`read_llm_leaderboard`). Those are pinned by the real-DB sibling suite
`tests/integration/test_aggregate_summaries_ranking_kills.py` (it needs the
`db_conn` + factory fixtures that only exist under `tests/integration/`) and
by `services/api/tests/unit/test_aggregate_summaries.py`. This file pins the
PURE, no-DB helpers.

Import setup mirrors the other workers pure-helper kill suites
(test_statistics_mutation_kills.py): /shared is first on sys.path inside the
worker test container, so `import aggregate_summaries` resolves to the
shared module.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# /shared is placed first on sys.path by services/workers/tests/conftest.py.
# Re-assert workers_root for parity with the sibling kill suites; the shared
# dir is already wired by conftest before this module imports.
workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import aggregate_summaries as agg  # noqa: E402
from aggregate_summaries import (  # noqa: E402
    _coerce_metric_value,
    _confidence_interval,
    _period_cutoff,
)
from metric_filters import metric_key_is_real  # noqa: E402


# ===========================================================================
# _period_cutoff — period -> time-window cutoff (noise/period boundary)
# ===========================================================================
class TestPeriodCutoff:
    def test_overall_has_no_cutoff(self):
        # 'overall' must NOT filter by time. A mutation that returns a
        # datetime here would silently drop historical evals from the
        # all-time leaderboard.
        assert _period_cutoff("overall") is None

    def test_unknown_period_falls_through_to_no_cutoff(self):
        # Any non-monthly/weekly string -> None (the function's else branch).
        assert _period_cutoff("yearly") is None
        assert _period_cutoff("") is None

    def test_monthly_is_30_days_back(self):
        before = datetime.now(timezone.utc)
        cutoff = _period_cutoff("monthly")
        after = datetime.now(timezone.utc)
        assert cutoff is not None
        # The cutoff is now-30d. Bracket it between (before-30d, after-30d)
        # so the test is immune to the microseconds between the two now()s
        # but still fails if the constant is 7/29/31/365 or the sign flips.
        assert before - timedelta(days=30) <= cutoff <= after - timedelta(days=30)
        # It must be strictly in the PAST, never the future (sign-flip kill).
        assert cutoff < before

    def test_weekly_is_7_days_back(self):
        before = datetime.now(timezone.utc)
        cutoff = _period_cutoff("weekly")
        after = datetime.now(timezone.utc)
        assert cutoff is not None
        assert before - timedelta(days=7) <= cutoff <= after - timedelta(days=7)
        assert cutoff < before

    def test_weekly_window_is_tighter_than_monthly(self):
        # Distinguishes the two constants from each other: a swap of 7<->30
        # must fail. Weekly cutoff is MORE RECENT (larger datetime) than
        # monthly because it reaches back fewer days.
        assert _period_cutoff("weekly") > _period_cutoff("monthly")

    def test_cutoff_is_timezone_aware_utc(self):
        # A naive datetime would break the `created_at >= cutoff` comparison
        # against tz-aware columns in the worker query.
        assert _period_cutoff("weekly").tzinfo is not None


# ===========================================================================
# _coerce_metric_value — JSON metric value -> float | None
# Wrong coercion silently drops a score from (or injects garbage into) a
# bucket, biasing the model's mean.
# ===========================================================================
class TestCoerceMetricValue:
    def test_none_is_none(self):
        assert _coerce_metric_value(None) is None

    def test_bool_is_rejected_even_though_python_bool_is_int(self):
        # CRITICAL: in Python `isinstance(True, int)` is True. If the bool
        # guard were removed/reordered, True would coerce to 1.0 and pollute
        # a numeric metric's mean. Both bools must map to None.
        assert _coerce_metric_value(True) is None
        assert _coerce_metric_value(False) is None

    def test_int_becomes_float(self):
        out = _coerce_metric_value(7)
        assert out == 7.0
        assert isinstance(out, float)

    def test_float_passthrough_exact(self):
        assert _coerce_metric_value(0.83) == 0.83

    def test_zero_is_preserved_not_treated_as_falsey(self):
        # A model legitimately scoring 0.0 must NOT be dropped (a `if not val`
        # style mutation would lose it and inflate the mean).
        out = _coerce_metric_value(0.0)
        assert out == 0.0
        assert out is not None

    def test_numeric_string_parses(self):
        assert _coerce_metric_value("12.5") == 12.5
        assert _coerce_metric_value("0") == 0.0

    def test_non_numeric_string_is_none(self):
        assert _coerce_metric_value("n/a") is None
        assert _coerce_metric_value("") is None

    def test_dict_value_key_preferred_first(self):
        # The dict branch tries ("value", "total_score", "score") IN ORDER.
        # 'value' wins when present.
        assert _coerce_metric_value(
            {"value": 0.7, "total_score": 99, "score": 1}
        ) == 0.7

    def test_dict_falls_through_value_keys_in_order(self):
        # 'value' absent -> 'total_score' next.
        assert _coerce_metric_value({"total_score": 14, "score": 3}) == 14.0
        # both absent -> 'score'.
        assert _coerce_metric_value({"score": 3}) == 3.0

    def test_dict_value_zero_is_used_not_skipped(self):
        # value=0.0 coerces to 0.0 (not None), so the loop must STOP at
        # 'value' and not fall through to 'score'. A `coerced is not None`
        # check (correct) vs a truthiness check (buggy) diverge here.
        assert _coerce_metric_value({"value": 0.0, "score": 5}) == 0.0

    def test_dict_skips_uncoercible_value_and_tries_next_key(self):
        # value is non-numeric -> None -> fall through to total_score.
        assert _coerce_metric_value({"value": "bad", "total_score": 8}) == 8.0

    def test_dict_with_no_recognised_keys_is_none(self):
        assert _coerce_metric_value({"foo": 1, "bar": 2}) is None

    def test_nested_dict_recursion(self):
        # value itself is a dict carrying a value -> recursion resolves it.
        assert _coerce_metric_value({"value": {"value": 4.5}}) == 4.5

    def test_unsupported_type_is_none(self):
        assert _coerce_metric_value([1, 2, 3]) is None


# ===========================================================================
# _confidence_interval — 95% t-CI of the mean
# A wrong t-quantile, sem formula, sign, or df mis-states every CI shown on
# the leaderboard. Values hand-computed against the documented t-distribution
# formula (verified independently with numpy/scipy).
# ===========================================================================
class TestConfidenceInterval:
    def test_fewer_than_two_samples_returns_none_none(self):
        # n<2 has no CI of the mean. Boundary: exactly 1 sample -> (None,None).
        assert _confidence_interval([]) == (None, None)
        assert _confidence_interval([0.5]) == (None, None)

    def test_zero_variance_collapses_to_the_mean(self):
        # All-equal samples -> sem==0 -> both bounds == the mean (not None,
        # not 0). Pins the sem==0 short-circuit branch.
        lo, hi = _confidence_interval([5.0, 5.0, 5.0])
        assert lo == 5.0
        assert hi == 5.0

    def test_two_sample_ci_exact_bounds(self):
        # values=[2,4]: mean=3, sample-std(ddof=1)=sqrt(2), sem=1.0,
        # t.ppf(0.975, df=1)=12.706204736174694, half=12.7062047...
        # => lower=-9.706204736174694, upper=15.706204736174694.
        lo, hi = _confidence_interval([2.0, 4.0])
        assert lo == pytest.approx(-9.706204736174694, abs=1e-9)
        assert hi == pytest.approx(15.706204736174694, abs=1e-9)

    def test_three_sample_ci_exact_bounds(self):
        # values=[2,4,9]: mean=5, var(ddof=1)=13, std=sqrt(13),
        # sem=sqrt(13)/sqrt(3)=2.081665999..., t.ppf(0.975, df=2)=4.30265273,
        # half=8.95669... => lower=-3.9566858950, upper=13.9566858950.
        lo, hi = _confidence_interval([2.0, 4.0, 9.0])
        assert lo == pytest.approx(-3.9566858950295973, abs=1e-9)
        assert hi == pytest.approx(13.9566858950295973, abs=1e-9)

    def test_ci_is_symmetric_about_the_mean(self):
        # The two bounds must be equidistant from the mean (the half-width is
        # added/subtracted). A dropped sign or asymmetric formula fails here.
        values = [1.0, 2.0, 3.0, 10.0]
        mean = sum(values) / len(values)  # 4.0
        lo, hi = _confidence_interval(values)
        assert (lo + hi) / 2 == pytest.approx(mean, abs=1e-9)
        assert hi > mean > lo  # ordering: lower < mean < upper

    def test_wider_sample_spread_gives_wider_interval(self):
        # Sanity ordering that kills a constant/garbled-sem mutation:
        # a tighter sample -> narrower CI than a more dispersed one of the
        # same size.
        tight_lo, tight_hi = _confidence_interval([4.9, 5.0, 5.1])
        wide_lo, wide_hi = _confidence_interval([0.0, 5.0, 10.0])
        assert (tight_hi - tight_lo) < (wide_hi - wide_lo)


# ===========================================================================
# metric_key_is_real — noise filter (re-exported by aggregate_summaries as
# _metric_key_is_real). Decides which metric keys reach a bucket at all, so
# a wrong suffix or membership check changes WHICH metrics get ranked.
# ===========================================================================
class TestMetricKeyIsReal:
    def test_module_reexports_the_same_predicate(self):
        # aggregate_summaries imports `_metric_key_is_real` from
        # metric_filters and uses it inline. Pin that the name is the real
        # filter, not a stub.
        assert agg._metric_key_is_real is metric_key_is_real

    def test_plain_metric_is_real(self):
        assert metric_key_is_real("accuracy") is True
        assert metric_key_is_real("bleu") is True

    def test_none_and_empty_are_not_real(self):
        assert metric_key_is_real(None) is False
        assert metric_key_is_real("") is False

    def test_noise_suffixes_are_filtered(self):
        # These would otherwise be averaged into the leaderboard as if real.
        assert metric_key_is_real("accuracy_details") is False
        assert metric_key_is_real("bleu_raw") is False
        assert metric_key_is_real("something_passed") is False
        assert metric_key_is_real("foo_response") is False

    def test_excluded_exact_keys_are_filtered(self):
        assert metric_key_is_real("raw_score") is False
        assert metric_key_is_real("error") is False

    def test_registered_override_beats_suffix_rule(self):
        # 'llm_judge_falloesung_grade_points' ends in the '_grade_points'
        # noise suffix BUT is a registered displayable metric — the override
        # must win, otherwise the leaderboard's DEFAULT column shows n/a for
        # everyone (this is the metric users cite for Falllösung).
        assert metric_key_is_real("llm_judge_falloesung_grade_points") is True
        # A different *_grade_points key is NOT overridden -> stays filtered.
        assert metric_key_is_real("other_grade_points") is False


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
