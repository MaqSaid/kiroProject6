"""Correlation ID middleware for request tracing."""

import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging_config import correlation_id_ctx

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate correlation ID and bind to log context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        # Set context variable for logging
        token = correlation_id_ctx.set(correlation_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response: Response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")
            correlation_id_ctx.reset(token)
