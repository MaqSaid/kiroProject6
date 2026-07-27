"""Graph Service FastAPI application.

Exclusive owner of Neo4j — no other service connects to Neo4j directly.
Exposes entity/relationship CRUD and traversal via REST API.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from src.config import Settings
from src.infrastructure.neo4j_adapter import Neo4jGraphStore
from src.logging_config import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: Neo4j driver init and cleanup."""
    settings = Settings()
    configure_logging()
    logger.info("service.starting", service=settings.service_name)

    # Initialize Neo4j graph store
    graph_store = await Neo4jGraphStore.create(settings)
    await graph_store.initialize()
    app.state.graph_store = graph_store

    logger.info("service.started", service=settings.service_name)
    yield

    # Cleanup
    await graph_store.close()
    logger.info("service.stopped", service=settings.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Graph Service",
        description="Neo4j graph service for the Legislation RAG Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    from src.api.health import health_router
    from src.api.metrics import metrics_router
    from src.api.routes import router

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    from src.middleware.correlation_id import CorrelationIdMiddleware
    from src.middleware.error_handler import ErrorHandlerMiddleware
    from src.middleware.metrics import MetricsMiddleware

    # Middleware is applied in reverse order (last added = outermost)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    return app


app = create_app()
