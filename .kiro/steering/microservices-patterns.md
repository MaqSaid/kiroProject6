---
inclusion: fileMatch
fileMatchPattern: services/**
---

# Microservices Patterns Guide

## ResilientClient Usage

All inter-service HTTP calls use `ResilientClient` from `libs/service-client/`. Never use raw httpx directly for service-to-service communication.

### Basic Usage

```python
from service_client import ResilientClient, CircuitBreaker, RetryPolicy

# Create per-service clients during lifespan startup
graph_client = ResilientClient(
    base_url="http://graph-service:8000",
    circuit_breaker=CircuitBreaker(
        failure_threshold=5,
        reset_timeout=30.0,
        half_open_max_calls=1,
    ),
    max_connections=100,
    max_keepalive_connections=20,
)

# Make requests with correlation ID propagation
response = await graph_client.request(
    method="POST",
    path="/entities",
    correlation_id=correlation_id,
    json={"entities": entities},
)
```

### Per-Service Client Configuration

| Target Service | Base URL (Docker Compose) | Timeout | Notes |
|---|---|---|---|
| Graph Service | `http://graph-service:8000` | 5s | Entity/relationship CRUD + traversal |
| Embedding Service | `http://embedding-service:8000` | 10s | Vector embedding generation |
| Query Service | `http://query-service:8000` | 30s | Full agent pipeline |
| Ingestion Service | `http://ingestion-service:8000` | 60s | Document processing |

## Circuit Breaker Configuration

Each service gets its own CircuitBreaker instance. Configuration is per-client, not global.

```python
circuit_breaker = CircuitBreaker(
    failure_threshold=5,      # Open after 5 consecutive failures
    reset_timeout=30.0,       # Stay open for 30 seconds
    half_open_max_calls=1,    # Allow 1 probe request in half-open state
)
```

State transitions:
- **CLOSED → OPEN**: After 5 consecutive failures (timeouts, 5xx responses, connection errors)
- **OPEN → HALF_OPEN**: After 30 seconds elapse
- **HALF_OPEN → CLOSED**: Probe request succeeds
- **HALF_OPEN → OPEN**: Probe request fails

When circuit is OPEN, `ResilientClient.request()` raises `CircuitOpenError` immediately without making the HTTP call.

## Retry Policy

Retries are built into `ResilientClient` via `RetryPolicy`:

```python
retry_policy = RetryPolicy(
    max_attempts=3,       # Total attempts (1 initial + 2 retries)
    base_delay=1.0,       # 1 second initial delay
    multiplier=2.0,       # Exponential: 1s, 2s, 4s
    max_jitter=0.5,       # Random jitter up to 500ms added to each delay
)
```

Retryable conditions:
- HTTP 502, 503, 504 responses
- Connection timeout / refused
- `asyncio.TimeoutError`

Non-retryable (fail immediately):
- HTTP 400, 401, 403, 404, 422 (client errors)
- `CircuitOpenError` (circuit is open)
- Request body validation errors

## Correlation ID Propagation

Every request entering the system through the API Gateway receives an `X-Correlation-ID` header (UUID v4). This ID must be passed through all inter-service calls.

```python
# Extracting correlation ID from incoming request
correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

# Bind to structlog context for all log entries in this request
structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

# Pass to downstream service calls
response = await embedding_client.request(
    method="POST",
    path="/embed",
    correlation_id=correlation_id,
    json={"text": query_text},
)
```

The `ResilientClient` automatically injects `X-Correlation-ID` into all outgoing request headers.

## Health Endpoint Pattern

Every service exposes three health endpoints:

```python
@router.get("/health")
async def health_check():
    """Connectivity check to primary dependency."""
    # e.g., Graph Service checks Neo4j connectivity
    await check_neo4j_connection()
    return {"status": "healthy"}

@router.get("/health/ready")
async def readiness_check():
    """Service is ready to accept traffic."""
    # Check connection pools, indexes, caches are initialized
    await check_pool_established()
    await check_indexes_exist()
    return {"status": "ready"}

@router.get("/health/live")
async def liveness_check():
    """Process is running."""
    # Always returns 200 — just confirms the process is alive
    return {"status": "alive"}
```

Docker Compose and load balancers use `/health/live` for liveness and `/health/ready` for readiness.

## Graceful Degradation

When a non-critical service is unavailable:

```python
async def hybrid_search(self, query: str, correlation_id: str) -> list[ScoredChunk]:
    results = {}
    available_methods = []

    # Execute all methods in parallel, catch failures
    tasks = {
        "dense": self._dense_search(query, correlation_id),
        "sparse": self._sparse_search(query),
        "graph": self._graph_search(query, correlation_id),
    }

    for method, task in tasks.items():
        try:
            results[method] = await asyncio.wait_for(task, timeout=5.0)
            available_methods.append(method)
        except (CircuitOpenError, asyncio.TimeoutError, httpx.HTTPError) as e:
            logger.warning(
                "search_method_unavailable",
                method=method,
                error=str(e),
                correlation_id=correlation_id,
            )

    if not available_methods:
        raise AllRetrievalMethodsUnavailableError()

    # Renormalize weights for available methods
    weights = self._renormalize_weights(available_methods)
    return self._rrf_fusion(results, weights)
```

Rules:
- **Embedding Service unavailable** during ingestion: return 503 (critical dependency)
- **Graph Service unavailable** during ingestion: complete without graph storage (degraded)
- **Graph Service unavailable** during query: renormalize RRF weights, proceed with dense + sparse
- **Embedding Service unavailable** during query: renormalize RRF weights, proceed with sparse + graph (if vectors cached)

## Structured Logging

All services use structlog with consistent fields:

```python
import structlog

logger = structlog.get_logger()

# Always include these fields via contextvars
structlog.contextvars.bind_contextvars(
    service_name="graph-service",
    correlation_id=correlation_id,
)

# Log with operation context
logger.info("entities_stored", count=len(entities), document_id=doc_id)
logger.warning("circuit_open", target_service="embedding-service")
logger.error("neo4j_timeout", operation="traverse", query=query[:100])
```

## Service Lifespan Pattern

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize clients, pools, indexes
    app.state.graph_client = await create_graph_client()
    app.state.embedding_client = await create_embedding_client()
    yield
    # Shutdown: close connections gracefully
    await app.state.graph_client.close()
    await app.state.embedding_client.close()

app = FastAPI(lifespan=lifespan)
```
