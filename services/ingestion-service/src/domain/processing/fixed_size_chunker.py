"""Fixed-size chunker for the Ingestion Service.

Splits documents into fixed-size chunks without regard to document structure.
Used as the fallback strategy and for .txt files.
"""

from __future__ import annotations

import uuid
from typing import Any

from .legal_hierarchical_chunker import Chunk, NormalizedDocument


class FixedSizeChunker:
    """Splits documents into fixed-size character chunks.

    Chunks are produced by splitting the document plaintext into segments
    of `chunk_size` characters with `overlap` characters of overlap between
    consecutive chunks.
    """

    def __init__(self, chunk_size: int = 1000, overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split document into fixed-size chunks.

        Args:
            document: The normalized document with plaintext content.

        Returns:
            List of Chunk objects with metadata.
        """
        text = document.plaintext
        if not text.strip():
            return []

        chunks: list[Chunk] = []
        index = 0
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            if not chunk_text.strip():
                start = end - self.overlap if self.overlap > 0 else end
                continue

            chunk = Chunk(
                id=uuid.uuid4(),
                document_id=document.source_document_id,
                index=index,
                text=chunk_text,
                section_heading=document.source_path,
                strategy="fixed_size",
                char_count=len(chunk_text),
                metadata={
                    "parent_document_title": document.source_path,
                    "hierarchy_path": "",
                },
            )
            chunks.append(chunk)
            index += 1

            # Advance with overlap
            step = self.chunk_size - self.overlap
            if step <= 0:
                step = self.chunk_size
            start += step

        return chunks
