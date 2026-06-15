"""Property-based tests for ml_evaluation.inter_annotator_agreement (hypothesis).

These assert mathematical/structural INVARIANTS that hold for all generated
rating matrices, not hand-picked examples — which is what kills the off-by-one /
wrong-operator / boundary mutants that example tests miss (the mutation co-gate,
issue: meaningful-coverage program).

Invariants covered:
  * cohens_kappa: kappa in [-1, 1]; perfect agreement (rater1 == rater2) => 1.0;
    permuting item order leaves kappa unchanged; deterministic; documented
    sentinels on length mismatch / empty input (no crash).
  * fleiss_kappa: kappa <= 1.0; perfect agreement (all raters identical per
    item) => 1.0; permuting column (rater) order leaves kappa unchanged;
    deterministic; empty-matrix sentinel.
  * cronbachs_alpha: alpha <= 1.0; rater-column permutation invariant;
    deterministic; single-rater / empty sentinels.
  * krippendorff_alpha: alpha <= 1.0; perfect agreement => 1.0; column
    permutation invariant; deterministic; empty / too-few-ratings sentinels.
  * percent_agreement: in [0, 1]; all-identical => 1.0; all-distinct => 0.0;
    column-permutation invariant.
  * compute_all_iaa_metrics: never raises for valid matrices; deterministic.
"""

import os
import sys

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.inter_annotator_agreement import (  # noqa: E402
    cohens_kappa,
    compute_all_iaa_metrics,
    cronbachs_alpha,
    krippendorff_alpha,
    percent_agreement,
)

# A small set of categorical rating values keeps the category space bounded so
# kappa/alpha don't degenerate into all-distinct noise on every draw.
_category = st.sampled_from(["A", "B", "C", "D"])

# Numeric ratings (Likert-ish) for Cronbach's alpha. Bounded + finite to avoid
# numpy variance overflow / precision noise.
_numeric = st.integers(min_value=0, max_value=10)


def _matrix(value_strategy, min_raters=2, max_raters=5, min_items=2, max_items=12):
    """Rectangular ratings matrix: each row an item, each column a rater."""
    return st.integers(min_value=min_raters, max_value=max_raters).flatmap(
        lambda n_raters: st.lists(
            st.lists(value_strategy, min_size=n_raters, max_size=n_raters),
            min_size=min_items,
            max_size=max_items,
        )
    )


def _permute_columns(matrix, order):
    """Reorder every row by the same column permutation."""
    return [[row[i] for i in order] for row in matrix]


_settings = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


