"""Resilient HTTP client wrapping httpx with circuit breaker, retry, and correlation ID."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from service_client.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from service_client.retry_policy import MaxRetriesExceededError, RetryPolicy

logger = structlog.get_logger(__name__)


class ResilientClient:
    """httpx AsyncClient with circuit breaker, retry, and correlation ID propagation.

    Provides resilient inter-service HTTP communication with:
    - Connection pooling (configurable max connections and keepalive)
    - Circuit breaker pattern to prevent cascade failures
    - Exponential backoff retry with jitter
    - Automatic X-Correlation-ID header propagation
    """

    def __init__(
        self,
        base_url: str,
        circuit_breaker: CircuitBreaker,
        retry_policy: RetryPolicy | None = None,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy or RetryPolicy()

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            timeout=httpx.Timeout(timeout),
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Return the circuit breaker instance."""
        return self._circuit_breaker

    @property
    def base_url(self) -> str:
        """Return the base URL."""
        return self._base_url

    async def request(
        self,
        method: str,
        path: str,
        correlation_id: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with circuit breaker, retry, and correlation ID.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: URL path relative to base_url.
            correlation_id: Correlation ID to propagate via X-Correlation-ID header.
            **kwargs: Additional arguments passed to httpx.AsyncClient.request
                (json, content, headers, params, etc.)

        Returns:
            httpx.Response on success.

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open.
            MaxRetriesExceededError: When all retry attempts are exhausted.
            httpx.HTTPStatusError: When server returns 5xx after retries.
        """
        # Check circuit breaker
        if not await self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(
                service_name=self._circuit_breaker.service_name,
                reset_timeout=self._circuit_breaker._reset_timeout,
            )

        # Inject correlation ID header
        headers = kwargs.pop("headers", None) or {}
        headers["X-Correlation-ID"] = correlation_id
        kwargs["headers"] = headers

        async def _do_request() -> httpx.Response:
            response = await self._client.request(method, path, **kwargs)

            # Treat 5xx as failures for circuit breaker
            if response.status_code >= 500:
                await self._circuit_breaker.record_failure()
                response.raise_for_status()

            # Success
            await self._circuit_breaker.record_success()
            return response

        try:
            return await self._retry_policy.execute(_do_request)
        except MaxRetriesExceededError:
            logger.error(
                "resilient_client.request_failed_after_retries",
                service=self._circuit_breaker.service_name,
                method=method,
                path=path,
                correlation_id=correlation_id,
            )
            raise
        except httpx.RequestError as exc:
            await self._circuit_breaker.record_failure()
            logger.error(
                "resilient_client.connection_error",
                service=self._circuit_breaker.service_name,
                method=method,
                path=path,
                correlation_id=correlation_id,
                error=str(exc),
            )
            raise

    async def get(
        self, path: str, correlation_id: str, **kwargs: Any
    ) -> httpx.Response:
        """Convenience method for GET requests."""
        return await self.request("GET", path, correlation_id, **kwargs)

    async def post(
        self, path: str, correlation_id: str, **kwargs: Any
    ) -> httpx.Response:
        """Convenience method for POST requests."""
        return await self.request("POST", path, correlation_id, **kwargs)

    async def put(
        self, path: str, correlation_id: str, **kwargs: Any
    ) -> httpx.Response:
        """Convenience method for PUT requests."""
        return await self.request("PUT", path, correlation_id, **kwargs)

    async def delete(
        self, path: str, correlation_id: str, **kwargs: Any
    ) -> httpx.Response:
        """Convenience method for DELETE requests."""
        return await self.request("DELETE", path, correlation_id, **kwargs)

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def __aenter__(self) -> ResilientClient:
        """Support async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close client on context exit."""
        await self.close()
