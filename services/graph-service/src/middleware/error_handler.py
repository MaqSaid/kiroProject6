"""Global error handler middleware."""

import json

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.neo4j_adapter import GraphStoreUnavailableError

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except GraphStoreUnavailableError as exc:
            correlation_id = request.headers.get("x-correlation-id", "unknown")
            logger.error(
                "neo4j_unavailable",
                error=str(exc),
                correlation_id=correlation_id,
            )
            error_body = json.dumps(
                {
                    "error_code": "NEO4J_UNAVAILABLE",
                    "message": "Neo4j database is unreachable or query timed out after 5 seconds",
                    "correlation_id": correlation_id,
                }
            )
            return Response(
                content=error_body,
                status_code=503,
                media_type="application/json",
            )
        except Exception as exc:
            correlation_id = request.headers.get("x-correlation-id", "unknown")
            logger.error(
                "unhandled_exception",
                error=str(exc),
                correlation_id=correlation_id,
            )
            error_body = json.dumps(
                {
                    "error_code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "correlation_id": correlation_id,
                }
            )
            return Response(
                content=error_body,
                status_code=500,
                media_type="application/json",
            )
