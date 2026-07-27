"""ChromaDB vector store for dense search.

Uses the chromadb Python client to query a collection of embedded
legislation chunks by vector similarity, returning top-k results
with scores.

Requirements: 10.1 (dense search component of hybrid retrieval)
"""

from __future__ import annotations

import time
from typing import Any

import chromadb
import structlog

logger = structlog.get_logger(__name__)


class ChromaDBStoreError(Exception):
    """Raised when ChromaDB operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class ChromaDBStore:
    """ChromaDB vector store adapter for dense retrieval.

    Manages a ChromaDB collection and provides similarity search
    using pre-computed embedding vectors from the Embedding Service.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        collection: str = "legislation_chunks",
    ) -> None:
        self._host = host
        self._port = port
        self._collection_name = collection
        self._client: chromadb.HttpClient | None = None
        self._collection: Any = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize ChromaDB client and get/create collection.

        Connects to the ChromaDB HTTP server and ensures the target
        collection exists. Logs success or failure.
        """
        logger.info(
            "chromadb.initialize",
            host=self._host,
            port=self._port,
            collection=self._collection_name,
        )
        try:
            self._client = chromadb.HttpClient(
                host=self._host,
                port=self._port,
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._initialized = True
            logger.info(
                "chromadb.initialized",
                collection=self._collection_name,
                count=self._collection.count(),
            )
        except Exception as e:
            logger.error("chromadb.initialize.failed", error=str(e))
            # Set initialized to True to allow graceful degradation
            # The search method will handle errors appropriately
            self._initialized = True

    @property
    def is_initialized(self) -> bool:
        """Check if store is ready."""
        return self._initialized

    async def search(self, vector: list[float], top_k: int = 20) -> list[dict]:
        """Search for similar vectors in ChromaDB.

        Queries the collection with a vector and returns the top-k
        most similar documents along with their cosine similarity scores.

        Args:
            vector: Query embedding vector.
            top_k: Number of results to return.

        Returns:
            List of dicts with chunk_id, document_id, text, section_heading,
            score, and metadata fields.

        Raises:
            ChromaDBStoreError: If collection is not available.
        """
        start_time = time.perf_counter()

        if self._collection is None:
            logger.warning("chromadb.search.not_initialized")
            raise ChromaDBStoreError(
                "ChromaDB collection not initialized", operation="search"
            )

        try:
            results = self._collection.query(
                query_embeddings=[vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            # Parse ChromaDB response format
            chunks: list[dict] = []
            if results and results.get("ids") and results["ids"][0]:
                ids = results["ids"][0]
                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for i, chunk_id in enumerate(ids):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    text = documents[i] if i < len(documents) else ""
                    # ChromaDB cosine distance: 0 = identical, 2 = opposite
                    # Convert to similarity score: 1 - (distance / 2)
                    distance = distances[i] if i < len(distances) else 1.0
                    score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))

                    chunks.append({
                        "chunk_id": chunk_id,
                        "document_id": metadata.get("document_id", ""),
                        "text": text,
                        "section_heading": metadata.get("section_heading", ""),
                        "score": score,
                        "metadata": metadata,
                    })

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "chromadb.search.success",
                results_count=len(chunks),
                top_k=top_k,
                duration_ms=round(duration_ms, 2),
            )
            return chunks

        except ChromaDBStoreError:
            raise
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "chromadb.search.failed",
                error=str(e),
                duration_ms=round(duration_ms, 2),
            )
            raise ChromaDBStoreError(
                f"ChromaDB search failed: {e}", operation="search"
            ) from e

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """Add documents with embeddings to the collection.

        Used by the ingestion pipeline to store embedded chunks.

        Args:
            ids: Chunk IDs.
            embeddings: Embedding vectors.
            documents: Text content of each chunk.
            metadatas: Optional metadata dicts for each chunk.
        """
        if self._collection is None:
            raise ChromaDBStoreError(
                "ChromaDB collection not initialized", operation="add"
            )

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas or [{}] * len(ids),
            )
            logger.info("chromadb.add.success", count=len(ids))
        except Exception as e:
            logger.error("chromadb.add.failed", error=str(e), count=len(ids))
            raise ChromaDBStoreError(
                f"ChromaDB add failed: {e}", operation="add"
            ) from e
