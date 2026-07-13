---
inclusion: fileMatch
fileMatchPattern: "src/infrastructure/**"
---

# Infrastructure Adapter Implementation Checklist

When implementing any adapter in `src/infrastructure/`, follow this checklist:

## Required Structure

```python
"""<Name> adapter for <PortName>.

<Brief description of what external system this connects to.>
"""
from __future__ import annotations

from typing import Any

import structlog

from src.ports.<port_module> import <PortProtocol>
from src.domain.models.entities import <relevant models>

logger = structlog.get_logger(__name__)


class <AdapterName>:
    """<Description> implementing <PortProtocol>."""

    def __init__(self, <client params>) -> None:
        self._client = client
        logger.info("<adapter>.initialized", ...)

    async def <method>(self, ...) -> ...:
        """<Docstring>."""
        logger.info("<adapter>.<method>.start", ...)
        try:
            result = ...  # actual implementation
            logger.info("<adapter>.<method>.success", duration_ms=...)
            return result
        except Exception as e:
            logger.error("<adapter>.<method>.failed", error=str(e))
            raise
```

## Checklist Before Marking Complete

- [ ] Implements exactly one port protocol
- [ ] Has structured logging on every operation (start, success, failure)
- [ ] Includes duration_ms in success logs
- [ ] All methods are `async def`
- [ ] No imports from `src/domain/services/` (adapters don't know about services)
- [ ] Uses Pydantic models from `src/domain/models/` for inputs/outputs
- [ ] Has explicit timeout configuration
- [ ] Handles connection errors gracefully (logs + raises typed exception)
- [ ] Has an in-memory fake counterpart in tests for unit testing
- [ ] Passes `ruff check` and `mypy` strict

## Bedrock-Specific Adapters

For Bedrock-backed adapters (embeddings, LLM):
- Use `boto3` session management
- Set `region_name` explicitly
- Handle rate limiting (429) with retry
- Track token usage for cost monitoring
- Log model_id and token counts on every call

## Local Development Stubs

Every adapter should have a working in-memory fake at:
`tests/fakes/<adapter_name>_fake.py`

This allows unit tests to run without external services.
