"""
Agreement metrics: Cohen's kappa, Fleiss kappa, percent agreement, plus the
generic `compute_agreement` composite that takes (rater_id, item_id, score)
triples.

Used by:
- multi-judge / multi-run LLM evaluation statistics
- human inter-annotator agreement (korrektur workflow)
- worker-side IAA reporting

Numerical implementation lifted (with consolidation) from the prior
`workers/ml_evaluation/inter_annotator_agreement.py` and
`api/services/analytics_service.py:_calculate_fleiss_kappa`.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


ScoreType = Literal["categorical", "numeric", "ordinal"]


def _interpret_kappa(kappa: float) -> str:
    if kappa < 0:
        return "poor (worse than chance)"
    if kappa < 0.20:
        return "slight"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost perfect"


def cohens_kappa(
    rater1: List[Any],
    rater2: List[Any],
    weights: str = "none",
) -> Dict[str, Any]:
    """
    Cohen's Kappa for two raters over the same items.

    `weights` ∈ {"none", "linear", "quadratic"}.
    """
    if len(rater1) != len(rater2):
        return {"error": "Raters must have same number of ratings"}
    if not rater1:
        return {"error": "No ratings provided"}
    if not NUMPY_AVAILABLE:
        return {"error": "numpy unavailable"}

    all_ratings = sorted(set(rater1) | set(rater2), key=lambda x: (str(type(x)), str(x)))
    n_categories = len(all_ratings)
    n_samples = len(rater1)
    rating_to_idx = {r: i for i, r in enumerate(all_ratings)}

    confusion = np.zeros((n_categories, n_categories))
    for r1, r2 in zip(rater1, rater2):
        confusion[rating_to_idx[r1], rating_to_idx[r2]] += 1

    if weights == "none":
        po = float(np.sum(np.diag(confusion)) / n_samples)
        weight_matrix = None
    elif weights == "linear":
        weight_matrix = np.zeros((n_categories, n_categories))
        for i in range(n_categories):
            for j in range(n_categories):
                weight_matrix[i, j] = (
                    1 - abs(i - j) / (n_categories - 1) if n_categories > 1 else 1.0
                )
        po = float(np.sum(weight_matrix * confusion) / n_samples)
    elif weights == "quadratic":
        weight_matrix = np.zeros((n_categories, n_categories))
        for i in range(n_categories):
            for j in range(n_categories):
                weight_matrix[i, j] = (
                    1 - ((i - j) / (n_categories - 1)) ** 2 if n_categories > 1 else 1.0
                )
        po = float(np.sum(weight_matrix * confusion) / n_samples)
    else:
        return {"error": f"Unknown weights: {weights}"}

    row_marginals = np.sum(confusion, axis=1) / n_samples
    col_marginals = np.sum(confusion, axis=0) / n_samples

    if weights == "none":
        pe = float(np.sum(row_marginals * col_marginals))
    else:
        pe = 0.0
        for i in range(n_categories):
            for j in range(n_categories):
                pe += float(weight_matrix[i, j] * row_marginals[i] * col_marginals[j])

    if pe == 1:
        kappa = 1.0 if po == 1 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)

    return {
        "kappa": float(kappa),
        "observed_agreement": float(po),
        "expected_agreement": float(pe),
        "interpretation": _interpret_kappa(kappa),
        "weights": weights,
        "n_samples": n_samples,
        "n_categories": n_categories,
    }


def fleiss_kappa(
    ratings_matrix: List[List[Any]],
    categories: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Fleiss' Kappa for ≥2 raters over the same items.

    Each row of `ratings_matrix` is one item; each column is one rater's rating
    (or None when that rater didn't rate the item). Items with <2 ratings are
    skipped.
    """
    if not ratings_matrix or not ratings_matrix[0]:
        return {"error": "Empty ratings matrix"}
    if not NUMPY_AVAILABLE:
        return {"error": "numpy unavailable"}

    if categories is None:
        flat = [r for row in ratings_matrix for r in row if r is not None]
        if not flat:
            return {"error": "No non-null ratings"}
        categories = sorted(set(flat), key=lambda x: (str(type(x)), str(x)))

    n_categories = len(categories)
    cat_to_idx = {c: i for i, c in enumerate(categories)}

    counts = np.zeros((len(ratings_matrix), n_categories))
    for i, row in enumerate(ratings_matrix):
        for rating in row:
            if rating is not None and rating in cat_to_idx:
                counts[i, cat_to_idx[rating]] += 1

    n_raters_per_item = np.sum(counts, axis=1)
    valid = n_raters_per_item >= 2
    if not np.any(valid):
        return {
            "kappa": 1.0,
            "observed_agreement": 1.0,
            "expected_agreement": 1.0,
            "interpretation": _interpret_kappa(1.0),
            "n_items": 0,
            "n_categories": n_categories,
            "n_raters": None,
            "categories": categories,
        }

    counts = counts[valid]
    n_raters_per_item = n_raters_per_item[valid]
    n_items = len(counts)
    n_total_ratings = float(np.sum(counts))

    p_j = np.sum(counts, axis=0) / n_total_ratings

    P_i = np.zeros(n_items)
    for i in range(n_items):
        n_i = n_raters_per_item[i]
        if n_i > 1:
            P_i[i] = (np.sum(counts[i] ** 2) - n_i) / (n_i * (n_i - 1))

    P_bar = float(np.mean(P_i))
    P_e = float(np.sum(p_j ** 2))

    if P_e == 1:
        kappa = 1.0 if P_bar == 1 else 0.0
    else:
        kappa = (P_bar - P_e) / (1 - P_e)

    uniform_n = (
        int(n_raters_per_item[0]) if len(set(n_raters_per_item.tolist())) == 1 else None
    )

    return {
        "kappa": float(kappa),
        "observed_agreement": float(P_bar),
        "expected_agreement": float(P_e),
        "interpretation": _interpret_kappa(kappa),
        "n_items": int(n_items),
        "n_categories": int(n_categories),
        "n_raters": uniform_n,
        "categories": list(categories),
    }


