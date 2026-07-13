"""Fixed-size document chunker with configurable overlap."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.domain.models.entities import Chunk, NormalizedDocument, Section
from src.domain.models.enums import ChunkingStrategy

logger = logging.getLogger(__name__)


class FixedSizeChunker:
    """Splits text into fixed-size chunks with configurable overlap.

    Implements the Chunker protocol. Splits document plaintext into chunks
    of `chunk_size` characters with `overlap` characters shared between
    consecutive chunks. Attaches metadata including section heading, strategy,
    and character count to each chunk.

    If a chunk exceeds the embedding model's token limit (estimated as
    char_count * 0.25), it is split further and a warning is logged.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 200,
        max_token_limit: int = 8191,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_token_limit = max_token_limit
        # Maximum characters before token limit is hit (tokens ≈ chars * 0.25)
        self._max_char_limit = int(max_token_limit / 0.25)

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split document plaintext into fixed-size chunks with overlap.

        Args:
            document: The normalized document to chunk.

        Returns:
            A list of Chunk objects with metadata populated.
        """
        text = document.plaintext
        if not text:
            return []

        raw_segments = self._split_text(text)
        chunks: list[Chunk] = []

        for segment in raw_segments:
            # Check if segment exceeds embedding model token limit
            estimated_tokens = len(segment["text"]) * 0.25
            if estimated_tokens > self.max_token_limit:
                logger.warning(
                    "Chunk at offset %d exceeds max token limit (%d estimated tokens > %d limit). "
                    "Splitting further.",
                    segment["start_offset"],
                    int(estimated_tokens),
                    self.max_token_limit,
                )
                sub_segments = self._split_oversized(
                    segment["text"], segment["start_offset"]
                )
            else:
                sub_segments = [segment]

            for sub_seg in sub_segments:
                section_heading = self._find_section_heading(
                    document.sections, sub_seg["start_offset"]
                )
                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=document.source_document_id,
                    index=len(chunks),
                    text=sub_seg["text"],
                    section_heading=section_heading,
                    strategy=ChunkingStrategy.FIXED_SIZE,
                    char_count=len(sub_seg["text"]),
                    metadata={},
                )
                chunks.append(chunk)

        return chunks

    def _split_text(self, text: str) -> list[dict[str, Any]]:
        """Split text into segments of chunk_size with overlap.

        Returns a list of dicts with 'text' and 'start_offset' keys.
        """
        segments: list[dict[str, Any]] = []
        step = self.chunk_size - self.overlap
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            segment_text = text[start:end]
            segments.append({"text": segment_text, "start_offset": start})
            if end >= len(text):
                break
            start += step

        return segments

    def _split_oversized(
        self, text: str, base_offset: int
    ) -> list[dict[str, Any]]:
        """Split an oversized chunk into smaller pieces within token limit.

        Uses the max_char_limit as the sub-chunk size, with the same overlap.
        """
        sub_chunk_size = self._max_char_limit
        sub_overlap = min(self.overlap, sub_chunk_size - 1)
        step = sub_chunk_size - sub_overlap
        segments: list[dict[str, Any]] = []
        start = 0

        while start < len(text):
            end = min(start + sub_chunk_size, len(text))
            segment_text = text[start:end]
            segments.append({
                "text": segment_text,
                "start_offset": base_offset + start,
            })
            if end >= len(text):
                break
            start += step

        return segments

    def _find_section_heading(
        self, sections: list[Section], offset: int
    ) -> str:
        """Find the section heading that contains the given character offset.

        Returns the heading of the deepest-level section that contains offset.
        If no section contains the offset, returns an empty string.
        """
        best_heading = ""
        best_level = -1

        for section in sections:
            if section.start_offset <= offset < section.end_offset:
                # Prefer deeper (higher level number) sections for more specific heading
                if section.level > best_level:
                    best_heading = section.heading
                    best_level = section.level

        return best_heading
