"""Unit tests for the Legal-Hierarchical Chunker.

Tests cover:
- Act title detection (H1 and pattern matching)
- Part/Division heading detection
- Contextual prefix construction
- Hierarchy path metadata
- max_chunk_size enforcement with prefix retention
- Minimum 100-char body guarantee
- section_heading non-empty invariant
- parent_document_title with filename fallback
- Warning logged when no title markers found
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from src.domain.processing.legal_hierarchical_chunker import (
    Chunk,
    LegalHierarchicalChunker,
    NormalizedDocument,
    Section,
)


# --- Fixtures ---


def make_document(
    plaintext: str,
    sections: list[Section] | None = None,
    source_path: str = "test_document.md",
) -> NormalizedDocument:
    """Create a NormalizedDocument for testing."""
    if sections is None:
        sections = [
            Section(
                heading="",
                level=0,
                start_offset=0,
                end_offset=len(plaintext),
            )
        ]
    return NormalizedDocument(
        id=uuid.uuid4(),
        source_document_id=uuid.uuid4(),
        plaintext=plaintext,
        sections=sections,
        source_path=source_path,
    )


SAMPLE_LEGISLATIVE_TEXT = """\
# Transport Infrastructure Act 2024

Part 3 — Licensing

Division 2 — Heavy Vehicles

Section 45 — Speed limit enforcement

The holder of a heavy vehicle licence must comply with all posted speed limits on controlled roads. Failure to comply with this section constitutes an offence under Part 3 of this Act.

Section 46 — Vehicle inspections

All heavy vehicles operating under a licence granted pursuant to Division 2 must undergo annual safety inspections conducted by an accredited inspection station.
"""


class TestActTitleDetection:
    """Tests for detecting Act/Regulation titles."""

    def test_detects_h1_act_title(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert len(chunks) > 0
        # All chunks should reference the act title
        for chunk in chunks:
            assert chunk.metadata["parent_document_title"] == "Transport Infrastructure Act 2024"

    def test_detects_act_pattern_without_h1(self) -> None:
        text = """\
Transport Infrastructure Act 2024

Part 1 — General

Section 1 — Short title

This Act may be cited as the Transport Infrastructure Act 2024. It establishes the framework for transport governance.
"""
        doc = make_document(text)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert len(chunks) > 0
        assert chunks[0].metadata["parent_document_title"] == "Transport Infrastructure Act 2024"

    def test_detects_regulation_title(self) -> None:
        text = """\
# Heavy Vehicle Access Regulation 2024

Part 1 — Preliminary

Section 1 — Commencement

This Regulation commences on the date it is published in the Gazette. All provisions come into force immediately.
"""
        doc = make_document(text)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert chunks[0].metadata["parent_document_title"] == "Heavy Vehicle Access Regulation 2024"

    def test_filename_fallback_when_no_title_markers(self) -> None:
        text = "This is a plain document without any legislative markers. " * 5
        doc = make_document(text, source_path="internal_policy_v2.md")
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)

        with patch(
            "src.domain.processing.legal_hierarchical_chunker.logger"
        ) as mock_logger:
            chunks = chunker.chunk(doc)
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert "no_act_regulation_title_markers_found" in str(call_kwargs)

        assert chunks[0].metadata["parent_document_title"] == "internal_policy_v2.md"


class TestPrefixConstruction:
    """Tests for contextual prefix building."""

    def test_prefix_includes_act_title_and_part(self) -> None:
        doc = make_document(
            SAMPLE_LEGISLATIVE_TEXT,
            sections=[
                Section(
                    heading="Section 45 — Speed limit enforcement",
                    level=3,
                    start_offset=SAMPLE_LEGISLATIVE_TEXT.index("The holder"),
                    end_offset=SAMPLE_LEGISLATIVE_TEXT.index("Section 46"),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert len(chunks) > 0
        chunk_text = chunks[0].text
        # Prefix should contain Act title
        assert "Transport Infrastructure Act 2024" in chunk_text
        # Prefix should contain Part heading
        assert "Part 3" in chunk_text

    def test_prefix_includes_division(self) -> None:
        doc = make_document(
            SAMPLE_LEGISLATIVE_TEXT,
            sections=[
                Section(
                    heading="Section 45 — Speed limit enforcement",
                    level=3,
                    start_offset=SAMPLE_LEGISLATIVE_TEXT.index("The holder"),
                    end_offset=SAMPLE_LEGISLATIVE_TEXT.index("Section 46"),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        chunk_text = chunks[0].text
        assert "Division 2" in chunk_text


class TestHierarchyPath:
    """Tests for hierarchy_path metadata."""

    def test_hierarchy_path_with_part_division_section(self) -> None:
        doc = make_document(
            SAMPLE_LEGISLATIVE_TEXT,
            sections=[
                Section(
                    heading="Section 45 — Speed limit enforcement",
                    level=3,
                    start_offset=SAMPLE_LEGISLATIVE_TEXT.index("The holder"),
                    end_offset=SAMPLE_LEGISLATIVE_TEXT.index("Section 46"),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        path = chunks[0].metadata["hierarchy_path"]
        assert "Part 3" in path
        assert "Division 2" in path
        assert "Section 45" in path

    def test_hierarchy_path_part_only(self) -> None:
        text = """\
