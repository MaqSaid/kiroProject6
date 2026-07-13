"""Chunking protocol and factory for document chunking strategies."""

from __future__ import annotations

from typing import Protocol

from src.domain.models.entities import Chunk, NormalizedDocument
from src.domain.models.enums import ChunkingStrategy


class Chunker(Protocol):
    """Protocol for strategy-specific document chunkers.

    All implementations must produce a list of Chunk objects with
    required metadata fields populated: document_id, index (sequential
    from 0), section_heading, strategy, and char_count == len(text).
    """

    def chunk(self, document: NormalizedDocument) -> list[Chunk]: ...


class ChunkerFactory:
    """Factory that dispatches to strategy-specific chunkers.

    Implements the Strategy pattern: register chunker implementations
    for each ChunkingStrategy, then retrieve them by enum value.
    """

    def __init__(self) -> None:
        self._chunkers: dict[ChunkingStrategy, Chunker] = {}

    def register(self, strategy: ChunkingStrategy, chunker: Chunker) -> None:
        """Register a chunker implementation for a given strategy."""
        self._chunkers[strategy] = chunker

    def get_chunker(self, strategy: ChunkingStrategy) -> Chunker:
        """Retrieve the chunker for the given strategy.

        Raises:
            ValueError: If no chunker is registered for the strategy.
        """
        chunker = self._chunkers.get(strategy)
        if chunker is None:
            raise ValueError(
                f"No chunker registered for strategy: {strategy}. "
                f"Registered strategies: {list(self._chunkers.keys())}"
            )
        return chunker

    @property
    def registered_strategies(self) -> list[ChunkingStrategy]:
        """Return list of strategies that have registered chunkers."""
        return list(self._chunkers.keys())
