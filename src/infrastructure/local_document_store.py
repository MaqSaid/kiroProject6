"""Local filesystem adapter for DocumentStorePort.

Stores raw documents on local filesystem for development use.
An S3 adapter can be provided as an alternate for production.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from src.domain.models.entities import DocumentMetadata, RawDocument
from src.domain.models.enums import DocumentFormat

logger = structlog.get_logger(__name__)


class DocumentNotFoundError(Exception):
    """Raised when a requested document is not found in the store."""

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"Document not found: {document_id}")


class LocalDocumentStore:
    """Local filesystem adapter implementing DocumentStorePort.

    Stores documents in UUID-based subdirectories with JSON sidecar
    metadata files alongside raw content.

    Directory structure:
        base_dir/
            <uuid>/
                content.bin     — raw document bytes
                metadata.json   — document metadata as JSON sidecar
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "local_document_store.initialized",
            base_dir=str(self._base_dir),
        )

    def _document_dir(self, document_id: str) -> Path:
        """Get the directory for a specific document by ID."""
        return self._base_dir / document_id

    def _content_path(self, document_id: str) -> Path:
        """Get the path to raw content file."""
        return self._document_dir(document_id) / "content.bin"

    def _metadata_path(self, document_id: str) -> Path:
        """Get the path to the JSON sidecar metadata file."""
        return self._document_dir(document_id) / "metadata.json"

    def _serialize_metadata(self, document: RawDocument) -> dict[str, Any]:
        """Serialize document metadata to a JSON-compatible dict."""
        return {
            "id": str(document.id),
            "filename": document.filename,
            "format": document.format.value,
            "uploaded_by": document.uploaded_by,
            "uploaded_at": document.uploaded_at.isoformat(),
            "size_bytes": document.size_bytes,
        }

    def _deserialize_document(self, document_id: str) -> RawDocument:
        """Deserialize a document from filesystem storage."""
        content_path = self._content_path(document_id)
        metadata_path = self._metadata_path(document_id)

        content = content_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        return RawDocument(
            id=UUID(metadata["id"]),
            filename=metadata["filename"],
            format=DocumentFormat(metadata["format"]),
            content=content,
            uploaded_by=metadata["uploaded_by"],
            uploaded_at=datetime.fromisoformat(metadata["uploaded_at"]),
            size_bytes=metadata["size_bytes"],
        )

    async def store(self, document: RawDocument) -> str:
        """Store a raw document on the local filesystem.

        Creates a UUID-based subdirectory containing the raw content
        and a JSON sidecar metadata file.

        Args:
            document: The raw document to store.

        Returns:
            The document_id (string UUID) used for retrieval.
        """
        document_id = str(document.id)
        doc_dir = self._document_dir(document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Write raw content
        content_path = self._content_path(document_id)
        content_path.write_bytes(document.content)

        # Write metadata sidecar
        metadata_path = self._metadata_path(document_id)
        metadata = self._serialize_metadata(document)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        logger.info(
            "local_document_store.stored",
            document_id=document_id,
            filename=document.filename,
            format=document.format.value,
            size_bytes=document.size_bytes,
        )

        return document_id

    async def retrieve(self, document_id: str) -> RawDocument:
        """Retrieve a raw document from the local filesystem.

        Args:
            document_id: The UUID string of the document to retrieve.

        Returns:
            The reconstructed RawDocument.

        Raises:
            DocumentNotFoundError: If the document does not exist.
        """
        doc_dir = self._document_dir(document_id)
        if not doc_dir.exists():
            logger.warning(
                "local_document_store.not_found",
                document_id=document_id,
            )
            raise DocumentNotFoundError(document_id)

        document = self._deserialize_document(document_id)

        logger.info(
            "local_document_store.retrieved",
            document_id=document_id,
            filename=document.filename,
        )

        return document

    async def list_documents(self, filters: Any = None) -> list[DocumentMetadata]:
        """List stored documents, optionally filtered.

        Args:
            filters: Optional DocumentFilters to apply (format, uploaded_by).

        Returns:
            List of DocumentMetadata for matching documents.
        """
        results: list[DocumentMetadata] = []

        if not self._base_dir.exists():
            return results

        for doc_dir in sorted(self._base_dir.iterdir()):
            if not doc_dir.is_dir():
                continue

            metadata_path = doc_dir / "metadata.json"
            if not metadata_path.exists():
                continue

            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "local_document_store.metadata_read_error",
                    document_dir=str(doc_dir),
                )
                continue

            doc_format = DocumentFormat(metadata["format"])
            uploaded_at = datetime.fromisoformat(metadata["uploaded_at"])

            # Apply filters if provided
            if filters is not None:
                if hasattr(filters, "format") and filters.format is not None:
                    if doc_format.value != filters.format:
                        continue
                if hasattr(filters, "uploaded_by") and filters.uploaded_by is not None:
                    if metadata.get("uploaded_by") != filters.uploaded_by:
                        continue

            doc_metadata = DocumentMetadata(
                source_path=metadata["filename"],
                format=doc_format,
                page_count=None,
                ingested_at=uploaded_at,
                chunk_count=0,
            )
            results.append(doc_metadata)

        logger.info(
            "local_document_store.listed",
            total=len(results),
            filters_applied=filters is not None,
        )

        return results

    async def delete(self, document_id: str) -> None:
        """Delete a document and its metadata from the filesystem.

        Args:
            document_id: The UUID string of the document to delete.

        Raises:
            DocumentNotFoundError: If the document does not exist.
        """
        doc_dir = self._document_dir(document_id)
        if not doc_dir.exists():
            logger.warning(
                "local_document_store.delete_not_found",
                document_id=document_id,
            )
            raise DocumentNotFoundError(document_id)

        shutil.rmtree(doc_dir)

        logger.info(
            "local_document_store.deleted",
            document_id=document_id,
        )
