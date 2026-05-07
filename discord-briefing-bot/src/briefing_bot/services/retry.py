"""Async retry helpers with exponential backoff."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    operation_name: str = "operation",
) -> T:
    """Run an async operation with exponential backoff.

    Args:
        operation: Zero-argument async operation to retry.
        attempts: Maximum number of attempts.
        initial_delay: First delay between attempts.
        backoff_factor: Delay multiplier after each failure.
        operation_name: Human-readable operation name for logs.

    Returns:
        The successful operation result.
    """
    delay = initial_delay
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception:
            if attempt == attempts:
                raise
            logger.warning("%s failed on attempt %s", operation_name, attempt)
            await asyncio.sleep(delay)
            delay *= backoff_factor
    raise RuntimeError("retry loop ended unexpectedly")
