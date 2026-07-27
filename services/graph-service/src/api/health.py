"""Health check endpoints for the Graph Service."""

import json

import structlog
from fastapi import APIRouter, Request, Response

logger = structlog.get_logger(__name__)

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check(request: Request) -> Response:
    """Liveness check — verifies Neo4j connectivity."""
    try:
        graph_store = request.app.state.graph_store
        is_connected = await graph_store.verify_connectivity()
        if is_connected:
            return Response(
                content=json.dumps({"status": "healthy", "service": "graph-service"}),
                status_code=200,
                media_type="application/json",
            )
        else:
            return Response(
                content=json.dumps(
                    {"status": "unhealthy", "service": "graph-service", "error": "Neo4j unreachable"}
                ),
                status_code=503,
                media_type="application/json",
            )
    except Exception as e:
        logger.error("health.check_failed", error=str(e))
        return Response(
            content=json.dumps(
                {"status": "unhealthy", "service": "graph-service", "error": str(e)}
            ),
            status_code=503,
            media_type="application/json",
        )


@health_router.get("/health/ready")
async def readiness_check(request: Request) -> Response:
    """Readiness check — Neo4j pool established and indexes exist."""
    checks: dict[str, str] = {}
    all_ready = True

    try:
        graph_store = request.app.state.graph_store

        # Check Neo4j connectivity (pool established)
        is_connected = await graph_store.verify_connectivity()
        checks["neo4j_connectivity"] = "ready" if is_connected else "not_ready"
        if not is_connected:
            all_ready = False

        # Check indexes exist
        if is_connected:
            indexes_exist = await graph_store.verify_indexes()
            checks["neo4j_indexes"] = "ready" if indexes_exist else "not_ready"
            if not indexes_exist:
                all_ready = False
        else:
            checks["neo4j_indexes"] = "not_ready"
            all_ready = False

    except Exception as e:
        checks["neo4j_connectivity"] = "not_ready"
        checks["neo4j_indexes"] = "not_ready"
        all_ready = False
        logger.error("readiness.check_failed", error=str(e))

    status_code = 200 if all_ready else 503
    return Response(
        content=json.dumps(
            {
                "status": "ready" if all_ready else "not_ready",
                "service": "graph-service",
                "checks": checks,
            }
        ),
        status_code=status_code,
        media_type="application/json",
    )


@health_router.get("/health/live")
async def liveness_probe() -> dict:
    """Liveness probe — process is running (always 200)."""
    return {"status": "alive", "service": "graph-service"}