# Road Use Management Act 2024

Part 1 — General

This part establishes the general principles governing road use management across all jurisdictions in the territory.
"""
        doc = make_document(
            text,
            sections=[
                Section(
                    heading="Part 1 — General",
                    level=1,
                    start_offset=text.index("This part"),
                    end_offset=len(text),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        path = chunks[0].metadata["hierarchy_path"]
        assert "Part 1" in path
        assert "Division" not in path


class TestSizeConstraints:
    """Tests for max_chunk_size enforcement."""

    def test_chunk_within_size_limit(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            assert chunk.char_count <= 2000

    def test_prefix_retained_body_truncated(self) -> None:
        # Use a small max_chunk_size to force truncation
        text = """\
# Transport Infrastructure Act 2024

Part 3 — Licensing

Section 45 — Speed limit enforcement

""" + ("A" * 500)
        doc = make_document(
            text,
            sections=[
                Section(
                    heading="Section 45",
                    level=2,
                    start_offset=text.index("A" * 10),
                    end_offset=len(text),
                )
            ],
        )
        # Prefix is ~60 chars, body is 500 chars
        # With max_chunk_size=200, body must be truncated
        chunker = LegalHierarchicalChunker(max_chunk_size=200)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            # Prefix should still be present
            assert "Transport Infrastructure Act 2024" in chunk.text

    def test_minimum_body_100_chars_guaranteed(self) -> None:
        # When the prefix is large and max_chunk_size is small,
        # the body should still get at least min_body_chars (100) even if that
        # means exceeding max_chunk_size.
        # Prefix: "Short Act 2024\nPart 1 — General" ~33 chars
        # Separator: "\n" = 1 char
        # With max_chunk_size = 110, available_for_body = 110 - 34 = 76 < 100
        # So body should be 100 chars (exceeding max_chunk_size)
        body_text = "X" * 150  # single piece, won't be split further
        long_prefix_text = """\
# Short Act 2024

Part 1 — General

Section 1 — Title

""" + body_text
        doc = make_document(
            long_prefix_text,
            sections=[
                Section(
                    heading="Section 1",
                    level=2,
                    start_offset=long_prefix_text.index("X" * 10),
                    end_offset=len(long_prefix_text),
                )
            ],
        )
        # Use a max_chunk_size that forces body truncation
        # but the min_body_chars guarantee should still hold
        chunker = LegalHierarchicalChunker(max_chunk_size=110)
        chunks = chunker.chunk(doc)

        assert len(chunks) > 0
        # Verify the body is at least 100 chars
        act_title = "Short Act 2024"
        part_heading = chunker._detect_part_or_division(
            long_prefix_text[: long_prefix_text.index("X" * 10)]
        )
        prefix = chunker._build_prefix(act_title, part_heading)
        # First chunk should have the full prefix + at least 100 chars body
        body = chunks[0].text[len(prefix) + 1:]  # +1 for separator newline
        assert len(body) >= 100


class TestSectionHeading:
    """Tests for non-empty section_heading."""

    def test_section_heading_from_section(self) -> None:
        doc = make_document(
            SAMPLE_LEGISLATIVE_TEXT,
            sections=[
                Section(
                    heading="Section 45 — Speed limit enforcement",
                    level=3,
                    start_offset=SAMPLE_LEGISLATIVE_TEXT.index("The holder"),
                    end_offset=SAMPLE_LEGISLATIVE_TEXT.index("Section 46"),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert chunks[0].section_heading == "Section 45 — Speed limit enforcement"

    def test_section_heading_never_empty(self) -> None:
        # Section with empty heading should still get a non-empty section_heading
        text = """\