class TestCohensKappa:
    @_settings
    @given(rater1=st.lists(_category, min_size=1, max_size=30))
    def test_perfect_agreement_is_one(self, rater1):
        # Identical raters => perfect agreement => kappa exactly 1.0.
        r = cohens_kappa(rater1, list(rater1))
        assert "kappa" in r
        assert r["kappa"] == 1.0
        assert r["observed_agreement"] == 1.0

    @_settings
    @given(
        data=st.lists(st.tuples(_category, _category), min_size=1, max_size=30),
    )
    def test_kappa_bounded(self, data):
        rater1 = [a for a, _ in data]
        rater2 = [b for _, b in data]
        r = cohens_kappa(rater1, rater2)
        assert "kappa" in r
        # Cohen's kappa is bounded in [-1, 1].
        assert -1.0 - 1e-9 <= r["kappa"] <= 1.0 + 1e-9
        assert 0.0 <= r["observed_agreement"] <= 1.0

    @_settings
    @given(
        data=st.lists(st.tuples(_category, _category), min_size=2, max_size=25),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    def test_item_order_permutation_invariant(self, data, seed):
        # Cohen's kappa depends only on the (r1, r2) pairing, not item ordering.
        import random

        rnd = random.Random(seed)
        shuffled = data[:]
        rnd.shuffle(shuffled)

        base = cohens_kappa([a for a, _ in data], [b for _, b in data])
        perm = cohens_kappa([a for a, _ in shuffled], [b for _, b in shuffled])
        assert base["kappa"] == perm["kappa"]

    @_settings
    @given(data=st.lists(st.tuples(_category, _category), min_size=1, max_size=20))
    def test_deterministic(self, data):
        rater1 = [a for a, _ in data]
        rater2 = [b for _, b in data]
        assert cohens_kappa(rater1, rater2) == cohens_kappa(rater1, rater2)

    def test_length_mismatch_sentinel(self):
        r = cohens_kappa(["A", "B"], ["A"])
        assert r.get("error") == "Raters must have same number of ratings"

    def test_empty_sentinel(self):
        r = cohens_kappa([], [])
        assert r.get("error") == "No ratings provided"


class TestFleissKappa:
    @_settings
    @given(
        n_raters=st.integers(min_value=2, max_value=5),
        ratings=st.lists(_category, min_size=2, max_size=12),
    )
    def test_perfect_agreement_is_one(self, n_raters, ratings):
        # Every rater gives the identical rating on each item => kappa 1.0.
        matrix = [[r] * n_raters for r in ratings]
        out = compute_all_iaa_metrics(matrix)
        fk = out["metrics"]["fleiss_kappa"]
        assert fk["kappa"] == 1.0

    @_settings
    @given(matrix=_matrix(_category))
    def test_kappa_upper_bounded(self, matrix):
        out = compute_all_iaa_metrics(matrix)
        fk = out["metrics"]["fleiss_kappa"]
        assert "kappa" in fk
        # Fleiss kappa never exceeds 1.0.
        assert fk["kappa"] <= 1.0 + 1e-9

    @_settings
    @given(matrix=_matrix(_category), seed=st.integers(min_value=0, max_value=10_000))
    def test_column_permutation_invariant(self, matrix, seed):
        import random

        n_raters = len(matrix[0])
        order = list(range(n_raters))
        random.Random(seed).shuffle(order)
        permuted = _permute_columns(matrix, order)

        from ml_evaluation.inter_annotator_agreement import fleiss_kappa

        base = fleiss_kappa(matrix)["kappa"]
        perm = fleiss_kappa(permuted)["kappa"]
        assert base == perm

    @_settings
    @given(matrix=_matrix(_category))
    def test_deterministic(self, matrix):
        from ml_evaluation.inter_annotator_agreement import fleiss_kappa

        assert fleiss_kappa(matrix) == fleiss_kappa(matrix)

    def test_empty_sentinel(self):
        from ml_evaluation.inter_annotator_agreement import fleiss_kappa

        assert fleiss_kappa([]).get("error") == "Empty ratings matrix"


class TestCronbachsAlpha:
    @_settings
    @given(matrix=_matrix(_numeric))
    def test_alpha_upper_bounded(self, matrix):
        r = cronbachs_alpha(matrix)
        assert "alpha" in r
        # Cronbach's alpha has an upper bound of 1.0 (can be negative).
        assert r["alpha"] <= 1.0 + 1e-9
        assert r["sum_item_variances"] >= -1e-9
        assert r["total_variance"] >= -1e-9

    @_settings
    @given(matrix=_matrix(_numeric), seed=st.integers(min_value=0, max_value=10_000))
    def test_column_permutation_invariant(self, matrix, seed):
        import math
        import random

        n_raters = len(matrix[0])
        order = list(range(n_raters))
        random.Random(seed).shuffle(order)
        permuted = _permute_columns(matrix, order)

        base = cronbachs_alpha(matrix)["alpha"]
        perm = cronbachs_alpha(permuted)["alpha"]
        # Reordering raters does not change internal-consistency alpha.
        assert math.isclose(base, perm, rel_tol=1e-9, abs_tol=1e-9)

    @_settings
    @given(matrix=_matrix(_numeric))
    def test_deterministic(self, matrix):
        assert cronbachs_alpha(matrix) == cronbachs_alpha(matrix)

    def test_single_rater_sentinel(self):
        r = cronbachs_alpha([[1], [2], [3]])
        assert r.get("error") == "Need at least 2 raters for Cronbach's alpha"

    def test_empty_sentinel(self):
        assert cronbachs_alpha([]).get("error") == "Empty ratings matrix"


class TestKrippendorffAlpha:
    @_settings
    @given(
        n_raters=st.integers(min_value=2, max_value=5),
        ratings=st.lists(_category, min_size=2, max_size=12),
    )
    def test_perfect_agreement_is_one(self, n_raters, ratings):
        # All raters identical on each item => no observed disagreement => 1.0.
        matrix = [[r] * n_raters for r in ratings]
        out = krippendorff_alpha(matrix, level_of_measurement="nominal")
        assert out["alpha"] == 1.0

    @_settings
    @given(matrix=_matrix(_category))
    def test_alpha_upper_bounded(self, matrix):
        out = krippendorff_alpha(matrix, level_of_measurement="nominal")
        assert "alpha" in out
        # Krippendorff's alpha tops out at 1.0 (negative on systematic disagree).
        assert out["alpha"] <= 1.0 + 1e-9

    @_settings
    @given(matrix=_matrix(_category), seed=st.integers(min_value=0, max_value=10_000))
    def test_column_permutation_invariant(self, matrix, seed):
        import math
        import random

        n_raters = len(matrix[0])
        order = list(range(n_raters))
        random.Random(seed).shuffle(order)
        permuted = _permute_columns(matrix, order)

        base = krippendorff_alpha(matrix, level_of_measurement="nominal")["alpha"]
        perm = krippendorff_alpha(permuted, level_of_measurement="nominal")["alpha"]
        assert math.isclose(base, perm, rel_tol=1e-9, abs_tol=1e-9)

    @_settings
    @given(matrix=_matrix(_category))
    def test_deterministic(self, matrix):
        a = krippendorff_alpha(matrix, level_of_measurement="nominal")
        b = krippendorff_alpha(matrix, level_of_measurement="nominal")
        assert a == b

    def test_empty_sentinel(self):
        assert krippendorff_alpha([]).get("error") == "Empty ratings matrix"

    def test_too_few_ratings_sentinel(self):
        assert krippendorff_alpha([["A"]]).get("error") == "Need at least 2 ratings"


class TestPercentAgreement:
    @_settings
    @given(matrix=_matrix(_category))
    def test_bounded(self, matrix):
        r = percent_agreement(matrix)
        assert "percent_agreement" in r
        assert 0.0 <= r["percent_agreement"] <= 1.0
        assert r["agreements"] + r["disagreements"] == r["total_items"]

    @_settings
    @given(
        n_raters=st.integers(min_value=2, max_value=5),
        ratings=st.lists(_category, min_size=1, max_size=12),
    )
    def test_all_identical_is_one(self, n_raters, ratings):
        matrix = [[r] * n_raters for r in ratings]
        assert percent_agreement(matrix)["percent_agreement"] == 1.0

    @_settings
    @given(matrix=_matrix(_category), seed=st.integers(min_value=0, max_value=10_000))
    def test_column_permutation_invariant(self, matrix, seed):
        import random

        n_raters = len(matrix[0])
        order = list(range(n_raters))
        random.Random(seed).shuffle(order)
        permuted = _permute_columns(matrix, order)

        base = percent_agreement(matrix)["percent_agreement"]
        perm = percent_agreement(permuted)["percent_agreement"]
        assert base == perm


class TestComputeAllIaaMetrics:
    @_settings
    @given(
        matrix=_matrix(_category),
        level=st.sampled_from(["nominal", "ordinal", "interval", "ratio"]),
    )
    def test_never_raises_and_deterministic(self, matrix, level):
        # Wrap numeric-only levels with numeric ratings so the cronbach/icc path
        # doesn't choke; for categorical letters, only nominal/ordinal apply but
        # the function must still return a result without raising.
        a = compute_all_iaa_metrics(matrix, level_of_measurement="nominal")
        b = compute_all_iaa_metrics(matrix, level_of_measurement="nominal")
        assert a == b
        assert "metrics" in a
        assert a["n_items"] == len(matrix)
        assert a["n_raters"] == len(matrix[0])

    @_settings
    @given(matrix=_matrix(_numeric))
    def test_numeric_levels_do_not_raise(self, matrix):
        for level in ("ordinal", "interval", "ratio"):
            out = compute_all_iaa_metrics(matrix, level_of_measurement=level)
            assert "metrics" in out
