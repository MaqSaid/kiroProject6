"""Retry policy with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class MaxRetriesExceededError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exception: Exception) -> None:
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Max retries exceeded after {attempts} attempts. "
            f"Last error: {last_exception}"
        )


class RetryPolicy:
    """Exponential backoff retry with jitter.

    Delays follow the pattern: base_delay * multiplier^(attempt-1) + random_jitter
    With defaults (base=1.0, multiplier=2.0, max_jitter=0.5):
    - Attempt 1 delay: ~1.0s + jitter (0-500ms)
    - Attempt 2 delay: ~2.0s + jitter (0-500ms)
    - Attempt 3 delay: ~4.0s + jitter (0-500ms)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        multiplier: float = 2.0,
        max_jitter: float = 0.5,
    ) -> None:
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._multiplier = multiplier
        self._max_jitter = max_jitter

    @property
    def max_attempts(self) -> int:
        """Return maximum number of attempts."""
        return self._max_attempts

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed).

        Returns the delay in seconds including jitter.
        """
        exponential_delay = self._base_delay * (self._multiplier ** attempt)
        jitter = random.uniform(0, self._max_jitter)  # noqa: S311
        return exponential_delay + jitter

    async def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a function with retry logic.

        Args:
            func: An async callable to execute.
            *args: Positional arguments passed to func.
            **kwargs: Keyword arguments passed to func.

        Returns:
            The result of func if successful.

        Raises:
            MaxRetriesExceededError: When all retry attempts are exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(self._max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exception = exc

                if attempt < self._max_attempts - 1:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "retry_policy.retrying",
                        attempt=attempt + 1,
                        max_attempts=self._max_attempts,
                        delay_seconds=round(delay, 3),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        raise MaxRetriesExceededError(
            attempts=self._max_attempts,
            last_exception=last_exception,  # type: ignore[arg-type]
        )
