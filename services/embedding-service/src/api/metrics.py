"""Prometheus metrics endpoint and metric definitions for the Embedding Service."""

from fastapi import APIRouter, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

metrics_router = APIRouter(tags=["metrics"])

# Embedding service metrics
EMBED_REQUESTS_TOTAL = Counter(
    "embed_requests_total",
    "Total embedding requests received",
)
EMBED_CACHE_HITS_TOTAL = Counter(
    "embed_cache_hits_total",
    "Total embedding cache hits",
)
EMBED_CACHE_MISSES_TOTAL = Counter(
    "embed_cache_misses_total",
    "Total embedding cache misses",
)
EMBED_LATENCY_SECONDS = Histogram(
    "embed_latency_seconds",
    "Embedding request latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
TOKENS_USED_TOTAL = Counter(
    "tokens_used_total",
    "Total tokens consumed across all embedding requests",
)


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus-compatible metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
