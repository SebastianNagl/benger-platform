"""
Inter-Annotator Agreement (IAA) Metrics

Provides comprehensive IAA metrics for human evaluation quality assessment.
Supports multiple annotators, different data types, and provides interpretation.

Issue #483: Human evaluation quality metrics
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Try to import scipy for advanced statistics
try:
    pass

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def cohens_kappa(
    rater1: List[Any],
    rater2: List[Any],
    weights: str = "none",
) -> Dict[str, Any]:
    """
    Calculate Cohen's Kappa for two raters.

    Args:
        rater1: Ratings from first annotator
        rater2: Ratings from second annotator
        weights: Weighting scheme ("none", "linear", "quadratic")

    Returns:
        Dictionary with kappa value and interpretation
    """
    if len(rater1) != len(rater2):
        return {"error": "Raters must have same number of ratings"}

    if len(rater1) == 0:
        return {"error": "No ratings provided"}

    # Get unique categories
    all_ratings = list(set(rater1) | set(rater2))
    n_categories = len(all_ratings)
    n_samples = len(rater1)

    # Create rating to index mapping
    rating_to_idx = {r: i for i, r in enumerate(all_ratings)}

    # Build confusion matrix
    confusion = np.zeros((n_categories, n_categories))
    for r1, r2 in zip(rater1, rater2):
        i, j = rating_to_idx[r1], rating_to_idx[r2]
        confusion[i, j] += 1

    # Calculate observed agreement
    if weights == "none":
        # Unweighted (exact agreement only)
        po = np.sum(np.diag(confusion)) / n_samples
    elif weights == "linear":
        # Linear weighting
        weight_matrix = np.zeros((n_categories, n_categories))
        for i in range(n_categories):
            for j in range(n_categories):
                weight_matrix[i, j] = 1 - abs(i - j) / (n_categories - 1)
        po = np.sum(weight_matrix * confusion) / n_samples
    elif weights == "quadratic":
        # Quadratic weighting
        weight_matrix = np.zeros((n_categories, n_categories))
        for i in range(n_categories):
            for j in range(n_categories):
                weight_matrix[i, j] = 1 - ((i - j) / (n_categories - 1)) ** 2
        po = np.sum(weight_matrix * confusion) / n_samples
    else:
        return {"error": f"Unknown weights: {weights}"}

    # Calculate expected agreement (chance)
    row_marginals = np.sum(confusion, axis=1) / n_samples
    col_marginals = np.sum(confusion, axis=0) / n_samples

    if weights == "none":
        pe = np.sum(row_marginals * col_marginals)
    else:
        pe = 0
        for i in range(n_categories):
            for j in range(n_categories):
                pe += weight_matrix[i, j] * row_marginals[i] * col_marginals[j]

    # Calculate kappa
    if pe == 1:
        kappa = 1.0 if po == 1 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)

    # Interpretation (Landis & Koch, 1977)
    if kappa < 0:
        interpretation = "poor (worse than chance)"
    elif kappa < 0.20:
        interpretation = "slight"
    elif kappa < 0.40:
        interpretation = "fair"
    elif kappa < 0.60:
        interpretation = "moderate"
    elif kappa < 0.80:
        interpretation = "substantial"
    else:
        interpretation = "almost perfect"

    return {
        "kappa": float(kappa),
        "observed_agreement": float(po),
        "expected_agreement": float(pe),
        "interpretation": interpretation,
        "weights": weights,
        "n_samples": n_samples,
        "n_categories": n_categories,
    }


def fleiss_kappa(
    ratings_matrix: List[List[int]],
    categories: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Calculate Fleiss' Kappa for multiple raters.

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater's rating
                       (can have different numbers of raters per item)
        categories: Optional list of category values (auto-detected if not provided)

    Returns:
        Dictionary with kappa value and interpretation
    """
    if not ratings_matrix or not ratings_matrix[0]:
        return {"error": "Empty ratings matrix"}

    # Convert to numpy and detect categories
    ratings = np.array(ratings_matrix)
    n_items = len(ratings)

    if categories is None:
        # Flatten and get unique categories
        all_ratings = [r for row in ratings_matrix for r in row if r is not None]
        categories = sorted(set(all_ratings))

    n_categories = len(categories)
    cat_to_idx = {c: i for i, c in enumerate(categories)}

    # Build count matrix: n_items x n_categories
    # Each cell = number of raters who chose that category for that item
    counts = np.zeros((n_items, n_categories))

    for i, item_ratings in enumerate(ratings_matrix):
        for rating in item_ratings:
            if rating is not None and rating in cat_to_idx:
                counts[i, cat_to_idx[rating]] += 1

    # Number of raters per item
    n_raters_per_item = np.sum(counts, axis=1)

    # Check if all items have same number of raters
    n = int(n_raters_per_item[0]) if len(set(n_raters_per_item)) == 1 else None

    if n is None:
        # Variable number of raters - use generalized formula
        n_total_ratings = np.sum(counts)

        # Proportion of ratings per category
        p_j = np.sum(counts, axis=0) / n_total_ratings

        # Per-item agreement
        P_i = np.zeros(n_items)
        for i in range(n_items):
            n_i = n_raters_per_item[i]
            if n_i > 1:
                P_i[i] = (np.sum(counts[i] ** 2) - n_i) / (n_i * (n_i - 1))

        # Overall observed agreement
        P_bar = np.mean(P_i)

        # Expected agreement by chance
        P_e = np.sum(p_j**2)
    else:
        # Standard Fleiss' Kappa (all items have n raters)
        # Proportion of ratings per category
        p_j = np.sum(counts, axis=0) / (n_items * n)

        # Per-item agreement
        P_i = (np.sum(counts**2, axis=1) - n) / (n * (n - 1))

        # Overall observed agreement
        P_bar = np.mean(P_i)

        # Expected agreement by chance
        P_e = np.sum(p_j**2)

    # Calculate kappa
    if P_e == 1:
        kappa = 1.0 if P_bar == 1 else 0.0
    else:
        kappa = (P_bar - P_e) / (1 - P_e)

    # Interpretation
    if kappa < 0:
        interpretation = "poor (worse than chance)"
    elif kappa < 0.20:
        interpretation = "slight"
    elif kappa < 0.40:
        interpretation = "fair"
    elif kappa < 0.60:
        interpretation = "moderate"
    elif kappa < 0.80:
        interpretation = "substantial"
    else:
        interpretation = "almost perfect"

    return {
        "kappa": float(kappa),
        "observed_agreement": float(P_bar),
        "expected_agreement": float(P_e),
        "interpretation": interpretation,
        "n_items": n_items,
        "n_categories": n_categories,
        "n_raters": n,
        "categories": categories,
    }


