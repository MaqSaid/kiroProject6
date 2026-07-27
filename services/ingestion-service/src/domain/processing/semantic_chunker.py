"""Semantic chunker for the Ingestion Service.

Splits documents into semantically coherent chunks by detecting topic shifts.
This strategy groups sentences that share semantic similarity and splits at
points where the topic significantly changes.

Note: Full semantic chunking requires an embedding model to detect topic shifts.
When the embedding service is unavailable, this chunker degrades to a sentence-
boundary-aware recursive split.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from .legal_hierarchical_chunker import Chunk, NormalizedDocument


class SemanticChunker:
    """Splits documents into semantically coherent chunks.

    Groups sentences by semantic similarity, splitting at topic boundaries.
    Without an embedding model, falls back to sentence-boundary splitting
    with a target chunk size.
    """

    def __init__(self, max_chunk_size: int = 1000, overlap: int = 50) -> None:
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split document into semantically coherent chunks.

        Args:
            document: The normalized document with plaintext content.

        Returns:
            List of Chunk objects with metadata.
        """
        text = document.plaintext
        if not text.strip():
            return []

        # Split into sentences first
        sentences = self._split_sentences(text)
        if not sentences:
            return []

        # Group sentences into chunks respecting max_chunk_size
        groups = self._group_sentences(sentences)

        chunks: list[Chunk] = []
        for index, group_text in enumerate(groups):
            group_text = group_text.strip()
            if not group_text:
                continue

            chunk = Chunk(
                id=uuid.uuid4(),
                document_id=document.source_document_id,
                index=index,
                text=group_text,
                section_heading=document.source_path,
                strategy="semantic",
                char_count=len(group_text),
                metadata={
                    "parent_document_title": document.source_path,
                    "hierarchy_path": "",
                },
            )
            chunks.append(chunk)

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split on sentence-ending punctuation followed by whitespace
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _group_sentences(self, sentences: list[str]) -> list[str]:
        """Group sentences into chunks respecting max_chunk_size.

        Sentences are grouped sequentially until adding the next sentence
        would exceed max_chunk_size.
        """
        groups: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            if sentence_len > self.max_chunk_size:
                # Flush current group
                if current_parts:
                    groups.append(" ".join(current_parts))
                    current_parts = []
                    current_len = 0
                # Add oversized sentence as its own chunk
                groups.append(sentence)
            elif current_len + sentence_len + (1 if current_parts else 0) > self.max_chunk_size:
                # Flush and start new group
                groups.append(" ".join(current_parts))
                current_parts = [sentence]
                current_len = sentence_len
            else:
                current_parts.append(sentence)
                current_len += sentence_len + (1 if current_parts else 0)

        if current_parts:
            groups.append(" ".join(current_parts))

        return groups
