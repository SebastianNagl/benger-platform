"""
MoverScore implementation with pluggable EMD backend.

Supports both pyemd (x86_64) and POT (ARM64).

Reference: Zhao et al. (2019) "MoverScore: Text Generation Evaluating with
Contextualized Embeddings and Earth Mover Distance"
"""

import logging
import platform
from typing import List, Optional

import numpy as np

from .base import EmbeddingBackend
from .emd_backend import get_emd_backend

logger = logging.getLogger(__name__)

IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')


class MoverScoreComputer:
    """
    MoverScore computation with ARM64 support.
    Uses ONNX for embeddings and POT for EMD on ARM64.
    """

    def __init__(
        self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2", use_onnx: bool = False
    ):
        self.model_name = model_name
        self.use_onnx = use_onnx or IS_ARM64
        self._embedding_backend: Optional[EmbeddingBackend] = None
        self._emd_backend = None

    def _get_embedding_backend(self) -> EmbeddingBackend:
        if self._embedding_backend is None:
            if self.use_onnx:
                from .onnx_backend import ONNXEmbeddingBackend

                self._embedding_backend = ONNXEmbeddingBackend(self.model_name)
                logger.info("MoverScore using ONNX embedding backend")
            else:
                from .torch_backend import TorchEmbeddingBackend

                self._embedding_backend = TorchEmbeddingBackend(self.model_name)
                logger.info("MoverScore using PyTorch embedding backend")
        return self._embedding_backend

    def _get_emd_backend(self):
        if self._emd_backend is None:
            self._emd_backend = get_emd_backend()
        return self._emd_backend

    def compute_moverscore(
        self,
        references: List[str],
        hypotheses: List[str],
        n_gram: int = 1,
        remove_subwords: bool = True,
    ) -> List[float]:
        """
        Compute MoverScore for hypothesis-reference pairs.

        Args:
            references: List of reference texts
            hypotheses: List of hypothesis texts
            n_gram: N-gram size for word mover (default: 1)
            remove_subwords: Whether to remove subword tokens

        Returns:
            List of MoverScore values [0, 1]
        """
        if len(references) != len(hypotheses):
            raise ValueError("References and hypotheses must have same length")

        embedding_backend = self._get_embedding_backend()
        emd_backend = self._get_emd_backend()

        scores = []
        for ref, hyp in zip(references, hypotheses):
            try:
                score = self._compute_single_moverscore(ref, hyp, embedding_backend, emd_backend)
                scores.append(score)
            except Exception as e:
                logger.error(f"MoverScore computation failed: {e}")
                raise RuntimeError(f"MoverScore computation failed: {e}")

        return scores

    def _compute_single_moverscore(
        self, reference: str, hypothesis: str, embedding_backend: EmbeddingBackend, emd_backend
    ) -> float:
        """Compute MoverScore for a single pair."""
        # Validate inputs
        if not reference or not reference.strip():
            raise ValueError("MoverScore requires non-empty reference text")
        if not hypothesis or not hypothesis.strip():
            raise ValueError("MoverScore requires non-empty hypothesis text")

        # Tokenize
        ref_tokens = reference.lower().split()
        hyp_tokens = hypothesis.lower().split()

        if not ref_tokens or not hyp_tokens:
            return 0.0

        # Get embeddings for tokens
        ref_embeddings = embedding_backend.encode(ref_tokens)
        hyp_embeddings = embedding_backend.encode(hyp_tokens)

        # Compute distance matrix (cosine distance)
        ref_norm = ref_embeddings / (np.linalg.norm(ref_embeddings, axis=1, keepdims=True) + 1e-9)
        hyp_norm = hyp_embeddings / (np.linalg.norm(hyp_embeddings, axis=1, keepdims=True) + 1e-9)

        # Cosine similarity -> distance
        similarity = np.dot(ref_norm, hyp_norm.T)
        distance_matrix = 1 - similarity  # Convert to distance
        distance_matrix = np.clip(distance_matrix, 0, 2)  # Ensure valid range

        # Pad to square matrix (required by pyemd >= 1.1.0)
        n_ref, n_hyp = len(ref_tokens), len(hyp_tokens)
        n = max(n_ref, n_hyp)
        if n_ref != n_hyp:
            # Use max distance as padding to prevent cheap transport through phantom nodes
            max_dist = float(distance_matrix.max()) if distance_matrix.size > 0 else 1.0
            padded = np.full((n, n), max_dist, dtype=np.float64)
            padded[:n_ref, :n_hyp] = distance_matrix
            distance_matrix = padded

        # Uniform weights (padded entries get zero weight)
        ref_weights = np.zeros(n, dtype=np.float64)
        ref_weights[:n_ref] = 1.0 / n_ref
        hyp_weights = np.zeros(n, dtype=np.float64)
        hyp_weights[:n_hyp] = 1.0 / n_hyp

        # Compute EMD
        emd_distance = emd_backend.compute_emd(ref_weights, hyp_weights, distance_matrix)

        # Convert distance to similarity score [0, 1]
        # Sentence transformer embeddings have non-negative cosine similarity,
        # so cosine distances are bounded by ~1.0, not 2.0
        score = max(0.0, 1.0 - emd_distance)

        return float(score)
