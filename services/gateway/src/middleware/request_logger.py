"""Request/response logging middleware with structlog JSON output."""

from __future__ import annotations

import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request/response with method, path, status_code, duration_ms, correlation_id, and key identifier."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        # Extract key prefix for logging (never log full key)
        api_key = request.headers.get("X-API-Key", "")
        key_prefix = api_key[:8] if api_key else "none"

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            key_prefix=key_prefix,
        )

        return response
