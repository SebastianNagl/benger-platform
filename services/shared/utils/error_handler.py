"""
Standardized error handling utilities for BenGER services
"""

import logging
from functools import wraps
from typing import Any, Callable, Optional, Type

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class BenGERError(Exception):
    """Base exception for BenGER application errors"""
    
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationError(BenGERError):
    """Raised when validation fails"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR")


class NotFoundError(BenGERError):
    """Raised when a resource is not found"""
    
    def __init__(self, resource: str, identifier: str):
        message = f"{resource} with identifier '{identifier}' not found"
        super().__init__(message, "NOT_FOUND")


class PermissionError(BenGERError):
    """Raised when user lacks permission"""
    
    def __init__(self, action: str, resource: str):
        message = f"Permission denied for action '{action}' on '{resource}'"
        super().__init__(message, "PERMISSION_DENIED")


def handle_service_errors(
    default_message: str = "An error occurred", 
    log_errors: bool = True
) -> Callable:
    """
    Decorator for standardized service error handling
    
    Args:
        default_message: Default error message for unknown exceptions
        log_errors: Whether to log caught exceptions
    
    Usage:
        @handle_service_errors("Failed to process data")
        def process_data():
            # function implementation
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BenGERError:
                # Re-raise known application errors
                raise
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                raise BenGERError(default_message, "SERVICE_ERROR") from e
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except BenGERError:
                # Re-raise known application errors
                raise
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
                raise BenGERError(default_message, "SERVICE_ERROR") from e
        
        return async_wrapper if hasattr(func, '__code__') and func.__code__.co_flags & 0x80 else wrapper
    
    return decorator


def handle_api_errors(func: Callable) -> Callable:
    """
    Decorator for converting service errors to HTTP exceptions
    
    Usage:
        @handle_api_errors
        async def api_endpoint():
            # endpoint implementation
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": e.message, "code": e.code, "field": e.field}
            )
        except NotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": e.message, "code": e.code}
            )
        except PermissionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"message": e.message, "code": e.code}
            )
        except BenGERError as e:
            logger.error(f"Service error in {func.__name__}: {e.message}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": e.message, "code": e.code}
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "Internal server error", "code": "INTERNAL_ERROR"}
            )
    
    return async_wrapper