"""Mutation-kill tests for ml_evaluation/inter_annotator_agreement.py.

Every test here exists to KILL a specific surviving LOGIC mutant from the mutmut
baseline (the meaningful-coverage / mutation co-gate). A killing test asserts the
EXACT statistical value, comparison boundary, or branch the mutation changes —
not merely that a line executes. The agreement coefficients computed in this
module (Cronbach's alpha, Krippendorff's alpha, percent agreement, ICC, span
F1/IoU/boundary) are the human-grading reliability numbers reported in papers, so
a wrong formula constant or band threshold is a real bug, not a style nit.

Two kinds of assertion appear:

  * FORMULA — a hand-computed textbook value (e.g. the Shrout & Fleiss (1979)
    ICC worked example, a closed-form Cronbach/Krippendorff result). Pinning the
    exact value kills every arithmetic mutant on the formula line at once,
    because each operator/constant flip moves the number off the pinned value.

  * THRESHOLD — an interpretation band cutoff (e.g. ICC < 0.40 -> "poor"). We
    feed a value engineered to sit just inside one band and assert the band
    label. That kills both the comparison-operator mutant (`< 0.40` ->
    `<= 0.40`) and the constant mutant (`0.40` -> a different number), since
    either would relabel the engineered point.

Interpretation MESSAGE STRINGS (e.g. "Excellent boundary agreement") and
output dict-KEY spellings are presentation, not statistics; their `XX..XX`
mutants are pragma'd in the source, not defended here.

No model is loaded; all inputs are pure numbers. Mirrors the idioms of
test_inter_annotator_agreement*.py and test_statistics_mutation_kills.py.
"""

import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from ml_evaluation.inter_annotator_agreement import (  # noqa: E402
    _match_spans,
    _span_iou,
    compute_all_iaa_metrics,
    cronbachs_alpha,
    intraclass_correlation,
    krippendorff_alpha,
    percent_agreement,
    span_agreement,
    span_boundary_agreement,
)


# ============================================================================
# cronbachs_alpha — the n/(n-1) * (1 - sum_item_var/total_var) formula
# ============================================================================


class TestCronbachsAlphaFormula:
    def test_exact_alpha_value(self):
        """Pins the closed-form alpha = 0.93 for a hand-computed 3-item x 2-rater
        matrix. n_items=3, sum_item_variances=19, total_variance=50:

            alpha = (3/2) * (1 - 19/50) = 1.5 * 0.62 = 0.93

        Every arithmetic mutant on the formula moves this off 0.93:
          n/(n-1) -> n/(n+1)  => 0.465
          mul    -> div        => 2.419
          1 - x  -> 1 + x       => 2.07
          inner / -> *          => -1423.5
        so asserting 0.93 kills the whole family. Also pins the two emitted
        variance numbers (sum_item_variances, total_variance) so a swap of the
        np.var ddof / axis terms is caught."""
        matrix = [[1.0, 3.0], [2.0, 5.0], [4.0, 9.0]]
        result = cronbachs_alpha(matrix)
        assert result["alpha"] == pytest.approx(0.93, abs=1e-9)
        assert result["sum_item_variances"] == pytest.approx(19.0, abs=1e-9)
        assert result["total_variance"] == pytest.approx(50.0, abs=1e-9)
        assert result["n_items"] == 3
        assert result["n_raters"] == 2

    def test_min_raters_guard_is_strictly_less_than_two(self):
        """n_raters < 2 returns the error sentinel; n_raters == 2 must NOT.
        Kills `< 2` -> `<= 2` (which would reject every valid 2-rater matrix —
        the overwhelmingly common human-grading case) and the constant `2` flip."""
        one_rater = [[1.0], [2.0], [3.0]]
        assert "error" in cronbachs_alpha(one_rater)
        two_raters = [[1.0, 2.0], [2.0, 4.0], [3.0, 5.0]]
        assert "error" not in cronbachs_alpha(two_raters)

    def test_zero_total_variance_returns_zero_not_one(self):
        """total_variance == 0 short-circuits alpha to 0.0. Kills the
        `== 0` -> `!= 0` flip (which would take the formula branch and divide by
        zero) and the `0.0` return-value mutant (-> 1.0 etc.)."""
        result = cronbachs_alpha([[3.0, 3.0], [3.0, 3.0], [3.0, 3.0]])
        assert result["alpha"] == 0.0