# Transport Infrastructure Act 2024

Part 1 — General

Some introductory text about the general principles of transport infrastructure law that applies across all sections.
"""
        doc = make_document(
            text,
            sections=[
                Section(
                    heading="",
                    level=0,
                    start_offset=text.index("Some introductory"),
                    end_offset=len(text),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            assert chunk.section_heading != ""
            assert len(chunk.section_heading) > 0


class TestChunkMetadata:
    """Tests for chunk metadata completeness."""

    def test_all_chunks_have_required_metadata(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            assert "hierarchy_path" in chunk.metadata
            assert "parent_document_title" in chunk.metadata
            assert chunk.strategy == "legal_hierarchical"
            assert chunk.char_count == len(chunk.text)
            assert chunk.section_heading != ""

    def test_chunks_have_sequential_indices(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)
        chunker = LegalHierarchicalChunker(max_chunk_size=500)
        chunks = chunker.chunk(doc)

        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_document_id_matches_source_document(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        for chunk in chunks:
            assert chunk.document_id == doc.source_document_id


class TestWarningOnNoTitleMarkers:
    """Tests for warning when no Act/Regulation markers found."""

    def test_logs_warning_on_no_markers(self) -> None:
        text = "This is just some regular text without any legislation markers. " * 5
        doc = make_document(text, source_path="plain_notes.txt")

        with patch(
            "src.domain.processing.legal_hierarchical_chunker.logger"
        ) as mock_logger:
            chunker = LegalHierarchicalChunker(max_chunk_size=2000)
            chunker.chunk(doc)

            mock_logger.warning.assert_called_once()
            args, kwargs = mock_logger.warning.call_args
            assert args[0] == "no_act_regulation_title_markers_found"
            assert kwargs["source_path"] == "plain_notes.txt"

    def test_no_warning_when_title_found(self) -> None:
        doc = make_document(SAMPLE_LEGISLATIVE_TEXT)

        with patch(
            "src.domain.processing.legal_hierarchical_chunker.logger"
        ) as mock_logger:
            chunker = LegalHierarchicalChunker(max_chunk_size=2000)
            chunker.chunk(doc)

            mock_logger.warning.assert_not_called()


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_document(self) -> None:
        doc = make_document("", sections=[])
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)
        assert chunks == []

    def test_whitespace_only_document(self) -> None:
        doc = make_document("   \n\n   \t\t  ", sections=[])
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)
        assert chunks == []

    def test_roman_numeral_part(self) -> None:
        text = """\
# Road Use Management Act 2024

Part III — Road Design

Section 10 — Design standards

All road designs must comply with national safety standards as established under Part III of this Act including all amendments.
"""
        doc = make_document(
            text,
            sections=[
                Section(
                    heading="Section 10 — Design standards",
                    level=2,
                    start_offset=text.index("All road"),
                    end_offset=len(text),
                )
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert "Part III" in chunks[0].metadata["hierarchy_path"]
        assert "Part III" in chunks[0].text

    def test_multiple_sections_produce_multiple_chunks(self) -> None:
        text = SAMPLE_LEGISLATIVE_TEXT
        s45_start = text.index("The holder")
        s46_start = text.index("Section 46")
        s46_body = text.index("All heavy vehicles")

        doc = make_document(
            text,
            sections=[
                Section(
                    heading="Section 45 — Speed limit enforcement",
                    level=3,
                    start_offset=s45_start,
                    end_offset=s46_start,
                ),
                Section(
                    heading="Section 46 — Vehicle inspections",
                    level=3,
                    start_offset=s46_body,
                    end_offset=len(text),
                ),
            ],
        )
        chunker = LegalHierarchicalChunker(max_chunk_size=2000)
        chunks = chunker.chunk(doc)

        assert len(chunks) >= 2
        assert chunks[0].section_heading == "Section 45 — Speed limit enforcement"
        assert chunks[1].section_heading == "Section 46 — Vehicle inspections"
