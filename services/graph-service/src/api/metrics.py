"""Prometheus metrics endpoint for the Graph Service."""

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
NEO4J_QUERY_DURATION = Histogram(
    "neo4j_query_duration_seconds",
    "Neo4j query duration in seconds",
    ["operation"],
)
ENTITIES_STORED = Counter(
    "graph_entities_stored_total",
    "Total number of entities stored",
)
RELATIONSHIPS_STORED = Counter(
    "graph_relationships_stored_total",
    "Total number of relationships stored",
)
RELATIONSHIPS_SKIPPED = Counter(
    "graph_relationships_skipped_total",
    "Total number of relationships skipped due to missing endpoints",
)


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus-compatible metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
