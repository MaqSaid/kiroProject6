---
inclusion: fileMatch
fileMatchPattern: "tests/**"
---

# Testing Guide

## Property-Based Tests (Hypothesis)

Property tests validate formal correctness properties from the design document.

### File Naming
- `tests/property/test_prop_normalizers.py` — Properties 1
- `tests/property/test_prop_document_store.py` — Property 2
- `tests/property/test_prop_ingestion.py` — Property 3
- `tests/property/test_prop_chunkers.py` — Properties 4, 5, 6, 7, 8
- `tests/property/test_prop_deduplication.py` — Property 9
- `tests/property/test_prop_retrieval.py` — Properties 10, 11, 12
- `tests/property/test_prop_generation.py` — Properties 13, 14, 15
- `tests/property/test_prop_security.py` — Property 16
- `tests/property/test_prop_confidence.py` — Properties 17, 18
- `tests/property/test_prop_api.py` — Properties 19, 20

### Template

```python
"""Property tests for <module>.

# Feature: production-rag-pipeline-hybrid-search, Property N: <title>
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Custom strategies
reasonable_text = st.text(min_size=1, max_size=10000, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z")
))

@pytest.mark.property
@settings(max_examples=100)
@given(text=reasonable_text)
def test_property_name(text: str) -> None:
    """Property N: <description>."""
    # Arrange: set up with generated input
    # Act: run the code under test
    # Assert: verify the property holds for ALL generated inputs
    ...
```

### Key Hypothesis Strategies

- Text with controlled size: `st.text(min_size=1, max_size=N)`
- Floats in range: `st.floats(min_value=0.0, max_value=1.0, allow_nan=False)`
- Lists of fixed size: `st.lists(element_strategy, min_size=1, max_size=50)`
- UUIDs: `st.uuids()`
- Use `assume()` to skip invalid combinations (e.g., overlap >= chunk_size)

## Unit Tests

### Structure
Mirror `src/` directory in `tests/unit/`:
```
tests/unit/
├── domain/
│   ├── services/
│   ├── processing/
│   └── models/
├── api/
│   └── routes/
└── infrastructure/
```

### Mocking Ports
Create in-memory fakes rather than using `unittest.mock` for port implementations:

```python
class InMemoryVectorStore:
    """Fake VectorStorePort for unit tests."""
    def __init__(self):
        self._store: dict[str, EmbeddingRecord] = {}

    async def store(self, embeddings: list[EmbeddingRecord]) -> None:
        for e in embeddings:
            self._store[str(e.chunk_id)] = e

    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        # Simple cosine similarity over stored vectors
        ...
```

### API Tests
Use `httpx.AsyncClient` with FastAPI's `TestClient`:

```python
from httpx import AsyncClient, ASGITransport
from src.api import create_app

@pytest.mark.asyncio
async def test_endpoint():
    app = create_app(...)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/ask", json={...})
        assert response.status_code == 200
```

## Integration Tests

- Require external services (Neo4j, ChromaDB, Redis)
- Guard with `@pytest.mark.integration`
- Use docker-compose for service dependencies
- Each test cleans up its own data (use transaction rollback or delete after)

## Running Tests

```bash
# All unit + property tests (fast)
pytest tests/unit tests/property -m "not integration"

# Single property file
pytest tests/property/test_prop_chunkers.py -v

# With coverage
pytest --cov=src --cov-report=html tests/

# CI profile (more examples)
pytest --hypothesis-profile=ci tests/property/
```
