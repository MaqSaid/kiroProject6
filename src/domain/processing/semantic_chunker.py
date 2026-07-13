"""Semantic chunker that splits documents at embedding similarity boundaries."""

from __future__ import annotations

import asyncio
import uuid

from src.domain.models.entities import Chunk, NormalizedDocument, Section
from src.domain.models.enums import ChunkingStrategy
from src.ports.embedding import EmbeddingPort


class SemanticChunker:
    """Splits documents at points where embedding similarity drops below a threshold.

    Computes pairwise cosine similarity between consecutive sentences.
    Splits occur at boundaries where similarity falls below the configured
    threshold, grouping semantically related sentences together.

    Uses the EmbeddingPort for sentence-level embeddings.
    """

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        similarity_threshold: float = 0.5,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
    ) -> None:
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")
        if min_chunk_size <= 0:
            raise ValueError("min_chunk_size must be positive")
        if max_chunk_size <= min_chunk_size:
            raise ValueError("max_chunk_size must be greater than min_chunk_size")

        self._embedding_port = embedding_port
        self.similarity_threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split document into semantically coherent chunks.

        Runs the async embedding calls synchronously via asyncio to
        conform to the synchronous Chunker protocol.

        Args:
            document: The normalized document to chunk.

        Returns:
            A list of Chunk objects grouped by semantic similarity.
        """
        text = document.plaintext
        if not text or not text.strip():
            return []

        sentences = self._split_into_sentences(text)
        if not sentences:
            return []

        # Get embeddings for all sentences
        embeddings = self._get_embeddings(sentences)

        # Find split points based on similarity drops
        split_indices = self._find_split_points(embeddings)

        # Group sentences into chunks
        groups = self._group_sentences(sentences, split_indices)

        # Build Chunk objects
        chunks: list[Chunk] = []
        current_offset = 0

        for idx, group_text in enumerate(groups):
            # Advance offset to find where this group starts in the plaintext
            group_start = text.find(group_text[:50], current_offset)
            if group_start == -1:
                group_start = current_offset

            section_heading = self._find_section_heading(
                document.sections, group_start
            )

            chunk = Chunk(
                id=uuid.uuid4(),
                document_id=document.source_document_id,
                index=idx,
                text=group_text,
                section_heading=section_heading,
                strategy=ChunkingStrategy.SEMANTIC,
                char_count=len(group_text),
                metadata={},
            )
            chunks.append(chunk)
            current_offset = group_start + len(group_text)

        return chunks

    def _get_embeddings(self, sentences: list[str]) -> list[list[float]]:
        """Get embeddings for sentences, handling the async port synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in an async context — create a new thread to run it
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._embedding_port.embed(sentences))
                return future.result()
        else:
            return asyncio.run(self._embedding_port.embed(sentences))

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using punctuation boundaries.

        Filters out very short fragments that aren't meaningful sentences.
        """
        import re

        # Split on sentence-ending punctuation followed by whitespace
        raw_sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in raw_sentences if s.strip()]

        # Filter out fragments shorter than a reasonable minimum
        return [s for s in sentences if len(s) >= 10]

    def _find_split_points(self, embeddings: list[list[float]]) -> list[int]:
        """Find indices where consecutive sentence similarity drops below threshold.

        Returns indices after which a split should occur (0-indexed).
        """
        if len(embeddings) <= 1:
            return []

        split_points: list[int] = []

        for i in range(len(embeddings) - 1):
            similarity = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            if similarity < self.similarity_threshold:
                split_points.append(i)

        return split_points

    def _group_sentences(
        self, sentences: list[str], split_indices: list[int]
    ) -> list[str]:
        """Group sentences into chunks based on split points.

        Respects min_chunk_size and max_chunk_size constraints:
        - Merges small groups into the next group if below min_chunk_size.
        - Splits groups that exceed max_chunk_size at the nearest split point.
        """
        if not split_indices:
            # No splits — everything is one chunk
            full_text = " ".join(sentences)
            if len(full_text) > self.max_chunk_size:
                return self._hard_split_text(full_text)
            return [full_text]

        groups: list[str] = []
        prev_idx = 0

        for split_idx in split_indices:
            group = " ".join(sentences[prev_idx : split_idx + 1])
            groups.append(group)
            prev_idx = split_idx + 1

        # Add remaining sentences
        if prev_idx < len(sentences):
            groups.append(" ".join(sentences[prev_idx:]))

        # Enforce size constraints
        return self._enforce_size_constraints(groups)

    def _enforce_size_constraints(self, groups: list[str]) -> list[str]:
        """Merge groups below min_chunk_size and split those above max_chunk_size."""
        result: list[str] = []
        buffer = ""

        for group in groups:
            if buffer:
                candidate = buffer + " " + group
            else:
                candidate = group

            if len(candidate) > self.max_chunk_size:
                # Flush buffer if non-empty
                if buffer:
                    if len(buffer) >= self.min_chunk_size:
                        result.append(buffer)
                    elif result:
                        result[-1] = result[-1] + " " + buffer
                    else:
                        result.append(buffer)
                    buffer = ""

                # Handle the oversized group
                if len(group) > self.max_chunk_size:
                    sub_parts = self._hard_split_text(group)
                    result.extend(sub_parts)
                else:
                    buffer = group
            elif len(candidate) < self.min_chunk_size:
                buffer = candidate
            else:
                result.append(candidate)
                buffer = ""

        # Flush remaining buffer
        if buffer:
            if result and len(buffer) < self.min_chunk_size:
                result[-1] = result[-1] + " " + buffer
            else:
                result.append(buffer)

        return result

    def _hard_split_text(self, text: str) -> list[str]:
        """Split text at max_chunk_size boundaries as a last resort."""
        parts: list[str] = []
        for i in range(0, len(text), self.max_chunk_size):
            part = text[i : i + self.max_chunk_size]
            if part.strip():
                parts.append(part)
        return parts

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a * a for a in vec_a) ** 0.5
        magnitude_b = sum(b * b for b in vec_b) ** 0.5

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def _find_section_heading(
        self, sections: list[Section], offset: int
    ) -> str:
        """Find the section heading that contains the given offset."""
        best_heading = ""
        best_level = -1

        for section in sections:
            if section.start_offset <= offset < section.end_offset:
                if section.level > best_level:
                    best_heading = section.heading
                    best_level = section.level

        return best_heading
