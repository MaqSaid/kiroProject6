"""Health check endpoints for the Query Service."""

import json

import structlog
from fastapi import APIRouter, Request, Response

logger = structlog.get_logger(__name__)

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check(request: Request) -> Response:
    """Basic health check — verifies orchestrator is initialized."""
    try:
        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator is None:
            raise RuntimeError("Orchestrator not initialized")

        return Response(
            content=json.dumps({"status": "healthy", "service": "query-service"}),
            status_code=200,
            media_type="application/json",
        )
    except Exception as e:
        logger.error("health.check_failed", error=str(e))
        return Response(
            content=json.dumps({"status": "unhealthy", "service": "query-service"}),
            status_code=503,
            media_type="application/json",
        )


@health_router.get("/health/ready")
async def readiness_check(request: Request) -> Response:
    """Readiness check — orchestrator initialized and dependencies reachable."""
    checks: dict[str, str] = {}
    all_ready = True

    # Check orchestrator
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is not None:
        checks["orchestrator"] = "ready"
    else:
        checks["orchestrator"] = "not_ready"
        all_ready = False

    # Check embedding client
    embedding_client = getattr(request.app.state, "embedding_client", None)
    if embedding_client is not None:
        checks["embedding_service"] = "ready"
    else:
        checks["embedding_service"] = "not_ready"
        all_ready = False

    # Check graph client
    graph_client = getattr(request.app.state, "graph_client", None)
    if graph_client is not None:
        checks["graph_service"] = "ready"
    else:
        checks["graph_service"] = "not_ready"
        all_ready = False

    status_code = 200 if all_ready else 503
    return Response(
        content=json.dumps({
            "status": "ready" if all_ready else "not_ready",
            "service": "query-service",
            "checks": checks,
        }),
        status_code=status_code,
        media_type="application/json",
    )


@health_router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Liveness probe — process is running (always 200)."""
    return {"status": "alive", "service": "query-service"}
