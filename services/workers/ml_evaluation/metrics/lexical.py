"""Lexical text-similarity metric-family computations.

Covers bleu / rouge / meteor / chrf / edit_distance. Extracted from
``SampleEvaluator``. ``edit_distance`` uses ``ev._levenshtein_distance``
(canonical home is the hierarchical family); the class shim re-routes.
"""

from typing import Any, Dict, Optional

import sacrebleu
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer


def compute_text_similarity(
    ev, metric_name: str, gt: str, pred: str, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute text similarity metrics with configurable parameters.

    Args:
        metric_name: Name of the metric
        gt: Ground truth text
        pred: Predicted text
        parameters: Optional metric-specific parameters

    Returns:
        Similarity score (0.0-1.0)
    """
    if parameters is None:
        parameters = {}

    if metric_name == "edit_distance":
        # Levenshtein distance normalized to [0, 1]
        max_len = max(len(gt), len(pred))
        if max_len == 0:
            return 1.0
        return 1.0 - (ev._levenshtein_distance(gt, pred) / max_len)

    elif metric_name == "bleu":
        # BLEU score - NO FALLBACK, real implementation required
        max_order = parameters.get("max_order", 4)
        smoothing_method = parameters.get("smoothing", "method1")

        default_weights = {
            1: [1.0],
            2: [0.5, 0.5],
            3: [0.33, 0.33, 0.34],
            4: [0.25, 0.25, 0.25, 0.25],
        }
        weights = parameters.get("weights", default_weights.get(max_order, [0.25] * 4))

        reference = [gt.lower().split()]
        candidate = pred.lower().split()

        if not candidate:
            return 0.0

        # Validate the smoothing method explicitly. The previous
        # `getattr(smoothing, smoothing_method, smoothing.method1)`
        # silently substituted method1 on a typo, which silently
        # changed the benchmark — exactly the kind of unobservable
        # metric semantic shift the academic-rigor overhaul is
        # eliminating. Fail loud so a misconfigured project surfaces
        # at evaluation time, not in a paper.
        smoothing = SmoothingFunction()
        allowed_smoothing = {
            name for name in dir(smoothing)
            if name.startswith("method") and not name.startswith("__")
        }
        if smoothing_method not in allowed_smoothing:
            raise ValueError(
                f"Invalid BLEU smoothing method: {smoothing_method!r}; "
                f"allowed values are {sorted(allowed_smoothing)}."
            )
        smoothing_func = getattr(smoothing, smoothing_method)

        score = sentence_bleu(
            reference,
            candidate,
            smoothing_function=smoothing_func,
            weights=tuple(weights[:max_order]),
        )
        return score

    elif metric_name == "rouge":
        # ROUGE score - NO FALLBACK, real implementation required
        variant = parameters.get("variant", "rougeL")
        use_stemmer = parameters.get("use_stemmer", True)

        scorer = rouge_scorer.RougeScorer([variant], use_stemmer=use_stemmer)
        scores = scorer.score(gt, pred)
        return scores[variant].fmeasure

    elif metric_name == "meteor":
        # METEOR score - NO FALLBACK, real implementation required
        reference = gt.lower().split()
        candidate = pred.lower().split()

        if not candidate:
            return 0.0

        score = meteor_score([reference], candidate)
        return score

    elif metric_name == "chrf":
        # chrF score - NO FALLBACK, real implementation required
        char_order = parameters.get("char_order", 6)
        word_order = parameters.get("word_order", 0)
        beta = parameters.get("beta", 2)

        score = sacrebleu.sentence_chrf(
            pred, [gt], char_order=char_order, word_order=word_order, beta=beta
        )
        return score.score / 100.0  # Normalize to [0, 1]

    return 0.0
