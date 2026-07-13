"""ChromaDB adapter for VectorStorePort.

Uses ChromaDB as the dense vector store for storing and querying
embedding vectors with metadata. Supports cosine similarity search,
document-level deletion, and near-duplicate detection.

ChromaDB runs locally for development or as a container in production.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import chromadb
import structlog

from src.domain.models.entities import Chunk, EmbeddingRecord, ScoredChunk
from src.domain.models.enums import ChunkingStrategy
from src.ports.vector_store import (
    VectorStorePort,  # noqa: F401 — documents which port this implements
)

logger = structlog.get_logger(__name__)

# Default configuration
DEFAULT_COLLECTION_NAME = "rag_chunks"
DEFAULT_DISTANCE_METRIC = "cosine"


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class ChromaDBVectorStoreAdapter:
    """ChromaDB adapter implementing VectorStorePort.

    Stores embedding vectors with metadata in a ChromaDB collection.
    Supports cosine similarity search, document-level deletion,
    and near-duplicate detection via similarity threshold.

    Usage:
        # Local (ephemeral for testing)
        adapter = ChromaDBVectorStoreAdapter()

        # Persistent local
        adapter = ChromaDBVectorStoreAdapter(persist_directory="./chroma_data")

        # Remote server
        adapter = ChromaDBVectorStoreAdapter(host="localhost", port=8000)
    """

    def __init__(
        self,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        host: str | None = None,
        port: int = 8000,
        persist_directory: str | None = None,
    ) -> None:
        """Initialize the ChromaDB vector store adapter.

        Args:
            collection_name: Name of the ChromaDB collection.
            host: Remote ChromaDB server host. If None, uses local client.
            port: Remote ChromaDB server port.
            persist_directory: Path for persistent local storage.
                If None and no host, uses ephemeral in-memory client.
        """
        self._collection_name = collection_name

        if host:
            self._client = chromadb.HttpClient(host=host, port=port)
        elif persist_directory:
            self._client = chromadb.PersistentClient(path=persist_directory)
        else:
            self._client = chromadb.Client()

        # Get or create the collection with cosine distance
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": DEFAULT_DISTANCE_METRIC},
        )

        logger.info(
            "chromadb_vector_store.initialized",
            collection=collection_name,
            host=host or "local",
            port=port if host else None,
            persist_directory=persist_directory,
            count=self._collection.count(),
        )

    async def store(self, embeddings: list[EmbeddingRecord]) -> None:
        """Store embedding records in ChromaDB.

        Each record includes the vector, chunk_id, document_id, and metadata.
        Uses upsert to handle re-indexing without duplicates.

        Args:
            embeddings: List of embedding records to store.

        Raises:
            VectorStoreError: If the ChromaDB operation fails.
        """
        if not embeddings:
            return

        start_time = time.perf_counter()

        try:
            ids = [str(record.chunk_id) for record in embeddings]
            vectors = [record.vector for record in embeddings]
            metadatas = [
                {
                    "document_id": str(record.document_id),
                    "chunk_id": str(record.chunk_id),
                    **{
                        k: v
                        for k, v in record.metadata.items()
                        if isinstance(v, (str, int, float, bool))
                    },
                }
                for record in embeddings
            ]

            # Store chunk text in documents field if available
            documents = [
                record.metadata.get("text", "")
                for record in embeddings
            ]

            self._collection.upsert(
                ids=ids,
                embeddings=vectors,
                metadatas=metadatas,
                documents=documents if any(documents) else None,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "chromadb_vector_store.store.success",
                count=len(embeddings),
                duration_ms=round(duration_ms, 2),
            )

        except Exception as e:
            logger.error(
                "chromadb_vector_store.store.failed",
                error=str(e),
                count=len(embeddings),
            )
            raise VectorStoreError(
                f"Failed to store embeddings: {e}",
                operation="store",
            ) from e

    async def search(
        self, query_vector: list[float], top_k: int
    ) -> list[ScoredChunk]:
        """Search for the most similar vectors by cosine similarity.

        Args:
            query_vector: The query embedding vector.
            top_k: Maximum number of results to return.

        Returns:
            List of ScoredChunk objects sorted by relevance (highest first).

        Raises:
            VectorStoreError: If the ChromaDB query fails.
        """
        start_time = time.perf_counter()

        try:
            count = self._collection.count()
            if count == 0:
                return []

            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k, count),
                include=["metadatas", "documents", "distances"],
            )

            scored_chunks = self._results_to_scored_chunks(results)

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "chromadb_vector_store.search.success",
                top_k=top_k,
                results_count=len(scored_chunks),
                duration_ms=round(duration_ms, 2),
            )

            return scored_chunks

        except Exception as e:
            logger.error(
                "chromadb_vector_store.search.failed",
                error=str(e),
                top_k=top_k,
            )
            raise VectorStoreError(
                f"Failed to search vectors: {e}",
                operation="search",
            ) from e

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors associated with a document.

        Args:
            document_id: The document UUID string whose chunks to remove.

        Raises:
            VectorStoreError: If the deletion fails.
        """
        start_time = time.perf_counter()

        try:
            self._collection.delete(
                where={"document_id": document_id},
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "chromadb_vector_store.delete_by_document.success",
                document_id=document_id,
                duration_ms=round(duration_ms, 2),
            )

        except Exception as e:
            logger.error(
                "chromadb_vector_store.delete_by_document.failed",
                error=str(e),
                document_id=document_id,
            )
            raise VectorStoreError(
                f"Failed to delete document vectors: {e}",
                operation="delete_by_document",
            ) from e

    async def find_similar(
        self, vector: list[float], threshold: float
    ) -> list[ScoredChunk]:
        """Find vectors with similarity above a threshold.

        Used for deduplication: checks if a chunk is too similar
        to existing content (cosine similarity > threshold).

        Args:
            vector: The embedding vector to compare against.
            threshold: Minimum similarity score (0.0 to 1.0).

        Returns:
            List of ScoredChunk objects above the threshold.

        Raises:
            VectorStoreError: If the query fails.
        """
        start_time = time.perf_counter()

        try:
            count = self._collection.count()
            if count == 0:
                return []

            results = self._collection.query(
                query_embeddings=[vector],
                n_results=min(10, count),
                include=["metadatas", "documents", "distances"],
            )

            scored_chunks = self._results_to_scored_chunks(results)

            # Filter by threshold (score is cosine similarity)
            filtered = [sc for sc in scored_chunks if sc.score >= threshold]

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "chromadb_vector_store.find_similar.success",
                threshold=threshold,
                candidates=len(scored_chunks),
                above_threshold=len(filtered),
                duration_ms=round(duration_ms, 2),
            )

            return filtered

        except Exception as e:
            logger.error(
                "chromadb_vector_store.find_similar.failed",
                error=str(e),
                threshold=threshold,
            )
            raise VectorStoreError(
                f"Failed to find similar vectors: {e}",
                operation="find_similar",
            ) from e

    def _results_to_scored_chunks(
        self, results: dict[str, Any]
    ) -> list[ScoredChunk]:
        """Convert ChromaDB query results to ScoredChunk objects.

        ChromaDB returns cosine distance (0 = identical, 2 = opposite).
        We convert to similarity: score = 1 - (distance / 2).
        """
        scored_chunks: list[ScoredChunk] = []

        if not results or not results.get("ids") or not results["ids"][0]:
            return scored_chunks

        ids = results["ids"][0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        for i, chunk_id in enumerate(ids):
            distance = distances[i] if i < len(distances) else 0.0
            score = 1.0 - (distance / 2.0)

            metadata = metadatas[i] if i < len(metadatas) else {}
            document_text = documents[i] if documents and i < len(documents) else ""

            doc_id_str = metadata.get("document_id", chunk_id)
            section = metadata.get("section", metadata.get("section_heading", ""))
            strategy_str = metadata.get("strategy", "fixed_size")
            char_count = metadata.get("char_count", len(document_text) if document_text else 0)

            try:
                chunk_uuid = UUID(chunk_id)
            except (ValueError, TypeError):
                chunk_uuid = UUID(int=0)

            try:
                doc_uuid = UUID(doc_id_str)
            except (ValueError, TypeError):
                doc_uuid = UUID(int=0)

            try:
                strategy = ChunkingStrategy(strategy_str)
            except ValueError:
                strategy = ChunkingStrategy.FIXED_SIZE

            chunk = Chunk(
                id=chunk_uuid,
                document_id=doc_uuid,
                index=metadata.get("index", 0),
                text=document_text or "",
                section_heading=section,
                strategy=strategy,
                char_count=int(char_count) if char_count else 0,
            )

            scored_chunks.append(
                ScoredChunk(
                    chunk=chunk,
                    score=score,
                    retrieval_method="dense",
                )
            )

        return scored_chunks

    @property
    def count(self) -> int:
        """Return the number of vectors in the collection."""
        return self._collection.count()

    @property
    def collection_name(self) -> str:
        """Return the collection name."""
        return self._collection_name
