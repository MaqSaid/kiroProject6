---
inclusion: fileMatch
fileMatchPattern: "src/infrastructure/**"
---

# Infrastructure Adapter Guide

## Adapter Implementation Pattern

Every adapter implements exactly one port protocol and follows this structure:

```python
"""<StoreName> adapter for <PortName>."""
import structlog
from src.ports.<port_module> import <PortProtocol>
from src.infrastructure.resilience import CircuitBreaker, RetryConfig, retry_with_backoff

logger = structlog.get_logger(__name__)


class <AdapterName>:
    """Production adapter implementing <PortProtocol>."""

    def __init__(self, client: <ExternalClient>, circuit_breaker: CircuitBreaker):
        self._client = client
        self._cb = circuit_breaker

    async def <port_method>(self, ...) -> ...:
        async with self._cb:
            return await retry_with_backoff(
                self._do_operation, ...
            )
```

## Circuit Breaker Integration

- Every external call (LLM, embedding, vector store, graph store, cache) goes through a circuit breaker
- Circuit breaker states: CLOSED → OPEN → HALF_OPEN → CLOSED
- Configuration: `failure_threshold=5`, `recovery_timeout=30s`, `success_threshold=2`
- When circuit opens, emit a structured log event with `level=warning`

## Retry Logic

- Use `tenacity` decorators or the shared `retry_with_backoff` utility
- Config: `max_retries=3`, `base_delay=0.5s`, `max_delay=10s`, `jitter=True`
- Only retry on transient errors (network timeouts, 429, 5xx)
- Never retry on 4xx client errors or validation failures

## Adapter Responsibilities

| Adapter | Port | External Dependency |
|---------|------|---------------------|
| `ChromaDBVectorStore` | `VectorStorePort` | ChromaDB client |
| `BM25SparseIndex` | `SparseIndexPort` | rank_bm25 (in-memory) |
| `Neo4jGraphStore` | `GraphStorePort` | Neo4j driver |
| `OpenAIEmbedding` | `EmbeddingPort` | OpenAI API (httpx) |
| `OpenAILLM` | `LLMPort` | OpenAI API (httpx) |
| `AnthropicLLM` | `LLMPort` | Anthropic API (httpx) |
| `CrossEncoderReranker` | `RerankerPort` | sentence-transformers (local) |
| `RedisCache` | `CachePort` | Redis client |
| `LocalDocumentStore` | `DocumentStorePort` | Filesystem |

## Key Rules

1. **Never import domain services** — adapters only know about port interfaces and domain models
2. **Structured logging** — log every external call with: operation, duration_ms, success/failure, correlation_id
3. **Timeouts** — set explicit timeouts on all client calls (embedding: 10s, LLM: 30s, vector: 5s, graph: 5s, cache: 2s)
4. **Connection pooling** — reuse clients across requests, don't create per-request connections
5. **Graceful degradation** — if adapter fails, raise a typed exception that the service layer can handle for fallback
