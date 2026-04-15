"""
Statistical Analysis Utilities for Evaluation

Provides bootstrap confidence intervals, significance testing, and
effect size calculations for research-grade evaluation.

Issue #483: Statistical rigor for research-grade evaluation
"""

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# Try to import scipy for advanced statistics
try:
    from scipy import stats as scipy_stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available - some statistical tests will be limited")

# Try to import statsmodels for additional tests (required dependency)
try:
    from statsmodels.stats.contingency_tables import mcnemar

    STATSMODELS_AVAILABLE = True
except ImportError as e:
    STATSMODELS_AVAILABLE = False
    # Log as ERROR - this is a required dependency declared in requirements.txt
    logger.error(f"statsmodels import failed: {e}. McNemar test will not work.")


def bootstrap_confidence_interval(
    data: List[float],
    statistic: str = "mean",
    confidence_level: float = 0.95,
    n_bootstrap: int = 1000,
    random_state: int = 42,
) -> Dict[str, float]:
    """
    Calculate bootstrap confidence interval for a statistic.

    Args:
        data: List of values to analyze
        statistic: Statistic to compute ("mean", "median", "std")
        confidence_level: Confidence level (default: 0.95 for 95% CI)
        n_bootstrap: Number of bootstrap samples
        random_state: Random seed for reproducibility

    Returns:
        Dictionary with point estimate, lower bound, upper bound, and std error
    """
    if not data or len(data) < 2:
        return {
            "point_estimate": data[0] if data else 0.0,
            "ci_lower": data[0] if data else 0.0,
            "ci_upper": data[0] if data else 0.0,
            "std_error": 0.0,
            "confidence_level": confidence_level,
        }

    data_array = np.array(data)
    np.random.seed(random_state)

    # Define statistic function
    stat_funcs = {
        "mean": np.mean,
        "median": np.median,
        "std": np.std,
    }
    stat_func = stat_funcs.get(statistic, np.mean)

    # Point estimate
    point_estimate = float(stat_func(data_array))

    # Bootstrap resampling
    bootstrap_stats = []
    n = len(data_array)

    for _ in range(n_bootstrap):
        # Resample with replacement
        sample = np.random.choice(data_array, size=n, replace=True)
        bootstrap_stats.append(stat_func(sample))

    bootstrap_stats = np.array(bootstrap_stats)

    # Calculate confidence interval (percentile method)
    alpha = 1 - confidence_level
    ci_lower = float(np.percentile(bootstrap_stats, 100 * alpha / 2))
    ci_upper = float(np.percentile(bootstrap_stats, 100 * (1 - alpha / 2)))

    # Standard error
    std_error = float(np.std(bootstrap_stats))

    return {
        "point_estimate": point_estimate,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "std_error": std_error,
        "confidence_level": confidence_level,
        "n_samples": n,
        "n_bootstrap": n_bootstrap,
    }


