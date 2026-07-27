"""Recursive chunker for the Ingestion Service.

Splits documents by paragraph/sentence boundaries recursively.
Used for .html files and .pdf/.md without legislative keywords.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from .legal_hierarchical_chunker import Chunk, NormalizedDocument


class RecursiveChunker:
    """Splits documents recursively by paragraph and sentence boundaries.

    Attempts to split by paragraphs first, then sentences, then hard character
    splits as a last resort. Produces chunks that respect natural text boundaries.
    """

    def __init__(self, max_chunk_size: int = 1000, overlap: int = 50) -> None:
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split document recursively into chunks.

        Args:
            document: The normalized document with plaintext content.

        Returns:
            List of Chunk objects with metadata.
        """
        text = document.plaintext
        if not text.strip():
            return []

        pieces = self._split_recursive(text)
        chunks: list[Chunk] = []

        for index, piece in enumerate(pieces):
            piece = piece.strip()
            if not piece:
                continue

            chunk = Chunk(
                id=uuid.uuid4(),
                document_id=document.source_document_id,
                index=index,
                text=piece,
                section_heading=document.source_path,
                strategy="recursive",
                char_count=len(piece),
                metadata={
                    "parent_document_title": document.source_path,
                    "hierarchy_path": "",
                },
            )
            chunks.append(chunk)

        return chunks

    def _split_recursive(self, text: str) -> list[str]:
        """Split text recursively, trying paragraphs then sentences."""
        if len(text) <= self.max_chunk_size:
            return [text] if text.strip() else []

        # Try splitting by double newline (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)
        if len(paragraphs) > 1:
            return self._merge_pieces(paragraphs)

        # Try splitting by sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) > 1:
            return self._merge_pieces(sentences)

        # Hard split
        return self._hard_split(text)

    def _merge_pieces(self, pieces: list[str]) -> list[str]:
        """Merge small pieces together respecting max_chunk_size."""
        result: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue

            piece_len = len(piece)

            if piece_len > self.max_chunk_size:
                # Flush current
                if current_parts:
                    result.append("\n\n".join(current_parts))
                    current_parts = []
                    current_len = 0
                # Recursively split the large piece
                sub_pieces = self._split_recursive(piece)
                result.extend(sub_pieces)
            elif current_len + piece_len + (2 if current_parts else 0) > self.max_chunk_size:
                # Flush and start new
                result.append("\n\n".join(current_parts))
                current_parts = [piece]
                current_len = piece_len
            else:
                current_parts.append(piece)
                current_len += piece_len + (2 if len(current_parts) > 1 else 0)

        if current_parts:
            result.append("\n\n".join(current_parts))

        return result

    def _hard_split(self, text: str) -> list[str]:
        """Hard split text at max_chunk_size boundaries."""
        result: list[str] = []
        for i in range(0, len(text), self.max_chunk_size):
            piece = text[i: i + self.max_chunk_size]
            if piece.strip():
                result.append(piece)
        return result