class TestCronbachsAlphaBandThresholds:
    """Interpretation cutoffs: <0.5 unacceptable, <0.6 poor, <0.7 questionable,
    <0.8 acceptable, <0.9 good, else excellent. Each test sits a real alpha just
    inside one band so a moved cutoff (`< 0.8` -> `<= 0.8`, or `0.8` -> `1.8`)
    relabels it."""

    def _alpha_for(self, matrix):
        return cronbachs_alpha(matrix)["alpha"]

    def test_unacceptable_below_half(self):
        # alpha = 0.0 (zero between-rater covariance) -> < 0.5 -> "unacceptable"
        m = [[1.0, 5.0], [5.0, 1.0], [1.0, 5.0], [5.0, 1.0]]
        r = cronbachs_alpha(m)
        assert r["alpha"] < 0.5
        assert r["interpretation"] == "unacceptable"

    def test_excellent_at_and_above_point_nine(self):
        # alpha = 0.93 -> >= 0.9 -> "excellent" (the top, open band)
        r = cronbachs_alpha([[1.0, 3.0], [2.0, 5.0], [4.0, 9.0]])
        assert r["alpha"] == pytest.approx(0.93)
        assert r["interpretation"] == "excellent"

    def test_good_band_just_below_point_nine(self):
        # ~0.884 -> [0.8, 0.9) -> "good" (verified band in branches suite)
        r = cronbachs_alpha([[5.0, 1.0], [7.0, 2.0], [6.0, 2.0], [5.0, 5.0]])
        assert 0.8 <= r["alpha"] < 0.9
        assert r["interpretation"] == "good"


# ============================================================================
# krippendorff_alpha — distance functions, D_o, D_e, alpha = 1 - D_o/D_e
# ============================================================================


class TestKrippendorffAlphaFormula:
    def test_nominal_exact_alpha_do_de(self):
        """Hand-computed nominal case. Matrix [[a,a],[a,b],[b,b],[b,b]]:
        observed disagreement over within-item pairs D_o = 1/4 = 0.25;
        expected disagreement over all flat pairs D_e = 15/28 = 0.535714...;
        alpha = 1 - D_o/D_e = 1 - 0.25/0.535714 = 0.5333...

        Pinning all three numbers kills:
          * the nominal distance `0 if v1==v2 else 1` (a `==`->`!=` flip inverts
            agreement, sending alpha negative);
          * the `observed/total_pairs` and `expected/expected_pairs` divisions;
          * the `1 - D_o/D_e` master formula (`-`->`+`, `/`->`*`)."""
        matrix = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        r = krippendorff_alpha(matrix, level_of_measurement="nominal")
        assert r["observed_disagreement"] == pytest.approx(0.25, abs=1e-9)
        assert r["expected_disagreement"] == pytest.approx(15.0 / 28.0, abs=1e-9)
        assert r["alpha"] == pytest.approx(8.0 / 15.0, abs=1e-9)

    def test_interval_distance_is_squared_difference(self):
        """Interval distance = (v1 - v2)**2. Matrix [[1,1],[1,2],[2,2],[2,3]]:
        D_o = (0+1+0+1)/4 = 0.5; D_e over the 28 flat pairs = 1.0; alpha = 0.5.
        Kills the interval-distance exponent/subtraction mutants and confirms the
        squared metric (not absolute) is used."""
        matrix = [[1, 1], [1, 2], [2, 2], [2, 3]]
        r = krippendorff_alpha(matrix, level_of_measurement="interval")
        assert r["observed_disagreement"] == pytest.approx(0.5, abs=1e-9)
        assert r["expected_disagreement"] == pytest.approx(1.0, abs=1e-9)
        assert r["alpha"] == pytest.approx(0.5, abs=1e-9)

    def test_min_ratings_guard_is_strictly_less_than_two(self):
        """len(all_ratings) < 2 -> error. One rating errors; two do not.
        Kills `< 2` -> `<= 2` and the `2` constant flip on the guard."""
        assert "error" in krippendorff_alpha([[5, None], [None, None]])
        assert "error" not in krippendorff_alpha([[1, 2]])

    def test_perfect_agreement_returns_one(self):
        """D_o == 0 with non-zero D_e -> alpha = 1 - 0 = 1.0. Pins the perfect
        ceiling so a sign/operator flip on the master formula is caught."""
        r = krippendorff_alpha([["a", "a"], ["b", "b"], ["c", "c"]], "nominal")
        assert r["alpha"] == 1.0


