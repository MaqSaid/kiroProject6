"""Ingestion Service FastAPI application.

Entry point for the Ingestion Service. Creates the FastAPI app with lifespan
event managing ChromaDB, BM25 index, Chunker Registry, and inter-service clients.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from src.clients.service_clients import create_embedding_client, create_graph_client
from src.config import Settings
from src.domain.processing.chunker_registry import ChunkerRegistry
from src.domain.processing.fixed_size_chunker import FixedSizeChunker
from src.domain.processing.legal_hierarchical_chunker import LegalHierarchicalChunker
from src.domain.processing.recursive_chunker import RecursiveChunker
from src.domain.processing.semantic_chunker import SemanticChunker
from src.infrastructure.bm25_index import BM25Index
from src.infrastructure.chromadb_store import ChromaDBStore
from src.logging_config import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: initialize and teardown resources."""
    settings = Settings()
    configure_logging()
    logger.info("service.starting", service=settings.service_name)

    # --- Initialize ChromaDB store ---
    chromadb_store = ChromaDBStore(
        host=settings.chromadb_host,
        port=settings.chromadb_port,
    )
    try:
        await chromadb_store.initialize()
    except Exception as e:
        logger.warning(
            "chromadb_initialization_failed",
            error=str(e),
            message="ChromaDB will be unavailable until connection is restored",
        )
    app.state.chromadb_store = chromadb_store

    # --- Initialize BM25 in-memory index ---
    bm25_index = BM25Index()
    app.state.bm25_index = bm25_index
    logger.info("bm25_index_initialized")

    # --- Register chunkers in ChunkerRegistry ---
    chunker_registry = ChunkerRegistry()

    fixed_size_chunker = FixedSizeChunker(chunk_size=1000, overlap=100)
    recursive_chunker = RecursiveChunker(max_chunk_size=1000, overlap=50)
    semantic_chunker = SemanticChunker(max_chunk_size=1000, overlap=50)
    legal_hierarchical_chunker = LegalHierarchicalChunker(
        max_chunk_size=1000, min_body_chars=100
    )

    chunker_registry.register("fixed_size", fixed_size_chunker, available=True)
    chunker_registry.register("recursive", recursive_chunker, available=True)
    chunker_registry.register("semantic", semantic_chunker, available=True)
    chunker_registry.register(
        "legal_hierarchical", legal_hierarchical_chunker, available=True
    )
    app.state.chunker_registry = chunker_registry
    logger.info(
        "chunker_registry_initialized",
        strategies=[s["name"] for s in chunker_registry.registered_strategies],
    )

    # --- Create ResilientClient for Embedding Service (critical) ---
    embedding_client = create_embedding_client(
        base_url=settings.embedding_service_url,
        failure_threshold=settings.circuit_breaker_failure_threshold,
        reset_timeout=settings.circuit_breaker_reset_timeout,
        half_open_max_calls=settings.circuit_breaker_half_open_max_calls,
        max_attempts=settings.retry_max_attempts,
        base_delay=settings.retry_base_delay,
        multiplier=settings.retry_multiplier,
        max_jitter=settings.retry_max_jitter,
    )
    app.state.embedding_client = embedding_client

    # --- Create ResilientClient for Graph Service (non-critical) ---
    graph_client = create_graph_client(
        base_url=settings.graph_service_url,
        failure_threshold=settings.circuit_breaker_failure_threshold,
        reset_timeout=settings.circuit_breaker_reset_timeout,
        half_open_max_calls=settings.circuit_breaker_half_open_max_calls,
        max_attempts=settings.retry_max_attempts,
        base_delay=settings.retry_base_delay,
        multiplier=settings.retry_multiplier,
        max_jitter=settings.retry_max_jitter,
    )
    app.state.graph_client = graph_client

    logger.info(
        "service.started",
        service=settings.service_name,
        embedding_service_url=settings.embedding_service_url,
        graph_service_url=settings.graph_service_url,
        chromadb_host=settings.chromadb_host,
    )

    yield

    # --- Shutdown: close clients gracefully ---
    await embedding_client.close()
    await graph_client.close()
    logger.info("service.stopped", service=settings.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Ingestion Service",
        description="Document ingestion service for the Legislation RAG Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Include routers
    from src.api.health import health_router
    from src.api.metrics import metrics_router
    from src.api.routes import router

    app.include_router(router)
    app.include_router(health_router)
    app.include_router(metrics_router)

    # Add middleware (order matters: outermost first)
    from src.middleware.correlation_id import CorrelationIdMiddleware
    from src.middleware.error_handler import ErrorHandlerMiddleware

    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    return app


app = create_app()
