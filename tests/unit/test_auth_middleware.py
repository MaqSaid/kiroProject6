"""Unit tests for authentication and RBAC middleware.

Validates: Requirements 10.1, 10.2, 10.8
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from services.gateway.src.middleware.auth import APIKeyAuthMiddleware

VALID_KEYS = {"test-key-12345678", "admin-key-87654321"}


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with auth middleware for testing."""
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware, valid_keys=VALID_KEYS)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/v1/data")
    async def get_data():
        return {"data": "protected"}

    @app.post("/v1/ingest")
    async def ingest():
        return {"status": "ingested"}

    return app


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_endpoint_exempt_from_auth():
    """Requirement 10.1: Health endpoints are exempt from auth."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_api_key_returns_401():
    """Requirement 10.1: Missing API key results in 401."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/data")
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "UNAUTHORIZED"
        assert "Missing" in body["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_api_key_returns_401():
    """Requirement 10.1: Invalid API key results in 401."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/data", headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "UNAUTHORIZED"
        assert "Invalid" in body["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_api_key_grants_access():
    """Requirement 10.1: Valid API key grants access."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/data", headers={"X-API-Key": "test-key-12345678"}
        )
        assert response.status_code == 200
        assert response.json()["data"] == "protected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_error_does_not_disclose_resource_existence():
    """Requirement 10.8: 401 does not reveal whether the resource exists."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request a non-existent path without auth
        response = await client.get("/v1/nonexistent")
        assert response.status_code == 401  # Not 404
        body = response.json()
        assert "not found" not in body["message"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_post_endpoint_requires_auth():
    """Requirement 10.2: Write endpoints require authentication."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/ingest")
        assert response.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_auth_response_contains_correlation_id_field():
    """Requirement 10.8: Error responses include correlation_id."""
    app = create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/data")
        body = response.json()
        assert "correlation_id" in body