class TestKrippendorffAlphaBandThresholds:
    """Bands: <0 poor; <0.667 tentative; <0.800 acceptable; else good. Engineered
    points sit just inside a band so a moved cutoff relabels them."""

    def test_negative_is_poor_systematic(self):
        # Perfect anti-agreement on a binary nominal -> alpha < 0
        m = [["a", "b"], ["b", "a"], ["a", "b"], ["b", "a"]]
        r = krippendorff_alpha(m, "nominal")
        assert r["alpha"] < 0
        assert r["interpretation"] == "poor (systematic disagreement)"

    def test_just_below_0667_is_tentative(self):
        # alpha = 0.5333 (from the formula case) sits in [0, 0.667) -> tentative
        m = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
        r = krippendorff_alpha(m, "nominal")
        assert 0.0 <= r["alpha"] < 0.667
        assert r["interpretation"] == "tentative conclusions only"

    def test_between_0667_and_080_is_acceptable(self):
        # ~0.792 interval alpha sits in [0.667, 0.8) -> acceptable band
        m = [[5, 5], [2, 3], [5, 4]]
        r = krippendorff_alpha(m, "interval")
        assert 0.667 <= r["alpha"] < 0.8
        assert r["interpretation"] == "acceptable for tentative conclusions"

    def test_at_and_above_080_is_good(self):
        # Perfect agreement alpha = 1.0 >= 0.8 -> "good reliability" (top band)
        r = krippendorff_alpha([["a", "a"], ["b", "b"], ["c", "c"]], "nominal")
        assert r["alpha"] >= 0.8
        assert r["interpretation"] == "good reliability"


# ============================================================================
# percent_agreement — agreements/total and the band cutoffs
# ============================================================================


class TestPercentAgreementFormula:
    def test_exact_fraction(self):
        """3 of 4 multi-rater items in full agreement -> 0.75. Pins the
        agreements/total division and the agreements/disagreements split."""
        matrix = [["a", "a"], ["b", "b"], ["c", "c"], ["d", "e"]]
        r = percent_agreement(matrix)
        assert r["percent_agreement"] == pytest.approx(0.75)
        assert r["agreements"] == 3
        assert r["disagreements"] == 1
        assert r["total_items"] == 4

    def test_single_rater_items_excluded(self):
        """n_valid < 2 items are skipped from the denominator. Kills `< 2` ->
        `<= 2` (which would also drop genuine 2-rater items) and the constant."""
        matrix = [["a"], ["b", "b"], ["c", "d"]]
        r = percent_agreement(matrix)
        assert r["total_items"] == 2  # the single-rater row is excluded
        assert r["percent_agreement"] == pytest.approx(0.5)


class TestPercentAgreementBandThresholds:
    """Bands: >=0.9 excellent, >=0.8 good, >=0.7 moderate, >=0.6 fair, else poor.
    Points engineered exactly ON each cutoff so `>=` -> `>` (which would demote
    the on-cutoff value) and the constant flip both die."""

    def _ten_item_matrix(self, n_agree):
        rows = [["x", "x"]] * n_agree + [["x", "y"]] * (10 - n_agree)
        return rows

    def test_exactly_point_nine_is_excellent(self):
        r = percent_agreement(self._ten_item_matrix(9))
        assert r["percent_agreement"] == pytest.approx(0.9)
        assert r["interpretation"] == "excellent"

    def test_exactly_point_eight_is_good(self):
        r = percent_agreement(self._ten_item_matrix(8))
        assert r["percent_agreement"] == pytest.approx(0.8)
        assert r["interpretation"] == "good"

    def test_exactly_point_seven_is_moderate(self):
        r = percent_agreement(self._ten_item_matrix(7))
        assert r["percent_agreement"] == pytest.approx(0.7)
        assert r["interpretation"] == "moderate"

    def test_exactly_point_six_is_fair(self):
        r = percent_agreement(self._ten_item_matrix(6))
        assert r["percent_agreement"] == pytest.approx(0.6)
        assert r["interpretation"] == "fair"

    def test_just_below_point_six_is_poor(self):
        r = percent_agreement(self._ten_item_matrix(5))
        assert r["percent_agreement"] == pytest.approx(0.5)
        assert r["interpretation"] == "poor"


