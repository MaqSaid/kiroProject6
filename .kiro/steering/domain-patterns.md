---
inclusion: fileMatch
fileMatchPattern: "src/domain/**"
---

# Domain Layer Patterns

## Service Patterns

Every domain service follows this structure:

```python
class SomeService:
    def __init__(self, port1: Port1Protocol, port2: Port2Protocol, ...):
        self._port1 = port1
        self._port2 = port2

    async def operation(self, input: DomainModel, correlation_id: str) -> DomainResult:
        # 1. Validate input
        # 2. Execute domain logic
        # 3. Coordinate port calls
        # 4. Emit events if needed
        # 5. Return domain result
        ...
```

## Key Rules

1. **No infrastructure imports** — only import from `src/ports/`, `src/domain/models/`, and stdlib
2. **All I/O is async** — every method that touches a port must be `async def`
3. **Correlation ID threading** — pass `correlation_id: str` through all service methods
4. **Domain events** — emit via `EventBus.publish()` after successful operations
5. **Pydantic models only** — no plain dicts for structured data crossing service boundaries
6. **Explicit error types** — raise domain exceptions, not generic `ValueError`/`RuntimeError`

## Ingestion Pipeline Order

`validate → normalize → chunk → extract_entities → deduplicate → index → emit_event`

## Retrieval Pipeline Order

`embed_query → parallel(dense, sparse, graph) → fuse(RRF) → rerank → attach_metadata`

## Generation Pipeline Order

`check_budget → generate(context+query) → parse_citations → verify_citations → compute_confidence → maybe_fallback`

## Confidence Calculation

```
composite = (retrieval_weight * retrieval_confidence) 
          + (citation_weight * citation_coverage)
          + (completeness_weight * answer_completeness)
```

Default weights: retrieval=0.35, citation=0.4, completeness=0.25

## RRF Formula

```
score(d) = Σ (weight_i / (k + rank_i(d)))
```
- k = 60 (smoothing constant)
- Default weights: dense=0.5, sparse=0.2, graph=0.3
- All weights must sum to 1.0