def cronbachs_alpha(
    ratings_matrix: List[List[float]],
) -> Dict[str, Any]:
    """
    Calculate Cronbach's Alpha for internal consistency.

    Used for continuous/ordinal ratings (e.g., Likert scales).

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater
                       Values should be numeric (continuous or ordinal)

    Returns:
        Dictionary with alpha value and interpretation
    """
    if not ratings_matrix or not ratings_matrix[0]:
        return {"error": "Empty ratings matrix"}

    # Convert to numpy
    ratings = np.array(ratings_matrix, dtype=float)
    n_items, n_raters = ratings.shape

    if n_raters < 2:
        return {"error": "Need at least 2 raters for Cronbach's alpha"}

    # Calculate variances
    item_variances = np.var(ratings, axis=1, ddof=1)  # Variance per item
    total_scores = np.sum(ratings, axis=0)  # Sum across items for each rater
    total_variance = np.var(total_scores, ddof=1)

    # Cronbach's alpha formula
    if total_variance == 0:
        alpha = 0.0
    else:
        alpha = (n_items / (n_items - 1)) * (1 - np.sum(item_variances) / total_variance)

    # Interpretation
    if alpha < 0.5:
        interpretation = "unacceptable"
    elif alpha < 0.6:
        interpretation = "poor"
    elif alpha < 0.7:
        interpretation = "questionable"
    elif alpha < 0.8:
        interpretation = "acceptable"
    elif alpha < 0.9:
        interpretation = "good"
    else:
        interpretation = "excellent"

    return {
        "alpha": float(alpha),
        "interpretation": interpretation,
        "n_items": n_items,
        "n_raters": n_raters,
        "sum_item_variances": float(np.sum(item_variances)),
        "total_variance": float(total_variance),
    }


