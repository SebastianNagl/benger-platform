"""Python client for the BenGER API.

>>> from benger_client import BengerClient
>>> with BengerClient() as benger:          # BENGER_API_KEY, BENGER_BASE_URL
...     print(benger.me()["principal"]["scopes"])
"""

from ._client import DEFAULT_BASE_URL, BengerClient, mask_key
from ._version import __version__
from .errors import (
    AuthenticationError,
    BadRequestError,
    BengerAPIError,
    BengerConnectionError,
    BengerError,
    BengerJobError,
    BengerTimeoutError,
    ConflictError,
    GoneError,
    InsufficientScopeError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .polling import wait_until

__all__ = [
    "__version__",
    "DEFAULT_BASE_URL",
    "BengerClient",
    "mask_key",
    "wait_until",
    "BengerError",
    "BengerAPIError",
    "BengerConnectionError",
    "BengerTimeoutError",
    "BengerJobError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "InsufficientScopeError",
    "NotFoundError",
    "ConflictError",
    "GoneError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
]