# ============================================================================
# intraclass_correlation — Shrout & Fleiss (1979) worked example + bands
# ============================================================================


# The canonical Shrout & Fleiss (1979) Table: 6 targets (rows) x 4 judges (cols).
# Published single-measure ICCs: ICC(1,1)=.17, ICC(2,1)=.29, ICC(3,1)=.71.
SHROUT_FLEISS = [
    [9, 2, 5, 8],
    [6, 1, 3, 2],
    [8, 4, 6, 8],
    [7, 1, 2, 6],
    [10, 5, 6, 9],
    [6, 2, 4, 7],
]


class TestICCFormula:
    def test_icc_1_1_matches_textbook(self):
        """ICC(1,1) one-way random == 0.1657 on the Shrout & Fleiss data.
        Pins the MS_within pooling and the (MS_rows - MS_within)/(MS_rows +
        (k-1)*MS_within) formula. A wrong k-1 / sign / SS term moves this off."""
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(1,1)")
        assert r["icc"] == pytest.approx(0.1657, abs=5e-4)

    def test_icc_2_1_matches_textbook(self):
        """ICC(2,1) two-way random == 0.2898. Pins the full denominator
        MS_rows + (k-1)*MS_error + k*(MS_cols - MS_error)/n — the term that
        distinguishes ICC(2,1) from ICC(3,1)."""
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(2,1)")
        assert r["icc"] == pytest.approx(0.2898, abs=5e-4)

    def test_icc_3_1_matches_textbook(self):
        """ICC(3,1) two-way mixed == 0.7148. Pins (MS_rows - MS_error) /
        (MS_rows + (k-1)*MS_error). Because the three textbook values are
        distinct (0.17 / 0.29 / 0.71), each branch's formula is independently
        anchored — a mutant that turns one branch's expression into another's is
        caught."""
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(3,1)")
        assert r["icc"] == pytest.approx(0.7148, abs=5e-4)

    def test_mean_squares_reported(self):
        """The emitted mean squares pin the SS/MS decomposition itself
        (SS_total = SS_rows + SS_cols + SS_error; MS = SS / df). A mutated df or
        SS term shifts these."""
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(2,1)")
        assert r["ms_between_items"] == pytest.approx(11.2417, abs=1e-3)
        assert r["ms_between_raters"] == pytest.approx(32.4861, abs=1e-3)
        assert r["ms_error"] == pytest.approx(1.0194, abs=1e-3)

    def test_min_raters_guard_strictly_less_than_two(self):
        """n_raters < 2 -> error; == 2 must not. Kills `< 2` -> `<= 2`."""
        assert "error" in intraclass_correlation([[1.0], [2.0], [3.0]])
        assert "error" not in intraclass_correlation([[1.0, 2.0], [3.0, 5.0]])

    def test_unknown_icc_type_errors(self):
        assert "error" in intraclass_correlation([[1.0, 2.0]], "ICC(9,9)")


