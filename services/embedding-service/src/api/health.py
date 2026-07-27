"""Health check endpoints for the Embedding Service."""

import json

import structlog
from fastapi import APIRouter, Request, Response

from src.infrastructure.bedrock_adapter import EmbeddingUnavailableError

health_router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@health_router.get("/health")
async def health_check(request: Request) -> Response:
    """Bedrock connectivity check.

    Makes a lightweight Bedrock call to verify the embedding API is reachable.
    Returns 503 if Bedrock is unavailable.
    """
    adapter = request.app.state.bedrock_adapter
    try:
        is_connected = await adapter.check_connectivity()
        if is_connected:
            return Response(
                content=json.dumps({"status": "healthy", "service": "embedding-service"}),
                status_code=200,
                media_type="application/json",
            )
        else:
            return Response(
                content=json.dumps({"status": "unhealthy", "service": "embedding-service"}),
                status_code=503,
                media_type="application/json",
            )
    except Exception as e:
        logger.error("health.check_failed", error=str(e))
        return Response(
            content=json.dumps({"status": "unhealthy", "service": "embedding-service"}),
            status_code=503,
            media_type="application/json",
        )


@health_router.get("/health/ready")
async def readiness_check(request: Request) -> Response:
    """Readiness probe — cache initialized and Bedrock credentials valid.

    Returns 200 if both the cache is initialized and Bedrock is accessible.
    Returns 503 otherwise.
    """
    cache = request.app.state.embedding_cache
    adapter = request.app.state.bedrock_adapter

    checks: dict[str, str] = {}

    # Check cache initialization
    if cache.is_initialized:
        checks["cache"] = "ready"
    else:
        checks["cache"] = "not_ready"

    # Check Bedrock credentials by attempting a lightweight call
    try:
        is_connected = await adapter.check_connectivity()
        checks["bedrock_credentials"] = "valid" if is_connected else "invalid"
    except Exception:
        checks["bedrock_credentials"] = "invalid"

    all_ready = all(
        v in ("ready", "valid") for v in checks.values()
    )
    status_code = 200 if all_ready else 503
    status = "ready" if all_ready else "not_ready"

    return Response(
        content=json.dumps({"status": status, "service": "embedding-service", "checks": checks}),
        status_code=status_code,
        media_type="application/json",
    )


@health_router.get("/health/live")
async def liveness_probe() -> dict:
    """Liveness probe — process is running (always 200)."""
    return {"status": "alive", "service": "embedding-service"}
