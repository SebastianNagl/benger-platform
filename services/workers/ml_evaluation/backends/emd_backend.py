"""
Earth Mover Distance backends.

POT backend for ARM64 compatibility, pyemd for x86_64 performance.

References:
- POT: Flamary et al. (2021) "POT: Python Optimal Transport"
- pyemd: Standard EMD implementation using C++ SIMD
"""

import logging
import platform
from typing import Optional

import numpy as np

from .base import EMDBackend

logger = logging.getLogger(__name__)

IS_ARM64 = platform.machine().lower() in ('arm64', 'aarch64')


class POTEMDBackend(EMDBackend):
    """
    POT (Python Optimal Transport) based EMD computation.
    Works on ARM64 natively.

    Reference: Flamary et al. (2021) "POT: Python Optimal Transport"
    """

    def __init__(self):
        self._pot_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._pot_available is None:
            try:
                import ot  # noqa: F401

                self._pot_available = True
            except ImportError:
                self._pot_available = False
        return self._pot_available

    def compute_emd(
        self, source_weights: np.ndarray, target_weights: np.ndarray, distance_matrix: np.ndarray
    ) -> float:
        """
        Compute Earth Mover Distance using POT.

        Args:
            source_weights: Distribution weights for source (sums to 1)
            target_weights: Distribution weights for target (sums to 1)
            distance_matrix: Cost matrix [n_source, n_target]

        Returns:
            EMD distance value
        """
        import ot

        # Ensure float64 for POT
        source_weights = np.asarray(source_weights, dtype=np.float64)
        target_weights = np.asarray(target_weights, dtype=np.float64)
        distance_matrix = np.asarray(distance_matrix, dtype=np.float64)

        # Normalize weights
        source_sum = source_weights.sum()
        target_sum = target_weights.sum()

        if source_sum > 0:
            source_weights = source_weights / source_sum
        if target_sum > 0:
            target_weights = target_weights / target_sum

        # Compute EMD using network simplex solver
        emd_distance = ot.emd2(source_weights, target_weights, distance_matrix)

        return float(emd_distance)


class PyEMDBackend(EMDBackend):
    """
    PyEMD-based EMD computation.
    Faster on x86_64 but not available on ARM64.
    """

    def __init__(self):
        self._pyemd_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._pyemd_available is None:
            try:
                from pyemd import emd  # noqa: F401

                self._pyemd_available = True
            except (ImportError, ValueError, RuntimeError):
                # ImportError: pyemd not installed
                # ValueError: numpy binary incompatibility (dtype size mismatch)
                # RuntimeError: other C extension loading failures
                self._pyemd_available = False
        return self._pyemd_available

    def compute_emd(
        self, source_weights: np.ndarray, target_weights: np.ndarray, distance_matrix: np.ndarray
    ) -> float:
        """Compute EMD using pyemd."""
        from pyemd import emd

        return float(
            emd(
                np.asarray(source_weights, dtype=np.float64),
                np.asarray(target_weights, dtype=np.float64),
                np.asarray(distance_matrix, dtype=np.float64),
            )
        )


def get_emd_backend() -> EMDBackend:
    """Get the best available EMD backend for the current platform."""
    # Prefer POT on all platforms: pyemd >= 1.1.0 returns incorrect EMD values
    # for certain inputs (equal-length histograms with small distances).
    # POT's network simplex solver is well-tested and gives correct results.
    pot_backend = POTEMDBackend()
    if pot_backend.is_available():
        logger.info("Using POT EMD backend")
        return pot_backend

    # Fallback to pyemd on x86_64
    if not IS_ARM64:
        pyemd_backend = PyEMDBackend()
        if pyemd_backend.is_available():
            logger.info("Using PyEMD backend (POT not available)")
            return pyemd_backend

    raise RuntimeError("No EMD backend available. Install POT (recommended) or pyemd.")
