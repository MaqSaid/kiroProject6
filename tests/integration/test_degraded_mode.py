"""Integration tests for degraded mode behavior.

Tests that the retrieval pipeline degrades gracefully when components
are unavailable, falling back to available search methods.

Validates: Requirements 4.7, 4.8, 4.11, 5.7, 15.5, 15.6
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from src.domain.models.entities import Chunk, ScoredChunk
from src.domain.models.enums import ChunkingStrategy
from src.domain.services.retrieval_service import RetrievalService


# --- Fakes that simulate failures ---


class FailingEmbeddingPort:
    """Embedding port that always succeeds."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]

    async def embed_single(self, text: str) -> list[float]:
        return [0.1] * 8


class FailingSparseIndex:
    """Sparse index that raises an error (simulating BM25 unavailable)."""

    async def index(self, chunks: list) -> None:
        pass

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        raise ConnectionError("BM25 index unavailable")

    async def delete_by_document(self, document_id: str) -> None:
        pass


class FailingGraphStore:
    """Graph store that raises an error (simulating graph unavailable)."""

    async def store_entities(self, entities: list) -> None:
        pass

    async def store_relationships(self, relationships: list) -> None:
        pass

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        raise ConnectionError("Graph store unavailable")

    async def delete_by_document(self, document_id: str) -> None:
        pass


class WorkingVectorStore:
    """Vector store that returns results."""

    async def store(self, records: list) -> None:
        pass

    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        return [
            ScoredChunk(
                chunk=Chunk(
                    id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    index=0,
                    text="Dense search result content.",
                    section_heading="Results",
                    strategy=ChunkingStrategy.FIXED_SIZE,
                    char_count=28,
                ),
                score=0.85,
                retrieval_method="dense",
            )
        ]

    async def find_similar(self, vector: list[float], threshold: float) -> list[ScoredChunk]:
        return []

    async def delete_by_document(self, document_id: str) -> None:
        pass


class WorkingSparseIndex:
    """Sparse index that returns results."""

    async def index(self, chunks: list) -> None:
        pass

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        return [
            ScoredChunk(
                chunk=Chunk(
                    id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    index=0,
                    text="Sparse search result.",
                    section_heading="BM25",
                    strategy=ChunkingStrategy.FIXED_SIZE,
                    char_count=21,
                ),
                score=0.7,
                retrieval_method="sparse",
            )
        ]

    async def delete_by_document(self, document_id: str) -> None:
        pass


class FakeReranker:
    """Reranker that passes through top results."""

    async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        sorted_cands = sorted(candidates, key=lambda sc: sc.score, reverse=True)
        return [
            ScoredChunk(chunk=sc.chunk, score=sc.score, retrieval_method="reranked")
            for sc in sorted_cands[:top_n]
        ]


# --- Tests ---


@pytest.mark.integration
def test_sparse_unavailable_returns_dense_results():
    """Requirement 4.7: BM25 unavailable → dense+graph fallback.

    When BM25 is unavailable, retrieval still returns results from dense search.
    """
    service = RetrievalService(
        embedding_port=FailingEmbeddingPort(),
        vector_store=WorkingVectorStore(),
        sparse_index=FailingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FakeReranker(),
    )

    results = asyncio.run(service.retrieve("test query", top_k=5))

    # Should still get results from dense search
    assert len(results) >= 1
    # Results should be reranked
    assert all(sc.retrieval_method == "reranked" for sc in results)


@pytest.mark.integration
def test_graph_unavailable_returns_dense_plus_sparse():
    """Requirement 4.8: Graph unavailable → dense+sparse fallback."""
    service = RetrievalService(
        embedding_port=FailingEmbeddingPort(),
        vector_store=WorkingVectorStore(),
        sparse_index=WorkingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FakeReranker(),
    )

    results = asyncio.run(service.retrieve("test query", top_k=5))

    # Should get results from both dense and sparse
    assert len(results) >= 1


@pytest.mark.integration
def test_all_search_methods_fail_returns_empty():
    """Requirement 4.11: All methods fail → empty results (not crash)."""

    class FailingVectorStore:
        async def store(self, records: list) -> None:
            pass

        async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
            raise ConnectionError("Vector store unavailable")

        async def find_similar(self, vector: list[float], threshold: float) -> list[ScoredChunk]:
            return []

        async def delete_by_document(self, document_id: str) -> None:
            pass

    service = RetrievalService(
        embedding_port=FailingEmbeddingPort(),
        vector_store=FailingVectorStore(),
        sparse_index=FailingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FakeReranker(),
    )

    results = asyncio.run(service.retrieve("test query", top_k=5))

    # Should gracefully return empty, not raise
    assert results == [] or len(results) == 0


@pytest.mark.integration
def test_embedding_failure_returns_empty():
    """Requirement 15.6: Embedding service failure returns empty results."""

    class FailingEmbedding:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise ConnectionError("Embedding service down")

        async def embed_single(self, text: str) -> list[float]:
            raise ConnectionError("Embedding service down")

    service = RetrievalService(
        embedding_port=FailingEmbedding(),
        vector_store=WorkingVectorStore(),
        sparse_index=WorkingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FakeReranker(),
    )

    # Embedding failure during query embedding should return empty
    results = asyncio.run(service.retrieve("test query", top_k=5))
    assert results == []


@pytest.mark.integration
def test_reranker_failure_falls_back_to_fused():
    """Requirement 15.5: Reranker failure → return fused results without reranking."""

    class FailingReranker:
        async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
            raise RuntimeError("Reranker model unavailable")

    service = RetrievalService(
        embedding_port=FailingEmbeddingPort(),
        vector_store=WorkingVectorStore(),
        sparse_index=WorkingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FailingReranker(),
    )

    results = asyncio.run(service.retrieve("test query", top_k=5))

    # Should still return results (from RRF fusion without reranking)
    assert len(results) >= 1
