"""Legal-hierarchical chunker preserving legislative hierarchy context.

This chunker extends recursive chunking by prepending parent legislative context
(Act title, Part/Division heading) to each chunk for standalone comprehension.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# --- Local domain models compatible with the shared domain-models library ---


@dataclass
class Section:
    """A section within a normalized document."""

    heading: str
    level: int
    start_offset: int
    end_offset: int


@dataclass
class NormalizedDocument:
    """A document that has been normalized to plaintext with section boundaries."""

    id: uuid.UUID
    source_document_id: uuid.UUID
    plaintext: str
    sections: list[Section]
    source_path: str  # filename for fallback title


@dataclass
class Chunk:
    """A chunk of text from a document with hierarchy metadata."""

    id: uuid.UUID
    document_id: uuid.UUID
    index: int
    text: str
    section_heading: str
    strategy: str
    char_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Hierarchy detection patterns ---

# Matches "Something Act 2024" or "Something Regulation 2024"
ACT_TITLE_PATTERN = re.compile(
    r"^(.+?\s(?:Act|Regulation|Rule|Policy)\s+\d{4})", re.MULTILINE
)

# Matches markdown H1 heading: "# Title"
H1_HEADING_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Matches "Part 3", "Part III", "Part 3 — Licensing", etc.
PART_HEADING_PATTERN = re.compile(
    r"^(Part\s+(?:\d+|[IVXLCDM]+)(?:\s*[—–\-]\s*.+)?)\s*$", re.MULTILINE | re.IGNORECASE
)

# Matches "Division 2", "Division 2 — Heavy Vehicles", etc.
DIVISION_HEADING_PATTERN = re.compile(
    r"^(Division\s+\d+(?:\s*[—–\-]\s*.+)?)\s*$", re.MULTILINE | re.IGNORECASE
)

# Matches "Section 45" or "45." at line start
SECTION_PATTERN = re.compile(
    r"^(?:Section\s+(\d+)(?:\s|$)|(\d+)\.\s)", re.MULTILINE
)


class LegalHierarchicalChunker:
    """Chunker preserving legislative hierarchy context.

    Each chunk is prepended with Act title and Part/Division heading as
    contextual prefix. Section numbering hierarchy is preserved in chunk
    metadata under 'hierarchy_path'.
    """

    def __init__(self, max_chunk_size: int = 1000, min_body_chars: int = 100) -> None:
        self.max_chunk_size = max_chunk_size
        self.min_body_chars = min_body_chars

    def chunk(self, document: NormalizedDocument) -> list[Chunk]:
        """Split a normalized document into chunks with legislative hierarchy context.

        Args:
            document: The normalized document with sections and plaintext.

        Returns:
            A list of Chunk objects with hierarchy metadata.
        """
        plaintext = document.plaintext

        # Detect Act/Regulation title
        act_title = self._detect_act_title(plaintext)
        parent_document_title: str

        if act_title:
            parent_document_title = act_title
        else:
            # Filename fallback
            parent_document_title = document.source_path
            logger.warning(
                "no_act_regulation_title_markers_found",
                source_path=document.source_path,
                document_id=str(document.id),
                message="No Act/Regulation title markers found in document text; "
                "using filename as parent_document_title",
            )

        # Build section map with hierarchy context
        sections = document.sections
        if not sections:
            sections = [
                Section(
                    heading="",
                    level=0,
                    start_offset=0,
                    end_offset=len(plaintext),
                )
            ]

        chunks: list[Chunk] = []
        index = 0

        for section in sections:
            section_text = plaintext[section.start_offset: section.end_offset]
            if not section_text.strip():
                continue

            # Determine current Part/Division from the section text or heading
            part_heading = self._detect_part_or_division(
                plaintext[: section.start_offset + len(section_text)]
            )

            # Build hierarchy path for this section
            hierarchy_path = self._build_hierarchy_path(
                section, plaintext[: section.end_offset]
            )

            # Build the prefix
            prefix = self._build_prefix(act_title or parent_document_title, part_heading)

            # Determine section heading (never empty)
            section_heading = section.heading.strip() if section.heading.strip() else (
                hierarchy_path if hierarchy_path else parent_document_title
            )

            # Split section text into pieces (recursive approach)
            # Account for prefix size so pieces fit within max_chunk_size
            available_body_size = self.max_chunk_size - len(prefix) - 1  # -1 for separator
            effective_size = max(available_body_size, self.min_body_chars)
            text_pieces = self._split_text(section_text, effective_size)

            for piece in text_pieces:
                piece = piece.strip()
                if not piece:
                    continue

                # Apply prefix + body, respecting max_chunk_size
                chunk_text = self._apply_size_constraints(prefix, piece)

                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=document.source_document_id,
                    index=index,
                    text=chunk_text,
                    section_heading=section_heading,
                    strategy="legal_hierarchical",
                    char_count=len(chunk_text),
                    metadata={
                        "hierarchy_path": hierarchy_path,
                        "parent_document_title": parent_document_title,
                    },
                )
                chunks.append(chunk)
                index += 1

        return chunks

    def _detect_act_title(self, text: str) -> str | None:
        """Detect the Act/Regulation title from text.

        Looks for H1 heading first, then pattern matching.
        """
        # Try H1 heading first
        h1_match = H1_HEADING_PATTERN.search(text)
        if h1_match:
            title = h1_match.group(1).strip()
            # Verify it looks like a legislative title
            if ACT_TITLE_PATTERN.match(title):
                return title
            # Accept H1 as title even without Act/Regulation pattern
            return title

        # Try pattern matching for "<Title> Act <Year>"
        act_match = ACT_TITLE_PATTERN.search(text)
        if act_match:
            return act_match.group(1).strip()

        return None

    def _detect_part_or_division(self, text_up_to_section: str) -> str:
        """Find the most recent Part or Division heading before the current position."""
        # Find all Part headings
        part_matches = list(PART_HEADING_PATTERN.finditer(text_up_to_section))
        # Find all Division headings
        division_matches = list(DIVISION_HEADING_PATTERN.finditer(text_up_to_section))

        # Get the most recent one by position
        latest_part = part_matches[-1].group(1).strip() if part_matches else ""
        latest_division = division_matches[-1].group(1).strip() if division_matches else ""

        if latest_part and latest_division:
            # If division appears after part, use both
            part_pos = part_matches[-1].start()
            div_pos = division_matches[-1].start()
            if div_pos > part_pos:
                return f"{latest_part}\n{latest_division}"
            return latest_part
        elif latest_division:
            return latest_division
        return latest_part

    def _build_hierarchy_path(self, section: Section, text_up_to_section: str) -> str:
        """Build a hierarchy path like 'Part 3, Division 2, Section 45'."""
        parts: list[str] = []

        # Find the latest Part
        part_matches = list(PART_HEADING_PATTERN.finditer(text_up_to_section))
        if part_matches:
            part_text = part_matches[-1].group(1).strip()
            # Extract just "Part N" portion
            part_num_match = re.match(r"(Part\s+(?:\d+|[IVXLCDM]+))", part_text, re.IGNORECASE)
            if part_num_match:
                parts.append(part_num_match.group(1))

        # Find the latest Division
        division_matches = list(DIVISION_HEADING_PATTERN.finditer(text_up_to_section))
        if division_matches:
            div_text = division_matches[-1].group(1).strip()
            div_num_match = re.match(r"(Division\s+\d+)", div_text, re.IGNORECASE)
            if div_num_match:
                parts.append(div_num_match.group(1))

        # Detect section number from section heading or text
        section_num = self._detect_section_number(section)
        if section_num:
            parts.append(f"Section {section_num}")

        return ", ".join(parts)

    def _detect_section_number(self, section: Section) -> str | None:
        """Extract section number from the section heading."""
        heading = section.heading
        # Try "Section N"
        match = re.search(r"Section\s+(\d+)", heading, re.IGNORECASE)
        if match:
            return match.group(1)
        # Try "N." at start
        match = re.match(r"(\d+)\.", heading)
        if match:
            return match.group(1)
        return None

    def _build_prefix(self, act_title: str, part_heading: str) -> str:
        """Build the contextual prefix from Act title and Part/Division heading."""
        if part_heading:
            return f"{act_title}\n{part_heading}"
        return act_title

    def _apply_size_constraints(self, prefix: str, body: str) -> str:
        """Apply size constraints: keep prefix, reduce body if needed.

        Total chunk = prefix + "\\n" + body
        If total > max_chunk_size: keep prefix intact, reduce body
        Body must have minimum min_body_chars characters.
        """
        separator = "\n"
        total = len(prefix) + len(separator) + len(body)

        if total <= self.max_chunk_size:
            return f"{prefix}{separator}{body}"

        # Need to reduce body
        available_for_body = self.max_chunk_size - len(prefix) - len(separator)

        # Ensure minimum body size
        if available_for_body < self.min_body_chars:
            # Even with max_chunk_size constraint, we must have min_body_chars
            # This means we exceed max_chunk_size to preserve minimum body
            body_truncated = body[: self.min_body_chars]
        else:
            body_truncated = body[:available_for_body]

        return f"{prefix}{separator}{body_truncated}"

    # --- Recursive text splitting (mirrors RecursiveChunker approach) ---

    def _split_text(self, text: str, target_size: int | None = None) -> list[str]:
        """Split text if it exceeds target_size.

        First tries splitting by paragraphs, then by sentences.
        """
        size = target_size if target_size is not None else self.max_chunk_size
        if len(text) <= size:
            return [text]

        # Try splitting by paragraphs
        paragraphs = self._split_by_paragraphs(text)
        if len(paragraphs) > 1:
            return self._merge_or_split_pieces(paragraphs, size)

        # Single paragraph that's too large: split by sentences
        sentences = self._split_by_sentences(text)
        if len(sentences) > 1:
            return self._merge_or_split_pieces(sentences, size)

        # Single sentence that's too large: hard split
        return self._hard_split(text, size)

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs (separated by double newlines)."""
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_or_split_pieces(self, pieces: list[str], target_size: int) -> list[str]:
        """Merge small pieces together and split large ones further."""
        result: list[str] = []
        current: list[str] = []
        current_len = 0

        for piece in pieces:
            piece_len = len(piece)

            if piece_len > target_size:
                if current:
                    result.append("\n\n".join(current))
                    current = []
                    current_len = 0
                sub_pieces = self._split_text(piece, target_size)
                result.extend(sub_pieces)
            elif current_len + piece_len + (2 if current else 0) > target_size:
                result.append("\n\n".join(current))
                current = [piece]
                current_len = piece_len
            else:
                current.append(piece)
                current_len += piece_len + (2 if len(current) > 1 else 0)

        if current:
            result.append("\n\n".join(current))

        return result

    def _hard_split(self, text: str, target_size: int) -> list[str]:
        """Hard split text at target_size boundaries."""
        result: list[str] = []
        for i in range(0, len(text), target_size):
            piece = text[i: i + target_size]
            if piece.strip():
                result.append(piece)
        return result
