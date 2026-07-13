---
inclusion: manual
---

# Skill: Domain Service Implementation

## Purpose
Implement domain services that orchestrate business logic using port interfaces.

## Architecture Rules

1. Domain services live in `src/domain/services/`
2. They ONLY import from: `src/domain/models/`, `src/domain/events/`, `src/ports/`
3. They NEVER import from: `src/infrastructure/`, `src/api/`, external libraries directly
4. All I/O operations are async
5. Correlation ID flows through every method

## Service Template

```python
"""<ServiceName> — <one-line description>."""
from __future__ import annotations

import structlog

from src.domain.events import EventBus
from src.domain.models.entities import <Models>
from src.domain.models.enums import <Enums>
from src.ports.<port> import <PortProtocol>

logger = structlog.get_logger(__name__)


class <ServiceName>:
    """<Description of what this service orchestrates>."""

    def __init__(
        self,
        port1: <Port1Protocol>,
        port2: <Port2Protocol>,
        event_bus: EventBus,
        config_param: <type> = <default>,
    ) -> None:
        self._port1 = port1
        self._port2 = port2
        self._event_bus = event_bus
        self._config = config_param

    async def <primary_operation>(
        self,
        input_data: <InputModel>,
        correlation_id: str,
    ) -> <OutputModel>:
        """<Docstring explaining the orchestration flow>."""
        log = logger.bind(correlation_id=correlation_id)
        log.info("<service>.<operation>.start", input_id=str(input_data.id))

        try:
            # Step 1: Validate
            self._validate(input_data)

            # Step 2: Process via ports
            intermediate = await self._port1.operation(input_data)

            # Step 3: Further processing
            result = await self._port2.operation(intermediate)

            # Step 4: Emit domain event
            event = <DomainEvent>(...)
            await self._event_bus.publish(event)

            log.info("<service>.<operation>.success", result_id=str(result.id))
            return result

        except <DomainError> as e:
            log.warning("<service>.<operation>.domain_error", error=str(e))
            raise
        except Exception as e:
            log.error("<service>.<operation>.unexpected_error", error=str(e))
            raise <ServiceError>(str(e)) from e

    def _validate(self, input_data: <InputModel>) -> None:
        """Validate input before processing."""
        ...
```

## Service Inventory

| Service | Responsibilities | Key Ports Used |
|---------|-----------------|----------------|
| `IngestionService` | Validate → normalize → chunk → extract → index → emit | DocumentStore, EventBus, all indexing ports |
| `IndexingService` | Deduplicate → write vector/sparse/graph transactionally | VectorStore, SparseIndex, GraphStore, Embedding |
| `RetrievalService` | Parallel search → RRF fusion → rerank | VectorStore, SparseIndex, GraphStore, Reranker, Cache |
| `GenerationService` | LLM generation → citation parsing → verification | LLM (primary + fallback), CitationVerifier |
| `ConfidenceService` | Score computation → fallback decision | None (pure computation) |
| `SecurityService` | Input scanning → PII detection → validation | None (pattern matching) |

## Error Hierarchy

```python
class DomainError(Exception): ...
class ValidationError(DomainError): ...
class UnsupportedFormatError(ValidationError): ...
class DuplicateDocumentError(DomainError): ...
class InsufficientContextError(DomainError): ...
class TokenBudgetExceededError(DomainError): ...
class PromptInjectionDetectedError(DomainError): ...
class ExternalServiceError(DomainError): ...
class RetrievalTimeoutError(ExternalServiceError): ...
```
