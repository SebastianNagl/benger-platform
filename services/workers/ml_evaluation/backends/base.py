"""
Base backend interfaces for evaluation metrics.

Allows switching between ONNX and PyTorch implementations based on platform.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

import numpy as np


class EmbeddingBackend(ABC):
    """Abstract base for text embedding backends."""

    @abstractmethod
    def encode(self, texts: List[str]) -> np.ndarray:
        """
        Encode texts to embeddings.

        Args:
            texts: List of text strings to encode

        Returns:
            numpy array of shape [len(texts), embedding_dim]
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""


class BERTScoreBackend(ABC):
    """Abstract base for BERTScore computation."""

    @abstractmethod
    def compute(
        self, candidates: List[str], references: List[str], lang: str = "en"
    ) -> Tuple[float, float, float]:
        """
        Compute BERTScore precision, recall, F1.

        Args:
            candidates: List of candidate texts
            references: List of reference texts
            lang: Language code (e.g., "en", "de")

        Returns:
            Tuple of (precision, recall, f1) as floats
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""


class EMDBackend(ABC):
    """Abstract base for Earth Mover Distance computation."""

    @abstractmethod
    def compute_emd(
        self, source_weights: np.ndarray, target_weights: np.ndarray, distance_matrix: np.ndarray
    ) -> float:
        """
        Compute Earth Mover Distance.

        Args:
            source_weights: Distribution weights for source (sums to 1)
            target_weights: Distribution weights for target (sums to 1)
            distance_matrix: Cost matrix [n_source, n_target]

        Returns:
            EMD distance value
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""


class QAGSBackend(ABC):
    """
    Abstract base for QAGS (Question Answering for Generation Scoring).

    QAGS evaluates factual consistency by:
    1. Generating questions from source text
    2. Answering questions using both source and generated text
    3. Comparing answers for consistency

    Reference: Wang et al. (2020) "Asking and Answering Questions to
    Evaluate the Factual Consistency of Summaries"
    """

    @abstractmethod
    def generate_questions(self, text: str, num_questions: int = 5) -> List[str]:
        """
        Generate questions from text using T5.

        Args:
            text: Source text to generate questions from
            num_questions: Maximum number of questions to generate

        Returns:
            List of question strings
        """

    @abstractmethod
    def answer_question(self, question: str, context: str) -> Dict[str, Any]:
        """
        Answer a question given context using DistilBERT.

        Args:
            question: Question string
            context: Context text to find answer in

        Returns:
            Dict with 'answer' key and optional 'score' key
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""


class SummaCBackend(ABC):
    """
    Abstract base for SummaC factual consistency scoring.

    SummaC uses NLI (Natural Language Inference) to evaluate
    whether a summary is factually consistent with its source document.

    This is a reimplementation using the ViTC (Vitamin C) NLI model
    directly, avoiding the summac package dependency conflict.

    Reference: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models
    for Inconsistency Detection in Summarization"

    Model: Schuster et al. (2021) "Get Your Vitamin C! Robust Fact
    Verification with Contrastive Evidence" (tals/albert-xlarge-vitaminc-mnli)
    """

    @abstractmethod
    def score_consistency(self, document: str, summary: str) -> float:
        """
        Score factual consistency using sentence-level NLI.

        Args:
            document: Source document text
            summary: Summary or claim to check for consistency

        Returns:
            Consistency score between 0.0 (inconsistent) and 1.0 (consistent)
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available."""
