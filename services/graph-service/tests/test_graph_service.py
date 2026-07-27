"""Unit tests for the Graph Service application."""

import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from domain_models import ScoredChunk
from src.infrastructure.neo4j_adapter import GraphStoreUnavailableError


@pytest.fixture
def mock_graph_store():
    """Create a mock graph store with async methods."""
    store = AsyncMock()
    store.verify_connectivity.return_value = True
    store.verify_indexes.return_value = True
    store.store_entities.return_value = 2
    store.store_relationships.return_value = (1, 1)
    store.traverse.return_value = [
        ScoredChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            text="Section 45 content",
            section_heading="Section 45",
            score=0.5,
            retrieval_method="graph",
        )
    ]
    store.delete_by_document.return_value = (3, 2)
    return store


def create_test_app(graph_store) -> FastAPI:
    """Create a test app with a no-op lifespan that uses a mock graph store."""

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.graph_store = graph_store
        yield

    app = FastAPI(title="Graph Service Test", lifespan=test_lifespan)

    from src.api.health import health_router
    from src.api.metrics import metrics_router
    from src.api.routes import router
    from src.middleware.correlation_id import CorrelationIdMiddleware
    from src.middleware.error_handler import ErrorHandlerMiddleware
    from src.middleware.metrics import MetricsMiddleware

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    return app


@pytest.fixture
def client(mock_graph_store):
    """Create test client with mocked graph store (no Neo4j required)."""
    app = create_test_app(mock_graph_store)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestStoreEntities:
    """Tests for POST /entities endpoint."""

    def test_store_entities_success(self, client, mock_graph_store):
        response = client.post(
            "/entities",
            json={
                "entities": [
                    {
                        "id": "entity-001",
                        "name": "Transport Act 2024",
                        "entity_type": "Act",
                        "description": "Primary legislation",
                        "source_chunk_id": "chunk-001",
                        "properties": {"year": 2024},
                    }
                ]
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["stored_count"] == 2
        mock_graph_store.store_entities.assert_called_once()

    def test_store_entities_validation_error(self, client):
        response = client.post(
            "/entities",
            json={"entities": []},
        )
        assert response.status_code == 422

    def test_store_entities_missing_required_field(self, client):
        response = client.post(
            "/entities",
            json={
                "entities": [
                    {
                        "id": "entity-001",
                    }
                ]
            },
        )
        assert response.status_code == 422


class TestStoreRelationships:
    """Tests for POST /relationships endpoint."""

    def test_store_relationships_success(self, client, mock_graph_store):
        response = client.post(
            "/relationships",
            json={
                "relationships": [
                    {
                        "id": "rel-001",
                        "source_entity_id": "entity-001",
                        "target_entity_id": "entity-002",
                        "relationship_type": "CONTAINS",
                        "description": "Act contains section",
                        "properties": {},
                    }
                ]
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["stored_count"] == 1
        assert data["skipped_count"] == 1

    def test_store_relationships_validation_error(self, client):
        response = client.post(
            "/relationships",
            json={"relationships": []},
        )
        assert response.status_code == 422


class TestTraverse:
    """Tests for POST /traverse endpoint."""

    def test_traverse_success(self, client, mock_graph_store):
        response = client.post(
            "/traverse",
            json={"query": "Transport Act", "max_hops": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["chunk_id"] == "chunk-1"
        assert data["results"][0]["retrieval_method"] == "graph"
        assert data["results"][0]["score"] == 0.5

    def test_traverse_max_hops_capped(self, client, mock_graph_store):
        response = client.post(
            "/traverse",
            json={"query": "test", "max_hops": 5},
        )
        assert response.status_code == 200
        mock_graph_store.traverse.assert_called_once_with(query="test", max_hops=5)

    def test_traverse_max_hops_exceeds_limit(self, client):
        response = client.post(
            "/traverse",
            json={"query": "test", "max_hops": 10},
        )
        assert response.status_code == 422

    def test_traverse_missing_query(self, client):
        response = client.post(
            "/traverse",
            json={"max_hops": 2},
        )
        assert response.status_code == 422


class TestDeleteDocument:
    """Tests for DELETE /documents/{document_id} endpoint."""

    def test_delete_document_success(self, client, mock_graph_store):
        response = client.delete("/documents/doc-001")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_nodes"] == 3
        assert data["deleted_relationships"] == 2
        mock_graph_store.delete_by_document.assert_called_once_with("doc-001")


class TestHealth:
    """Tests for health check endpoints."""

    def test_health_healthy(self, client, mock_graph_store):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "graph-service"

    def test_health_unhealthy(self, client, mock_graph_store):
        mock_graph_store.verify_connectivity.return_value = False
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_health_ready(self, client, mock_graph_store):
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["neo4j_connectivity"] == "ready"
        assert data["checks"]["neo4j_indexes"] == "ready"

    def test_health_ready_indexes_missing(self, client, mock_graph_store):
        mock_graph_store.verify_indexes.return_value = False
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["neo4j_indexes"] == "not_ready"

    def test_health_live(self, client):
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestCorrelationId:
    """Tests for X-Correlation-ID header handling."""

    def test_correlation_id_propagated(self, client, mock_graph_store):
        response = client.post(
            "/traverse",
            json={"query": "test", "max_hops": 2},
            headers={"X-Correlation-ID": "test-correlation-123"},
        )
        assert response.status_code == 200
        assert response.headers.get("X-Correlation-ID") == "test-correlation-123"

    def test_correlation_id_generated_when_missing(self, client, mock_graph_store):
        response = client.post(
            "/traverse",
            json={"query": "test", "max_hops": 2},
        )
        assert response.status_code == 200
        correlation_id = response.headers.get("X-Correlation-ID")
        assert correlation_id is not None
        assert len(correlation_id) == 36  # UUID format


class TestNeo4jUnavailable:
    """Tests for Neo4j unavailability error handling."""

    def test_store_entities_503_on_unavailable(self, client, mock_graph_store):
        mock_graph_store.store_entities.side_effect = GraphStoreUnavailableError(
            "Neo4j unavailable"
        )
        response = client.post(
            "/entities",
            json={
                "entities": [
                    {
                        "id": "entity-001",
                        "name": "Test Act",
                        "entity_type": "Act",
                        "description": "Test",
                        "source_chunk_id": "chunk-001",
                        "properties": {},
                    }
                ]
            },
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "NEO4J_UNAVAILABLE"

    def test_traverse_503_on_unavailable(self, client, mock_graph_store):
        mock_graph_store.traverse.side_effect = GraphStoreUnavailableError(
            "Query timeout"
        )
        response = client.post(
            "/traverse",
            json={"query": "test", "max_hops": 2},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "NEO4J_UNAVAILABLE"


class TestMetrics:
    """Tests for /metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        content = response.text
        # Prometheus metrics should contain HELP and TYPE annotations
        assert "http_requests_total" in content
        assert "http_request_duration_seconds" in content
