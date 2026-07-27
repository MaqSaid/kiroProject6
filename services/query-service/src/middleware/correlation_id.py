"""Correlation ID middleware for request tracing."""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate correlation ID and bind to log context."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        """Process request with correlation ID."""
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        # Store in request state for dependency access
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        logger.info("request.start", method=request.method, path=str(request.url.path))
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info("request.end", status_code=response.status_code)

        structlog.contextvars.unbind_contextvars("correlation_id")
        return response
