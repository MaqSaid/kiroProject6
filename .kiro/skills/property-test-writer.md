---
inclusion: manual
---

# Skill: Property-Based Test Writer

## Purpose
Write Hypothesis property-based tests that validate the 20 correctness properties defined in the design document.

## Process

1. **Identify the property** — Read the property statement from the design doc (Property N)
2. **Determine inputs** — What are the "for any" variables? These become Hypothesis strategies
3. **Determine invariant** — What must ALWAYS hold? This is your assertion
4. **Build strategies** — Use composite strategies for domain objects
5. **Write the test** — Follow the template below

## Template

```python
"""Property tests for <module>.

# Feature: production-rag-pipeline-hybrid-search, Property N: <title>
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from uuid import uuid4

# Import the code under test
from src.domain.processing.<module> import <ClassUnderTest>
from src.domain.models.entities import <DomainModel>


# --- Strategies ---

@st.composite
def domain_object_strategy(draw):
    """Generate valid <DomainModel> instances."""
    return <DomainModel>(
        id=uuid4(),
        field=draw(st.text(min_size=1, max_size=1000)),
        ...
    )


# --- Property Tests ---

@pytest.mark.property
@settings(max_examples=100)
@given(obj=domain_object_strategy())
def test_property_N_description(obj):
    """Property N: <formal statement>.
    
    Validates: Requirements X.Y
    """
    # Arrange
    sut = <ClassUnderTest>(...)
    
    # Act
    result = sut.operation(obj)
    
    # Assert — the property that must hold for ALL valid inputs
    assert <invariant_holds>(result)
```

## Common Strategies for This Project

```python
# Chunk text
chunk_text = st.text(min_size=10, max_size=5000, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z")
))

# RRF weights (must sum to 1.0)
@st.composite  
def rrf_weights(draw):
    dense = draw(st.floats(min_value=0.01, max_value=0.98))
    sparse = draw(st.floats(min_value=0.01, max_value=min(0.98, 1.0 - dense - 0.01)))
    graph = 1.0 - dense - sparse
    assume(graph > 0.0)
    return RRFWeights(dense=dense, sparse=sparse, graph=graph)

# Scored chunks for retrieval tests
@st.composite
def scored_chunk_list(draw, min_size=1, max_size=20):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    chunks = []
    for i in range(n):
        chunks.append(ScoredChunk(
            chunk=Chunk(id=uuid4(), document_id=uuid4(), index=i, ...),
            score=draw(st.floats(min_value=0.0, max_value=1.0)),
            retrieval_method=draw(st.sampled_from(["dense", "sparse", "graph"])),
        ))
    return chunks

# Confidence dimensions
confidence_float = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
```

## Property Checklist

Before submitting a property test, verify:
- [ ] Uses `@pytest.mark.property` marker
- [ ] Has `@settings(max_examples=100)` minimum
- [ ] Has the feature/property comment tag
- [ ] Tests the UNIVERSAL property (holds for ALL valid inputs)
- [ ] Uses `assume()` to filter invalid input combinations
- [ ] Does NOT make external API calls (uses fakes/mocks)
- [ ] Documents which requirement it validates