def krippendorff_alpha(
    ratings_matrix: List[List[Optional[Any]]],
    level_of_measurement: str = "nominal",
) -> Dict[str, Any]:
    """
    Calculate Krippendorff's Alpha for any number of raters.

    Handles missing data and different measurement levels.

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater
                       None values indicate missing ratings
        level_of_measurement: "nominal", "ordinal", "interval", or "ratio"

    Returns:
        Dictionary with alpha value and interpretation
    """
    if not ratings_matrix:
        return {"error": "Empty ratings matrix"}

    # Collect all non-None ratings
    all_ratings = []
    for row in ratings_matrix:
        for r in row:
            if r is not None:
                all_ratings.append(r)

    if len(all_ratings) < 2:
        return {"error": "Need at least 2 ratings"}

    # Get unique values and create mapping
    unique_values = sorted(set(all_ratings))
    len(unique_values)
    value_to_idx = {v: i for i, v in enumerate(unique_values)}

    # Distance function based on measurement level
    def distance(v1, v2):
        if v1 is None or v2 is None:
            return 0
        i1, i2 = value_to_idx.get(v1, 0), value_to_idx.get(v2, 0)

        if level_of_measurement == "nominal":
            return 0 if v1 == v2 else 1
        elif level_of_measurement == "ordinal":
            # Metric distance for ordinal
            return (i1 - i2) ** 2
        elif level_of_measurement == "interval":
            return (float(v1) - float(v2)) ** 2
        elif level_of_measurement == "ratio":
            s = float(v1) + float(v2)
            if s == 0:
                return 0
            return ((float(v1) - float(v2)) / s) ** 2
        return 0 if v1 == v2 else 1

    # Calculate observed disagreement
    n_items = len(ratings_matrix)
    n_raters = len(ratings_matrix[0]) if ratings_matrix else 0

    total_pairs = 0
    observed_disagreement = 0

    for row in ratings_matrix:
        valid_ratings = [r for r in row if r is not None]
        n_valid = len(valid_ratings)

        if n_valid < 2:
            continue

        # All pairs within this item
        for i in range(n_valid):
            for j in range(i + 1, n_valid):
                observed_disagreement += distance(valid_ratings[i], valid_ratings[j])
                total_pairs += 1

    if total_pairs == 0:
        return {"error": "No valid rating pairs found"}

    D_o = observed_disagreement / total_pairs

    # Calculate expected disagreement
    # Flatten all valid ratings
    flat_ratings = [r for row in ratings_matrix for r in row if r is not None]
    n_total = len(flat_ratings)

    expected_disagreement = 0
    expected_pairs = 0

    for i in range(n_total):
        for j in range(i + 1, n_total):
            expected_disagreement += distance(flat_ratings[i], flat_ratings[j])
            expected_pairs += 1

    if expected_pairs == 0:
        return {"error": "Cannot calculate expected disagreement"}

    D_e = expected_disagreement / expected_pairs

    # Calculate alpha
    if D_e == 0:
        alpha = 1.0 if D_o == 0 else 0.0
    else:
        alpha = 1 - D_o / D_e

    # Interpretation
    if alpha < 0:
        interpretation = "poor (systematic disagreement)"
    elif alpha < 0.667:
        interpretation = "tentative conclusions only"
    elif alpha < 0.800:
        interpretation = "acceptable for tentative conclusions"
    else:
        interpretation = "good reliability"

    return {
        "alpha": float(alpha),
        "observed_disagreement": float(D_o),
        "expected_disagreement": float(D_e),
        "interpretation": interpretation,
        "level_of_measurement": level_of_measurement,
        "n_items": n_items,
        "n_raters": n_raters,
        "n_valid_pairs": total_pairs,
    }


def percent_agreement(
    ratings_matrix: List[List[Any]],
) -> Dict[str, Any]:
    """
    Calculate simple percent agreement.

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater

    Returns:
        Dictionary with percent agreement and related stats
    """
    if not ratings_matrix:
        return {"error": "Empty ratings matrix"}

    len(ratings_matrix)
    agreements = 0
    total_comparisons = 0

    for row in ratings_matrix:
        valid_ratings = [r for r in row if r is not None]
        n_valid = len(valid_ratings)

        if n_valid < 2:
            continue

        # Check if all raters agree
        if len(set(valid_ratings)) == 1:
            agreements += 1

        total_comparisons += 1

    if total_comparisons == 0:
        return {"error": "No items with multiple raters"}

    pct_agreement = agreements / total_comparisons

    return {
        "percent_agreement": float(pct_agreement),
        "agreements": agreements,
        "disagreements": total_comparisons - agreements,
        "total_items": total_comparisons,
        "interpretation": (
            "excellent"
            if pct_agreement >= 0.9
            else "good"
            if pct_agreement >= 0.8
            else "moderate"
            if pct_agreement >= 0.7
            else "fair"
            if pct_agreement >= 0.6
            else "poor"
        ),
    }


