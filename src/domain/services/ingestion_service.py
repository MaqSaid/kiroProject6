"""Ingestion Service — orchestrates the document processing pipeline.

Coordinates: validate → normalize → chunk → deduplicate → index → emit event.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from src.domain.events.bus import EventBus
from src.domain.events.events import DocumentIngestedEvent
from src.domain.models.entities import RawDocument
from src.domain.models.enums import ChunkingStrategy
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.normalizer import DocumentNormalizer
from src.domain.services.indexing_service import IndexingService
from src.domain.services.security_service import SecurityService
from src.ports.document_store import DocumentStorePort

logger = structlog.get_logger(__name__)

SUPPORTED_FORMATS = {"markdown", "plaintext", "html", "pdf"}
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024  # 50MB


class IngestionError(Exception):
    """Raised when ingestion fails."""

    def __init__(self, message: str, step: str = "", document_id: str = "") -> None:
        self.step = step
        self.document_id = document_id
        super().__init__(message)


class IngestionService:
    """Orchestrates the full document ingestion pipeline.

    Pipeline: validate → store → normalize → chunk → deduplicate → index → emit event.
    """

    def __init__(
        self,
        document_store: DocumentStorePort,
        normalizer: DocumentNormalizer,
        chunker_factory: ChunkerFactory,
        indexing_service: IndexingService,
        security_service: SecurityService,
        event_bus: EventBus,
    ) -> None:
        self._document_store = document_store
        self._normalizer = normalizer
        self._chunker_factory = chunker_factory
        self._indexing_service = indexing_service
        self._security_service = security_service
        self._event_bus = event_bus

        logger.info("ingestion_service.initialized")

    async def ingest(
        self,
        document: RawDocument,
        strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Ingest a document through the full pipeline.

        Args:
            document: The raw document to ingest.
            strategy: Chunking strategy to use.
            correlation_id: Request correlation ID.

        Returns:
            Dict with ingestion results.

        Raises:
            IngestionError: If a critical step fails.
        """
        if not correlation_id:
            correlation_id = str(uuid4())

        start_time = time.perf_counter()
        doc_id = str(document.id)

        logger.info(
            "ingestion_service.ingest.start",
            document_id=doc_id,
            filename=document.filename,
            format=document.format.value,
            size_bytes=document.size_bytes,
            strategy=strategy.value,
            correlation_id=correlation_id,
        )

        # Step 1: Validate
        self._validate(document, correlation_id)

        # Step 2: Store raw document
        await self._document_store.store(document)

        # Step 3: Normalize
        try:
            normalized = self._normalizer.normalize(document)
        except Exception as e:
            raise IngestionError(
                f"Normalization failed: {e}", step="normalize", document_id=doc_id
            ) from e

        # Step 4: Chunk
        try:
            chunker = self._chunker_factory.get_chunker(strategy)
            chunks = chunker.chunk(normalized)
        except Exception as e:
            raise IngestionError(
                f"Chunking failed: {e}", step="chunk", document_id=doc_id
            ) from e

        if not chunks:
            return {
                "document_id": doc_id,
                "filename": document.filename,
                "format": document.format.value,
                "chunk_count": 0,
                "entity_count": 0,
                "status": "completed_empty",
                "correlation_id": correlation_id,
            }

        # Step 5: Deduplicate
        duplicate_count = 0
        unique_chunks = []
        for chunk in chunks:
            is_dup, similarity = await self._indexing_service.check_duplicate(
                chunk, correlation_id
            )
            if is_dup:
                duplicate_count += 1
            else:
                unique_chunks.append(chunk)

        # Step 6: Index unique chunks
        if unique_chunks:
            await self._indexing_service.index_chunks(unique_chunks, correlation_id)

        # Step 7: Emit event
        event = DocumentIngestedEvent(
            document_id=document.id,
            format=document.format,
            size_bytes=document.size_bytes,
            timestamp=datetime.utcnow(),
            chunk_count=len(unique_chunks),
            entity_count=0,
        )
        await self._event_bus.publish(event)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "ingestion_service.ingest.complete",
            document_id=doc_id,
            chunk_count=len(unique_chunks),
            duplicate_count=duplicate_count,
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        return {
            "document_id": doc_id,
            "filename": document.filename,
            "format": document.format.value,
            "chunk_count": len(unique_chunks),
            "duplicate_count": duplicate_count,
            "entity_count": 0,
            "status": "success",
            "correlation_id": correlation_id,
            "duration_ms": round(duration_ms, 2),
        }

    async def reindex(
        self,
        document_id: str,
        strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        """Re-index an existing document with a different strategy.

        Args:
            document_id: UUID string of the document to re-index.
            strategy: New chunking strategy to apply.
            correlation_id: Request correlation ID.

        Returns:
            Dict with re-indexing results.
        """
        if not correlation_id:
            correlation_id = str(uuid4())

        # Remove old entries
        await self._indexing_service.remove_document_entries(document_id, correlation_id)

        # Retrieve and re-ingest
        document = await self._document_store.retrieve(document_id)
        return await self.ingest(document, strategy, correlation_id)

    def _validate(self, document: RawDocument, correlation_id: str) -> None:
        """Validate document before processing."""
        if document.format.value not in SUPPORTED_FORMATS:
            raise IngestionError(
                f"Unsupported format: {document.format.value}. Supported: {SUPPORTED_FORMATS}",
                step="validate",
                document_id=str(document.id),
            )

        if document.size_bytes == 0:
            raise IngestionError(
                "Document is empty (0 bytes)", step="validate", document_id=str(document.id)
            )

        if document.size_bytes > MAX_DOCUMENT_SIZE:
            raise IngestionError(
                f"Document exceeds {MAX_DOCUMENT_SIZE} byte limit ({document.size_bytes})",
                step="validate",
                document_id=str(document.id),
            )

        if ".." in document.filename or "\\" in document.filename:
            raise IngestionError(
                f"Filename contains path traversal characters: {document.filename}",
                step="validate",
                document_id=str(document.id),
            )
