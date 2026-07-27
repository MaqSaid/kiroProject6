---
inclusion: manual
---

# Skill: Contract Test Writer

## Purpose
Write Pydantic schema contract tests between services, validating that client expectations match server response schemas. Uses Hypothesis for property-based contract testing to ensure inter-service compatibility.

## Process

1. **Identify contract boundary** — Which two services communicate? What models does each use?
2. **Import both schemas** — Client-side model (what the caller expects) and server-side model (what the server returns)
3. **Generate valid data** — Use Hypothesis strategies to produce random valid server responses
4. **Validate client compatibility** — Verify client model can parse server model output
5. **Test edge cases** — Optional fields, empty lists, boundary values

## Template

### Basic Contract Test

```python
"""Contract tests between <ClientService> and <ServerService>.

Validates that <ClientService>'s expected response schema is compatible
with <ServerService>'s actual response schema.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

# Shared domain models used by both services
from domain_models import ServerResponseModel, ClientExpectedModel
```

### Hypothesis Strategy for Server Response

```python
@st.composite
def server_response_strategy(draw):
    """Generate valid server response data."""
    return ServerResponseModel(
        id=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "N")))),
        score=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        text=draw(st.text(min_size=0, max_size=5000)),
        metadata=draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.text(max_size=100),
            max_size=5,
        )),
    )
```

### Contract Property Test

```python
@pytest.mark.contract
@settings(max_examples=100)
@given(response=server_response_strategy())
def test_client_can_parse_server_response(response: ServerResponseModel):
    """Contract: Client model accepts all valid server responses.

    For any valid server response, the client-side model must be able
    to parse it without ValidationError.
    """
    # Serialize server response as it would appear on the wire
    wire_data = response.model_dump(mode="json")

    # Client must be able to parse the wire format
    parsed = ClientExpectedModel.model_validate(wire_data)

    # Verify key fields are preserved
    assert parsed.id == response.id
    assert parsed.score == response.score
```

### Bidirectional Contract Test

```python
@pytest.mark.contract
@settings(max_examples=100)
@given(request=client_request_strategy())
def test_server_can_parse_client_request(request: ClientRequestModel):
    """Contract: Server model accepts all valid client requests.

    For any valid client request, the server-side model must be able
    to parse it without ValidationError.
    """
    wire_data = request.model_dump(mode="json")
    parsed = ServerRequestModel.model_validate(wire_data)
    assert parsed.query == request.query
```

### Full Contract Test Example (Query Service - Embedding Service)

```python
"""Contract: Query Service client / Embedding Service server."""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from domain_models import EmbedResponse, EmbedBatchResponse


@st.composite
def embed_response_strategy(draw):
    """Generate valid EmbedResponse as Embedding Service would return."""
    dim = 1024
    return EmbedResponse(
        vector=draw(st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=dim, max_size=dim,
        )),
        tokens_used=draw(st.integers(min_value=1, max_value=8192)),
    )


@pytest.mark.contract
@settings(max_examples=50)
@given(response=embed_response_strategy())
def test_query_service_parses_embed_response(response: EmbedResponse):
    """Query Service can parse any valid Embedding Service response."""
    wire = response.model_dump(mode="json")
    parsed = EmbedResponse.model_validate(wire)
    assert len(parsed.vector) == 1024
    assert parsed.tokens_used >= 1
```

## Checklist

Before completing a contract test:
- [ ] Both client and server models imported from shared `domain_models`
- [ ] Hypothesis strategy generates ALL valid server/client data shapes
- [ ] Uses `model_dump(mode="json")` to simulate wire serialization
- [ ] Uses `model_validate()` to parse (not direct construction)
- [ ] Key fields asserted for preservation after round-trip
- [ ] Marked with `@pytest.mark.contract`
- [ ] Tests both directions if applicable (request and response)
- [ ] Optional fields tested (None values, missing keys)
- [ ] Empty collections tested (empty lists, empty dicts)
- [ ] Boundary values included in strategies (min/max lengths, 0.0/1.0)
