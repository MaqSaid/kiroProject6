"""Metrics middleware for tracking HTTP request counts and durations."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.metrics import REQUEST_COUNT, REQUEST_DURATION


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and duration for Prometheus metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        duration = time.perf_counter() - start_time

        # Skip metrics endpoint itself to avoid self-referencing
        endpoint = request.url.path
        method = request.method

        REQUEST_COUNT.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(response.status_code),
        ).inc()

        REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        return response
