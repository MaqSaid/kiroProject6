"""Indexing Service — coordinates writes to vector store, sparse index, and graph store.

Handles transactional indexing: if any write fails, rolls back successful ones.
Also provides deduplication checking and document re-indexing.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from src.domain.models.entities import (
    Chunk,
    EmbeddingRecord,
    ExtractedEntity,
    ExtractedRelationship,
)
from src.ports.embedding import EmbeddingPort
from src.ports.graph_store import GraphStorePort
from src.ports.sparse_index import SparseIndexPort
from src.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)

DEDUP_THRESHOLD = 0.95


class IndexingError(Exception):
    """Raised when indexing operations fail."""

    def __init__(self, message: str, step: str = "", partial: bool = False) -> None:
        self.step = step
        self.partial = partial
        super().__init__(message)


class IndexingService:
    """Coordinates writes to all three index stores.

    Handles:
    - Embedding generation + vector store writes
    - BM25 sparse index writes
    - Graph store entity/relationship writes
    - Deduplication checks before indexing
    - Document removal across all stores
    - Rollback on partial failures
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_store: VectorStorePort,
        sparse_index: SparseIndexPort,
        graph_store: GraphStorePort,
    ) -> None:
        self._embedding = embedding_port
        self._vector_store = vector_store
        self._sparse_index = sparse_index
        self._graph_store = graph_store

        logger.info("indexing_service.initialized")

    async def index_chunks(
        self,
        chunks: list[Chunk],
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Index chunks into vector store and sparse index.

        Generates embeddings, stores in vector store, and indexes in BM25.
        If vector store write fails after embedding, attempts rollback.

        Args:
            chunks: List of chunks to index.
            correlation_id: Request correlation ID.

        Returns:
            Dict with indexing results (counts, duration).

        Raises:
            IndexingError: If indexing fails critically.
        """
        if not chunks:
            return {"indexed": 0, "status": "empty"}

        start_time = time.perf_counter()

        # Step 1: Generate embeddings
        texts = [chunk.text for chunk in chunks]
        try:
            embeddings = await self._embedding.embed(texts)
        except Exception as e:
            logger.error(
                "indexing_service.embed_failed",
                error=str(e),
                correlation_id=correlation_id,
            )
            raise IndexingError(
                f"Embedding generation failed: {e}", step="embed"
            ) from e

        # Step 2: Store in vector store
        records = [
            EmbeddingRecord(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                vector=emb,
                metadata={
                    "text": chunk.text,
                    "section": chunk.section_heading,
                    "strategy": chunk.strategy.value,
                    "char_count": chunk.char_count,
                    "index": chunk.index,
                },
            )
            for chunk, emb in zip(chunks, embeddings, strict=True)
        ]

        try:
            await self._vector_store.store(records)
        except Exception as e:
            logger.error(
                "indexing_service.vector_store_failed",
                error=str(e),
                correlation_id=correlation_id,
            )
            raise IndexingError(
                f"Vector store write failed: {e}", step="vector_store"
            ) from e

        # Step 3: Index in BM25 sparse index
        try:
            await self._sparse_index.index(chunks)
        except Exception as e:
            # Attempt rollback of vector store
            logger.warning(
                "indexing_service.sparse_index_failed_rolling_back",
                error=str(e),
                correlation_id=correlation_id,
            )
            doc_id = str(chunks[0].document_id)
            try:
                await self._vector_store.delete_by_document(doc_id)
            except Exception:
                pass  # Best-effort rollback
            raise IndexingError(
                f"Sparse index write failed (rolled back vectors): {e}",
                step="sparse_index",
                partial=True,
            ) from e

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "indexing_service.index_chunks.success",
            chunk_count=len(chunks),
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        return {
            "indexed": len(chunks),
            "vector_store": "stored",
            "sparse_index": "stored",
            "duration_ms": round(duration_ms, 2),
            "status": "success",
        }

    async def index_entities(
        self,
        entities: list[ExtractedEntity],
        relationships: list[ExtractedRelationship],
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Store extracted entities and relationships in the graph store.

        Args:
            entities: Extracted entities to store.
            relationships: Extracted relationships to store.
            correlation_id: Request correlation ID.

        Returns:
            Dict with counts.
        """
        try:
            if entities:
                await self._graph_store.store_entities(entities)
            if relationships:
                await self._graph_store.store_relationships(relationships)

            logger.info(
                "indexing_service.index_entities.success",
                entity_count=len(entities),
                relationship_count=len(relationships),
                correlation_id=correlation_id,
            )

            return {
                "entities_stored": len(entities),
                "relationships_stored": len(relationships),
                "status": "success",
            }
        except Exception as e:
            logger.error(
                "indexing_service.index_entities.failed",
                error=str(e),
                correlation_id=correlation_id,
            )
            # Graph store failure is non-critical — pipeline continues
            return {
                "entities_stored": 0,
                "relationships_stored": 0,
                "status": "failed",
                "error": str(e),
            }

    async def check_duplicate(
        self,
        chunk: Chunk,
        correlation_id: str = "",
    ) -> tuple[bool, float]:
        """Check if a chunk is a near-duplicate of existing content.

        Args:
            chunk: The chunk to check.
            correlation_id: Request correlation ID.

        Returns:
            Tuple of (is_duplicate: bool, similarity: float).
            is_duplicate is True if similarity > DEDUP_THRESHOLD.
        """
        try:
            embedding = await self._embedding.embed_single(chunk.text)
            similar = await self._vector_store.find_similar(embedding, DEDUP_THRESHOLD)

            if similar:
                top_match = similar[0]
                logger.warning(
                    "indexing_service.duplicate_detected",
                    chunk_id=str(chunk.id),
                    similar_to=str(top_match.chunk.id),
                    similarity=top_match.score,
                    correlation_id=correlation_id,
                )
                return True, top_match.score

            return False, 0.0

        except Exception as e:
            logger.error(
                "indexing_service.check_duplicate.failed",
                error=str(e),
                correlation_id=correlation_id,
            )
            # On failure, assume not duplicate and proceed
            return False, 0.0

    async def remove_document_entries(
        self,
        document_id: str,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Remove all index entries for a document across all stores.

        Used before re-indexing to prevent stale entries.

        Args:
            document_id: UUID string of the document to remove.
            correlation_id: Request correlation ID.

        Returns:
            Dict with removal status per store.
        """
        start_time = time.perf_counter()
        results: dict[str, str] = {}

        try:
            await self._vector_store.delete_by_document(document_id)
            results["vector_store"] = "removed"
        except Exception as e:
            results["vector_store"] = f"failed: {e}"

        try:
            await self._sparse_index.delete_by_document(document_id)
            results["sparse_index"] = "removed"
        except Exception as e:
            results["sparse_index"] = f"failed: {e}"

        try:
            await self._graph_store.delete_by_document(document_id)
            results["graph_store"] = "removed"
        except Exception as e:
            results["graph_store"] = f"failed: {e}"

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "indexing_service.remove_document_entries.complete",
            document_id=document_id,
            results=results,
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        return {"document_id": document_id, "stores": results, "status": "complete"}
