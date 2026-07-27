"""Health check endpoints for the Ingestion Service."""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Request, Response

logger = structlog.get_logger(__name__)

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check(request: Request) -> Response:
    """Basic health check — verifies ChromaDB connectivity and BM25 availability."""
    try:
        chromadb_store = request.app.state.chromadb_store
        bm25_ok = request.app.state.bm25_index.is_initialized
        chromadb_ok = chromadb_store.heartbeat()

        if chromadb_ok and bm25_ok:
            return Response(
                content=json.dumps({"status": "healthy", "service": "ingestion-service"}),
                status_code=200,
                media_type="application/json",
            )
        else:
            return Response(
                content=json.dumps({"status": "unhealthy", "service": "ingestion-service"}),
                status_code=503,
                media_type="application/json",
            )
    except Exception as e:
        logger.error("health.check_failed", error=str(e))
        return Response(
            content=json.dumps({"status": "unhealthy", "service": "ingestion-service"}),
            status_code=503,
            media_type="application/json",
        )


@health_router.get("/health/ready")
async def readiness_check(request: Request) -> Response:
    """Readiness probe — verifies ChromaDB, BM25, and downstream services are reachable."""
    checks: dict[str, str] = {}
    all_ready = True

    # Check ChromaDB
    try:
        chromadb_ok = request.app.state.chromadb_store.heartbeat()
        checks["chromadb"] = "ready" if chromadb_ok else "not_ready"
        if not chromadb_ok:
            all_ready = False
    except Exception:
        checks["chromadb"] = "not_ready"
        all_ready = False

    # Check BM25
    bm25_ok = request.app.state.bm25_index.is_initialized
    checks["bm25"] = "ready" if bm25_ok else "not_ready"
    if not bm25_ok:
        all_ready = False

    # Check Embedding Service reachability
    try:
        embedding_client = request.app.state.embedding_client
        resp = await embedding_client.get("/health/live", correlation_id="readiness-probe")
        checks["embedding_service"] = "ready" if resp.status_code == 200 else "not_ready"
        if resp.status_code != 200:
            all_ready = False
    except Exception:
        checks["embedding_service"] = "not_ready"
        all_ready = False

    # Check Graph Service reachability
    try:
        graph_client = request.app.state.graph_client
        resp = await graph_client.get("/health/live", correlation_id="readiness-probe")
        checks["graph_service"] = "ready" if resp.status_code == 200 else "not_ready"
        if resp.status_code != 200:
            all_ready = False
    except Exception:
        checks["graph_service"] = "not_ready"
        # Graph service failure is non-critical but still reported in readiness
        all_ready = False

    status = "ready" if all_ready else "not_ready"
    status_code = 200 if all_ready else 503

    return Response(
        content=json.dumps({"status": status, "service": "ingestion-service", "checks": checks}),
        status_code=status_code,
        media_type="application/json",
    )


@health_router.get("/health/live")
async def liveness_probe() -> dict[str, str]:
    """Liveness probe — process is running (always 200)."""
    return {"status": "alive", "service": "ingestion-service"}
