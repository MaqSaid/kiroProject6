"""Unit tests for embedding API routes."""

import sys
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.infrastructure.embedding_cache import EmbeddingCache
from src.infrastructure.bedrock_adapter import BedrockEmbeddingAdapter, EmbeddingUnavailableError
from src.config import Settings


def create_test_app(settings, cache, adapter):
    """Create a test app with a no-op lifespan that uses provided dependencies."""

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.settings = settings
        app.state.embedding_cache = cache
        app.state.bedrock_adapter = adapter
        yield

    app = FastAPI(title="Embedding Service Test", lifespan=test_lifespan)

    from src.api.routes import router
    from src.api.health import health_router
    from src.api.metrics import metrics_router
    from src.middleware.error_handler import ErrorHandlerMiddleware
    from src.middleware.correlation_id import CorrelationIdMiddleware

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)

    return app


@pytest.fixture
def mock_settings():
    settings = Settings()
    settings.max_input_tokens = 8192
    settings.embedding_dimensions = 1024
    return settings


@pytest.fixture
def mock_cache():
    cache = EmbeddingCache()
    cache.initialize()
    return cache


@pytest.fixture
def mock_adapter(mock_settings):
    adapter = BedrockEmbeddingAdapter(mock_settings)
    return adapter


@pytest.fixture
def client(mock_settings, mock_cache, mock_adapter):
    """Create a test client with mocked dependencies via test lifespan."""
    app = create_test_app(mock_settings, mock_cache, mock_adapter)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


class TestEmbedEndpoint:
    """Tests for POST /embed."""

    def test_embed_returns_cached_result(self, client, mock_cache):
        mock_cache.put("cached text", [0.1, 0.2, 0.3], 5)

        response = client.post("/embed", json={"text": "cached text"})
        assert response.status_code == 200
        data = response.json()
        assert data["vector"] == [0.1, 0.2, 0.3]
        assert data["tokens_used"] == 5

    def test_embed_calls_bedrock_on_cache_miss(self, client, mock_adapter):
        async def mock_embed(text):
            return [0.5, 0.6], 10

        mock_adapter.embed_text = mock_embed

        response = client.post("/embed", json={"text": "new text"})
        assert response.status_code == 200
        data = response.json()
        assert data["vector"] == [0.5, 0.6]
        assert data["tokens_used"] == 10

    def test_embed_rejects_text_exceeding_token_budget(self, client):
        # Need estimated tokens > 8192. Estimate = len(text) // 4.
        # 8193 * 4 = 32772 chars gives estimate of 8193 > 8192.
        long_text = "x" * 32772

        response = client.post("/embed", json={"text": long_text})
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "token budget" in data["message"]

    def test_embed_returns_503_on_bedrock_unavailable(self, client, mock_adapter):
        async def mock_embed(text):
            raise EmbeddingUnavailableError("Bedrock down")

        mock_adapter.embed_text = mock_embed

        response = client.post("/embed", json={"text": "hello"})
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "BEDROCK_UNAVAILABLE"

    def test_embed_caches_result_after_bedrock_call(self, client, mock_cache, mock_adapter):
        async def mock_embed(text):
            return [0.9, 0.8], 7

        mock_adapter.embed_text = mock_embed

        response = client.post("/embed", json={"text": "cache me"})
        assert response.status_code == 200

        # Verify it was cached
        entry = mock_cache.get("cache me")
        assert entry is not None
        assert entry.vector == [0.9, 0.8]

    def test_embed_tokens_used_non_negative(self, client, mock_adapter):
        async def mock_embed(text):
            return [0.1], 0

        mock_adapter.embed_text = mock_embed

        response = client.post("/embed", json={"text": "x"})
        assert response.status_code == 200
        data = response.json()
        assert data["tokens_used"] >= 0


class TestEmbedBatchEndpoint:
    """Tests for POST /embed/batch."""

    def test_batch_returns_all_cached(self, client, mock_cache):
        mock_cache.put("text1", [0.1], 3)
        mock_cache.put("text2", [0.2], 4)

        response = client.post("/embed/batch", json={"texts": ["text1", "text2"]})
        assert response.status_code == 200
        data = response.json()
        assert data["vectors"] == [[0.1], [0.2]]
        assert data["tokens_used"] == 7

    def test_batch_calls_bedrock_only_for_uncached(self, client, mock_cache, mock_adapter):
        mock_cache.put("cached", [0.1], 3)

        call_count = 0

        async def mock_embed_batch(texts):
            nonlocal call_count
            call_count += 1
            assert texts == ["new"]
            return [[0.5]], 5

        mock_adapter.embed_batch = mock_embed_batch

        response = client.post("/embed/batch", json={"texts": ["cached", "new"]})
        assert response.status_code == 200
        data = response.json()
        assert data["vectors"] == [[0.1], [0.5]]
        assert call_count == 1

    def test_batch_rejects_oversized_text(self, client, mock_adapter):
        # 8193 * 4 = 32772 chars gives estimate of 8193 > 8192
        long_text = "x" * 32772

        async def mock_embed_batch(texts):
            return [[0.1]] * len(texts), 5

        mock_adapter.embed_batch = mock_embed_batch

        response = client.post("/embed/batch", json={"texts": ["short", long_text]})
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "index 1" in data["message"]

    def test_batch_returns_503_on_bedrock_unavailable(self, client, mock_adapter):
        async def mock_embed_batch(texts):
            raise EmbeddingUnavailableError("Bedrock down")

        mock_adapter.embed_batch = mock_embed_batch

        response = client.post("/embed/batch", json={"texts": ["hello"]})
        assert response.status_code == 503

    def test_batch_preserves_original_order(self, client, mock_cache, mock_adapter):
        mock_cache.put("b", [0.2], 2)

        async def mock_embed_batch(texts):
            return [[0.1], [0.3]], 6

        mock_adapter.embed_batch = mock_embed_batch

        response = client.post("/embed/batch", json={"texts": ["a", "b", "c"]})
        assert response.status_code == 200
        data = response.json()
        assert data["vectors"] == [[0.1], [0.2], [0.3]]


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_liveness_always_200(self, client):
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_health_returns_503_when_bedrock_unavailable(self, client, mock_adapter):
        async def mock_check():
            return False

        mock_adapter.check_connectivity = mock_check

        response = client.get("/health")
        assert response.status_code == 503

    def test_health_returns_200_when_bedrock_available(self, client, mock_adapter):
        async def mock_check():
            return True

        mock_adapter.check_connectivity = mock_check

        response = client.get("/health")
        assert response.status_code == 200

    def test_readiness_checks_cache_and_bedrock(self, client, mock_adapter):
        async def mock_check():
            return True

        mock_adapter.check_connectivity = mock_check

        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["cache"] == "ready"
        assert data["checks"]["bedrock_credentials"] == "valid"


class TestCorrelationId:
    """Tests for X-Correlation-ID propagation."""

    def test_correlation_id_returned_in_response(self, client, mock_cache):
        mock_cache.put("test", [0.1], 1)
        response = client.post(
            "/embed",
            json={"text": "test"},
            headers={"X-Correlation-ID": "test-corr-123"},
        )
        assert response.headers.get("x-correlation-id") == "test-corr-123"

    def test_correlation_id_generated_when_missing(self, client, mock_cache):
        mock_cache.put("test", [0.1], 1)
        response = client.post("/embed", json={"text": "test"})
        assert "x-correlation-id" in response.headers


class TestMetrics:
    """Tests for /metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "text/plain" in content_type
