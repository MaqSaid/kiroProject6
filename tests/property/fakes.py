"""In-memory fakes for property tests.

Provides fake implementations of service dependencies that don't require
external services (vector stores, embedding APIs, etc.).
"""

from __future__ import annotations

from typing import Any

from src.domain.models.entities import Chunk, ScoredChunk


class FakeIndexingService:
    """Fake IndexingService that accepts all chunks without external calls."""

    def __init__(self) -> None:
        self._indexed_chunks: list[Chunk] = []

    async def index_chunks(
        self, chunks: list[Chunk], correlation_id: str = ""
    ) -> dict[str, Any]:
        self._indexed_chunks.extend(chunks)
        return {"indexed": len(chunks), "status": "success"}

    async def check_duplicate(
        self, chunk: Chunk, correlation_id: str = ""
    ) -> tuple[bool, float]:
        """Never reports duplicates in testing."""
        return False, 0.0

    async def remove_document_entries(
        self, document_id: str, correlation_id: str = ""
    ) -> dict[str, Any]:
        self._indexed_chunks = [
            c for c in self._indexed_chunks if str(c.document_id) != document_id
        ]
        return {"document_id": document_id, "status": "complete"}

    @property
    def indexed_chunks(self) -> list[Chunk]:
        return self._indexed_chunks.copy()


class FakeEmbeddingPort:
    """Fake EmbeddingPort that returns deterministic embeddings."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic embeddings based on text hash."""
        return [self._text_to_vector(t) for t in texts]

    async def embed_single(self, text: str) -> list[float]:
        return self._text_to_vector(text)

    def _text_to_vector(self, text: str) -> list[float]:
        """Generate a deterministic vector from text content."""
        h = hash(text)
        return [((h >> (i * 4)) & 0xF) / 15.0 for i in range(self._dimensions)]


class FakeVectorStore:
    """Fake VectorStorePort for testing."""

    def __init__(self) -> None:
        self._records: dict[str, Any] = {}

    async def store(self, records: list[Any]) -> None:
        for r in records:
            self._records[str(r.chunk_id)] = r

    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        return []

    async def find_similar(
        self, vector: list[float], threshold: float
    ) -> list[ScoredChunk]:
        return []

    async def delete_by_document(self, document_id: str) -> None:
        self._records = {
            k: v for k, v in self._records.items()
            if str(v.document_id) != document_id
        }


class FakeSparseIndex:
    """Fake SparseIndexPort for testing."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    async def index(self, chunks: list[Chunk]) -> None:
        self._chunks.extend(chunks)

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        return []

    async def delete_by_document(self, document_id: str) -> None:
        self._chunks = [c for c in self._chunks if str(c.document_id) != document_id]


class FakeGraphStore:
    """Fake GraphStorePort for testing."""

    async def store_entities(self, entities: list[Any]) -> None:
        pass

    async def store_relationships(self, relationships: list[Any]) -> None:
        pass

    async def traverse(self, query: str, max_hops: int = 2) -> list[ScoredChunk]:
        return []

    async def delete_by_document(self, document_id: str) -> None:
        pass
