"""Token bucket rate limiting middleware."""

from __future__ import annotations

import time
from collections import defaultdict

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class TokenBucket:
    """In-memory token bucket rate limiter (dev environment).

    Continuous refill: tokens are added proportionally to elapsed time.
    """

    def __init__(self, rate: int = 60, period: float = 60.0) -> None:
        self.rate = rate  # tokens per period
        self.period = period  # period in seconds
        self.buckets: dict[str, dict] = defaultdict(
            lambda: {"tokens": float(rate), "last_refill": time.monotonic()}
        )

    def allow(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        bucket = self.buckets[key]
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]

        # Continuous refill based on elapsed time
        refill = elapsed * self.rate / self.period
        if refill > 0:
            bucket["tokens"] = min(float(self.rate), bucket["tokens"] + refill)
            bucket["last_refill"] = now

        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware: N requests per minute per API key."""

    def __init__(self, app, limiter: TokenBucket) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health and metrics endpoints
        if request.url.path.startswith("/health") or request.url.path == "/metrics":
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "anonymous")
        if not self.limiter.allow(api_key):
            correlation_id = getattr(request.state, "correlation_id", "unknown")
            logger.warning(
                "rate_limit_exceeded",
                key_prefix=api_key[:8] if len(api_key) >= 8 else api_key,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMITED",
                    "message": "Rate limit exceeded: 60 requests per minute per API key",
                    "correlation_id": correlation_id,
                },
            )
        return await call_next(request)
