"""Property tests for Embedding Service.

# Feature: legislation-rag-platform, Property 29: Embedding cache round-trip
# Feature: legislation-rag-platform, Property 30: Token usage tracking in responses
"""

import sys
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.infrastructure.embedding_cache import EmbeddingCache
from src.config import Settings
from tests.fakes.fake_bedrock import FakeBedrockAdapter


# --- Strategies ---

# Text strategy: random strings of length 1-5000 (valid embedding inputs)
valid_text_strategy = st.text(
    min_size=1,
    max_size=5000,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z", "S"),
        blacklist_characters="\x00",
    ),
)

# Batch strategy: lists of 1-20 text strings
valid_batch_strategy = st.lists(
    valid_text_strategy,
    min_size=1,
    max_size=20,
)


# --- Test App Factory ---

def create_test_app_with_fake(fake_adapter: FakeBedrockAdapter) -> tuple[FastAPI, TestClient]:
    """Create a test app using the provided FakeBedrockAdapter.

    Returns the app and a TestClient with lifespan managed.
    """
    test_settings = Settings()
    test_settings.max_input_tokens = 8192
    cache = EmbeddingCache()
    cache.initialize()

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = test_settings
        app.state.embedding_cache = cache
        app.state.bedrock_adapter = fake_adapter
        yield

    app = FastAPI(title="Embedding Service Test", lifespan=test_lifespan)

    from src.api.routes import router
    from src.api.health import health_router
    from src.api.metrics import metrics_router

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    client = TestClient(app, raise_server_exceptions=False)
    return app, client


# --- Property 29: Embedding cache round-trip ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(text=valid_text_strategy)
def test_property_29_single_text_cache_round_trip(text: str):
    """Property 29: Embedding cache round-trip (single text).

    First call computes hash and calls Bedrock; second call with same text
    returns identical vector from cache without Bedrock call.

    **Validates: Requirements 15.2, 15.3, 15.4**
    """
    # Filter out texts that would exceed token budget (len/4 > 8192 -> len > 32768)
    assume(len(text) <= 32768)

    fake_adapter = FakeBedrockAdapter(dimensions=1024)
    app, client = create_test_app_with_fake(fake_adapter)

    with client:
        # First call - should call Bedrock (cache miss)
        response1 = client.post("/embed", json={"text": text})
        assert response1.status_code == 200
        data1 = response1.json()
        vector1 = data1["vector"]

        # Record call count after first call
        calls_after_first = fake_adapter.embed_text_call_count
        assert calls_after_first == 1, "First call should invoke Bedrock exactly once"

        # Second call with same text - should NOT call Bedrock (cache hit)
        response2 = client.post("/embed", json={"text": text})
        assert response2.status_code == 200
        data2 = response2.json()
        vector2 = data2["vector"]

        calls_after_second = fake_adapter.embed_text_call_count
        assert calls_after_second == 1, "Second call should use cache, not Bedrock"

        # Vectors must be identical
        assert vector1 == vector2, "Cached vector must match original"


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(texts=valid_batch_strategy)
def test_property_29_batch_cache_checks_each_item(texts: list[str]):
    """Property 29: Embedding cache round-trip (batch).

    Batch requests check each item individually. If texts [A, B, A] are
    submitted, Bedrock is called only for unique uncached texts.

    **Validates: Requirements 15.2, 15.3, 15.4**
    """
    # Filter out texts that would exceed token budget
    assume(all(len(t) <= 32768 for t in texts))

    fake_adapter = FakeBedrockAdapter(dimensions=1024)
    app, client = create_test_app_with_fake(fake_adapter)

    with client:
        # First batch call
        response1 = client.post("/embed/batch", json={"texts": texts})
        assert response1.status_code == 200
        data1 = response1.json()
        vectors1 = data1["vectors"]
        assert len(vectors1) == len(texts)

        # Reset adapter counts to measure second call
        fake_adapter.reset()

        # Second batch call with same texts - all should be cached
        response2 = client.post("/embed/batch", json={"texts": texts})
        assert response2.status_code == 200
        data2 = response2.json()
        vectors2 = data2["vectors"]

        # No Bedrock calls on second request (all cached)
        assert fake_adapter.embed_text_call_count == 0, "All items should be cached"
        assert fake_adapter.embed_batch_call_count == 0, "No batch call needed when cached"

        # Vectors should be identical
        assert vectors1 == vectors2, "Cached batch vectors must match originals"


# --- Property 30: Token usage tracking in responses ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(text=valid_text_strategy)
def test_property_30_single_embed_tokens_used_non_negative(text: str):
    """Property 30: Token usage tracking in responses (single).

    For any valid text, the response from POST /embed includes
    tokens_used >= 0 (non-negative integer).

    **Validates: Requirements 15.5**
    """
    assume(len(text) <= 32768)

    fake_adapter = FakeBedrockAdapter(dimensions=1024)
    _, client = create_test_app_with_fake(fake_adapter)

    with client:
        response = client.post("/embed", json={"text": text})
        assert response.status_code == 200
        data = response.json()

        # tokens_used must be present and non-negative integer
        assert "tokens_used" in data
        assert isinstance(data["tokens_used"], int)
        assert data["tokens_used"] >= 0

        # For non-empty text, tokens_used should be at least 1
        if len(text.strip()) > 0:
            assert data["tokens_used"] >= 1


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(texts=valid_batch_strategy)
def test_property_30_batch_embed_tokens_used_non_negative(texts: list[str]):
    """Property 30: Token usage tracking in responses (batch).

    For any valid batch of texts, the response from POST /embed/batch
    includes tokens_used >= 0 (non-negative integer).

    **Validates: Requirements 15.5**
    """
    assume(all(len(t) <= 32768 for t in texts))

    fake_adapter = FakeBedrockAdapter(dimensions=1024)
    _, client = create_test_app_with_fake(fake_adapter)

    with client:
        response = client.post("/embed/batch", json={"texts": texts})
        assert response.status_code == 200
        data = response.json()

        # tokens_used must be present and non-negative integer
        assert "tokens_used" in data
        assert isinstance(data["tokens_used"], int)
        assert data["tokens_used"] >= 0

        # For a batch with at least one non-empty text, tokens_used >= 1
        if any(len(t.strip()) > 0 for t in texts):
            assert data["tokens_used"] >= 1


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(
    base_char=st.characters(whitelist_categories=("L",)),
    length=st.integers(min_value=32773, max_value=50000),
)
def test_property_30_token_budget_enforcement(base_char: str, length: int):
    """Property 30: Token budget enforcement.

    For any text where estimated tokens (len // 4) exceeds max_input_tokens (8192),
    the service should return HTTP 422 indicating token budget exceeded.
    This requires len(text) >= 32773 since 32773 // 4 = 8193 > 8192.

    **Validates: Requirements 15.5**
    """
    # Construct a text that exceeds the token budget
    text = base_char * length

    fake_adapter = FakeBedrockAdapter(dimensions=1024)
    _, client = create_test_app_with_fake(fake_adapter)

    with client:
        response = client.post("/embed", json={"text": text})
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "token budget" in data["message"].lower() or "token budget" in data["message"]

        # Bedrock should never have been called
        assert fake_adapter.embed_text_call_count == 0
