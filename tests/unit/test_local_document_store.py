"""Unit tests for LocalDocumentStore adapter."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.domain.models.entities import RawDocument
from src.domain.models.enums import DocumentFormat
from src.infrastructure.local_document_store import (
    DocumentNotFoundError,
    LocalDocumentStore,
)
from src.ports.document_store import DocumentFilters


@pytest.fixture
def store(tmp_path: Path) -> LocalDocumentStore:
    """Create a LocalDocumentStore backed by a temp directory."""
    return LocalDocumentStore(base_dir=tmp_path / "documents")


@pytest.fixture
def sample_document() -> RawDocument:
    """A sample raw document for testing."""
    return RawDocument(
        id=uuid4(),
        filename="test-doc.md",
        format=DocumentFormat.MARKDOWN,
        content=b"# Hello World\n\nThis is test content.",
        uploaded_by="test-user",
        uploaded_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        size_bytes=36,
    )


class TestStore:
    """Tests for the store method."""

    @pytest.mark.asyncio
    async def test_store_returns_document_id(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        assert doc_id == str(sample_document.id)

    @pytest.mark.asyncio
    async def test_store_creates_content_file(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        content_path = store._content_path(doc_id)
        assert content_path.exists()
        assert content_path.read_bytes() == sample_document.content

    @pytest.mark.asyncio
    async def test_store_creates_metadata_sidecar(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        metadata_path = store._metadata_path(doc_id)
        assert metadata_path.exists()

    @pytest.mark.asyncio
    async def test_store_creates_uuid_subdirectory(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        doc_dir = store._document_dir(doc_id)
        assert doc_dir.is_dir()
        assert doc_dir.name == str(sample_document.id)


class TestRetrieve:
    """Tests for the retrieve method."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_original_content(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        retrieved = await store.retrieve(doc_id)
        assert retrieved.content == sample_document.content

    @pytest.mark.asyncio
    async def test_retrieve_preserves_metadata(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        retrieved = await store.retrieve(doc_id)
        assert retrieved.id == sample_document.id
        assert retrieved.filename == sample_document.filename
        assert retrieved.format == sample_document.format
        assert retrieved.uploaded_by == sample_document.uploaded_by
        assert retrieved.uploaded_at == sample_document.uploaded_at
        assert retrieved.size_bytes == sample_document.size_bytes

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_raises_error(self, store: LocalDocumentStore):
        with pytest.raises(DocumentNotFoundError) as exc_info:
            await store.retrieve("nonexistent-id")
        assert "nonexistent-id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_roundtrip_binary_content(self, store: LocalDocumentStore):
        """Binary content (e.g. PDF) survives a store/retrieve cycle."""
        binary_content = bytes(range(256)) * 10
        doc = RawDocument(
            id=uuid4(),
            filename="binary.pdf",
            format=DocumentFormat.PDF,
            content=binary_content,
            uploaded_by="admin",
            uploaded_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
            size_bytes=len(binary_content),
        )
        doc_id = await store.store(doc)
        retrieved = await store.retrieve(doc_id)
        assert retrieved.content == binary_content


class TestListDocuments:
    """Tests for the list_documents method."""

    @pytest.mark.asyncio
    async def test_list_empty_store(self, store: LocalDocumentStore):
        results = await store.list_documents()
        assert results == []

    @pytest.mark.asyncio
    async def test_list_returns_all_documents(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        await store.store(sample_document)
        doc2 = RawDocument(
            id=uuid4(),
            filename="second.txt",
            format=DocumentFormat.PLAINTEXT,
            content=b"Second document.",
            uploaded_by="other-user",
            uploaded_at=datetime(2024, 2, 1, 8, 0, 0, tzinfo=UTC),
            size_bytes=16,
        )
        await store.store(doc2)

        results = await store.list_documents()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_with_format_filter(self, store: LocalDocumentStore):
        md_doc = RawDocument(
            id=uuid4(),
            filename="readme.md",
            format=DocumentFormat.MARKDOWN,
            content=b"# Markdown",
            uploaded_by="user1",
            uploaded_at=datetime(2024, 1, 1, tzinfo=UTC),
            size_bytes=10,
        )
        txt_doc = RawDocument(
            id=uuid4(),
            filename="notes.txt",
            format=DocumentFormat.PLAINTEXT,
            content=b"Plain text",
            uploaded_by="user1",
            uploaded_at=datetime(2024, 1, 2, tzinfo=UTC),
            size_bytes=10,
        )
        await store.store(md_doc)
        await store.store(txt_doc)

        filters = DocumentFilters(format="markdown")
        results = await store.list_documents(filters=filters)
        assert len(results) == 1
        assert results[0].format == DocumentFormat.MARKDOWN

    @pytest.mark.asyncio
    async def test_list_with_uploaded_by_filter(self, store: LocalDocumentStore):
        doc1 = RawDocument(
            id=uuid4(),
            filename="doc1.md",
            format=DocumentFormat.MARKDOWN,
            content=b"content1",
            uploaded_by="alice",
            uploaded_at=datetime(2024, 1, 1, tzinfo=UTC),
            size_bytes=8,
        )
        doc2 = RawDocument(
            id=uuid4(),
            filename="doc2.md",
            format=DocumentFormat.MARKDOWN,
            content=b"content2",
            uploaded_by="bob",
            uploaded_at=datetime(2024, 1, 2, tzinfo=UTC),
            size_bytes=8,
        )
        await store.store(doc1)
        await store.store(doc2)

        filters = DocumentFilters(uploaded_by="alice")
        results = await store.list_documents(filters=filters)
        assert len(results) == 1
        assert results[0].source_path == "doc1.md"


class TestDelete:
    """Tests for the delete method."""

    @pytest.mark.asyncio
    async def test_delete_removes_document(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        await store.delete(doc_id)

        with pytest.raises(DocumentNotFoundError):
            await store.retrieve(doc_id)

    @pytest.mark.asyncio
    async def test_delete_removes_directory(
        self, store: LocalDocumentStore, sample_document: RawDocument
    ):
        doc_id = await store.store(sample_document)
        doc_dir = store._document_dir(doc_id)
        assert doc_dir.exists()

        await store.delete(doc_id)
        assert not doc_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises_error(self, store: LocalDocumentStore):
        with pytest.raises(DocumentNotFoundError):
            await store.delete("nonexistent-id")

    @pytest.mark.asyncio
    async def test_delete_does_not_affect_other_documents(
        self, store: LocalDocumentStore
    ):
        doc1 = RawDocument(
            id=uuid4(),
            filename="keep.md",
            format=DocumentFormat.MARKDOWN,
            content=b"keep this",
            uploaded_by="user",
            uploaded_at=datetime(2024, 1, 1, tzinfo=UTC),
            size_bytes=9,
        )
        doc2 = RawDocument(
            id=uuid4(),
            filename="delete.md",
            format=DocumentFormat.MARKDOWN,
            content=b"delete this",
            uploaded_by="user",
            uploaded_at=datetime(2024, 1, 2, tzinfo=UTC),
            size_bytes=11,
        )
        doc1_id = await store.store(doc1)
        doc2_id = await store.store(doc2)

        await store.delete(doc2_id)

        # doc1 should still be retrievable
        retrieved = await store.retrieve(doc1_id)
        assert retrieved.content == b"keep this"
