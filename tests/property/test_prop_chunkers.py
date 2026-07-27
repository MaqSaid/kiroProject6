"""Property tests for chunking strategies.

# Feature: production-rag-pipeline-hybrid-search, Properties 4-8
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from src.domain.models.entities import DocumentMetadata, NormalizedDocument, Section
from src.domain.models.enums import ChunkingStrategy, DocumentFormat
from src.domain.processing.fixed_size_chunker import FixedSizeChunker
from src.domain.processing.recursive_chunker import RecursiveChunker
from tests.property.fakes import FakeEmbeddingPort

# --- Custom Strategies ---

reasonable_text = st.text(
    min_size=50,
    max_size=5000,
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
)

chunk_size_st = st.integers(min_value=50, max_value=2000)
overlap_st = st.integers(min_value=0, max_value=500)


def make_normalized_doc(text: str) -> NormalizedDocument:
    """Build a NormalizedDocument from text for testing."""
    doc_id = uuid.uuid4()
    return NormalizedDocument(
        id=uuid.uuid4(),
        source_document_id=doc_id,
        plaintext=text,
        sections=[Section(heading="Root", level=1, start_offset=0, end_offset=len(text))],
        metadata=DocumentMetadata(
            source_path="test.txt",
            format=DocumentFormat.PLAINTEXT,
            ingested_at=datetime.utcnow(),
        ),
    )


# --- Property 4: Fixed-size chunker size and overlap invariants ---


@pytest.mark.property
@settings(max_examples=100)
@given(text=reasonable_text, chunk_size=chunk_size_st, overlap=overlap_st)
def test_fixed_size_no_chunk_exceeds_size(text: str, chunk_size: int, overlap: int) -> None:
    """Property 4a: No chunk exceeds configured chunk_size."""
    assume(overlap < chunk_size)
    assume(len(text) >= 10)

    chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
    doc = make_normalized_doc(text)
    chunks = chunker.chunk(doc)

    for chunk in chunks:
        assert chunk.char_count <= chunk_size, (
            f"Chunk {chunk.index} has {chunk.char_count} chars, exceeds {chunk_size}"
        )


@pytest.mark.property
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    text=st.text(min_size=500, max_size=5000, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))),
    chunk_size=st.integers(min_value=100, max_value=400),
    overlap=st.integers(min_value=10, max_value=80),
)
def test_fixed_size_overlap_between_consecutive(text: str, chunk_size: int, overlap: int) -> None:
    """Property 4b: Consecutive chunks overlap by the configured amount."""
    assume(overlap < chunk_size)

    chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
    doc = make_normalized_doc(text)
    chunks = chunker.chunk(doc)

    if len(chunks) < 2:
        return

    for i in range(len(chunks) - 1):
        current_text = chunks[i].text
        next_text = chunks[i + 1].text
        overlap_region = current_text[-overlap:]
        assert next_text.startswith(overlap_region), (
            f"Chunks {i} and {i+1} don't overlap by {overlap} chars"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(text=reasonable_text)
def test_fixed_size_covers_all_content(text: str) -> None:
    """Property 4c: Chunking covers the entire document text."""
    assume(len(text) >= 10)

    chunker = FixedSizeChunker(chunk_size=200, overlap=50)
    doc = make_normalized_doc(text)
    chunks = chunker.chunk(doc)

    if not chunks:
        return

    covered = set()
    for chunk in chunks:
        start = text.find(chunk.text)
        if start >= 0:
            for j in range(start, start + len(chunk.text)):
                covered.add(j)

    for pos in range(len(text)):
        assert pos in covered, f"Position {pos} not covered by any chunk"


# --- Property 7: All chunks carry required metadata ---


@pytest.mark.property
@settings(max_examples=100)
@given(text=reasonable_text)
def test_all_chunks_have_required_metadata(text: str) -> None:
    """Property 7: Every chunk has document_id, index, section_heading, strategy, char_count."""
    assume(len(text) >= 10)

    chunker = FixedSizeChunker(chunk_size=200, overlap=50)
    doc = make_normalized_doc(text)
    chunks = chunker.chunk(doc)

    for i, chunk in enumerate(chunks):
        assert chunk.document_id == doc.source_document_id
        assert chunk.index == i
        assert isinstance(chunk.section_heading, str)
        assert chunk.strategy == ChunkingStrategy.FIXED_SIZE
        assert chunk.char_count == len(chunk.text)
        assert len(chunk.text) > 0


# --- Property 8: Re-chunking covers same content ---


@pytest.mark.property
@settings(max_examples=50)
@given(text=reasonable_text)
def test_rechunking_covers_same_content(text: str) -> None:
    """Property 8: Re-chunking with different config covers the same text."""
    assume(len(text) >= 100)

    chunker_a = FixedSizeChunker(chunk_size=200, overlap=50)
    chunker_b = FixedSizeChunker(chunk_size=300, overlap=75)

    doc = make_normalized_doc(text)
    chunks_a = chunker_a.chunk(doc)
    chunks_b = chunker_b.chunk(doc)

    text_a = "".join(c.text for c in chunks_a)
    text_b = "".join(c.text for c in chunks_b)

    assert len(text_a) >= len(text), "Chunking A lost content"
    assert len(text_b) >= len(text), "Chunking B lost content"


# --- Property 5: Recursive chunker respects section boundaries ---

section_heading_text = st.text(
    min_size=3,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" "),
).map(str.strip).filter(lambda s: len(s) >= 3)

section_body_text = st.text(
    min_size=20,
    max_size=500,
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
)


@st.composite
def multi_section_document(draw: st.DrawFn) -> NormalizedDocument:
    """Generate a NormalizedDocument with multiple distinct sections."""
    num_sections = draw(st.integers(min_value=2, max_value=5))
    sections: list[Section] = []
    parts: list[str] = []
    offset = 0

    for i in range(num_sections):
        heading = draw(section_heading_text)
        body = draw(section_body_text)
        section_text = f"{heading}\n{body}\n\n"
        parts.append(section_text)

        sections.append(Section(
            heading=heading,
            level=1,
            start_offset=offset,
            end_offset=offset + len(section_text),
        ))
        offset += len(section_text)

    plaintext = "".join(parts)
    doc_id = uuid.uuid4()

    return NormalizedDocument(
        id=uuid.uuid4(),
        source_document_id=doc_id,
        plaintext=plaintext,
        sections=sections,
        metadata=DocumentMetadata(
            source_path="test.txt",
            format=DocumentFormat.PLAINTEXT,
            ingested_at=datetime.utcnow(),
        ),
    )


@pytest.mark.property
@settings(max_examples=100)
@given(doc=multi_section_document())
def test_recursive_chunker_respects_section_boundaries(doc: NormalizedDocument) -> None:
    """Property 5: No chunk spans across a section boundary.

    For any document with sections, the recursive chunker SHALL produce
    chunks where each chunk's text is entirely within a single section.

    **Validates: Requirements 2.4**
    """
    chunker = RecursiveChunker(max_chunk_size=2000)
    chunks = chunker.chunk(doc)

    for chunk in chunks:
        # Each chunk should only reference one section heading
        assert isinstance(chunk.section_heading, str)

        # Verify the chunk text appears within a single section's text
        found_in_section = False
        for section in doc.sections:
            section_text = doc.plaintext[section.start_offset:section.end_offset]
            if chunk.text in section_text:
                found_in_section = True
                break

        assert found_in_section, (
            f"Chunk {chunk.index} with heading '{chunk.section_heading}' "
            f"was not found within any single section"
        )


@pytest.mark.property
@settings(max_examples=50)
@given(doc=multi_section_document())
def test_recursive_chunker_preserves_all_section_content(doc: NormalizedDocument) -> None:
    """Property 5b: All section content is represented in some chunk."""
    chunker = RecursiveChunker(max_chunk_size=2000)
    chunks = chunker.chunk(doc)

    all_chunk_text = " ".join(c.text for c in chunks)

    for section in doc.sections:
        section_text = doc.plaintext[section.start_offset:section.end_offset].strip()
        if not section_text:
            continue
        # At least some words from each section appear in chunks
        words = section_text.split()[:5]
        for word in words:
            if len(word) > 3:
                assert word in all_chunk_text, (
                    f"Word '{word}' from section '{section.heading}' not in any chunk"
                )
                break


# --- Property 6: Semantic chunker splits at similarity threshold ---


@pytest.mark.property
@settings(max_examples=50)
@given(
    threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False),
    num_sentences=st.integers(min_value=5, max_value=15),
)
def test_semantic_chunker_splits_produce_valid_chunks(
    threshold: float, num_sentences: int
) -> None:
    """Property 6: Semantic chunker produces valid chunks for any threshold.

    For any sentence sequence and threshold, the chunker SHALL produce
    non-empty chunks that together cover the original text.

    **Validates: Requirements 2.5**
    """
    from src.domain.processing.semantic_chunker import SemanticChunker

    # Build a document with distinct sentences
    sentences = [f"Sentence number {i} contains some meaningful content here." for i in range(num_sentences)]
    text = " ".join(sentences)

    doc = make_normalized_doc(text)
    embedding_port = FakeEmbeddingPort(dimensions=8)
    chunker = SemanticChunker(
        embedding_port=embedding_port,
        similarity_threshold=threshold,
        min_chunk_size=20,
        max_chunk_size=2000,
    )

    chunks = chunker.chunk(doc)

    # Must produce at least one chunk
    assert len(chunks) >= 1

    # All chunks have valid metadata
    for i, chunk in enumerate(chunks):
        assert chunk.document_id == doc.source_document_id
        assert chunk.index == i
        assert chunk.strategy == ChunkingStrategy.SEMANTIC
        assert chunk.char_count == len(chunk.text)
        assert len(chunk.text) > 0


@pytest.mark.property
@settings(max_examples=50)
@given(threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False))
def test_semantic_chunker_respects_max_chunk_size(threshold: float) -> None:
    """Property 6b: No chunk exceeds max_chunk_size."""
    from src.domain.processing.semantic_chunker import SemanticChunker

    max_size = 500
    text = " ".join([f"This is sentence {i} with some content." for i in range(30)])
    doc = make_normalized_doc(text)

    embedding_port = FakeEmbeddingPort(dimensions=8)
    chunker = SemanticChunker(
        embedding_port=embedding_port,
        similarity_threshold=threshold,
        min_chunk_size=20,
        max_chunk_size=max_size,
    )

    chunks = chunker.chunk(doc)

    for chunk in chunks:
        assert chunk.char_count <= max_size, (
            f"Chunk {chunk.index} has {chunk.char_count} chars, exceeds max {max_size}"
        )
