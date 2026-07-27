"""Global error handler middleware."""

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from domain_models import ErrorResponse

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with global error handling."""
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = request.headers.get("x-correlation-id", "unknown")
            logger.error(
                "unhandled_exception",
                error=str(exc),
                error_type=type(exc).__name__,
                correlation_id=correlation_id,
            )
            error = ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                correlation_id=correlation_id,
            )
            return Response(
                content=error.model_dump_json(),
                status_code=500,
                media_type="application/json",
            )
