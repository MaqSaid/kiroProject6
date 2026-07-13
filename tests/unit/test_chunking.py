"""Unit tests for ChunkerFactory dispatch logic."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from src.domain.models.entities import Chunk, DocumentMetadata, NormalizedDocument, Section
from src.domain.models.enums import ChunkingStrategy, DocumentFormat
from src.domain.processing.chunking import ChunkerFactory


def _make_document(plaintext: str = "Hello world", sections: list[Section] | None = None) -> NormalizedDocument:
    """Create a minimal NormalizedDocument for testing."""
    return NormalizedDocument(
        id=uuid4(),
        source_document_id=uuid4(),
        plaintext=plaintext,
        sections=sections or [],
        metadata=DocumentMetadata(
            source_path="test.md",
            format=DocumentFormat.MARKDOWN,
            ingested_at=datetime.utcnow(),
        ),
    )


class FakeChunker:
    """A fake chunker that produces a single chunk from the document."""

    def __init__(self, strategy: ChunkingStrategy) -> None:
        self._strategy = strategy

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        return [
            Chunk(
                id=uuid4(),
                document_id=document.source_document_id,
                index=0,
                text=document.plaintext,
                section_heading="",
                strategy=self._strategy,
                char_count=len(document.plaintext),
            )
        ]


class TestChunkerFactory:
    """Tests for ChunkerFactory registration and dispatch."""

    def test_register_and_get_chunker(self) -> None:
        factory = ChunkerFactory()
        chunker = FakeChunker(ChunkingStrategy.FIXED_SIZE)
        factory.register(ChunkingStrategy.FIXED_SIZE, chunker)

        result = factory.get_chunker(ChunkingStrategy.FIXED_SIZE)
        assert result is chunker

    def test_get_unregistered_strategy_raises_value_error(self) -> None:
        factory = ChunkerFactory()

        with pytest.raises(ValueError, match="No chunker registered for strategy"):
            factory.get_chunker(ChunkingStrategy.SEMANTIC)

    def test_register_multiple_strategies(self) -> None:
        factory = ChunkerFactory()
        fixed = FakeChunker(ChunkingStrategy.FIXED_SIZE)
        recursive = FakeChunker(ChunkingStrategy.RECURSIVE)
        semantic = FakeChunker(ChunkingStrategy.SEMANTIC)

        factory.register(ChunkingStrategy.FIXED_SIZE, fixed)
        factory.register(ChunkingStrategy.RECURSIVE, recursive)
        factory.register(ChunkingStrategy.SEMANTIC, semantic)

        assert factory.get_chunker(ChunkingStrategy.FIXED_SIZE) is fixed
        assert factory.get_chunker(ChunkingStrategy.RECURSIVE) is recursive
        assert factory.get_chunker(ChunkingStrategy.SEMANTIC) is semantic

    def test_registered_strategies_property(self) -> None:
        factory = ChunkerFactory()
        factory.register(ChunkingStrategy.FIXED_SIZE, FakeChunker(ChunkingStrategy.FIXED_SIZE))
        factory.register(ChunkingStrategy.RECURSIVE, FakeChunker(ChunkingStrategy.RECURSIVE))

        strategies = factory.registered_strategies
        assert ChunkingStrategy.FIXED_SIZE in strategies
        assert ChunkingStrategy.RECURSIVE in strategies
        assert ChunkingStrategy.SEMANTIC not in strategies

    def test_register_overwrites_existing(self) -> None:
        factory = ChunkerFactory()
        chunker1 = FakeChunker(ChunkingStrategy.FIXED_SIZE)
        chunker2 = FakeChunker(ChunkingStrategy.FIXED_SIZE)

        factory.register(ChunkingStrategy.FIXED_SIZE, chunker1)
        factory.register(ChunkingStrategy.FIXED_SIZE, chunker2)

        assert factory.get_chunker(ChunkingStrategy.FIXED_SIZE) is chunker2

    def test_dispatched_chunker_produces_valid_chunks(self) -> None:
        factory = ChunkerFactory()
        factory.register(ChunkingStrategy.FIXED_SIZE, FakeChunker(ChunkingStrategy.FIXED_SIZE))

        doc = _make_document("Some text content for chunking")
        chunker = factory.get_chunker(ChunkingStrategy.FIXED_SIZE)
        chunks = chunker.chunk(doc)

        assert len(chunks) == 1
        chunk = chunks[0]
        # Verify required metadata fields
        assert chunk.document_id == doc.source_document_id
        assert chunk.index == 0
        assert chunk.strategy == ChunkingStrategy.FIXED_SIZE
        assert chunk.char_count == len(chunk.text)
        assert chunk.text == doc.plaintext

    def test_factory_empty_registered_strategies(self) -> None:
        factory = ChunkerFactory()
        assert factory.registered_strategies == []

    def test_error_message_includes_registered_strategies(self) -> None:
        factory = ChunkerFactory()
        factory.register(ChunkingStrategy.FIXED_SIZE, FakeChunker(ChunkingStrategy.FIXED_SIZE))

        with pytest.raises(ValueError, match="Registered strategies"):
            factory.get_chunker(ChunkingStrategy.SEMANTIC)