def paired_bootstrap_test(
    scores_a: List[float],
    scores_b: List[float],
    n_bootstrap: int = 10000,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Paired bootstrap test for comparing two systems.

    Tests if system A is significantly different from system B
    using paired bootstrap resampling.

    Args:
        scores_a: Scores from system A (per sample)
        scores_b: Scores from system B (per sample)
        n_bootstrap: Number of bootstrap iterations
        random_state: Random seed

    Returns:
        Dictionary with p-value, mean difference, and CI
    """
    if len(scores_a) != len(scores_b):
        return {"error": "Score lists must have same length"}

    if len(scores_a) < 2:
        return {"error": "Need at least 2 samples for comparison"}

    scores_a = np.array(scores_a)
    scores_b = np.array(scores_b)
    np.random.seed(random_state)

    # Observed difference
    observed_diff = np.mean(scores_a) - np.mean(scores_b)

    # Bootstrap
    n = len(scores_a)
    bootstrap_diffs = []

    for _ in range(n_bootstrap):
        indices = np.random.choice(n, size=n, replace=True)
        sample_a = scores_a[indices]
        sample_b = scores_b[indices]
        bootstrap_diffs.append(np.mean(sample_a) - np.mean(sample_b))

    bootstrap_diffs = np.array(bootstrap_diffs)

    # Two-sided p-value
    # Count how often the bootstrap difference is as extreme as observed
    p_value = np.mean(np.abs(bootstrap_diffs) >= np.abs(observed_diff))

    # Confidence interval for difference
    ci_lower = float(np.percentile(bootstrap_diffs, 2.5))
    ci_upper = float(np.percentile(bootstrap_diffs, 97.5))

    return {
        "mean_difference": float(observed_diff),
        "p_value": float(p_value),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "significant_at_05": p_value < 0.05,
        "significant_at_01": p_value < 0.01,
        "a_better": observed_diff > 0,
        "n_samples": n,
    }


def significance_test(
    scores_a: List[float],
    scores_b: List[float],
    test_type: str = "auto",
    paired: bool = True,
) -> Dict[str, Any]:
    """
    Perform significance test between two systems.

    Args:
        scores_a: Scores from system A
        scores_b: Scores from system B
        test_type: Test to use ("t-test", "wilcoxon", "mannwhitney", "auto")
        paired: Whether samples are paired (same test instances)

    Returns:
        Dictionary with test statistic, p-value, and interpretation
    """
    if not SCIPY_AVAILABLE:
        # Fall back to bootstrap test
        if paired and len(scores_a) == len(scores_b):
            return paired_bootstrap_test(scores_a, scores_b)
        return {"error": "scipy not available for parametric tests"}

    scores_a = np.array(scores_a)
    scores_b = np.array(scores_b)

    # Auto-select test based on data characteristics
    if test_type == "auto":
        # Check normality (Shapiro-Wilk)
        if len(scores_a) >= 3 and len(scores_b) >= 3:
            _, p_norm_a = scipy_stats.shapiro(scores_a)
            _, p_norm_b = scipy_stats.shapiro(scores_b)
            is_normal = p_norm_a > 0.05 and p_norm_b > 0.05
        else:
            is_normal = True  # Assume normal for small samples

        if is_normal:
            test_type = "t-test"
        else:
            test_type = "wilcoxon" if paired else "mannwhitney"

    # Run selected test
    result = {
        "test_type": test_type,
        "paired": paired,
        "n_a": len(scores_a),
        "n_b": len(scores_b),
        "mean_a": float(np.mean(scores_a)),
        "mean_b": float(np.mean(scores_b)),
        "mean_difference": float(np.mean(scores_a) - np.mean(scores_b)),
    }

    try:
        if test_type == "t-test":
            if paired and len(scores_a) == len(scores_b):
                stat, p_value = scipy_stats.ttest_rel(scores_a, scores_b)
            else:
                stat, p_value = scipy_stats.ttest_ind(scores_a, scores_b)
            result["statistic"] = float(stat)
            result["p_value"] = float(p_value)

        elif test_type == "wilcoxon":
            if len(scores_a) != len(scores_b):
                return {"error": "Wilcoxon requires paired samples"}
            stat, p_value = scipy_stats.wilcoxon(scores_a, scores_b)
            result["statistic"] = float(stat)
            result["p_value"] = float(p_value)

        elif test_type == "mannwhitney":
            stat, p_value = scipy_stats.mannwhitneyu(scores_a, scores_b, alternative="two-sided")
            result["statistic"] = float(stat)
            result["p_value"] = float(p_value)

        # Add significance interpretation
        result["significant_at_05"] = result["p_value"] < 0.05
        result["significant_at_01"] = result["p_value"] < 0.01
        result["a_better"] = result["mean_difference"] > 0

    except Exception as e:
        result["error"] = str(e)

    return result


def cohens_d(scores_a: List[float], scores_b: List[float]) -> Dict[str, Any]:
    """
    Calculate Cohen's d effect size.

    Args:
        scores_a: Scores from system A
        scores_b: Scores from system B

    Returns:
        Dictionary with effect size and interpretation
    """
    scores_a = np.array(scores_a)
    scores_b = np.array(scores_b)

    # Pooled standard deviation
    n_a, n_b = len(scores_a), len(scores_b)
    var_a, var_b = np.var(scores_a, ddof=1), np.var(scores_b, ddof=1)
    pooled_std = np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))

    if pooled_std == 0:
        d = 0.0
    else:
        d = (np.mean(scores_a) - np.mean(scores_b)) / pooled_std

    # Interpretation (Cohen's conventions)
    if abs(d) < 0.2:
        interpretation = "negligible"
    elif abs(d) < 0.5:
        interpretation = "small"
    elif abs(d) < 0.8:
        interpretation = "medium"
    else:
        interpretation = "large"

    return {
        "cohens_d": float(d),
        "interpretation": interpretation,
        "a_better": d > 0,
        "pooled_std": float(pooled_std),
    }


def cliffs_delta(scores_a: List[float], scores_b: List[float]) -> Dict[str, Any]:
    """
    Calculate Cliff's delta effect size (non-parametric).

    Cliff's delta measures how often values in one distribution are larger
    than values in another. More robust than Cohen's d for non-normal data.

    Reference: Cliff, N. (1993). Dominance statistics: Ordinal analyses
    to answer ordinal questions. Psychological Bulletin, 114(3), 494-509.

    Args:
        scores_a: Scores from system A
        scores_b: Scores from system B

    Returns:
        Dictionary with effect size and interpretation
    """
    scores_a = np.array(scores_a)
    scores_b = np.array(scores_b)

    n_a, n_b = len(scores_a), len(scores_b)

    if n_a == 0 or n_b == 0:
        return {
            "cliffs_delta": 0.0,
            "interpretation": "negligible",
            "a_better": False,
            "dominance_count": 0,
        }

    # Count dominance pairs
    dominance_count = 0
    for a in scores_a:
        for b in scores_b:
            if a > b:
                dominance_count += 1
            elif a < b:
                dominance_count -= 1

    # Cliff's delta: proportion of dominance
    delta = dominance_count / (n_a * n_b)

    # Interpretation (Romano et al., 2006 thresholds)
    abs_delta = abs(delta)
    if abs_delta < 0.147:
        interpretation = "negligible"
    elif abs_delta < 0.33:
        interpretation = "small"
    elif abs_delta < 0.474:
        interpretation = "medium"
    else:
        interpretation = "large"

    return {
        "cliffs_delta": float(delta),
        "interpretation": interpretation,
        "a_better": delta > 0,
        "dominance_count": int(dominance_count),
        "total_pairs": n_a * n_b,
    }


def correlation_matrix(
    metrics_data: Dict[str, List[float]],
    method: str = "pearson",
) -> Dict[str, Dict[str, float]]:
    """
    Calculate correlation matrix between metrics.

    Args:
        metrics_data: Dict mapping metric names to lists of scores
        method: Correlation method ("pearson" or "spearman")

    Returns:
        Nested dict with correlation coefficients
    """
    metric_names = list(metrics_data.keys())
    n_metrics = len(metric_names)

    if n_metrics < 2:
        return {}

    # Build matrix
    result = {m: {} for m in metric_names}

    for i, metric_a in enumerate(metric_names):
        for j, metric_b in enumerate(metric_names):
            if i == j:
                result[metric_a][metric_b] = 1.0
                continue

            scores_a = np.array(metrics_data[metric_a])
            scores_b = np.array(metrics_data[metric_b])

            # Ensure same length
            min_len = min(len(scores_a), len(scores_b))
            if min_len < 3:
                result[metric_a][metric_b] = None
                continue

            scores_a = scores_a[:min_len]
            scores_b = scores_b[:min_len]

            try:
                if method == "spearman" and SCIPY_AVAILABLE:
                    corr, _ = scipy_stats.spearmanr(scores_a, scores_b)
                elif SCIPY_AVAILABLE:
                    corr, _ = scipy_stats.pearsonr(scores_a, scores_b)
                else:
                    # Fallback to numpy pearson
                    corr = np.corrcoef(scores_a, scores_b)[0, 1]

                result[metric_a][metric_b] = float(corr) if not np.isnan(corr) else None
            except Exception:
                result[metric_a][metric_b] = None

    return result


def mcnemar_test(
    correct_a: List[bool],
    correct_b: List[bool],
) -> Dict[str, Any]:
    """
    McNemar's test for comparing binary classification accuracy.

    Tests whether two classifiers have significantly different error rates
    on the same test set.

    Requires statsmodels>=0.14.0 (declared in requirements.txt).

    Args:
        correct_a: List of booleans indicating if system A was correct
        correct_b: List of booleans indicating if system B was correct

    Returns:
        Dictionary with test statistic and p-value

    Raises:
        RuntimeError: If statsmodels is not available
        ValueError: If input lists are invalid
    """
    # NO FALLBACK - require statsmodels for scientific rigor
    if not STATSMODELS_AVAILABLE:
        raise RuntimeError(
            "McNemar test requires statsmodels library. "
            "Install with: pip install statsmodels>=0.14.0"
        )

    # Validate inputs
    if len(correct_a) != len(correct_b):
        raise ValueError("Input lists must have equal length")
    if len(correct_a) == 0:
        raise ValueError("Input lists cannot be empty")

    # Use statsmodels implementation
    correct_a = np.array(correct_a)
    correct_b = np.array(correct_b)

    # Build contingency table
    # [A correct & B correct, A correct & B wrong]
    # [A wrong & B correct, A wrong & B wrong]
    table = np.array(
        [
            [np.sum(correct_a & correct_b), np.sum(correct_a & ~correct_b)],
            [np.sum(~correct_a & correct_b), np.sum(~correct_a & ~correct_b)],
        ]
    )

    result = mcnemar(table, exact=True)

    return {
        "statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "significant_at_05": result.pvalue < 0.05,
        "a_correct_b_wrong": int(table[0, 1]),
        "a_wrong_b_correct": int(table[1, 0]),
        "a_better": table[0, 1] > table[1, 0],
    }


def aggregate_with_statistics(
    per_sample_scores: List[float],
    metric_name: str,
    confidence_level: float = 0.95,
) -> Dict[str, Any]:
    """
    Aggregate per-sample scores with statistical measures.

    Args:
        per_sample_scores: List of scores for each sample
        metric_name: Name of the metric
        confidence_level: Confidence level for CI

    Returns:
        Dictionary with mean, CI, std, and other statistics
    """
    if not per_sample_scores:
        return {
            "metric": metric_name,
            "mean": None,
            "ci_lower": None,
            "ci_upper": None,
            "std": None,
            "n_samples": 0,
        }

    scores = np.array(per_sample_scores)

    # Basic statistics
    result = {
        "metric": metric_name,
        "mean": float(np.mean(scores)),
        "median": float(np.median(scores)),
        "std": float(np.std(scores)),
        "min": float(np.min(scores)),
        "max": float(np.max(scores)),
        "n_samples": len(scores),
    }

    # Bootstrap CI
    ci = bootstrap_confidence_interval(per_sample_scores, "mean", confidence_level=confidence_level)
    result["ci_lower"] = ci["ci_lower"]
    result["ci_upper"] = ci["ci_upper"]
    result["std_error"] = ci["std_error"]
    result["confidence_level"] = confidence_level

    return result


def compute_inter_judge_agreement(
    judge_scores: Dict[str, List[float]],
) -> Dict[str, Any]:
    """
    Compute agreement metrics between multiple judges (raters).

    Used for multi-judge LLM-as-Judge evaluation to measure
    inter-rater reliability.

    Reference:
    - Krippendorff, K. (2011). Computing Krippendorff's Alpha-Reliability.

    Args:
        judge_scores: Dict mapping judge model IDs to lists of scores.
                     All lists must have the same length (one score per sample).

    Returns:
        Dictionary with:
        - krippendorff_alpha: Agreement coefficient (-1 to 1, 1 = perfect agreement)
        - fleiss_kappa: Agreement for categorical ratings (if applicable)
        - pairwise_correlations: Correlation matrix between judges
        - mean_pairwise_correlation: Average correlation
        - score_variance: Variance in scores across judges per sample
    """
    if not judge_scores or len(judge_scores) < 2:
        return {
            "error": "Need at least 2 judges for agreement metrics",
            "krippendorff_alpha": None,
            "mean_pairwise_correlation": None,
        }

    judges = list(judge_scores.keys())
    n_judges = len(judges)

    # Validate all judges have same number of scores
    n_samples = len(judge_scores[judges[0]])
    for judge in judges:
        if len(judge_scores[judge]) != n_samples:
            return {"error": "All judges must rate the same number of samples"}

    if n_samples < 2:
        return {"error": "Need at least 2 samples for agreement metrics"}

    # Build rating matrix (judges x samples)
    ratings = np.array([judge_scores[j] for j in judges])

    result = {
        "n_judges": n_judges,
        "n_samples": n_samples,
        "judges": judges,
    }

    # Krippendorff's alpha for interval data
    result["krippendorff_alpha"] = _krippendorff_alpha_interval(ratings)

    # Pairwise correlations between judges
    pairwise_corr = {}
    correlations = []
    for i in range(n_judges):
        for j in range(i + 1, n_judges):
            judge_a, judge_b = judges[i], judges[j]
            if SCIPY_AVAILABLE:
                corr, _ = scipy_stats.pearsonr(ratings[i], ratings[j])
            else:
                corr = np.corrcoef(ratings[i], ratings[j])[0, 1]
            pairwise_corr[f"{judge_a}_vs_{judge_b}"] = float(corr) if not np.isnan(corr) else None
            if not np.isnan(corr):
                correlations.append(corr)

    result["pairwise_correlations"] = pairwise_corr
    result["mean_pairwise_correlation"] = float(np.mean(correlations)) if correlations else None

    # Score variance across judges per sample
    sample_variances = np.var(ratings, axis=0)
    result["mean_score_variance"] = float(np.mean(sample_variances))
    result["max_score_variance"] = float(np.max(sample_variances))

    # Interpretation
    alpha = result["krippendorff_alpha"]
    if alpha is not None:
        if alpha >= 0.8:
            result["interpretation"] = "high agreement"
        elif alpha >= 0.667:
            result["interpretation"] = "moderate agreement"
        elif alpha >= 0.0:
            result["interpretation"] = "low agreement"
        else:
            result["interpretation"] = "no agreement (worse than chance)"

    return result


def _krippendorff_alpha_interval(
    ratings: np.ndarray,
) -> float:
    """
    Calculate Krippendorff's alpha for interval data.

    Implementation based on:
    Krippendorff, K. (2011). Computing Krippendorff's Alpha-Reliability.

    Args:
        ratings: 2D array of shape (n_judges, n_samples)

    Returns:
        Alpha coefficient between -1 and 1
    """
    n_judges, n_samples = ratings.shape

    # Observed disagreement
    # For interval data: squared differences
    observed_disagreement = 0.0
    pairs_count = 0

    for sample in range(n_samples):
        sample_ratings = ratings[:, sample]
        # All pairs of ratings for this sample
        for i in range(n_judges):
            for j in range(i + 1, n_judges):
                observed_disagreement += (sample_ratings[i] - sample_ratings[j]) ** 2
                pairs_count += 1

    if pairs_count == 0:
        return 0.0

    observed_disagreement /= pairs_count

    # Expected disagreement (across all ratings)
    all_ratings = ratings.flatten()
    n_total = len(all_ratings)

    expected_disagreement = 0.0
    for i in range(n_total):
        for j in range(i + 1, n_total):
            expected_disagreement += (all_ratings[i] - all_ratings[j]) ** 2

    expected_pairs = n_total * (n_total - 1) / 2
    if expected_pairs > 0:
        expected_disagreement /= expected_pairs
    else:
        return 0.0

    if expected_disagreement == 0:
        return 1.0  # Perfect agreement

    alpha = 1 - (observed_disagreement / expected_disagreement)
    return float(alpha)


def compute_consensus_score(
    judge_scores: Dict[str, float],
    method: str = "mean",
) -> Dict[str, Any]:
    """
    Compute consensus score from multiple judges.

    Args:
        judge_scores: Dict mapping judge model IDs to scores for a single sample
        method: Aggregation method ("mean", "median", "trimmed_mean")

    Returns:
        Dictionary with consensus score and confidence metrics
    """
    scores = list(judge_scores.values())
    n_judges = len(scores)

    if n_judges == 0:
        return {"consensus_score": None, "error": "No judge scores provided"}

    if n_judges == 1:
        return {
            "consensus_score": scores[0],
            "method": method,
            "n_judges": 1,
            "variance": 0.0,
        }

    scores_array = np.array(scores)

    if method == "median":
        consensus = float(np.median(scores_array))
    elif method == "trimmed_mean" and n_judges >= 3:
        # Trim highest and lowest
        sorted_scores = np.sort(scores_array)
        trimmed = sorted_scores[1:-1] if n_judges > 2 else sorted_scores
        consensus = float(np.mean(trimmed))
    else:  # default: mean
        consensus = float(np.mean(scores_array))

    return {
        "consensus_score": consensus,
        "method": method,
        "n_judges": n_judges,
        "variance": float(np.var(scores_array)),
        "std": float(np.std(scores_array)),
        "min_score": float(np.min(scores_array)),
        "max_score": float(np.max(scores_array)),
        "range": float(np.max(scores_array) - np.min(scores_array)),
    }


def compare_systems(
    system_a_scores: Dict[str, List[float]],
    system_b_scores: Dict[str, List[float]],
    system_a_name: str = "System A",
    system_b_name: str = "System B",
) -> Dict[str, Any]:
    """
    Comprehensive comparison between two systems across multiple metrics.

    Args:
        system_a_scores: Dict mapping metric names to per-sample scores for system A
        system_b_scores: Dict mapping metric names to per-sample scores for system B
        system_a_name: Display name for system A
        system_b_name: Display name for system B

    Returns:
        Dictionary with comparison results for each metric
    """
    results = {
        "system_a": system_a_name,
        "system_b": system_b_name,
        "metrics": {},
        "summary": {"a_wins": 0, "b_wins": 0, "ties": 0},
    }

    # Find common metrics
    common_metrics = set(system_a_scores.keys()) & set(system_b_scores.keys())

    for metric in common_metrics:
        scores_a = system_a_scores[metric]
        scores_b = system_b_scores[metric]

        metric_result = {
            "mean_a": float(np.mean(scores_a)),
            "mean_b": float(np.mean(scores_b)),
        }

        # Significance test
        if len(scores_a) == len(scores_b) and len(scores_a) >= 3:
            sig_test = significance_test(scores_a, scores_b, paired=True)
            metric_result["significance"] = sig_test

            effect = cohens_d(scores_a, scores_b)
            metric_result["effect_size"] = effect

            # Determine winner
            if sig_test.get("significant_at_05"):
                if sig_test.get("a_better"):
                    results["summary"]["a_wins"] += 1
                    metric_result["winner"] = system_a_name
                else:
                    results["summary"]["b_wins"] += 1
                    metric_result["winner"] = system_b_name
            else:
                results["summary"]["ties"] += 1
                metric_result["winner"] = "tie"

        results["metrics"][metric] = metric_result

    return results
