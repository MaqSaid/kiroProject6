"""Unit tests for RetryPolicy."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.retry_policy import MaxRetriesExceededError, RetryPolicy


@pytest.fixture
def policy() -> RetryPolicy:
    """Create a retry policy with fast delays for testing."""
    return RetryPolicy(
        max_attempts=3,
        base_delay=0.01,
        multiplier=2.0,
        max_jitter=0.005,
    )


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt(policy: RetryPolicy) -> None:
    """Successful function returns immediately."""
    func = AsyncMock(return_value="result")
    result = await policy.execute(func)
    assert result == "result"
    assert func.call_count == 1


@pytest.mark.asyncio
async def test_retries_on_failure(policy: RetryPolicy) -> None:
    """Retries after transient failures."""
    func = AsyncMock(side_effect=[ValueError("err1"), ValueError("err2"), "success"])
    result = await policy.execute(func)
    assert result == "success"
    assert func.call_count == 3


@pytest.mark.asyncio
async def test_raises_after_max_attempts(policy: RetryPolicy) -> None:
    """Raises MaxRetriesExceededError when all attempts fail."""
    func = AsyncMock(side_effect=ValueError("persistent error"))
    with pytest.raises(MaxRetriesExceededError) as exc_info:
        await policy.execute(func)
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_exception, ValueError)
    assert func.call_count == 3


@pytest.mark.asyncio
async def test_exponential_delay_increases() -> None:
    """Delays increase exponentially between attempts."""
    policy = RetryPolicy(
        max_attempts=4,
        base_delay=1.0,
        multiplier=2.0,
        max_jitter=0.0,  # No jitter for predictable delays
    )
    # attempt 0: 1.0 * 2^0 = 1.0
    assert policy._calculate_delay(0) == 1.0
    # attempt 1: 1.0 * 2^1 = 2.0
    assert policy._calculate_delay(1) == 2.0
    # attempt 2: 1.0 * 2^2 = 4.0
    assert policy._calculate_delay(2) == 4.0


@pytest.mark.asyncio
async def test_jitter_is_bounded() -> None:
    """Jitter stays within [0, max_jitter]."""
    policy = RetryPolicy(
        max_attempts=3,
        base_delay=1.0,
        multiplier=2.0,
        max_jitter=0.5,
    )
    for _ in range(100):
        delay = policy._calculate_delay(0)
        assert 1.0 <= delay <= 1.5


@pytest.mark.asyncio
async def test_max_attempts_property() -> None:
    """Max attempts is accessible."""
    policy = RetryPolicy(max_attempts=5)
    assert policy.max_attempts == 5


@pytest.mark.asyncio
async def test_passes_args_and_kwargs(policy: RetryPolicy) -> None:
    """Arguments are forwarded to the wrapped function."""
    async def func(a: int, b: str, c: bool = False) -> tuple:
        return (a, b, c)

    result = await policy.execute(func, 1, "hello", c=True)
    assert result == (1, "hello", True)
