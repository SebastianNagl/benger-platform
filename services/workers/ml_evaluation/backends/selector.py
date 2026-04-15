"""
Automatic backend selection based on platform and availability.

Selects ONNX backends on ARM64, PyTorch backends on x86_64.
"""

import logging
import os
import platform
from typing import Optional

from .base import BERTScoreBackend, EmbeddingBackend, QAGSBackend, SummaCBackend

logger = logging.getLogger(__name__)

IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')


class BackendSelector:
    """
    Selects optimal backend for the current platform.

    On ARM64: Uses ONNX Runtime + POT
    On x86_64: Uses PyTorch + pyemd (with ONNX fallback if env var set)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._bertscore_backend: Optional[BERTScoreBackend] = None
        self._embedding_backend: Optional[EmbeddingBackend] = None
        self._moverscore_computer = None
        self._qags_backend: Optional[QAGSBackend] = None
        self._summac_backend: Optional[SummaCBackend] = None

        self._initialized = True
        logger.info(f"BackendSelector initialized for platform: {platform.machine()}")

    def _should_use_onnx(self) -> bool:
        """Check if ONNX should be preferred."""
        # Allow forcing PyTorch backend (bypasses ONNX export which has JIT issues)
        if os.environ.get("BENGER_USE_PYTORCH", "").lower() in ("true", "1", "yes"):
            logger.info("BENGER_USE_PYTORCH set - using PyTorch backend")
            return False
        if IS_ARM64:
            return True
        # Allow forcing ONNX on x86_64 for testing
        return os.environ.get("BENGER_USE_ONNX", "").lower() in ("true", "1", "yes")

    def get_bertscore_backend(self) -> BERTScoreBackend:
        """Get appropriate BERTScore backend."""
        if self._bertscore_backend is not None:
            return self._bertscore_backend

        if self._should_use_onnx():
            from .onnx_backend import ONNXBERTScoreBackend

            backend = ONNXBERTScoreBackend()
            if backend.is_available():
                self._bertscore_backend = backend
                logger.info("Using ONNX BERTScore backend")
                return self._bertscore_backend

        # Fall back to PyTorch (or use it directly on x86_64)
        from .torch_backend import TorchBERTScoreBackend

        backend = TorchBERTScoreBackend()
        if backend.is_available():
            self._bertscore_backend = backend
            logger.info("Using PyTorch BERTScore backend")
            return self._bertscore_backend

        raise RuntimeError("No BERTScore backend available. Install bert-score or onnxruntime.")

    def get_embedding_backend(self, model_name: Optional[str] = None) -> EmbeddingBackend:
        """Get appropriate embedding backend."""
        # If model name is specified, create a new backend (don't cache)
        if model_name is not None:
            if self._should_use_onnx():
                from .onnx_backend import ONNXEmbeddingBackend

                return ONNXEmbeddingBackend(model_name)
            else:
                from .torch_backend import TorchEmbeddingBackend

                return TorchEmbeddingBackend(model_name)

        # Use cached backend for default model
        if self._embedding_backend is not None:
            return self._embedding_backend

        default_model = "paraphrase-multilingual-MiniLM-L12-v2"

        if self._should_use_onnx():
            from .onnx_backend import ONNXEmbeddingBackend

            backend = ONNXEmbeddingBackend(default_model)
            if backend.is_available():
                self._embedding_backend = backend
                logger.info("Using ONNX embedding backend")
                return self._embedding_backend

        from .torch_backend import TorchEmbeddingBackend

        backend = TorchEmbeddingBackend(default_model)
        if backend.is_available():
            self._embedding_backend = backend
            logger.info("Using PyTorch embedding backend")
            return self._embedding_backend

        raise RuntimeError("No embedding backend available. Install sentence-transformers.")

    def get_moverscore_computer(self):
        """Get MoverScore computer with appropriate backend."""
        if self._moverscore_computer is None:
            from .moverscore_impl import MoverScoreComputer

            self._moverscore_computer = MoverScoreComputer(use_onnx=self._should_use_onnx())
        return self._moverscore_computer

    def get_qags_backend(self) -> QAGSBackend:
        """
        Get appropriate QAGS backend for factual consistency evaluation.

        Uses T5 for question generation and DistilBERT for question answering.
        Reference: Wang et al. (2020) "Asking and Answering Questions to
        Evaluate the Factual Consistency of Summaries"
        """
        if self._qags_backend is not None:
            return self._qags_backend

        if self._should_use_onnx():
            from .onnx_backend import ONNXQAGSBackend

            backend = ONNXQAGSBackend()
            if backend.is_available():
                self._qags_backend = backend
                logger.info("Using ONNX QAGS backend")
                return self._qags_backend

        # Fall back to PyTorch (or use it directly on x86_64)
        from .torch_backend import TorchQAGSBackend

        backend = TorchQAGSBackend()
        if backend.is_available():
            self._qags_backend = backend
            logger.info("Using PyTorch QAGS backend")
            return self._qags_backend

        raise RuntimeError(
            "No QAGS backend available. Install transformers and optimum[onnxruntime]."
        )

    def get_summac_backend(self) -> SummaCBackend:
        """
        Get appropriate SummaC backend for factual consistency evaluation.

        Uses ViTC (Vitamin C) NLI model for sentence-level consistency scoring.
        This is a reimplementation of SummaC that avoids dependency conflicts.

        References:
        - Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models for
          Inconsistency Detection in Summarization"
        - Schuster et al. (2021) "Get Your Vitamin C! Robust Fact Verification
          with Contrastive Evidence" (ViTC model)
        """
        if self._summac_backend is not None:
            return self._summac_backend

        if self._should_use_onnx():
            from .onnx_backend import ONNXSummaCBackend

            backend = ONNXSummaCBackend()
            if backend.is_available():
                self._summac_backend = backend
                logger.info("Using ONNX SummaC backend (ViTC-based)")
                return self._summac_backend

        # Fall back to PyTorch (or use it directly on x86_64)
        from .torch_backend import TorchSummaCBackend

        backend = TorchSummaCBackend()
        if backend.is_available():
            self._summac_backend = backend
            logger.info("Using PyTorch SummaC backend (ViTC-based)")
            return self._summac_backend

        raise RuntimeError(
            "No SummaC backend available. Install transformers and optimum[onnxruntime]."
        )


# Global singleton instance
backend_selector = BackendSelector()
