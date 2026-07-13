"""FastAPI application factory with dependency injection.

Creates the application, wires all services and adapters, and registers routes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.domain.events.bus import InMemoryEventBus
from src.domain.models.enums import ChunkingStrategy, DocumentFormat
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.fixed_size_chunker import FixedSizeChunker
from src.domain.processing.normalizer import DocumentNormalizer
from src.domain.processing.plaintext_normalizer import PlaintextNormalizer
from src.domain.services.generation_service import GenerationService
from src.domain.services.indexing_service import IndexingService
from src.domain.services.ingestion_service import IngestionService
from src.domain.services.retrieval_service import RetrievalService
from src.domain.services.security_service import SecurityService
from src.infrastructure.bedrock_embedding import BedrockEmbeddingAdapter
from src.infrastructure.bm25_sparse_index import BM25SparseIndexAdapter
from src.infrastructure.chromadb_vector_store import ChromaDBVectorStoreAdapter
from src.infrastructure.cross_encoder_reranker import CrossEncoderRerankerAdapter
from src.infrastructure.in_memory_graph_store import InMemoryGraphStore
from src.infrastructure.local_document_store import LocalDocumentStore

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and teardown services."""
    logger.info("app.startup")

    # Infrastructure adapters
    # Embeddings use us-east-1 (Titan not available in ap-southeast-4)
    app.state.embedding = BedrockEmbeddingAdapter(region_name="us-east-1")
    app.state.vector_store = ChromaDBVectorStoreAdapter(persist_directory="./data/chroma")
    app.state.sparse_index = BM25SparseIndexAdapter()
    app.state.graph_store = InMemoryGraphStore()
    app.state.reranker = CrossEncoderRerankerAdapter()
    app.state.event_bus = InMemoryEventBus()
    app.state.document_store = LocalDocumentStore(base_dir=Path("./data/documents"))

    # Processing
    normalizer = DocumentNormalizer()
    normalizer.register(DocumentFormat.PLAINTEXT, PlaintextNormalizer())
    app.state.normalizer = normalizer

    chunker_factory = ChunkerFactory()
    chunker_factory.register(
        ChunkingStrategy.FIXED_SIZE, FixedSizeChunker(chunk_size=500, overlap=100)
    )
    app.state.chunker_factory = chunker_factory

    # Domain services
    app.state.indexing_service = IndexingService(
        embedding_port=app.state.embedding,
        vector_store=app.state.vector_store,
        sparse_index=app.state.sparse_index,
        graph_store=app.state.graph_store,
    )
    app.state.security_service = SecurityService()
    app.state.ingestion_service = IngestionService(
        document_store=app.state.document_store,
        normalizer=app.state.normalizer,
        chunker_factory=app.state.chunker_factory,
        indexing_service=app.state.indexing_service,
        security_service=app.state.security_service,
        event_bus=app.state.event_bus,
    )
    app.state.retrieval_service = RetrievalService(
        embedding_port=app.state.embedding,
        vector_store=app.state.vector_store,
        sparse_index=app.state.sparse_index,
        graph_store=app.state.graph_store,
        reranker=app.state.reranker,
    )
    app.state.generation_service = GenerationService(
        model_id="apac.amazon.nova-pro-v1:0",
        region_name="ap-southeast-4",
    )

    logger.info("app.startup.complete")
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RAG Pipeline API",
        description="Production RAG pipeline with hybrid search",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        request.state.correlation_id = correlation_id
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    from src.api.routes.pipeline import router as pipeline_router

    app.include_router(pipeline_router)

    return app