class TestICCBandThresholds:
    """Cicchetti (1994): <0.40 poor, <0.60 fair, <0.75 good, else excellent.
    Points sit just inside a band so a moved cutoff relabels them."""

    def test_poor_below_040(self):
        # ICC(2,1) ~0.29 on Shrout-Fleiss is < 0.40 -> "poor"
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(2,1)")
        assert r["icc"] < 0.40
        assert r["interpretation"] == "poor"

    def test_good_between_060_and_075(self):
        # ICC(3,1) ~0.715 is in [0.60, 0.75) -> "good"
        r = intraclass_correlation(SHROUT_FLEISS, "ICC(3,1)")
        assert 0.60 <= r["icc"] < 0.75
        assert r["interpretation"] == "good"

    def test_excellent_at_and_above_075(self):
        # Near-perfect data -> icc >= 0.75 -> "excellent" (top, open band)
        r = intraclass_correlation(
            [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0], [5.0, 5.0]], "ICC(2,1)"
        )
        assert r["icc"] >= 0.75
        assert r["interpretation"] == "excellent"

    def test_degenerate_perfect_maps_to_one(self):
        """All-identical ratings have zero total variance -> the 0/0 ICC is
        non-finite; the guard maps SS_total≈0 to 1.0 (perfect). Kills the
        `np.isclose(SS_total, 0)` branch and its 1.0 / 0.0 return constants."""
        r = intraclass_correlation([[4.0, 4.0], [4.0, 4.0], [4.0, 4.0]], "ICC(2,1)")
        assert r["icc"] == 1.0
        assert r["interpretation"] == "excellent"


# ============================================================================
# _span_iou — intersection-over-union geometry
# ============================================================================


class TestSpanIoUFormula:
    def test_partial_overlap_exact(self):
        """[0,10] vs [5,15]: intersection = min(10,15)-max(0,5) = 5;
        union = 10 + 10 - 5 = 15; IoU = 1/3. Pins the intersection clamp, the
        union = len1 + len2 - inter formula, and the final division."""
        assert _span_iou({"start": 0, "end": 10}, {"start": 5, "end": 15}) == pytest.approx(
            1.0 / 3.0
        )

    def test_contained_exact(self):
        """[2,8] inside [0,10]: inter = 6, union = 6 + 10 - 6 = 10, IoU = 0.6."""
        assert _span_iou({"start": 2, "end": 8}, {"start": 0, "end": 10}) == pytest.approx(0.6)

    def test_disjoint_is_zero_via_clamp(self):
        """[0,5] vs [10,15]: raw intersection_end - intersection_start = -5;
        the max(0, ...) clamp pins it to 0 -> IoU 0.0. Kills the `max(0, ...)`
        -> `min(0, ...)` and constant mutants (without the clamp, union math
        would yield a spurious negative/positive IoU)."""
        assert _span_iou({"start": 0, "end": 5}, {"start": 10, "end": 15}) == 0.0

    def test_zero_union_perfect_point(self):
        """Two empty spans at the same point: union == 0 -> returns 1.0. Kills
        the `union == 0` guard operator and its 1.0/0.0 return constants."""
        assert _span_iou({"start": 3, "end": 3}, {"start": 3, "end": 3}) == 1.0

    def test_missing_start_defaults_to_zero(self):
        """A span dict without "start" must default start to 0. {end:10} vs
        {0,10} -> identical [0,10] -> IoU 1.0; the `.get("start", 0)` -> ", 1"
        mutant would make it [1,10] -> 0.9. Kills the start-default constant."""
        assert _span_iou({"end": 10}, {"start": 0, "end": 10}) == 1.0

    def test_missing_end_defaults_to_zero(self):
        """A span dict without "end" must default end to 0. {start:0} -> [0,0]
        (empty) vs [0,10] -> intersection 0, union 10 -> IoU 0.0; the
        `.get("end", 0)` -> ", 1" mutant would make it [0,1] -> 0.1. Kills the
        end-default constant."""
        assert _span_iou({"start": 0}, {"start": 0, "end": 10}) == 0.0


# ============================================================================
# _match_spans — the IoU >= threshold gate and one-to-one matching
# ============================================================================


