"""Query Service FastAPI application.

Coordinates the RAG agent pipeline (Retrieval, Generation,
Citation Verification, Evaluation) for legislation queries.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from service_client import CircuitBreaker, ResilientClient, RetryPolicy

from src.agents.agent_config import load_all_agent_prompts
from src.agents.citation_agent import CitationVerificationAgent
from src.agents.evaluation_agent import EvaluationAgent
from src.agents.generation_agent import GenerationAgent
from src.agents.retrieval_agent import RetrievalAgent
from src.config import Settings
from src.infrastructure.bm25_index import BM25Index
from src.infrastructure.chromadb_store import ChromaDBStore
from src.logging_config import configure_logging
from src.orchestrator import RAGOrchestrator

logger = structlog.get_logger(__name__)


def _create_embedding_client(settings: Settings) -> ResilientClient:
    """Create ResilientClient for the Embedding Service."""
    circuit_breaker = CircuitBreaker(
        service_name="embedding-service",
        failure_threshold=settings.circuit_failure_threshold,
        reset_timeout=settings.circuit_reset_timeout,
    )
    retry_policy = RetryPolicy(
        max_attempts=3,
        base_delay=1.0,
        multiplier=2.0,
        max_jitter=0.5,
    )
    return ResilientClient(
        base_url=settings.embedding_service_url,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
        timeout=settings.embedding_timeout,
    )


def _create_graph_client(settings: Settings) -> ResilientClient:
    """Create ResilientClient for the Graph Service."""
    circuit_breaker = CircuitBreaker(
        service_name="graph-service",
        failure_threshold=settings.circuit_failure_threshold,
        reset_timeout=settings.circuit_reset_timeout,
    )
    retry_policy = RetryPolicy(
        max_attempts=3,
        base_delay=1.0,
        multiplier=2.0,
        max_jitter=0.5,
    )
    return ResilientClient(
        base_url=settings.graph_service_url,
        circuit_breaker=circuit_breaker,
        retry_policy=retry_policy,
        timeout=settings.graph_timeout,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle — initialize and cleanup resources."""
    settings = Settings()
    configure_logging()
    logger.info("service.starting", service=settings.service_name)

    # Initialize inter-service clients
    embedding_client = _create_embedding_client(settings)
    graph_client = _create_graph_client(settings)

    # Load and validate all agent prompts (raises ConfigurationError if any missing/empty)
    agent_prompts = load_all_agent_prompts()
    logger.info("service.prompts_loaded", agent_count=5)

    # Initialize local stores
    chromadb_store = ChromaDBStore(
        host=settings.chromadb_host,
        port=settings.chromadb_port,
        collection=settings.chromadb_collection,
    )
    await chromadb_store.initialize()

    bm25_index = BM25Index()
    await bm25_index.initialize()

    # Initialize agents with system prompts and real dependencies
    retrieval_agent = RetrievalAgent(
        embedding_client=embedding_client,
        graph_client=graph_client,
        chromadb_store=chromadb_store,
        bm25_index=bm25_index,
        system_prompt=agent_prompts.retrieval.system_prompt,
    )
    generation_agent = GenerationAgent(
        system_prompt=agent_prompts.generation.system_prompt,
    )
    citation_agent = CitationVerificationAgent(
        system_prompt=agent_prompts.citation_verification.system_prompt,
    )
    evaluation_agent = EvaluationAgent(
        system_prompt=agent_prompts.evaluation.system_prompt,
    )

    # Create orchestrator and store in app.state
    orchestrator = RAGOrchestrator(
        retrieval_agent=retrieval_agent,
        generation_agent=generation_agent,
        citation_agent=citation_agent,
        evaluation_agent=evaluation_agent,
    )
    app.state.orchestrator = orchestrator
    app.state.settings = settings

    # Store client references for health checks
    app.state.embedding_client = embedding_client
    app.state.graph_client = graph_client

    logger.info("service.started", service=settings.service_name)
    yield
    # Cleanup
    logger.info("service.stopping", service=settings.service_name)
    # Close clients
    await embedding_client.close()
    await graph_client.close()
    logger.info("service.stopped", service=settings.service_name)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Query Service",
        description="RAG query orchestration for the Legislation Platform",
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
