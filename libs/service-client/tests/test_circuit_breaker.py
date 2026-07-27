"""Unit tests for CircuitBreaker."""

import asyncio
import time
from unittest.mock import patch

import pytest

from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


@pytest.fixture
def breaker() -> CircuitBreaker:
    """Create a circuit breaker with default settings."""
    return CircuitBreaker(
        service_name="test-service",
        failure_threshold=5,
        reset_timeout=30.0,
        half_open_max_calls=1,
    )


@pytest.mark.asyncio
async def test_initial_state_is_closed(breaker: CircuitBreaker) -> None:
    """Circuit breaker starts in CLOSED state."""
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_allows_requests_when_closed(breaker: CircuitBreaker) -> None:
    """CLOSED state allows all requests."""
    assert await breaker.allow_request() is True


@pytest.mark.asyncio
async def test_stays_closed_below_threshold(breaker: CircuitBreaker) -> None:
    """Circuit stays CLOSED with fewer than threshold failures."""
    for _ in range(4):
        await breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert await breaker.allow_request() is True


@pytest.mark.asyncio
async def test_opens_at_threshold(breaker: CircuitBreaker) -> None:
    """Circuit opens after 5 consecutive failures."""
    for _ in range(5):
        await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert await breaker.allow_request() is False


@pytest.mark.asyncio
async def test_success_resets_failure_count(breaker: CircuitBreaker) -> None:
    """A success resets the consecutive failure count."""
    for _ in range(4):
        await breaker.record_failure()
    await breaker.record_success()
    assert breaker.failure_count == 0
    # Now 4 more failures still shouldn't open
    for _ in range(4):
        await breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_transitions_to_half_open_after_timeout() -> None:
    """OPEN state transitions to HALF_OPEN after reset_timeout."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=5,
        reset_timeout=0.1,  # 100ms for testing
    )
    for _ in range(5):
        await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    await asyncio.sleep(0.15)
    assert breaker.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_allows_one_probe() -> None:
    """HALF_OPEN state allows exactly one probe request."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=5,
        reset_timeout=0.1,
    )
    for _ in range(5):
        await breaker.record_failure()
    await asyncio.sleep(0.15)

    # First probe allowed
    assert await breaker.allow_request() is True
    # Second probe rejected
    assert await breaker.allow_request() is False


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit() -> None:
    """Successful probe in HALF_OPEN closes the circuit."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=5,
        reset_timeout=0.1,
    )
    for _ in range(5):
        await breaker.record_failure()
    await asyncio.sleep(0.15)

    await breaker.allow_request()  # Allow probe
    await breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert await breaker.allow_request() is True


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit() -> None:
    """Failed probe in HALF_OPEN reopens the circuit."""
    breaker = CircuitBreaker(
        service_name="test-service",
        failure_threshold=5,
        reset_timeout=0.1,
    )
    for _ in range(5):
        await breaker.record_failure()
    await asyncio.sleep(0.15)

    await breaker.allow_request()  # Allow probe
    await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_service_name_property(breaker: CircuitBreaker) -> None:
    """Service name is accessible."""
    assert breaker.service_name == "test-service"
