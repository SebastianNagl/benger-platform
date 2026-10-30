"""Polling helper shared by every ``wait`` method."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .errors import BengerTimeoutError

__all__ = ["wait_until"]

T = TypeVar("T")


def wait_until(
    predicate: Callable[[], T],
    *,
    timeout: float = 600.0,
    interval: float = 2.0,
    max_interval: float | None = 30.0,
    description: str = "condition",
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> T:
    """Call ``predicate()`` until it returns something truthy and return that.

    Sleeps ``interval`` seconds between calls, growing by half each round up
    to ``max_interval`` (``None`` keeps it fixed). Raises
    :class:`~benger_client.errors.BengerTimeoutError` once ``timeout`` seconds
    have passed; the exception's ``last_value`` holds the last result.
    Exceptions raised by ``predicate`` propagate unchanged.
    """
    deadline = clock() + timeout
    delay = interval
    last: T | None = None
    while True:
        last = predicate()
        if last:
            return last
        remaining = deadline - clock()
        if remaining <= 0:
            raise BengerTimeoutError(
                f"Timed out after {timeout:g}s waiting for {description}", last_value=last
            )
        sleep(min(delay, remaining))
        if max_interval is not None:
            delay = min(max_interval, delay * 1.5)
