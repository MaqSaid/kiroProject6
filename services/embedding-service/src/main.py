"""Embedding Service FastAPI application.

This service exclusively owns AWS Bedrock embedding API access.
It provides caching via SHA-256 hashing to avoid redundant calls
and tracks token usage for cost attribution.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from src.config import Settings
from src.infrastructure.bedrock_adapter import BedrockEmbeddingAdapter
from src.infrastructure.embedding_cache import EmbeddingCache
from src.logging_config import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle.

    Startup:
      - Load settings
      - Configure structured logging
      - Initialize embedding cache
      - Initialize Bedrock client

    Shutdown:
      - Clean up resources
    """
    settings = Settings()
    configure_logging()
    logger.info("service.starting", service=settings.service_name)

    # Initialize embedding cache
    cache = EmbeddingCache()
    cache.initialize()

    # Initialize Bedrock adapter
    adapter = BedrockEmbeddingAdapter(settings)
    adapter.initialize()

    # Store in app state for dependency injection
    app.state.settings = settings
    app.state.embedding_cache = cache
    app.state.bedrock_adapter = adapter

    logger.info("service.started", service=settings.service_name)
    yield

    # Shutdown
    logger.info("service.stopped", service=settings.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Embedding Service",
        description="Internal embedding service wrapping AWS Bedrock embedding calls",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register routers
    from src.api.routes import router
    from src.api.health import health_router
    from src.api.metrics import metrics_router

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    # Register middleware (order matters: first added = outermost)
    from src.middleware.error_handler import ErrorHandlerMiddleware
    from src.middleware.correlation_id import CorrelationIdMiddleware

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)

    return app


app = create_app()