def intraclass_correlation(
    ratings_matrix: List[List[float]],
    icc_type: str = "ICC(2,1)",
) -> Dict[str, Any]:
    """
    Calculate Intraclass Correlation Coefficient (ICC).

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater
        icc_type: Type of ICC to calculate
                 "ICC(1,1)" - One-way random effects
                 "ICC(2,1)" - Two-way random effects (default)
                 "ICC(3,1)" - Two-way mixed effects

    Returns:
        Dictionary with ICC value and interpretation
    """
    if not ratings_matrix or not ratings_matrix[0]:
        return {"error": "Empty ratings matrix"}

    # Convert to numpy
    ratings = np.array(ratings_matrix, dtype=float)
    n_items, n_raters = ratings.shape

    if n_raters < 2:
        return {"error": "Need at least 2 raters for ICC"}

    # Calculate means
    grand_mean = np.mean(ratings)
    row_means = np.mean(ratings, axis=1)  # Item means
    col_means = np.mean(ratings, axis=0)  # Rater means

    # Sum of squares
    SS_total = np.sum((ratings - grand_mean) ** 2)
    SS_rows = n_raters * np.sum((row_means - grand_mean) ** 2)  # Between items
    SS_cols = n_items * np.sum((col_means - grand_mean) ** 2)  # Between raters
    SS_error = SS_total - SS_rows - SS_cols

    # Mean squares
    MS_rows = SS_rows / (n_items - 1)
    MS_cols = SS_cols / (n_raters - 1) if n_raters > 1 else 0
    MS_error = SS_error / ((n_items - 1) * (n_raters - 1)) if (n_items > 1 and n_raters > 1) else 1

    # Calculate ICC based on type
    if icc_type == "ICC(1,1)":
        # One-way random effects, single measure
        MS_within = (SS_cols + SS_error) / (n_items * (n_raters - 1))
        icc = (MS_rows - MS_within) / (MS_rows + (n_raters - 1) * MS_within)
    elif icc_type == "ICC(2,1)":
        # Two-way random effects, single measure
        icc = (MS_rows - MS_error) / (
            MS_rows + (n_raters - 1) * MS_error + n_raters * (MS_cols - MS_error) / n_items
        )
    elif icc_type == "ICC(3,1)":
        # Two-way mixed effects, single measure
        icc = (MS_rows - MS_error) / (MS_rows + (n_raters - 1) * MS_error)
    else:
        return {"error": f"Unknown ICC type: {icc_type}"}

    # Interpretation (Cicchetti, 1994)
    if icc < 0.40:
        interpretation = "poor"
    elif icc < 0.60:
        interpretation = "fair"
    elif icc < 0.75:
        interpretation = "good"
    else:
        interpretation = "excellent"

    return {
        "icc": float(icc),
        "icc_type": icc_type,
        "interpretation": interpretation,
        "n_items": n_items,
        "n_raters": n_raters,
        "ms_between_items": float(MS_rows),
        "ms_between_raters": float(MS_cols),
        "ms_error": float(MS_error),
    }


def compute_all_iaa_metrics(
    ratings_matrix: List[List[Any]],
    level_of_measurement: str = "nominal",
) -> Dict[str, Any]:
    """
    Compute all applicable IAA metrics for a ratings matrix.

    Args:
        ratings_matrix: Matrix where each row is an item, each column is a rater
        level_of_measurement: "nominal", "ordinal", "interval", or "ratio"

    Returns:
        Dictionary with all computed IAA metrics
    """
    result = {
        "n_items": len(ratings_matrix) if ratings_matrix else 0,
        "n_raters": len(ratings_matrix[0]) if ratings_matrix and ratings_matrix[0] else 0,
        "level_of_measurement": level_of_measurement,
        "metrics": {},
    }

    # Percent agreement (always applicable)
    result["metrics"]["percent_agreement"] = percent_agreement(ratings_matrix)

    # Fleiss' Kappa (for categorical data)
    if level_of_measurement in ["nominal", "ordinal"]:
        result["metrics"]["fleiss_kappa"] = fleiss_kappa(ratings_matrix)

    # Cohen's Kappa (for 2 raters)
    if result["n_raters"] == 2:
        rater1 = [row[0] for row in ratings_matrix if row[0] is not None]
        rater2 = [row[1] for row in ratings_matrix if row[1] is not None]
        if len(rater1) == len(rater2):
            weights = "quadratic" if level_of_measurement == "ordinal" else "none"
            result["metrics"]["cohens_kappa"] = cohens_kappa(rater1, rater2, weights=weights)

    # Krippendorff's Alpha (handles missing data)
    result["metrics"]["krippendorff_alpha"] = krippendorff_alpha(
        ratings_matrix, level_of_measurement=level_of_measurement
    )

    # For continuous/ordinal data, add Cronbach's Alpha and ICC
    if level_of_measurement in ["ordinal", "interval", "ratio"]:
        try:
            # Convert to numeric for these metrics
            numeric_matrix = [
                [float(r) if r is not None else np.nan for r in row] for row in ratings_matrix
            ]
            # Remove rows with any NaN
            clean_matrix = [row for row in numeric_matrix if not any(np.isnan(row))]

            if len(clean_matrix) >= 2:
                result["metrics"]["cronbachs_alpha"] = cronbachs_alpha(clean_matrix)
                result["metrics"]["icc"] = intraclass_correlation(clean_matrix)
        except (ValueError, TypeError):
            pass  # Skip if conversion fails

    return result