class TestMatchSpansThreshold:
    def test_iou_at_threshold_matches(self):
        """IoU exactly at the default 0.5 threshold must match (`>=`, not `>`).
        [0,10] vs [5,15] gives IoU 1/3 (< 0.5, no match); [0,10] vs [3,10] gives
        inter=7 union=10 -> 0.7 (>= 0.5, match). To pin the boundary we use a
        pair whose IoU is exactly 0.5: [0,10] vs [5,20] -> inter=5 union=20 ->
        0.25 no; use [0,12] vs [6,12] -> inter=6 union=12 -> 0.5 exactly."""
        spans1 = [{"start": 0, "end": 12}]
        spans2 = [{"start": 6, "end": 12}]
        # IoU = 6 / 12 = 0.5 exactly -> with >= it matches at the default 0.5
        matches = _match_spans(spans1, spans2, iou_threshold=0.5)
        assert len(matches) == 1
        assert matches[0][2] == pytest.approx(0.5)

    def test_iou_just_below_threshold_no_match(self):
        """IoU 1/3 < 0.5 -> no match. Confirms the gate actually rejects below
        threshold (a `>=` -> always-true / `0.5` -> `0.0` mutant would wrongly
        match)."""
        spans1 = [{"start": 0, "end": 10}]
        spans2 = [{"start": 5, "end": 15}]
        assert _match_spans(spans1, spans2, iou_threshold=0.5) == []

    def test_one_to_one_each_target_used_once(self):
        """Two identical spans1 against one spans2 -> only one match (the
        used_spans2 set prevents reuse). Kills mutants that drop the
        used-tracking guard."""
        spans1 = [{"start": 0, "end": 10}, {"start": 0, "end": 10}]
        spans2 = [{"start": 0, "end": 10}]
        assert len(_match_spans(spans1, spans2)) == 1


# ============================================================================
# span_agreement — precision / recall / F1 and bands
# ============================================================================


class TestSpanAgreementFormula:
    def test_precision_recall_f1_exact(self):
        """2 matched of 3 annotator-1 spans / 4 annotator-2 spans:
        precision = matched/spans_a2 = 2/4 = 0.5;
        recall    = matched/spans_a1 = 2/3 = 0.6667;
        F1 = 2PR/(P+R) = 2*0.5*0.6667 / 1.1667 = 0.5714.
        Pins all three formulas (note precision divides by a2, recall by a1)."""
        annotations = [
            [
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 40, "end": 45},
                ],
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                ],
            ]
        ]
        r = span_agreement(annotations, include_labels=False)
        assert r["precision"] == pytest.approx(0.5)
        assert r["recall"] == pytest.approx(0.6667, abs=1e-4)
        assert r["span_agreement"] == pytest.approx(0.5714, abs=1e-4)
        assert r["total_matched_spans"] == 2
        assert r["total_spans_annotator1"] == 3
        assert r["total_spans_annotator2"] == 4

    def test_label_agreement_fraction(self):
        """One matched pair with equal labels, one with different -> label
        agreement = 1/2 = 0.5. Pins label_matches/label_comparisons."""
        annotations = [
            [
                [
                    {"start": 0, "end": 5, "labels": ["PER"]},
                    {"start": 10, "end": 15, "labels": ["ORG"]},
                ],
                [
                    {"start": 0, "end": 5, "labels": ["PER"]},
                    {"start": 10, "end": 15, "labels": ["LOC"]},
                ],
            ]
        ]
        r = span_agreement(annotations, include_labels=True)
        assert r["label_agreement"] == pytest.approx(0.5)
        assert r["label_comparisons"] == 2


