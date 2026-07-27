"""Global error handler middleware for structured error responses."""

import uuid

import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from domain_models.api_models import ErrorResponse

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        """Process request with error handling."""
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = getattr(request.state, "correlation_id", None)
            if correlation_id is None:
                correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))

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
            return JSONResponse(
                content=error.model_dump(),
                status_code=500,
            )
