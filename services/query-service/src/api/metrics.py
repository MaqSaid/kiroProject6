"""Prometheus metrics endpoint for the Query Service."""

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

metrics_router = APIRouter(tags=["metrics"])

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
)
ORCHESTRATOR_DURATION = Histogram(
    "orchestrator_ask_duration_seconds",
    "RAGOrchestrator ask() call duration",
)


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus-compatible metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
