"""
Backend module for platform-aware ML metric computation.

Provides automatic selection between ONNX (ARM64) and PyTorch (x86_64) backends.
"""

from .selector import IS_ARM64, backend_selector

__all__ = ["backend_selector", "IS_ARM64"]