def percent_agreement(ratings_matrix: List[List[Any]]) -> Optional[float]:
    """
    Simple percent agreement: fraction of items where all raters chose the same value.
    Items with <2 ratings are skipped. None when no comparable items.
    """
    comparable = 0
    agreed = 0
    for row in ratings_matrix:
        non_null = [r for r in row if r is not None]
        if len(non_null) < 2:
            continue
        comparable += 1
        if all(r == non_null[0] for r in non_null):
            agreed += 1
    if comparable == 0:
        return None
    return round(agreed / comparable, 4)


@dataclass
class AgreementReport:
    """Composite agreement output from `compute_agreement`."""

    n_raters: int
    n_items: int
    score_type: ScoreType
    cohens_kappa_pairwise: Dict[Tuple[Any, Any], float] = field(default_factory=dict)
    fleiss_kappa: Optional[float] = None
    percent_agreement: Optional[float] = None
    pearson_r_pairwise: Dict[Tuple[Any, Any], float] = field(default_factory=dict)
    mean_absolute_deviation: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_raters": self.n_raters,
            "n_items": self.n_items,
            "score_type": self.score_type,
            "cohens_kappa_pairwise": {
                f"{a}__{b}": v for (a, b), v in self.cohens_kappa_pairwise.items()
            },
            "fleiss_kappa": self.fleiss_kappa,
            "percent_agreement": self.percent_agreement,
            "pearson_r_pairwise": {
                f"{a}__{b}": v for (a, b), v in self.pearson_r_pairwise.items()
            },
            "mean_absolute_deviation": self.mean_absolute_deviation,
        }


def compute_agreement(
    triples: Iterable[Tuple[Any, Any, Any]],
    score_type: ScoreType,
) -> AgreementReport:
    """
    Generic agreement composite over (rater_id, item_id, score) triples.

    For score_type ∈ {"categorical", "ordinal"}: returns Fleiss kappa (all raters),
    pairwise Cohen's kappa, and percent agreement. For "numeric": returns pairwise
    Pearson correlations and mean absolute deviation across raters per item.

    Single helper backing multi-judge LLM evaluation, multi-run same-model
    evaluation, and human-annotator agreement.
    """
    triples = list(triples)
    if not triples:
        return AgreementReport(n_raters=0, n_items=0, score_type=score_type)

    raters_set = sorted({t[0] for t in triples}, key=str)
    items_set = sorted({t[1] for t in triples}, key=str)
    rater_idx = {r: i for i, r in enumerate(raters_set)}
    item_idx = {it: i for i, it in enumerate(items_set)}

    matrix: List[List[Any]] = [[None] * len(raters_set) for _ in items_set]
    for r, it, score in triples:
        matrix[item_idx[it]][rater_idx[r]] = score

    report = AgreementReport(
        n_raters=len(raters_set),
        n_items=len(items_set),
        score_type=score_type,
    )

    if score_type in ("categorical", "ordinal"):
        if len(raters_set) >= 2:
            fk = fleiss_kappa(matrix)
            if "kappa" in fk:
                report.fleiss_kappa = round(float(fk["kappa"]), 4)
            for i, ra in enumerate(raters_set):
                for rb in raters_set[i + 1 :]:
                    paired_a: List[Any] = []
                    paired_b: List[Any] = []
                    for row in matrix:
                        va = row[rater_idx[ra]]
                        vb = row[rater_idx[rb]]
                        if va is not None and vb is not None:
                            paired_a.append(va)
                            paired_b.append(vb)
                    if len(paired_a) >= 2:
                        ck = cohens_kappa(paired_a, paired_b)
                        if "kappa" in ck:
                            report.cohens_kappa_pairwise[(ra, rb)] = round(float(ck["kappa"]), 4)
        report.percent_agreement = percent_agreement(matrix)

    elif score_type == "numeric":
        from .correlation import pearson  # local to keep module imports flat

        if len(raters_set) >= 2:
            for i, ra in enumerate(raters_set):
                for rb in raters_set[i + 1 :]:
                    paired_a: List[float] = []
                    paired_b: List[float] = []
                    for row in matrix:
                        va = row[rater_idx[ra]]
                        vb = row[rater_idx[rb]]
                        if va is not None and vb is not None:
                            try:
                                paired_a.append(float(va))
                                paired_b.append(float(vb))
                            except (TypeError, ValueError):
                                continue
                    r = pearson(paired_a, paired_b)
                    if r is not None:
                        report.pearson_r_pairwise[(ra, rb)] = r

        if NUMPY_AVAILABLE:
            per_item_devs: List[float] = []
            for row in matrix:
                vals = [v for v in row if v is not None]
                if len(vals) < 2:
                    continue
                try:
                    arr = np.asarray([float(v) for v in vals])
                except (TypeError, ValueError):
                    continue
                m = float(np.mean(arr))
                per_item_devs.append(float(np.mean(np.abs(arr - m))))
            if per_item_devs:
                report.mean_absolute_deviation = round(float(np.mean(per_item_devs)), 4)

    return report
