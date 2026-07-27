"""Property tests for document store round-trip.

# Feature: production-rag-pipeline-hybrid-search, Property 2: Raw document storage round-trip
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.domain.models.entities import RawDocument
from src.domain.models.enums import DocumentFormat
from src.infrastructure.local_document_store import LocalDocumentStore

# --- Strategies ---

document_content = st.binary(min_size=1, max_size=10000)
filename_text = st.text(
    min_size=3,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._-"),
).filter(lambda s: ".." not in s and "\\" not in s)

format_strategy = st.sampled_from([
    DocumentFormat.MARKDOWN,
    DocumentFormat.PLAINTEXT,
    DocumentFormat.HTML,
    DocumentFormat.PDF,
])


def make_raw_document(content: bytes, filename: str, fmt: DocumentFormat) -> RawDocument:
    """Build a RawDocument for testing."""
    return RawDocument(
        id=uuid4(),
        filename=filename,
        format=fmt,
        content=content,
        uploaded_by="test_user",
        uploaded_at=datetime.utcnow(),
        size_bytes=len(content),
    )


# --- Property 2: Raw document storage round-trip ---


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(content=document_content, filename=filename_text, fmt=format_strategy)
def test_store_then_retrieve_produces_identical_content(
    content: bytes, filename: str, fmt: DocumentFormat
) -> None:
    """Property 2: For any valid document, store then retrieve produces byte-identical content.

    **Validates: Requirements 1.3**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalDocumentStore(base_dir=Path(tmp_dir))
        doc = make_raw_document(content, filename, fmt)

        doc_id = asyncio.run(store.store(doc))
        retrieved = asyncio.run(store.retrieve(doc_id))

        assert retrieved.content == doc.content, (
            f"Content mismatch: stored {len(doc.content)} bytes, "
            f"retrieved {len(retrieved.content)} bytes"
        )


@pytest.mark.property
@settings(max_examples=100, deadline=None)
@given(content=document_content, filename=filename_text, fmt=format_strategy)
def test_store_then_retrieve_preserves_metadata(
    content: bytes, filename: str, fmt: DocumentFormat
) -> None:
    """Property 2b: Store/retrieve preserves all document metadata."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalDocumentStore(base_dir=Path(tmp_dir))
        doc = make_raw_document(content, filename, fmt)

        doc_id = asyncio.run(store.store(doc))
        retrieved = asyncio.run(store.retrieve(doc_id))

        assert retrieved.id == doc.id
        assert retrieved.filename == doc.filename
        assert retrieved.format == doc.format
        assert retrieved.uploaded_by == doc.uploaded_by
        assert retrieved.size_bytes == doc.size_bytes


@pytest.mark.property
@settings(max_examples=50, deadline=None)
@given(content=document_content, filename=filename_text, fmt=format_strategy)
def test_store_id_matches_document_id(
    content: bytes, filename: str, fmt: DocumentFormat
) -> None:
    """Property 2c: Returned document_id matches the document's UUID."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalDocumentStore(base_dir=Path(tmp_dir))
        doc = make_raw_document(content, filename, fmt)

        doc_id = asyncio.run(store.store(doc))
        assert doc_id == str(doc.id)
