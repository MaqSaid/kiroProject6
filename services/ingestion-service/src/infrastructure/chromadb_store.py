"""ChromaDB vector store for the Ingestion Service.

Stores embeddings received from the Embedding Service into ChromaDB collections.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Default collection name for legislation documents
COLLECTION_NAME = "legislation_chunks"


class ChromaDBStore:
    """ChromaDB vector store that stores embeddings for document chunks."""

    def __init__(self, host: str = "chromadb", port: int = 8000) -> None:
        self._host = host
        self._port = port
        self._client: Any = None
        self._collection: Any = None

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        import chromadb

        self._client = chromadb.HttpClient(host=self._host, port=self._port)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "chromadb_initialized",
            host=self._host,
            port=self._port,
            collection=COLLECTION_NAME,
        )

    @property
    def is_initialized(self) -> bool:
        """Check if the store is initialized."""
        return self._client is not None and self._collection is not None

    def store_vectors(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Store vectors with documents and metadata in ChromaDB.

        Args:
            ids: Unique IDs for each chunk.
            vectors: Embedding vectors from the Embedding Service.
            documents: Text content of each chunk.
            metadatas: Metadata dicts for each chunk.
        """
        if not self._collection:
            raise RuntimeError("ChromaDB store not initialized")

        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("chromadb_vectors_stored", count=len(ids))

    def heartbeat(self) -> bool:
        """Check if ChromaDB is reachable."""
        if not self._client:
            return False
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False
