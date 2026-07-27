"""ResilientClient instances for Embedding and Graph services.

Provides factory functions to create configured clients during lifespan startup.
"""

from __future__ import annotations

from service_client import CircuitBreaker, ResilientClient, RetryPolicy


def create_embedding_client(
    base_url: str,
    failure_threshold: int = 5,
    reset_timeout: float = 30.0,
    half_open_max_calls: int = 1,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_jitter: float = 0.5,
) -> ResilientClient:
    """Create a ResilientClient for the Embedding Service.

    Args:
        base_url: Base URL of the Embedding Service.
        failure_threshold: Circuit breaker failure threshold.
        reset_timeout: Circuit breaker reset timeout in seconds.
        half_open_max_calls: Max calls in half-open state.
        max_attempts: Retry max attempts.
        base_delay: Retry base delay.
        multiplier: Retry multiplier.
        max_jitter: Retry max jitter.

    Returns:
        Configured ResilientClient instance.
    """
    circuit_breaker = CircuitBreaker(
        service_name="embedding-service",
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout,
        half_open_max_calls=half_open_max_calls,
    )
    retry_policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        multiplier=multiplier,
        max_jitter=max_jitter,
    )
    return ResilientClient(
        base_url=base_url,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
        timeout=10.0,
    )


def create_graph_client(
    base_url: str,
    failure_threshold: int = 5,
    reset_timeout: float = 30.0,
    half_open_max_calls: int = 1,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_jitter: float = 0.5,
) -> ResilientClient:
    """Create a ResilientClient for the Graph Service.

    Args:
        base_url: Base URL of the Graph Service.
        failure_threshold: Circuit breaker failure threshold.
        reset_timeout: Circuit breaker reset timeout in seconds.
        half_open_max_calls: Max calls in half-open state.
        max_attempts: Retry max attempts.
        base_delay: Retry base delay.
        multiplier: Retry multiplier.
        max_jitter: Retry max jitter.

    Returns:
        Configured ResilientClient instance.
    """
    circuit_breaker = CircuitBreaker(
        service_name="graph-service",
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout,
        half_open_max_calls=half_open_max_calls,
    )
    retry_policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        multiplier=multiplier,
        max_jitter=max_jitter,
    )
    return ResilientClient(
        base_url=base_url,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
        timeout=5.0,
    )
