"""Shared service client library for inter-service HTTP communication.

Provides:
- CircuitBreaker: Circuit breaker pattern with CLOSED/OPEN/HALF_OPEN states
- RetryPolicy: Exponential backoff retry with jitter
- ResilientClient: httpx AsyncClient wrapper with circuit breaker, retry,
  and X-Correlation-ID propagation
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState
from .resilient_client import ResilientClient
from .retry_policy import MaxRetriesExceededError, RetryPolicy

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "MaxRetriesExceededError",
    "ResilientClient",
    "RetryPolicy",
]
