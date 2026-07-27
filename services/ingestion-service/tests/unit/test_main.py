"""Unit tests for the Ingestion Service main module and lifespan."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    """Create a fresh FastAPI app instance for testing."""
    from src.main import create_app

    return create_app()


@pytest.fixture
async def client(app):
    """Create an async test client with mocked lifespan dependencies."""
    from src.domain.processing.chunker_registry import ChunkerRegistry
    from src.domain.processing.fixed_size_chunker import FixedSizeChunker
    from src.domain.processing.legal_hierarchical_chunker import LegalHierarchicalChunker
    from src.domain.processing.recursive_chunker import RecursiveChunker
    from src.infrastructure.bm25_index import BM25Index

    # Set up state manually (bypass lifespan for unit tests)
    app.state.chromadb_store = _MockChromaDBStore()
    app.state.bm25_index = BM25Index()
    app.state.embedding_client = _MockResilientClient(
        response_data={"vectors": [[0.1] * 10], "tokens_used": 5}
    )
    app.state.graph_client = _MockResilientClient(response_data={})

    chunker_registry = ChunkerRegistry()
    chunker_registry.register("fixed_size", FixedSizeChunker(), available=True)
    chunker_registry.register("recursive", RecursiveChunker(), available=True)
    chunker_registry.register("legal_hierarchical", LegalHierarchicalChunker(), available=True)
    app.state.chunker_registry = chunker_registry

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class _MockResponse:
    """Mock HTTP response."""

    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class _MockResilientClient:
    """Mock ResilientClient for testing."""

    def __init__(self, response_data: dict, status_code: int = 200):
        self._response = _MockResponse(response_data, status_code)
        self.calls: list[tuple[str, str, dict]] = []

    async def post(self, path: str, correlation_id: str, **kwargs) -> _MockResponse:
        self.calls.append(("POST", path, kwargs))
        return self._response

    async def get(self, path: str, correlation_id: str, **kwargs) -> _MockResponse:
        self.calls.append(("GET", path, kwargs))
        return self._response

    async def close(self):
        pass


class _MockChromaDBStore:
    """Mock ChromaDB store for testing."""

    is_initialized = True

    def heartbeat(self) -> bool:
        return True

    def store_vectors(self, ids, vectors, documents, metadatas):
        pass


class _MockUnhealthyChromaDB:
    """Mock unhealthy ChromaDB store."""

    is_initialized = True

    def heartbeat(self) -> bool:
        return False

    def store_vectors(self, ids, vectors, documents, metadatas):
        raise RuntimeError("Unhealthy")


class TestLivenessEndpoint:
    """Tests for the /health/live endpoint."""

    async def test_liveness_always_returns_200(self, client: AsyncClient):
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert data["service"] == "ingestion-service"


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    async def test_health_returns_200_when_healthy(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_returns_503_when_chromadb_down(self, app, client: AsyncClient):
        app.state.chromadb_store = _MockUnhealthyChromaDB()
        response = await client.get("/health")
        assert response.status_code == 503


class TestIngestEndpoint:
    """Tests for the POST /v1/ingest endpoint."""

    async def test_ingest_rejects_unsupported_format(self, client: AsyncClient):
        response = await client.post(
            "/v1/ingest",
            files={"file": ("test.xyz", b"hello world", "text/plain")},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert ".xyz" in data["message"]

    async def test_ingest_rejects_oversized_file(self, client: AsyncClient):
        # Create a file > 50 MB
        large_content = b"x" * (50 * 1024 * 1024 + 1)
        response = await client.post(
            "/v1/ingest",
            files={"file": ("test.txt", large_content, "text/plain")},
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "50" in data["message"]

    async def test_ingest_txt_returns_201(self, client: AsyncClient):
        response = await client.post(
            "/v1/ingest",
            files={"file": ("test.txt", b"Hello world. This is a test document.", "text/plain")},
        )
        assert response.status_code == 201
        data = response.json()
        assert "document_id" in data
        assert data["filename"] == "test.txt"
        assert data["chunks_produced"] >= 1
        assert data["chunking_strategy"] == "fixed_size"

    async def test_ingest_md_with_legislative_keyword_uses_legal_hierarchical(
        self, client: AsyncClient
    ):
        content = "# Privacy Act 2024\n\nPart 1\n\nSection 1.\nData protection obligations."
        response = await client.post(
            "/v1/ingest",
            files={"file": ("Privacy_Act_2024.md", content.encode(), "text/markdown")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["chunking_strategy"] == "legal_hierarchical"

    async def test_ingest_html_uses_recursive(self, client: AsyncClient):
        content = "<html><body><p>Hello world.</p></body></html>"
        response = await client.post(
            "/v1/ingest",
            files={"file": ("page.html", content.encode(), "text/html")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["chunking_strategy"] == "recursive"

    async def test_ingest_returns_503_when_embedding_unavailable(self, app, client: AsyncClient):
        from service_client import CircuitBreakerOpenError

        class FailingClient:
            async def post(self, path, correlation_id, **kwargs):
                raise CircuitBreakerOpenError(
                    service_name="embedding-service", reset_timeout=30.0
                )

            async def close(self):
                pass

        app.state.embedding_client = FailingClient()
        response = await client.post(
            "/v1/ingest",
            files={"file": ("test.txt", b"Hello world content.", "text/plain")},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "DEPENDENCY_UNAVAILABLE"

    async def test_ingest_calls_graph_service_entities_and_relationships(
        self, app, client: AsyncClient
    ):
        """Verify ingestion calls POST /entities and POST /relationships on Graph Service."""
        content = (
            "The Transport Infrastructure Act 2024 establishes road management.\n"
            "The Road Use Management Act references the Transport Infrastructure Act."
        )
        response = await client.post(
            "/v1/ingest",
            files={"file": ("Transport_Act.md", content.encode(), "text/markdown")},
        )
        assert response.status_code == 201

        # Check graph_client received POST /entities and POST /relationships
        graph_client = app.state.graph_client
        post_paths = [path for method, path, _ in graph_client.calls if method == "POST"]
        assert "/entities" in post_paths
        assert "/relationships" in post_paths

    async def test_ingest_completes_without_graph_on_failure(self, app, client: AsyncClient):
        """Verify ingestion completes in degraded mode when Graph Service is unavailable."""
        from service_client import CircuitBreakerOpenError

        class FailingGraphClient:
            calls: list = []

            async def post(self, path, correlation_id, **kwargs):
                raise CircuitBreakerOpenError(
                    service_name="graph-service", reset_timeout=30.0
                )

            async def close(self):
                pass

        app.state.graph_client = FailingGraphClient()
        content = "The Privacy Act 2024 defines obligations for data protection."
        response = await client.post(
            "/v1/ingest",
            files={"file": ("Privacy_Act.md", content.encode(), "text/markdown")},
        )
        # Ingestion still succeeds (degraded mode - no graph)
        assert response.status_code == 201
        data = response.json()
        assert "document_id" in data


class TestDocumentsEndpoint:
    """Tests for the GET /v1/documents endpoint."""

    async def test_list_documents_empty(self, client: AsyncClient):
        response = await client.get("/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data

    async def test_list_documents_after_ingest(self, client: AsyncClient):
        # Ingest a document first
        await client.post(
            "/v1/ingest",
            files={"file": ("doc1.txt", b"Some content here.", "text/plain")},
        )
        response = await client.get("/v1/documents")
        assert response.status_code == 200
        data = response.json()
        docs = data["documents"]
        assert len(docs) >= 1
        doc = docs[0]
        assert "document_id" in doc
        assert "filename" in doc
        assert "format" in doc
        assert "ingestion_date" in doc
        assert "chunks_produced" in doc

    async def test_documents_sorted_by_ingestion_date_descending(self, client: AsyncClient):
        # Ingest two documents
        await client.post(
            "/v1/ingest",
            files={"file": ("first.txt", b"First document content.", "text/plain")},
        )
        await client.post(
            "/v1/ingest",
            files={"file": ("second.txt", b"Second document content.", "text/plain")},
        )
        response = await client.get("/v1/documents")
        data = response.json()
        docs = data["documents"]
        # Most recent should be first
        if len(docs) >= 2:
            assert docs[0]["ingestion_date"] >= docs[1]["ingestion_date"]


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    async def test_metrics_returns_200(self, client: AsyncClient):
        response = await client.get("/metrics")
        assert response.status_code == 200


class TestCreateApp:
    """Tests for the create_app factory function."""

    def test_app_has_correct_title(self, app):
        assert app.title == "Ingestion Service"

    def test_app_has_routes(self, app):
        paths = [route.path for route in app.routes]
        assert "/v1/ingest" in paths
        assert "/v1/documents" in paths
        assert "/health" in paths
        assert "/health/ready" in paths
        assert "/health/live" in paths
        assert "/metrics" in paths
