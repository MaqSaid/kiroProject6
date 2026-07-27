"""Circuit breaker implementation for inter-service communication."""

from __future__ import annotations

import asyncio
import time
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and call is rejected."""

    def __init__(self, service_name: str, reset_timeout: float) -> None:
        self.service_name = service_name
        self.reset_timeout = reset_timeout
        super().__init__(
            f"Circuit breaker open for '{service_name}'. "
            f"Reset timeout: {reset_timeout}s"
        )


class CircuitBreaker:
    """Circuit breaker with configurable thresholds.

    State transitions:
    - CLOSED -> OPEN: after failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: after reset_timeout seconds elapsed
    - HALF_OPEN -> CLOSED: probe request succeeds
    - HALF_OPEN -> OPEN: probe request fails
    """

    def __init__(
        self,
        service_name: str = "unknown",
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._service_name = service_name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Return current circuit state, checking for timeout-based transitions."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._reset_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        """Return current consecutive failure count."""
        return self._failure_count

    @property
    def service_name(self) -> str:
        """Return the service name this breaker protects."""
        return self._service_name

    async def allow_request(self) -> bool:
        """Check whether a request is allowed through the circuit breaker.

        Returns True if the request can proceed, False if it should be rejected.
        """
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                return False

            # HALF_OPEN: allow limited probe requests
            if self._half_open_calls < self._half_open_max_calls:
                self._half_open_calls += 1
                return True

            return False

    async def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        async with self._lock:
            previous_state = self.state
            self._failure_count = 0
            self._half_open_calls = 0

            if previous_state != CircuitState.CLOSED:
                self._state = CircuitState.CLOSED
                logger.info(
                    "circuit_breaker.closed",
                    service=self._service_name,
                    previous_state=previous_state.value,
                )

    async def record_failure(self) -> None:
        """Record a failed call. May open the circuit."""
        async with self._lock:
            self._failure_count += 1
            current_state = self.state

            if current_state == CircuitState.HALF_OPEN:
                # Probe failed, go back to OPEN
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._half_open_calls = 0
                logger.warning(
                    "circuit_breaker.opened",
                    service=self._service_name,
                    reason="half_open_probe_failed",
                    failure_count=self._failure_count,
                )
            elif (
                current_state == CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                # Threshold reached, open the circuit
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                logger.warning(
                    "circuit_breaker.opened",
                    service=self._service_name,
                    reason="failure_threshold_reached",
                    failure_count=self._failure_count,
                )