class TestSpanAgreementBandThresholds:
    """Bands: F1>=0.8 Strong, >=0.6 Moderate, >=0.4 Fair, else Poor. Points sit
    just inside a band so a moved cutoff (`>=`->`>`, constant flip) relabels."""

    def test_strong_at_and_above_080(self):
        # Perfect overlap -> F1 = 1.0 >= 0.8 -> "Strong span agreement"
        annotations = [
            [
                [{"start": 0, "end": 10}],
                [{"start": 0, "end": 10}],
            ]
        ]
        r = span_agreement(annotations, include_labels=False)
        assert r["span_agreement"] >= 0.8
        assert r["interpretation"] == "Strong span agreement"

    def test_moderate_between_060_and_080(self):
        # 2 matched of 2 a1 / 4 a2 -> P=0.5 R=1.0 F1=0.6667 in [0.6, 0.8)
        annotations = [
            [
                [{"start": 0, "end": 5}, {"start": 10, "end": 15}],
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                ],
            ]
        ]
        r = span_agreement(annotations, include_labels=False)
        assert 0.6 <= r["span_agreement"] < 0.8
        assert r["interpretation"] == "Moderate span agreement"

    def test_fair_between_040_and_060(self):
        # 2 matched of 3 a1 / 5 a2 -> P=0.4 R=0.6667 F1=0.5 in [0.4, 0.6)
        annotations = [
            [
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 40, "end": 45},
                ],
                [
                    {"start": 0, "end": 5},
                    {"start": 10, "end": 15},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                    {"start": 50, "end": 55},
                ],
            ]
        ]
        r = span_agreement(annotations, include_labels=False)
        assert 0.4 <= r["span_agreement"] < 0.6
        assert r["interpretation"] == "Fair span agreement"

    def test_poor_below_040(self):
        # 1 matched of 1 a1 / 5 a2 -> P=0.2 R=1.0 F1=0.333 < 0.4 -> "Poor ..."
        annotations = [
            [
                [{"start": 0, "end": 5}],
                [
                    {"start": 0, "end": 5},
                    {"start": 20, "end": 25},
                    {"start": 30, "end": 35},
                    {"start": 40, "end": 45},
                    {"start": 50, "end": 55},
                ],
            ]
        ]
        r = span_agreement(annotations, include_labels=False)
        assert r["span_agreement"] < 0.4
        assert r["interpretation"].startswith("Poor span agreement")


# ============================================================================
# span_boundary_agreement — start/end/avg and the tolerance <= comparison
# ============================================================================


class TestSpanBoundaryFormula:
    def test_start_end_avg_exact(self):
        """One exact pair + one start-only pair (end off by 6, tolerance 0):
        start_agreement = 2/2 = 1.0; end_agreement = 1/2 = 0.5;
        boundary_agreement = (1.0 + 0.5)/2 = 0.75. Pins each fraction and the
        averaging formula (`(s+e)/2`, not `s+e/2` or `(s+e)*2`)."""
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 0, "end": 10}]],
            [[{"start": 20, "end": 30}], [{"start": 20, "end": 36}]],
        ]
        r = span_boundary_agreement(annotations, tolerance=0)
        assert r["start_agreement"] == pytest.approx(1.0)
        assert r["end_agreement"] == pytest.approx(0.5)
        assert r["boundary_agreement"] == pytest.approx(0.75)
        assert r["n_comparisons"] == 2

    def test_tolerance_is_inclusive(self):
        """A boundary off by exactly `tolerance` counts as a match
        (`abs(diff) <= tolerance`). Off by 1 with tolerance=1 -> full agreement;
        with tolerance=0 -> the start/end disagree. Kills `<=` -> `<` and the
        tolerance constant flip."""
        annotations = [[[{"start": 0, "end": 10}], [{"start": 1, "end": 11}]]]
        tol1 = span_boundary_agreement(annotations, tolerance=1)
        tol0 = span_boundary_agreement(annotations, tolerance=0)
        assert tol1["boundary_agreement"] == pytest.approx(1.0)
        assert tol0["boundary_agreement"] == pytest.approx(0.0)


class TestSpanBoundaryBandThresholds:
    """Bands: >=0.9 Excellent, >=0.7 Good, >=0.5 Moderate, else Poor. Points sit
    just inside a band so a moved cutoff relabels them."""

    def test_excellent_at_and_above_090(self):
        # Perfect boundaries -> 1.0 >= 0.9 -> "Excellent boundary agreement"
        annotations = [[[{"start": 0, "end": 10}], [{"start": 0, "end": 10}]]]
        r = span_boundary_agreement(annotations, tolerance=0)
        assert r["boundary_agreement"] >= 0.9
        assert r["interpretation"] == "Excellent boundary agreement"

    def test_good_between_070_and_090(self):
        # boundary 0.75 in [0.7, 0.9) -> "Good boundary agreement"
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 0, "end": 10}]],
            [[{"start": 20, "end": 30}], [{"start": 20, "end": 36}]],
        ]
        r = span_boundary_agreement(annotations, tolerance=0)
        assert 0.7 <= r["boundary_agreement"] < 0.9
        assert r["interpretation"] == "Good boundary agreement"

    def test_moderate_between_050_and_070(self):
        # start=0.5 end=0.5 -> 0.5 in [0.5, 0.7) -> "Moderate boundary agreement"
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 2, "end": 10}]],
            [[{"start": 20, "end": 30}], [{"start": 20, "end": 33}]],
        ]
        r = span_boundary_agreement(annotations, tolerance=0)
        assert 0.5 <= r["boundary_agreement"] < 0.7
        assert r["interpretation"] == "Moderate boundary agreement"

    def test_poor_below_050(self):
        # start=0 end=0 -> 0.0 < 0.5 -> "Poor boundary agreement ..."
        annotations = [
            [[{"start": 0, "end": 10}], [{"start": 3, "end": 7}]],
        ]
        r = span_boundary_agreement(annotations, tolerance=0)
        assert r["boundary_agreement"] < 0.5
        assert r["interpretation"].startswith("Poor boundary agreement")


