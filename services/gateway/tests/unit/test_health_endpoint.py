"""Unit tests for the aggregated /health endpoint."""

import httpx
import pytest
import respx
from httpx import ASGITransport, Response

from src.config import Settings
from src.main import app


@pytest.fixture(autouse=True)
def setup_app_state():
    """Set up app.state.settings for tests (simulates lifespan startup)."""
    app.state.settings = Settings()
    yield


@pytest.fixture
async def client():
    """Create a test client for the gateway app."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestAggregatedHealthEndpoint:
    """Tests for the /health aggregated endpoint."""

    @respx.mock
    async def test_all_services_healthy(self, client):
        """When all downstream services respond 200, return 200 with all healthy."""
        respx.get("http://query-service:8001/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://graph-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )

        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert len(data["services"]) == 4

        for svc in data["services"]:
            assert svc["status"] == "healthy"
            assert svc["latency_ms"] is not None
            assert svc["latency_ms"] >= 0

        service_names = {s["service"] for s in data["services"]}
        assert service_names == {
            "query_service",
            "ingestion_service",
            "graph_service",
            "embedding_service",
        }

    @respx.mock
    async def test_one_service_unhealthy_returns_503(self, client):
        """When one downstream service is unreachable, return 503."""
        respx.get("http://query-service:8001/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://graph-service:8000/health/live").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )

        response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

        graph_status = next(
            s for s in data["services"] if s["service"] == "graph_service"
        )
        assert graph_status["status"] == "unhealthy"
        assert graph_status["latency_ms"] is None

        healthy_services = [
            s for s in data["services"] if s["service"] != "graph_service"
        ]
        for svc in healthy_services:
            assert svc["status"] == "healthy"

    @respx.mock
    async def test_all_services_unhealthy_returns_503(self, client):
        """When all downstream services are unreachable, return 503."""
        respx.get("http://query-service:8001/health/live").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://graph-service:8000/health/live").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        for svc in data["services"]:
            assert svc["status"] == "unhealthy"
            assert svc["latency_ms"] is None

    @respx.mock
    async def test_service_returns_non_200_is_unhealthy(self, client):
        """When a downstream service returns non-200 status, mark as unhealthy."""
        respx.get("http://query-service:8001/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            return_value=Response(503, json={"status": "not ready"})
        )
        respx.get("http://graph-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )

        response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

        ingestion_status = next(
            s for s in data["services"] if s["service"] == "ingestion_service"
        )
        assert ingestion_status["status"] == "unhealthy"
        assert ingestion_status["latency_ms"] is not None

    @respx.mock
    async def test_timeout_marks_service_unhealthy(self, client):
        """When a downstream service times out, mark as unhealthy."""
        respx.get("http://query-service:8001/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://graph-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            side_effect=httpx.ReadTimeout("Read timed out")
        )

        response = await client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

        embedding_status = next(
            s for s in data["services"] if s["service"] == "embedding_service"
        )
        assert embedding_status["status"] == "unhealthy"
        assert embedding_status["latency_ms"] is None

    @respx.mock
    async def test_health_endpoint_no_auth_required(self, client):
        """Health endpoint should be accessible without API key."""
        respx.get("http://query-service:8001/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://ingestion-service:8002/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://graph-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )
        respx.get("http://embedding-service:8000/health/live").mock(
            return_value=Response(200, json={"status": "alive"})
        )

        # No X-API-Key header — health endpoints skip auth
        response = await client.get("/health")
        assert response.status_code == 200