# ============================================================================
# Span-Specific IAA Metrics (Issue #964)
# ============================================================================


def _span_iou(span1: Dict[str, int], span2: Dict[str, int]) -> float:
    """Calculate Intersection over Union for two spans.

    Args:
        span1: Dict with 'start' and 'end' keys
        span2: Dict with 'start' and 'end' keys

    Returns:
        IoU score between 0.0 and 1.0
    """
    start1, end1 = span1.get("start", 0), span1.get("end", 0)
    start2, end2 = span2.get("start", 0), span2.get("end", 0)

    intersection_start = max(start1, start2)
    intersection_end = min(end1, end2)
    intersection = max(0, intersection_end - intersection_start)

    union = (end1 - start1) + (end2 - start2) - intersection

    if union == 0:
        return 1.0 if intersection == 0 else 0.0

    return intersection / union


def _match_spans(spans1: List[Dict], spans2: List[Dict], iou_threshold: float = 0.5) -> List[tuple]:
    """Match spans between two annotators using IoU threshold.

    Args:
        spans1: List of span dicts from annotator 1
        spans2: List of span dicts from annotator 2
        iou_threshold: Minimum IoU to consider a match

    Returns:
        List of (span1, span2, iou) tuples for matches
    """
    matches = []
    used_spans2 = set()

    for s1 in spans1:
        best_match = None
        best_iou = 0.0

        for idx, s2 in enumerate(spans2):
            if idx in used_spans2:
                continue

            iou = _span_iou(s1, s2)
            if iou >= iou_threshold and iou > best_iou:
                best_iou = iou
                best_match = (s1, s2, iou, idx)

        if best_match:
            matches.append((best_match[0], best_match[1], best_match[2]))
            used_spans2.add(best_match[3])

    return matches


