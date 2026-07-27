"""Correlation ID middleware for request tracing."""

from __future__ import annotations

import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate correlation ID and bind to log context."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Extract or generate X-Correlation-ID, bind to structlog context."""
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        # Store on request state for use in route handlers
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        logger.info("request.start", method=request.method, path=request.url.path)
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info("request.end", status_code=response.status_code)

        structlog.contextvars.unbind_contextvars("correlation_id")
        return response
