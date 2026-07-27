"""Unit tests for ingestion service error paths.

Validates: Requirements 1.4, 1.5, 1.7
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.events.bus import InMemoryEventBus
from src.domain.models.entities import RawDocument
from src.domain.models.enums import ChunkingStrategy, DocumentFormat
from src.domain.processing.chunking import ChunkerFactory
from src.domain.processing.fixed_size_chunker import FixedSizeChunker
from src.domain.processing.normalizer import DocumentNormalizer
from src.domain.processing.plaintext_normalizer import PlaintextNormalizer
from src.domain.services.ingestion_service import IngestionError, IngestionService
from src.domain.services.security_service import SecurityService
from src.infrastructure.local_document_store import LocalDocumentStore
from tests.property.fakes import FakeIndexingService


def _build_service(tmp_dir: str) -> IngestionService:
    """Create an IngestionService with minimal valid config."""
    store = LocalDocumentStore(base_dir=Path(tmp_dir))
    normalizer = DocumentNormalizer()
    normalizer.register(DocumentFormat.PLAINTEXT, PlaintextNormalizer())

    chunker_factory = ChunkerFactory()
    chunker_factory.register(ChunkingStrategy.FIXED_SIZE, FixedSizeChunker(chunk_size=200, overlap=50))

    return IngestionService(
        document_store=store,
        normalizer=normalizer,
        chunker_factory=chunker_factory,
        indexing_service=FakeIndexingService(),
        security_service=SecurityService(),
        event_bus=InMemoryEventBus(),
    )


def _make_doc(
    content: bytes = b"Some valid content for testing purposes.",
    fmt: DocumentFormat = DocumentFormat.PLAINTEXT,
    filename: str = "test.txt",
    size_override: int | None = None,
) -> RawDocument:
    return RawDocument(
        id=uuid4(),
        filename=filename,
        format=fmt,
        content=content,
        uploaded_by="test-user",
        uploaded_at=datetime.utcnow(),
        size_bytes=size_override if size_override is not None else len(content),
    )


@pytest.mark.unit
class TestIngestionEmptyDocument:
    """Empty document handling."""

    def test_rejects_zero_byte_document(self):
        """Requirement 1.5: Reject empty documents."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(content=b"", size_override=0)
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step == "validate"
            assert "empty" in str(exc_info.value).lower() or "0 bytes" in str(exc_info.value).lower()


@pytest.mark.unit
class TestIngestionOversizedDocument:
    """Oversized document handling."""

    def test_rejects_document_exceeding_max_size(self):
        """Requirement 1.5: Reject oversized documents."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(content=b"x", size_override=50 * 1024 * 1024 + 1)
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step == "validate"
            assert "limit" in str(exc_info.value).lower() or "exceeds" in str(exc_info.value).lower()


@pytest.mark.unit
class TestIngestionPathTraversal:
    """Path traversal detection."""

    def test_rejects_dot_dot_in_filename(self):
        """Requirement 1.7: Reject filenames with path traversal characters."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(filename="../../../etc/passwd")
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step == "validate"
            assert "traversal" in str(exc_info.value).lower() or "path" in str(exc_info.value).lower()

    def test_rejects_backslash_in_filename(self):
        """Requirement 1.7: Reject filenames with backslash."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(filename="..\\secret\\file.txt")
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step == "validate"

    def test_rejects_embedded_traversal(self):
        """Requirement 1.7: Reject filenames with embedded path traversal."""
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(filename="docs/../../../etc/shadow")
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step == "validate"


@pytest.mark.unit
class TestIngestionErrorMetadata:
    """IngestionError contains useful metadata."""

    def test_error_includes_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(content=b"", size_override=0)
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.step != ""

    def test_error_includes_document_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(tmp)
            doc = _make_doc(content=b"", size_override=0)
            with pytest.raises(IngestionError) as exc_info:
                asyncio.run(service.ingest(doc, ChunkingStrategy.FIXED_SIZE))
            assert exc_info.value.document_id == str(doc.id)
