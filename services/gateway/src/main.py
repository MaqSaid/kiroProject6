"""API Gateway FastAPI application.

Central entry point for the Legislation RAG Platform. Handles:
- CORS
- Security headers (secure library)
- Penetration detection (fastapi-guard)
- Correlation ID generation/propagation
- API Key authentication
- Rate limiting (token bucket, 60 req/min/key)
- Request/response logging (structlog JSON)
- Proxy routing to downstream services
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from guard.middleware import SecurityConfig, SecurityMiddleware

from src.config import Settings
from src.logging_config import configure_logging, get_logger
from src.middleware.auth import APIKeyAuthMiddleware
from src.middleware.correlation_id import CorrelationIdMiddleware
from src.middleware.error_handler import ErrorHandlerMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware, TokenBucket
from src.middleware.request_logging import RequestLoggingMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.proxy import match_route, proxy_request

# Configure logging before app starts
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    settings = Settings()
    app.state.settings = settings
    logger.info("gateway_started", service_name=settings.service_name)
    yield
    logger.info("gateway_shutdown", service_name=settings.service_name)


# Create application
app = FastAPI(
    title="Legislation RAG API Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Settings and middleware instances ---
settings = Settings()
token_bucket = TokenBucket(rate=settings.rate_limit_per_minute, period=60.0)

# --- Middleware stack (order matters: registered in reverse execution order) ---
# According to the steering guide, register in this order:
# 1. CORS (outermost - handles preflight before other middleware)
# 2. Security headers (set on every response)
# 3. Guard (penetration detection - reject attacks early)
# 4. Correlation ID (generate/propagate before auth logs need it)
# 5. API Key Auth (authenticate before rate limiting)
# 6. Rate Limiting (after auth so we rate-limit per authenticated key)
# 7. Request Logging (innermost - log after all enrichment)

# Since Starlette executes middleware in reverse add_middleware order,
# we register them in reverse: last added = first executed (outermost).

# 7. Request Logging (innermost)
app.add_middleware(RequestLoggingMiddleware)

# 6. Rate Limiting
app.add_middleware(RateLimitMiddleware, limiter=token_bucket)

# 5. API Key Auth
app.add_middleware(APIKeyAuthMiddleware, valid_keys=settings.api_keys)

# 4. Correlation ID
app.add_middleware(CorrelationIdMiddleware)

# 3. Error Handler (catch unhandled exceptions from downstream middleware/routes)
app.add_middleware(ErrorHandlerMiddleware)

# 2. Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# 3b. Guard middleware (penetration detection)
# Configure fastapi-guard for attack detection only — we handle
# rate limiting, CORS, and security headers separately.
guard_config = SecurityConfig(
    enable_penetration_detection=True,
    enable_rate_limiting=False,
    enable_ip_banning=False,
    enable_cors=False,
    enforce_https=False,
    security_headers={"enabled": False},
    enable_redis=False,
    custom_error_responses={
        403: "Forbidden: Potential attack detected",
    },
    exclude_paths=["/health", "/health/ready", "/health/live", "/metrics"],
)
app.add_middleware(SecurityMiddleware, config=guard_config)

# 1. CORS (outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)


# --- Health endpoints ---


async def _check_downstream_service(
    client: httpx.AsyncClient,
    service_name: str,
    base_url: str,
    timeout: float,
) -> dict:
    """Check connectivity to a single downstream service via /health/live."""
    start = time.perf_counter()
    try:
        response = await client.get(
            f"{base_url}/health/live",
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            return {
                "service": service_name,
                "status": "healthy",
                "latency_ms": round(elapsed_ms, 2),
            }
        else:
            return {
                "service": service_name,
                "status": "unhealthy",
                "latency_ms": round(elapsed_ms, 2),
            }
    except (httpx.RequestError, httpx.TimeoutException):
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "service": service_name,
            "status": "unhealthy",
            "latency_ms": None,
        }


@app.get("/health")
async def health_check(request: Request):
    """Aggregated health check - checks all downstream services."""
    svc_settings = app.state.settings

    downstream_services = [
        ("query_service", svc_settings.query_service_url),
        ("ingestion_service", svc_settings.ingestion_service_url),
        ("graph_service", svc_settings.graph_service_url),
        ("embedding_service", svc_settings.embedding_service_url),
    ]

    timeout = svc_settings.health_check_timeout

    async with httpx.AsyncClient() as client:
        tasks = [
            _check_downstream_service(client, name, url, timeout)
            for name, url in downstream_services
        ]
        results = await asyncio.gather(*tasks)

    all_healthy = all(r["status"] == "healthy" for r in results)
    overall_status = "healthy" if all_healthy else "unhealthy"

    response_body = {
        "status": overall_status,
        "services": results,
    }

    status_code = 200 if all_healthy else 503
    return JSONResponse(content=response_body, status_code=status_code)


@app.get("/health/ready")
async def readiness_check():
    """Readiness check - gateway is ready to accept traffic."""
    return {"status": "ready", "service": "gateway"}


@app.get("/health/live")
async def liveness_check():
    """Liveness check - process is running."""
    return {"status": "alive"}


# --- Proxy routing ---


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_route(request: Request):
    """Proxy all non-health requests to downstream services."""
    path = request.url.path
    route = match_route(path)

    if route is None:
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=404,
            content={
                "error_code": "NOT_FOUND",
                "message": f"No route configured for path: {path}",
                "correlation_id": correlation_id,
            },
        )

    # Resolve target service URL
    service = route["service"]
    timeout_attr = route["timeout_attr"]

    if service == "query":
        target_url = settings.query_service_url
    elif service == "ingestion":
        target_url = settings.ingestion_service_url
    else:
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": f"Unknown service target: {service}",
                "correlation_id": correlation_id,
            },
        )

    timeout = getattr(settings, timeout_attr, 30.0)
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    return await proxy_request(
        request=request,
        target_base_url=target_url,
        timeout=timeout,
        correlation_id=correlation_id,
    )
