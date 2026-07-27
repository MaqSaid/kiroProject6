"""Prometheus metrics endpoint for the Ingestion Service."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

metrics_router = APIRouter(tags=["metrics"])

# Metrics
REQUEST_COUNT = Counter(
    "ingestion_http_requests_total",
    "Total HTTP requests to the Ingestion Service",
    ["method", "endpoint", "status_code"],
)
REQUEST_DURATION = Histogram(
    "ingestion_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)
DOCUMENTS_INGESTED = Counter(
    "ingestion_documents_total",
    "Total documents successfully ingested",
)
CHUNKS_PRODUCED = Counter(
    "ingestion_chunks_produced_total",
    "Total chunks produced during ingestion",
)


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus-compatible metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
