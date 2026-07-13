"""Demo script showing how to use RAG pipeline agents standalone.

This demonstrates agent usage with mock ports for local testing.
Run with: python -m src.agents.demo

Prerequisites:
    pip install strands-agents strands-agents-tools
    export AWS_ACCESS_KEY_ID=... (or AWS_BEDROCK_API_KEY=...)
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_REGION=us-east-1

    Ensure model access is enabled in Bedrock Console for Claude Sonnet.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from src.domain.events.bus import InMemoryEventBus
from src.domain.models.entities import (
    Chunk,
    EmbeddingRecord,
    ExtractedEntity,
    ExtractedRelationship,
    RawDocument,
    ScoredChunk,
)
from src.domain.models.enums import ChunkingStrategy, DocumentFormat
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.fixed_size_chunker import FixedSizeChunker
from src.domain.processing.normalizer import DocumentNormalizer
from src.domain.processing.plaintext_normalizer import PlaintextNormalizer

# --- Mock Port Implementations for Demo ---


class MockEmbeddingPort:
    """Mock embedding port that returns random vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import random

        return [[random.uniform(-1, 1) for _ in range(384)] for _ in texts]

    async def embed_single(self, text: str) -> list[float]:
        import random

        return [random.uniform(-1, 1) for _ in range(384)]


class MockVectorStore:
    """Mock vector store with in-memory storage."""

    def __init__(self) -> None:
        self._store: list[EmbeddingRecord] = []

    async def store(self, embeddings: list[EmbeddingRecord]) -> None:
        self._store.extend(embeddings)

    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        # Return some mock results
        results = []
        for record in self._store[:top_k]:
            chunk = Chunk(
                id=record.chunk_id,
                document_id=record.document_id,
                index=0,
                text=record.metadata.get("text", "Sample text from vector store"),
                section_heading=record.metadata.get("section", ""),
                strategy=ChunkingStrategy.FIXED_SIZE,
                char_count=100,
            )
            results.append(ScoredChunk(chunk=chunk, score=0.85, retrieval_method="dense"))
        return results

    async def delete_by_document(self, document_id: str) -> None:
        self._store = [r for r in self._store if str(r.document_id) != document_id]

    async def find_similar(self, vector: list[float], threshold: float) -> list[ScoredChunk]:
        return []


class MockSparseIndex:
    """Mock BM25 sparse index."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    async def index(self, chunks: list[Chunk]) -> None:
        self._chunks.extend(chunks)

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        results = []
        for chunk in self._chunks[:top_k]:
            if any(word.lower() in chunk.text.lower() for word in query.split()):
                results.append(
                    ScoredChunk(chunk=chunk, score=0.7, retrieval_method="sparse")
                )
        return results[:top_k]

    async def delete_by_document(self, document_id: str) -> None:
        self._chunks = [c for c in self._chunks if str(c.document_id) != document_id]


class MockGraphStore:
    """Mock knowledge graph store."""

    def __init__(self) -> None:
        self._entities: list[ExtractedEntity] = []
        self._relationships: list[ExtractedRelationship] = []

    async def store_entities(self, entities: list[ExtractedEntity]) -> None:
        self._entities.extend(entities)

    async def store_relationships(self, relationships: list[ExtractedRelationship]) -> None:
        self._relationships.extend(relationships)

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        return []

    async def delete_by_document(self, document_id: str) -> None:
        pass


class MockReranker:
    """Mock cross-encoder reranker."""

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        # Simple mock: just return top_n sorted by existing score
        sorted_candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
        return sorted_candidates[:top_n]


class MockDocumentStore:
    """Mock document store with in-memory storage."""

    def __init__(self) -> None:
        self._documents: dict[str, RawDocument] = {}

    async def store(self, document: RawDocument) -> str:
        doc_id = str(document.id)
        self._documents[doc_id] = document
        return doc_id

    async def retrieve(self, document_id: str) -> RawDocument:
        if document_id not in self._documents:
            raise KeyError(f"Document not found: {document_id}")
        return self._documents[document_id]

    async def list_documents(self, filters: Any = None) -> list:
        return []

    async def delete(self, document_id: str) -> None:
        self._documents.pop(document_id, None)


def setup_demo_orchestrator():
    """Set up the RAG orchestrator with mock ports for demo purposes."""
    from src.agents.orchestrator import RAGOrchestrator

    # Create mock ports
    embedding_port = MockEmbeddingPort()
    vector_store = MockVectorStore()
    sparse_index = MockSparseIndex()
    graph_store = MockGraphStore()
    reranker = MockReranker()
    document_store = MockDocumentStore()
    event_bus = InMemoryEventBus()

    # Set up normalizer
    normalizer = DocumentNormalizer()
    normalizer.register(DocumentFormat.PLAINTEXT, PlaintextNormalizer())

    # Set up chunker factory
    chunker_factory = ChunkerFactory()
    chunker_factory.register(ChunkingStrategy.FIXED_SIZE, FixedSizeChunker())

    # Create orchestrator
    orchestrator = RAGOrchestrator(
        embedding_port=embedding_port,
        vector_store=vector_store,
        sparse_index=sparse_index,
        graph_store=graph_store,
        reranker=reranker,
        document_store=document_store,
        normalizer=normalizer,
        chunker_factory=chunker_factory,
        event_bus=event_bus,
    )

    return orchestrator, document_store


def demo_ask():
    """Demo: Ask a question through the agent pipeline."""
    print("=" * 60)
    print("DEMO: Ask Pipeline (Retrieval → Generation → Verification)")
    print("=" * 60)

    orchestrator, _ = setup_demo_orchestrator()

    query = "What is the deployment process for our application?"
    print(f"\nQuery: {query}\n")

    response = orchestrator.ask(query)
    print(f"Response:\n{response}")


def demo_ingest():
    """Demo: Ingest a document through the agent pipeline."""
    print("=" * 60)
    print("DEMO: Ingestion Pipeline")
    print("=" * 60)

    orchestrator, document_store = setup_demo_orchestrator()

    # Create a sample document
    doc_id = uuid.uuid4()
    sample_doc = RawDocument(
        id=doc_id,
        filename="deployment-guide.txt",
        format=DocumentFormat.PLAINTEXT,
        content=b"""Deployment Guide

Our application is deployed using Docker containers orchestrated by Kubernetes.

Step 1: Build the Docker image using the Dockerfile in the project root.
Step 2: Push the image to our container registry.
Step 3: Apply the Kubernetes manifests in the infrastructure/ directory.
Step 4: Verify the deployment using kubectl get pods.

Rollback procedure: Use kubectl rollout undo if the new deployment fails health checks.
""",
        uploaded_by="demo-user",
        uploaded_at=datetime.utcnow(),
        size_bytes=400,
    )

    # Store the document
    asyncio.run(document_store.store(sample_doc))

    print(f"\nDocument: {sample_doc.filename} (ID: {doc_id})")
    print(f"Size: {sample_doc.size_bytes} bytes\n")

    response = orchestrator.ingest(str(doc_id))
    print(f"Response:\n{response}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        demo_ingest()
    else:
        demo_ask()
