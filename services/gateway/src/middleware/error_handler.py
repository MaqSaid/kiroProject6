"""Global error handler middleware."""

from __future__ import annotations

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured ErrorResponse."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            logger.error(
                "unhandled_exception",
                error=str(exc),
                error_type=type(exc).__name__,
                correlation_id=correlation_id,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "correlation_id": correlation_id,
                },
            )