def span_agreement(
    annotations: List[List[Dict]],
    iou_threshold: float = 0.5,
    include_labels: bool = True,
) -> Dict[str, Any]:
    """
    Calculate inter-annotator agreement for span annotations.

    Uses IoU-based matching to pair spans between annotators, then calculates
    agreement metrics based on matched pairs.

    Args:
        annotations: List of annotations per item, where each annotation is a list
                    of spans with 'start', 'end', and optionally 'labels' keys.
                    Format: [[annotator1_spans, annotator2_spans, ...], ...]
        iou_threshold: Minimum IoU to consider spans as matching (default 0.5)
        include_labels: If True, also require label match for agreement

    Returns:
        Dictionary with:
        - span_agreement: Overall agreement score (F1 of matched spans)
        - avg_iou: Average IoU of matched spans
        - precision: Proportion of predicted spans that match ground truth
        - recall: Proportion of ground truth spans that are matched
        - label_agreement: Agreement on labels (if include_labels=True)
        - n_items: Number of items analyzed
        - interpretation: Human-readable interpretation

    Reference:
        Brandsen et al. (2020) "Creating a Dataset for Named Entity Recognition
        in the Archaeology Domain" - Section on IAA for NER
    """
    if not annotations or len(annotations) == 0:
        return {"error": "No annotations provided"}

    # Ensure we have at least 2 annotators per item
    valid_items = [item for item in annotations if len(item) >= 2]
    if not valid_items:
        return {"error": "Need at least 2 annotators per item"}

    total_matches = 0
    total_spans_a1 = 0
    total_spans_a2 = 0
    iou_scores = []
    label_matches = 0
    label_comparisons = 0

    for item in valid_items:
        # For now, compare first two annotators (pairwise)
        spans1 = item[0] if isinstance(item[0], list) else []
        spans2 = item[1] if isinstance(item[1], list) else []

        matches = _match_spans(spans1, spans2, iou_threshold)

        total_matches += len(matches)
        total_spans_a1 += len(spans1)
        total_spans_a2 += len(spans2)

        for s1, s2, iou in matches:
            iou_scores.append(iou)

            if include_labels:
                labels1 = set(s1.get("labels", []))
                labels2 = set(s2.get("labels", []))
                if labels1 and labels2:
                    label_comparisons += 1
                    if labels1 == labels2:
                        label_matches += 1

    # Calculate metrics
    precision = total_matches / total_spans_a2 if total_spans_a2 > 0 else 0.0
    recall = total_matches / total_spans_a1 if total_spans_a1 > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    avg_iou = np.mean(iou_scores) if iou_scores else 0.0

    result = {
        "span_agreement": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "avg_iou": round(float(avg_iou), 4),
        "total_matched_spans": total_matches,
        "total_spans_annotator1": total_spans_a1,
        "total_spans_annotator2": total_spans_a2,
        "n_items": len(valid_items),
        "iou_threshold": iou_threshold,
    }

    if include_labels and label_comparisons > 0:
        result["label_agreement"] = round(label_matches / label_comparisons, 4)
        result["label_comparisons"] = label_comparisons

    # Interpretation
    if f1 >= 0.8:
        result["interpretation"] = "Strong span agreement"
    elif f1 >= 0.6:
        result["interpretation"] = "Moderate span agreement"
    elif f1 >= 0.4:
        result["interpretation"] = "Fair span agreement"
    else:
        result[
            "interpretation"
        ] = "Poor span agreement - annotation guidelines may need clarification"

    return result


def span_boundary_agreement(
    annotations: List[List[Dict]],
    tolerance: int = 0,
) -> Dict[str, Any]:
    """
    Calculate boundary agreement for span annotations.

    Measures how often annotators agree on span boundaries (start/end positions).

    Args:
        annotations: List of annotations per item, where each annotation is a list
                    of spans with 'start' and 'end' keys.
        tolerance: Number of characters of tolerance for boundary matching (default 0 = exact)

    Returns:
        Dictionary with:
        - start_agreement: Agreement on start positions
        - end_agreement: Agreement on end positions
        - boundary_agreement: Overall boundary agreement
        - n_comparisons: Number of span pairs compared
        - interpretation: Human-readable interpretation
    """
    if not annotations or len(annotations) == 0:
        return {"error": "No annotations provided"}

    valid_items = [item for item in annotations if len(item) >= 2]
    if not valid_items:
        return {"error": "Need at least 2 annotators per item"}

    start_matches = 0
    end_matches = 0
    total_comparisons = 0

    for item in valid_items:
        spans1 = item[0] if isinstance(item[0], list) else []
        spans2 = item[1] if isinstance(item[1], list) else []

        # Match spans by IoU first
        matches = _match_spans(spans1, spans2, iou_threshold=0.3)

        for s1, s2, _ in matches:
            total_comparisons += 1
            start1, end1 = s1.get("start", 0), s1.get("end", 0)
            start2, end2 = s2.get("start", 0), s2.get("end", 0)

            if abs(start1 - start2) <= tolerance:
                start_matches += 1
            if abs(end1 - end2) <= tolerance:
                end_matches += 1

    if total_comparisons == 0:
        return {
            "error": "No matching spans found between annotators",
            "n_comparisons": 0,
        }

    start_agreement = start_matches / total_comparisons
    end_agreement = end_matches / total_comparisons
    boundary_agreement = (start_agreement + end_agreement) / 2

    result = {
        "start_agreement": round(start_agreement, 4),
        "end_agreement": round(end_agreement, 4),
        "boundary_agreement": round(boundary_agreement, 4),
        "n_comparisons": total_comparisons,
        "tolerance": tolerance,
    }

    if boundary_agreement >= 0.9:
        result["interpretation"] = "Excellent boundary agreement"
    elif boundary_agreement >= 0.7:
        result["interpretation"] = "Good boundary agreement"
    elif boundary_agreement >= 0.5:
        result["interpretation"] = "Moderate boundary agreement"
    else:
        result["interpretation"] = "Poor boundary agreement - consider clearer boundary guidelines"

    return result
