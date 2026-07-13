"""Recursive chunker that splits documents by section headers respecting document hierarchy."""

from __future__ import annotations

import re
import uuid

from src.domain.models.entities import Chunk, NormalizedDocument, Section
from src.domain.models.enums import ChunkingStrategy


class RecursiveChunker:
    """Splits documents by section headers respecting document hierarchy.

    Each chunk is contained within a single section or subsection.
    If a section's text exceeds max_chunk_size, it is recursively split
    by paragraphs, then by sentences.
    """

    def __init__(self, max_chunk_size: int = 2000) -> None:
        self.max_chunk_size = max_chunk_size

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split a normalized document into chunks respecting section boundaries.

        Args:
            document: The normalized document with sections and plaintext.

        Returns:
            A list of Chunk objects, each within a single section.
        """
        sections = document.sections
        plaintext = document.plaintext

        if not sections:
            # No sections: treat the entire document as one section
            sections = [
                Section(
                    heading="",
                    level=0,
                    start_offset=0,
                    end_offset=len(plaintext),
                )
            ]

        section_texts = self._extract_section_texts(sections, plaintext)
        chunks: list[Chunk] = []
        index = 0

        for heading, text in section_texts:
            text_pieces = self._split_text(text)
            for piece in text_pieces:
                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=document.source_document_id,
                    index=index,
                    text=piece,
                    section_heading=heading,
                    strategy=ChunkingStrategy.RECURSIVE,
                    char_count=len(piece),
                    metadata={},
                )
                chunks.append(chunk)
                index += 1

        return chunks

    def _extract_section_texts(
        self, sections: list[Section], plaintext: str
    ) -> list[tuple[str, str]]:
        """Extract text for each section from the plaintext.

        Returns:
            A list of (heading, text) tuples for each section.
        """
        results: list[tuple[str, str]] = []
        for section in sections:
            text = plaintext[section.start_offset : section.end_offset]
            if text.strip():  # Only include sections with non-empty text
                results.append((section.heading, text))
        return results

    def _split_text(self, text: str) -> list[str]:
        """Split text if it exceeds max_chunk_size.

        First tries splitting by paragraphs, then by sentences.
        """
        if len(text) <= self.max_chunk_size:
            return [text]

        # Try splitting by paragraphs
        paragraphs = self._split_by_paragraphs(text)
        if len(paragraphs) > 1:
            return self._merge_or_split_pieces(paragraphs)

        # Single paragraph that's too large: split by sentences
        sentences = self._split_by_sentences(text)
        if len(sentences) > 1:
            return self._merge_or_split_pieces(sentences)

        # Single sentence that's too large: hard split at max_chunk_size
        return self._hard_split(text)

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs (separated by double newlines)."""
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split on sentence-ending punctuation followed by space or end
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_or_split_pieces(self, pieces: list[str]) -> list[str]:
        """Merge small pieces together and split large ones further.

        Merges consecutive pieces that fit within max_chunk_size.
        Recursively splits pieces that are still too large.
        """
        result: list[str] = []
        current: list[str] = []
        current_len = 0

        for piece in pieces:
            piece_len = len(piece)

            if piece_len > self.max_chunk_size:
                # Flush current buffer
                if current:
                    result.append("\n\n".join(current))
                    current = []
                    current_len = 0
                # Recursively split the large piece
                sub_pieces = self._split_text(piece)
                result.extend(sub_pieces)
            elif current_len + piece_len + (2 if current else 0) > self.max_chunk_size:
                # Adding this piece would exceed limit, flush current
                result.append("\n\n".join(current))
                current = [piece]
                current_len = piece_len
            else:
                current.append(piece)
                current_len += piece_len + (2 if len(current) > 1 else 0)

        if current:
            result.append("\n\n".join(current))

        return result

    def _hard_split(self, text: str) -> list[str]:
        """Hard split text at max_chunk_size boundaries when no other split point exists."""
        result: list[str] = []
        for i in range(0, len(text), self.max_chunk_size):
            piece = text[i : i + self.max_chunk_size]
            if piece.strip():
                result.append(piece)
        return result
