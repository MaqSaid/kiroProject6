"""Unit tests for ResilientClient."""

import httpx
import pytest
import respx

from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from src.resilient_client import ResilientClient
from src.retry_policy import MaxRetriesExceededError, RetryPolicy


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Create a circuit breaker for testing."""
    return CircuitBreaker(service_name="test-service", failure_threshold=5)


@pytest.fixture
def retry_policy() -> RetryPolicy:
    """Create a fast retry policy for testing."""
    return RetryPolicy(max_attempts=3, base_delay=0.01, multiplier=2.0, max_jitter=0.0)


@pytest.fixture
def client(circuit_breaker: CircuitBreaker, retry_policy: RetryPolicy) -> ResilientClient:
    """Create a resilient client for testing."""
    return ResilientClient(
        base_url="http://test-service:8000",
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
        max_connections=100,
        max_keepalive_connections=20,
    )


@pytest.mark.asyncio
@respx.mock
async def test_successful_get_request(client: ResilientClient) -> None:
    """Successful request returns response and propagates correlation ID."""
    route = respx.get("http://test-service:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    response = await client.get("/health", correlation_id="test-corr-123")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert route.called
    # Verify correlation ID was sent
    assert route.calls[0].request.headers["X-Correlation-ID"] == "test-corr-123"


@pytest.mark.asyncio
@respx.mock
async def test_successful_post_request(client: ResilientClient) -> None:
    """POST request sends body and propagates correlation ID."""
    route = respx.post("http://test-service:8000/entities").mock(
        return_value=httpx.Response(201, json={"created": 5})
    )
    response = await client.post(
        "/entities",
        correlation_id="corr-456",
        json={"entities": []},
    )
    assert response.status_code == 201
    assert route.calls[0].request.headers["X-Correlation-ID"] == "corr-456"


@pytest.mark.asyncio
@respx.mock
async def test_retries_on_server_error(client: ResilientClient) -> None:
    """Retries on 5xx responses."""
    route = respx.get("http://test-service:8000/data").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    response = await client.get("/data", correlation_id="corr-retry")
    assert response.status_code == 200
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_circuit_breaker_opens_after_failures(client: ResilientClient) -> None:
    """Circuit breaker opens after threshold consecutive 5xx responses."""
    respx.get("http://test-service:8000/fail").mock(
        return_value=httpx.Response(500)
    )

    # Each call does 3 retries (all 500), recording a failure each time
    # After enough calls the circuit should be open
    for _ in range(2):
        with pytest.raises((MaxRetriesExceededError, httpx.HTTPStatusError)):
            await client.get("/fail", correlation_id="corr-fail")

    # Circuit should now be open (6 failures > threshold of 5)
    with pytest.raises(CircuitBreakerOpenError):
        await client.get("/fail", correlation_id="corr-fail")


@pytest.mark.asyncio
@respx.mock
async def test_correlation_id_propagated_on_all_methods(client: ResilientClient) -> None:
    """All HTTP methods propagate X-Correlation-ID."""
    respx.put("http://test-service:8000/update").mock(
        return_value=httpx.Response(200)
    )
    respx.delete("http://test-service:8000/item/1").mock(
        return_value=httpx.Response(204)
    )

    await client.put("/update", correlation_id="corr-put", json={"key": "val"})
    await client.delete("/item/1", correlation_id="corr-delete")

    put_req = respx.calls[0].request
    del_req = respx.calls[1].request
    assert put_req.headers["X-Correlation-ID"] == "corr-put"
    assert del_req.headers["X-Correlation-ID"] == "corr-delete"


@pytest.mark.asyncio
async def test_context_manager(circuit_breaker: CircuitBreaker) -> None:
    """ResilientClient supports async context manager."""
    async with ResilientClient(
        base_url="http://test-service:8000",
        circuit_breaker=circuit_breaker,
    ) as client:
        assert client.base_url == "http://test-service:8000"


@pytest.mark.asyncio
async def test_base_url_trailing_slash_stripped() -> None:
    """Trailing slashes are stripped from base_url."""
    breaker = CircuitBreaker(service_name="test")
    client = ResilientClient(base_url="http://svc:8000/", circuit_breaker=breaker)
    assert client.base_url == "http://svc:8000"
    await client.close()
