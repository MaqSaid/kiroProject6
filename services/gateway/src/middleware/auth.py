"""API Key authentication middleware."""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header against configured key set."""

    def __init__(self, app, valid_keys: set[str]) -> None:
        super().__init__(app)
        self.valid_keys = valid_keys

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health and metrics endpoints
        if request.url.path.startswith("/health") or request.url.path == "/metrics":
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "UNAUTHORIZED",
                    "message": "Missing X-API-Key header",
                    "correlation_id": correlation_id,
                },
            )

        if api_key not in self.valid_keys:
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            logger.warning(
                "invalid_api_key",
                key_prefix=api_key[:8] if len(api_key) >= 8 else api_key,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "UNAUTHORIZED",
                    "message": "Invalid API key",
                    "correlation_id": correlation_id,
                },
            )

        # Log key identifier (first 8 chars), never the full key
        logger.info(
            "request_authenticated",
            key_prefix=api_key[:8] if len(api_key) >= 8 else api_key,
        )
        return await call_next(request)
