---
inclusion: manual
---

# Skill: FastAPI Microservice Scaffold

## Purpose
Scaffold a per-service FastAPI application with lifespan events, health endpoints, metrics, structured logging, Pydantic validation, and dependency injection following the platform's microservice conventions.

## Process

1. **Create app factory** — FastAPI app with lifespan async context manager
2. **Add health endpoints** — /health (liveness), /health/ready (dependency checks), /health/live (always 200)
3. **Add metrics endpoint** — /metrics for Prometheus scraping
4. **Configure structlog** — JSON logging with service_name binding and correlation ID
5. **Define request/response models** — Pydantic v2 models with validation
6. **Wire dependencies** — Depends() for services, config, and shared resources
7. **Add middleware** — Error handler and X-Correlation-ID propagation

## Template

### App Factory with Lifespan

```python
"""<Service Name> FastAPI application."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from src.config import Settings
from src.logging_config import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    settings = Settings()
    configure_logging(service_name=settings.service_name)
    logger.info("service.starting", service=settings.service_name)
    # Initialize dependencies: app.state.driver = await create_driver(...)
    yield
    # Cleanup: await app.state.driver.close()
    logger.info("service.stopped", service=settings.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="<Service Name>", version="1.0.0", lifespan=lifespan)
    from src.api.routes import router
    from src.api.health import health_router
    from src.api.metrics import metrics_router
    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    from src.middleware.correlation_id import CorrelationIdMiddleware
    from src.middleware.error_handler import ErrorHandlerMiddleware
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)
    return app

app = create_app()
```

### Health Endpoints

```python
"""Health check endpoints."""
import json
import structlog
from fastapi import APIRouter, Request, Response

health_router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@health_router.get("/health")
async def health_check(request: Request) -> Response:
    """Liveness check — verifies core dependency connectivity."""
    try:
        # await request.app.state.driver.verify_connectivity()
        return Response(
            content=json.dumps({"status": "healthy", "service": "<service-name>"}),
            status_code=200, media_type="application/json",
        )
    except Exception as e:
        logger.error("health.check_failed", error=str(e))
        return Response(
            content=json.dumps({"status": "unhealthy", "error": "dependency unavailable"}),
            status_code=503, media_type="application/json",
        )


@health_router.get("/health/ready")
async def readiness_check(request: Request) -> Response:
    """Readiness check — all dependencies initialized and operational."""
    checks = {}
    all_ready = True
    # Check each dependency and set checks["dep_name"] = "ready"/"not_ready"
    status_code = 200 if all_ready else 503
    return Response(
        content=json.dumps({"status": "ready" if all_ready else "not_ready", "checks": checks}),
        status_code=status_code, media_type="application/json",
    )


@health_router.get("/health/live")
async def liveness_probe() -> dict:
    """Liveness probe — process is running (always 200)."""
    return {"status": "alive"}
```

### Metrics Endpoint

```python
"""Prometheus metrics endpoint."""
from fastapi import APIRouter, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

metrics_router = APIRouter(tags=["metrics"])

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "Request duration", ["method", "endpoint"])


@metrics_router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus-compatible metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### Structlog Configuration

```python
"""Structured logging configuration."""
import logging
import structlog


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    """Configure structlog with JSON output and service_name binding."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service_name=service_name)
    logging.basicConfig(level=getattr(logging, log_level), format="%(message)s")
```

### Pydantic Request/Response Validation

```python
"""API request and response models."""
from pydantic import BaseModel, Field


class MyRequest(BaseModel):
    """Request body with validation."""
    query: str = Field(..., min_length=1, max_length=2000)
    max_results: int = Field(default=10, ge=1, le=100)


class MyResponse(BaseModel):
    """Response body."""
    results: list[ResultItem]
    total: int = Field(..., ge=0)
```

### Depends() Injection

```python
"""FastAPI dependency injection."""
from typing import Annotated
from fastapi import Depends, Request
from src.config import Settings


def get_settings() -> Settings:
    return Settings()


def get_service(request: Request) -> MyService:
    return request.app.state.my_service


SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceDep = Annotated[MyService, Depends(get_service)]


@router.post("/endpoint")
async def handle_request(body: MyRequest, service: ServiceDep, settings: SettingsDep) -> MyResponse:
    result = await service.process(body, timeout=settings.timeout)
    return MyResponse(results=result.items, total=result.count)
```

### Error Handler Middleware

```python
"""Global error handler middleware."""
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from domain_models import ErrorResponse

logger = structlog.get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = request.headers.get("x-correlation-id", "unknown")
            logger.error("unhandled_exception", error=str(exc), correlation_id=correlation_id)
            error = ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                correlation_id=correlation_id,
            )
            return Response(content=error.model_dump_json(), status_code=500, media_type="application/json")
```

### X-Correlation-ID Middleware

```python
"""Correlation ID middleware for request tracing."""
import uuid
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate correlation ID and bind to log context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        logger.info("request.start", method=request.method, path=request.url.path)
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info("request.end", status_code=response.status_code)
        structlog.contextvars.unbind_contextvars("correlation_id")
        return response
```

## Checklist

Before completing a FastAPI service:
- [ ] Lifespan manages all resource creation and cleanup
- [ ] /health checks primary dependency connectivity
- [ ] /health/ready verifies all dependencies initialized
- [ ] /health/live always returns 200
- [ ] /metrics exposes Prometheus counters and histograms
- [ ] structlog configured with JSON output and service_name
- [ ] All request bodies validated with Pydantic models
- [ ] Dependencies injected via Depends() (no globals)
- [ ] X-Correlation-ID propagated in logs and response headers
- [ ] Unhandled exceptions return structured ErrorResponse
- [ ] HTTP 422 returned for validation failures (automatic via FastAPI)
- [ ] HTTP 503 returned when critical dependencies unavailable