# ============================================================================
# compute_all_iaa_metrics — the level-of-measurement dispatch rules
# ============================================================================


class TestComputeAllIAADispatch:
    """The dispatch decides WHICH coefficients run for a given measurement level
    and rater count. These are statistical-applicability rules (Fleiss/Cohen only
    for categorical; Cronbach/ICC only for ordinal+; quadratic weights for ordinal
    Cohen's kappa), so the gating constants/strings are LOGIC, not wording."""

    def test_nominal_gets_categorical_metrics_not_continuous(self):
        """nominal -> fleiss + cohen + krippendorff + percent, but NOT
        cronbach/icc. Kills the `in ["ordinal","interval","ratio"]` membership
        mutant that would wrongly run Cronbach/ICC on nominal labels."""
        m = [["a", "a"], ["b", "b"], ["a", "b"]]
        metrics = compute_all_iaa_metrics(m, "nominal")["metrics"]
        assert "fleiss_kappa" in metrics
        assert "cohens_kappa" in metrics
        assert "krippendorff_alpha" in metrics
        assert "percent_agreement" in metrics
        assert "cronbachs_alpha" not in metrics
        assert "icc" not in metrics

    def test_interval_gets_continuous_metrics_not_fleiss(self):
        """interval -> cronbach + icc + krippendorff + percent, but NOT fleiss
        (Fleiss is categorical-only). Kills the `in ["nominal","ordinal"]`
        membership mutant for the Fleiss gate."""
        m = [[1.0, 1.1], [2.0, 2.1], [3.0, 3.1]]
        metrics = compute_all_iaa_metrics(m, "interval")["metrics"]
        assert "cronbachs_alpha" in metrics
        assert "icc" in metrics
        assert "fleiss_kappa" not in metrics

    def test_ordinal_uses_quadratic_weighted_cohen(self):
        """ordinal Cohen's kappa must use quadratic weights; any other level
        uses unweighted ("none"). Kills the
        `"quadratic" if level == "ordinal" else "none"` selector — a flipped
        condition or renamed string would change the reported kappa weighting."""
        ordinal = compute_all_iaa_metrics([[1, 1], [2, 2], [3, 3]], "ordinal")
        assert ordinal["metrics"]["cohens_kappa"]["weights"] == "quadratic"
        nominal = compute_all_iaa_metrics([["a", "a"], ["b", "b"]], "nominal")
        assert nominal["metrics"]["cohens_kappa"]["weights"] == "none"

    def test_cohen_only_for_exactly_two_raters(self):
        """Cohen's kappa is emitted only when n_raters == 2. A 3-rater matrix
        must NOT get it (Cohen's is a two-rater statistic). Kills the
        `== 2` -> `!= 2`/`> 2` and the `2` constant mutant on the gate."""
        three = compute_all_iaa_metrics([["a", "a", "a"], ["b", "b", "a"]], "nominal")
        assert "cohens_kappa" not in three["metrics"]
        assert three["n_raters"] == 3
        two = compute_all_iaa_metrics([["a", "a"], ["b", "b"]], "nominal")
        assert "cohens_kappa" in two["metrics"]
        assert two["n_raters"] == 2
