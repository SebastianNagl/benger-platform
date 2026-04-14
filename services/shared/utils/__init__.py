"""
Shared utilities for BenGER services
"""

from .error_handler import (
    BenGERError,
    NotFoundError,
    PermissionError,
    ValidationError,
    handle_api_errors,
    handle_service_errors,
)

__all__ = [
    "BenGERError",
    "NotFoundError", 
    "PermissionError",
    "ValidationError",
    "handle_api_errors",
    "handle_service_errors",
]