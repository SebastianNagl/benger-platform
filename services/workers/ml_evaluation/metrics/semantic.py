"""Semantic-similarity metric-family computations.

Covers bertscore / moverscore / semantic_similarity. Extracted from
``SampleEvaluator``.

The lazy-loaders (``_get_backend_selector`` / ``_get_sentence_transformer``),
the ``IS_ARM64`` flag, ``bert_score_compute`` and ``st_util`` are imported
*lazily* from ``..sample_evaluator`` inside the function body so that tests
which patch them on ``ml_evaluation.sample_evaluator`` take effect and so we
read the same module-level singletons the orchestrator uses.
"""

from typing import Any, Dict, Optional

import numpy as np


def compute_semantic_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute semantic similarity metrics using neural models.
    NO FALLBACKS - All models must be available for scientific rigor.

    Args:
        metric_name: One of 'bertscore', 'moverscore', 'semantic_similarity'
        gt: Ground truth text
        pred: Predicted text
        parameters: Optional metric-specific parameters
            - lang: Language code for BERTScore (default: 'de')
            - method: For FactCC, one of 'summac' or 'factcc' (default: 'summac')

    Returns:
        Similarity score (0.0-1.0)

    Raises:
        RuntimeError: If required dependencies are not available
    """
    from ..sample_evaluator import (
        IS_ARM64,
        _get_backend_selector,
        _get_sentence_transformer,
        bert_score_compute,
        st_util,
    )

    if parameters is None:
        parameters = {}

    gt_str = str(gt)
    pred_str = str(pred)

    if metric_name == "bertscore":
        # BERTScore - Use backend selector for platform compatibility
        lang = parameters.get("lang", "de")  # Default to German

        if IS_ARM64:
            # Use ONNX backend on ARM64
            selector = _get_backend_selector()
            backend = selector.get_bertscore_backend()
            P, R, F1 = backend.compute([pred_str], [gt_str], lang=lang)
            return float(F1)
        else:
            # Use original bert-score library on x86_64 for best accuracy
            P, R, F1 = bert_score_compute(
                [pred_str], [gt_str], lang=lang, rescale_with_baseline=True, verbose=False
            )
            return float(F1.mean().item())

    elif metric_name == "moverscore":
        # MoverScore via POT backend (platform-independent, replaces moverscore_v2/pyemd)
        if not gt_str or not gt_str.strip():
            raise ValueError("MoverScore requires non-empty ground truth text")
        if not pred_str or not pred_str.strip():
            raise ValueError("MoverScore requires non-empty prediction text")
        if len(gt_str.strip()) < 3 or len(pred_str.strip()) < 3:
            raise ValueError("MoverScore requires text longer than 3 characters")

        selector = _get_backend_selector()
        computer = selector.get_moverscore_computer()
        n_gram = parameters.get("n_gram", 1)
        remove_subwords = parameters.get("remove_subwords", True)
        scores = computer.compute_moverscore(
            [gt_str], [pred_str], n_gram=n_gram, remove_subwords=remove_subwords
        )
        return float(scores[0]) if scores else 0.0

    elif metric_name == "semantic_similarity":
        # Semantic similarity - Use backend selector for platform compatibility
        if IS_ARM64:
            # Use ONNX backend on ARM64
            selector = _get_backend_selector()
            backend = selector.get_embedding_backend()
            emb_gt = backend.encode([gt_str])[0]
            emb_pred = backend.encode([pred_str])[0]
            # Compute cosine similarity
            similarity = np.dot(emb_gt, emb_pred) / (
                np.linalg.norm(emb_gt) * np.linalg.norm(emb_pred) + 1e-9
            )
            return max(0.0, float(similarity))
        else:
            # Use sentence-transformers on x86_64
            model = _get_sentence_transformer()
            if model is None:
                raise RuntimeError(
                    "Sentence transformer model could not be loaded. "
                    "Ensure sentence-transformers package is installed."
                )
            emb_gt = model.encode(gt_str, convert_to_tensor=True)
            emb_pred = model.encode(pred_str, convert_to_tensor=True)
            similarity = st_util.cos_sim(emb_gt, emb_pred).item()
            return max(0.0, similarity)

    raise ValueError(f"Unknown semantic metric: {metric_name}")
