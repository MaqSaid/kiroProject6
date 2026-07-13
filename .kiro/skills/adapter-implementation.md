---
inclusion: manual
---

# Skill: Infrastructure Adapter Implementation

## Purpose
Implement adapters that connect domain ports to external infrastructure (databases, APIs, caches).

## Process

1. **Identify the port** — Which Protocol class from `src/ports/` does this adapter implement?
2. **Create adapter file** — In `src/infrastructure/<adapter_name>.py`
3. **Implement all methods** — Every method from the Protocol must be implemented
4. **Add circuit breaker** — Wrap external calls with CircuitBreaker
5. **Add retry logic** — Use tenacity for transient failures
6. **Add structured logging** — Log operation, duration, success/failure
7. **Add timeout** — Explicit timeout on every external call
8. **Create in-memory fake** — For unit testing in `tests/unit/fakes/`

## Adapter Template

```python
"""<Name> adapter implementing <Port>."""
from __future__ import annotations

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from src.domain.models.entities import <Models>
from src.infrastructure.resilience import CircuitBreaker

logger = structlog.get_logger(__name__)


class <AdapterName>:
    """<Description>."""

    def __init__(
        self,
        client: <ClientType>,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = client
        self._cb = circuit_breaker or CircuitBreaker()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=10),
    )
    async def <port_method>(self, ...) -> ...:
        """<Docstring>."""
        async with self._cb:
            logger.info("<operation>.start", ...)
            try:
                result = await self._client.<method>(...)
                logger.info("<operation>.success", duration_ms=...)
                return result
            except <TransientError> as e:
                logger.warning("<operation>.retry", error=str(e))
                raise
            except <PermanentError> as e:
                logger.error("<operation>.failed", error=str(e))
                raise <DomainException>(str(e)) from e
```

## In-Memory Fake Template

```python
"""In-memory fake for <Port> used in unit tests."""
from src.domain.models.entities import <Models>


class InMemory<Name>:
    """Test fake implementing <Port> protocol."""

    def __init__(self) -> None:
        self._store: dict[str, <Model>] = {}

    async def store(self, items: list[<Model>]) -> None:
        for item in items:
            self._store[str(item.id)] = item

    async def search(self, ...) -> list[<Result>]:
        # Simple linear scan for testing
        ...

    def reset(self) -> None:
        """Clear all stored data (test utility)."""
        self._store.clear()
```

## Timeout Guidelines

| Adapter | Timeout |
|---------|---------|
| Embedding API | 10s |
| LLM Generation | 30s |
| Vector Store | 5s |
| Graph Store | 5s |
| Cache (Redis) | 2s |
| Document Store | 10s |
| Reranker (local) | 5s |
