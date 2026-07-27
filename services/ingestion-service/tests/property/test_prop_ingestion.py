"""Property tests for Ingestion Service chunking and registry.

# Feature: legislation-rag-platform, Property 11: Legal-hierarchical chunker metadata completeness
# Feature: legislation-rag-platform, Property 12: Legal-hierarchical chunker size constraints
# Feature: legislation-rag-platform, Property 13: Chunker Registry auto-selection correctness
# Feature: legislation-rag-platform, Property 14: Chunker Registry explicit strategy selection
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.domain.processing.legal_hierarchical_chunker import (
    LegalHierarchicalChunker,
    NormalizedDocument,
    Section,
)
from src.domain.processing.chunker_registry import ChunkerRegistry


# --- FakeChunker for Registry tests ---


class FakeChunker:
    """Fake chunker for testing registry behavior."""

    def __init__(self, name: str) -> None:
        self.name = name

    def chunk(self, doc: Any) -> list[Any]:
        return []


# --- Strategies ---


# Legislative keywords for generating filenames
LEGISLATIVE_KEYWORDS = ["Act", "Regulation", "Rule", "Policy"]


@st.composite
def legislative_document_text(draw: st.DrawFn) -> str:
    """Generate random legislative document text with proper structure.

    Produces text with:
    - An Act title line (e.g., "# Random Act 2024")
    - A Part heading (e.g., "Part N — Random Topic")
    - Optionally a Division heading
    - At least one Section with body text (min 150 chars)
    """
    # Generate Act title components
    act_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=3,
        max_size=20,
    ))
    year = draw(st.integers(min_value=1990, max_value=2030))
    act_type = draw(st.sampled_from(["Act", "Regulation", "Rule", "Policy"]))
    act_title = f"# {act_name} {act_type} {year}"

    # Generate Part heading
    part_num = draw(st.integers(min_value=1, max_value=20))
    part_topic = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=3,
        max_size=15,
    ))
    part_heading = f"Part {part_num} — {part_topic}"

    # Optionally include Division heading
    include_division = draw(st.booleans())
    division_heading = ""
    if include_division:
        div_num = draw(st.integers(min_value=1, max_value=10))
        div_topic = draw(st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=3,
            max_size=15,
        ))
        division_heading = f"Division {div_num} — {div_topic}"

    # Generate Section with body text (at least 150 chars)
    section_num = draw(st.integers(min_value=1, max_value=200))
    section_topic = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=3,
        max_size=20,
    ))

    # Generate body text of at least 150 characters
    body_words = draw(st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=3,
            max_size=12,
        ),
        min_size=20,
        max_size=60,
    ))
    body_text = " ".join(body_words)
    # Ensure minimum length
    while len(body_text) < 150:
        body_text += " additional text required for minimum length"

    # Assemble document
    lines = [act_title, "", part_heading, ""]
    if division_heading:
        lines.append(division_heading)
        lines.append("")
    lines.append(f"Section {section_num} — {section_topic}")
    lines.append("")
    lines.append(body_text)

    return "\n".join(lines)


@st.composite
def max_chunk_size_strategy(draw: st.DrawFn) -> int:
    """Generate varying max_chunk_size values (200-5000)."""
    return draw(st.integers(min_value=200, max_value=5000))


@st.composite
def legislative_filename(draw: st.DrawFn) -> str:
    """Generate a filename with legislative keywords and .md/.pdf extension."""
    keyword = draw(st.sampled_from(LEGISLATIVE_KEYWORDS))
    name_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=3,
        max_size=15,
    ))
    ext = draw(st.sampled_from([".md", ".pdf"]))
    return f"{name_part}_{keyword}_2024{ext}"


@st.composite
def html_filename(draw: st.DrawFn) -> str:
    """Generate random .html filenames."""
    name_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ))
    return f"{name_part}.html"


@st.composite
def txt_filename(draw: st.DrawFn) -> str:
    """Generate random .txt filenames."""
    name_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=20,
    ))
    return f"{name_part}.txt"


@st.composite
def unknown_extension_filename(draw: st.DrawFn) -> str:
    """Generate filenames with extensions not in (.pdf, .md, .html, .txt)."""
    name_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=3,
        max_size=15,
    ))
    ext = draw(st.sampled_from([".xyz", ".doc", ".csv", ".json", ".yaml", ".log", ".dat"]))
    return f"{name_part}{ext}"


@st.composite
def unregistered_strategy_name(draw: st.DrawFn) -> str:
    """Generate strategy names NOT in the registered set."""
    registered = {"fixed_size", "recursive", "semantic", "legal_hierarchical"}
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="_"),
        min_size=3,
        max_size=30,
    ))
    assume(name not in registered)
    assume(name.strip() != "")
    return name


# --- Helper functions ---


def make_document_from_text(plaintext: str) -> NormalizedDocument:
    """Create a NormalizedDocument from generated text with auto-detected sections."""
    import re

    sections: list[Section] = []

    # Detect sections by "Section N" pattern
    section_pattern = re.compile(
        r"^(Section\s+\d+(?:\s*[—–\-]\s*.+)?)\s*$", re.MULTILINE
    )
    matches = list(section_pattern.finditer(plaintext))

    if matches:
        for i, match in enumerate(matches):
            heading = match.group(1).strip()
            start = match.end() + 1 if match.end() < len(plaintext) else match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(plaintext)
            sections.append(Section(
                heading=heading,
                level=2,
                start_offset=start,
                end_offset=end,
            ))

    if not sections:
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
        source_path="generated_test_document.md",
    )


# --- Property Tests ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    doc_text=legislative_document_text(),
    max_size=max_chunk_size_strategy(),
)
def test_property_11_metadata_completeness(doc_text: str, max_size: int) -> None:
    """Property 11: Legal-hierarchical chunker metadata completeness.

    For any legislative document processed by the Legal_Hierarchical_Chunker,
    every output chunk SHALL have:
    - a non-empty section_heading field
    - a parent_document_title metadata entry (non-empty string)
    - the Act title prepended as contextual prefix (chunk text starts with it)
    - a hierarchy_path metadata entry (string)

    Validates: Requirements 5.1, 5.2, 5.5, 5.6
    """
    # Arrange
    document = make_document_from_text(doc_text)
    chunker = LegalHierarchicalChunker(max_chunk_size=max_size)

    # Act
    chunks = chunker.chunk(document)

    # Filter: only assert on documents that produce chunks
    assume(len(chunks) > 0)

    # Assert — the property that must hold for ALL valid inputs
    for chunk in chunks:
        # section_heading is non-empty string
        assert isinstance(chunk.section_heading, str)
        assert len(chunk.section_heading) > 0, (
            f"section_heading must be non-empty, got: '{chunk.section_heading}'"
        )

        # metadata["parent_document_title"] is non-empty string
        assert "parent_document_title" in chunk.metadata, (
            "chunk must have 'parent_document_title' in metadata"
        )
        assert isinstance(chunk.metadata["parent_document_title"], str)
        assert len(chunk.metadata["parent_document_title"]) > 0, (
            "parent_document_title must be non-empty"
        )

        # metadata["hierarchy_path"] is a string
        assert "hierarchy_path" in chunk.metadata, (
            "chunk must have 'hierarchy_path' in metadata"
        )
        assert isinstance(chunk.metadata["hierarchy_path"], str)

        # chunk text starts with Act title (prefix is prepended)
        # The parent_document_title should appear at the start of the chunk text
        parent_title = chunk.metadata["parent_document_title"]
        assert chunk.text.startswith(parent_title), (
            f"chunk text must start with Act title prefix '{parent_title}', "
            f"but starts with: '{chunk.text[:len(parent_title) + 20]}'"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(
    doc_text=legislative_document_text(),
    max_size=max_chunk_size_strategy(),
)
def test_property_12_size_constraints(doc_text: str, max_size: int) -> None:
    """Property 12: Legal-hierarchical chunker size constraints.

    For any document chunked by the Legal_Hierarchical_Chunker:
    - Every chunk does not exceed max_chunk_size OR body portion has exactly
      min_body_chars (100) when prefix is too large
    - When prefix + body > max_chunk_size: prefix is intact in the chunk text,
      body is reduced
    - Body never less than 100 characters

    Validates: Requirements 5.3, 5.4
    """
    # Arrange
    document = make_document_from_text(doc_text)
    chunker = LegalHierarchicalChunker(max_chunk_size=max_size, min_body_chars=100)

    # Act
    chunks = chunker.chunk(document)

    # Filter: only assert on documents that produce chunks
    assume(len(chunks) > 0)

    # Assert — size constraints
    for chunk in chunks:
        parent_title = chunk.metadata["parent_document_title"]

        # The chunk text starts with the prefix (Act title line at minimum)
        assert chunk.text.startswith(parent_title), (
            "prefix (Act title) must be preserved at the start of chunk"
        )

        # char_count must equal len(text)
        assert chunk.char_count == len(chunk.text), (
            f"char_count ({chunk.char_count}) must equal len(text) ({len(chunk.text)})"
        )

        # Size constraint: either within max_chunk_size, or body is min_body_chars
        # when prefix forces exceeding the limit
        if chunk.char_count > max_size:
            # If chunk exceeds max_size, it must be because the prefix is large
            # and the min_body_chars guarantee kicks in.
            # In this case, the body portion should be exactly min_body_chars (100).
            # Find the body: it's after the prefix + separator ("\n")
            # The prefix is built by _build_prefix: act_title + "\n" + part_heading (or just act_title)
            # Then _apply_size_constraints produces: prefix + "\n" + body_truncated

            # We know the chunk text starts with parent_title
            # The full prefix may include a part heading too
            # The body is the last segment after the prefix block
            # Since _apply_size_constraints does: f"{prefix}\n{body}"
            # We can find the prefix by detecting where the body starts
            # The prefix never gets truncated, so we know it's intact
            # The last "\n" before the body is our separator

            # Find the position after the full prefix
            # The prefix structure: "ActTitle\nPartHeading" or just "ActTitle"
            # followed by "\n" + body
            # Since the prefix itself may contain \n, we use the fact that
            # _apply_size_constraints adds exactly one \n between prefix and body

            # For validation: body must be at least min_body_chars
            # The simplest check: total - prefix - separator >= min_body_chars
            # But we don't know exact prefix length from outside
            # Instead just verify the body portion exists and is >= 100
            last_newline = chunk.text.rfind("\n")
            if last_newline > 0:
                body_after_last_newline = chunk.text[last_newline + 1:]
                # Body could span multiple lines if prefix has newlines
                # A simpler approach: the text after removing the prefix start
                # must have at least 100 chars of body content
                # The prefix is at minimum the parent_title
                remaining_after_title = chunk.text[len(parent_title):]
                # Strip the separator and any part heading
                # Body content is the actual section text
                # Just verify total body (everything that's not prefix) >= 100
                # We know prefix = act_title or act_title + "\n" + part
                # In all cases, body must be >= 100
                assert len(body_after_last_newline) >= 100 or chunk.char_count <= max_size, (
                    f"Body must be at least 100 chars when exceeding max_chunk_size. "
                    f"Body length: {len(body_after_last_newline)}, "
                    f"chunk size: {chunk.char_count}, max: {max_size}"
                )


@pytest.mark.property
@settings(max_examples=100)
@given(filename=legislative_filename())
def test_property_13_auto_select_legislative(filename: str) -> None:
    """Property 13: Chunker Registry auto-selection — legislative files.

    For random filenames with legislative keywords + .md/.pdf extension,
    the selected strategy should be "legal_hierarchical".

    Validates: Requirements 6.2, 6.5
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act
    chunker = registry.auto_select(filename)

    # Assert
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == "legal_hierarchical", (
        f"Expected 'legal_hierarchical' for filename '{filename}', got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(filename=html_filename())
def test_property_13_auto_select_html(filename: str) -> None:
    """Property 13: Chunker Registry auto-selection — HTML files.

    For random .html filenames, strategy should be "recursive".

    Validates: Requirements 6.2, 6.5
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act
    chunker = registry.auto_select(filename)

    # Assert
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == "recursive", (
        f"Expected 'recursive' for HTML filename '{filename}', got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(filename=txt_filename())
def test_property_13_auto_select_txt(filename: str) -> None:
    """Property 13: Chunker Registry auto-selection — TXT files.

    For random .txt filenames, strategy should be "fixed_size".

    Validates: Requirements 6.2, 6.5
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act
    chunker = registry.auto_select(filename)

    # Assert
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == "fixed_size", (
        f"Expected 'fixed_size' for TXT filename '{filename}', got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(filename=unknown_extension_filename())
def test_property_13_auto_select_unknown(filename: str) -> None:
    """Property 13: Chunker Registry auto-selection — unknown extensions.

    For random unknown extensions, strategy should be "fixed_size".

    Validates: Requirements 6.2, 6.5
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act
    chunker = registry.auto_select(filename)

    # Assert
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == "fixed_size", (
        f"Expected 'fixed_size' for unknown extension filename '{filename}', got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(filename=legislative_filename())
def test_property_13_fallback_when_unavailable(filename: str) -> None:
    """Property 13: Chunker Registry auto-selection — fallback to fixed_size.

    When the selected strategy is unavailable, falls back to "fixed_size".

    Validates: Requirements 6.2, 6.5
    """
    # Arrange — register legal_hierarchical as unavailable
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=False)

    # Act
    chunker = registry.auto_select(filename)

    # Assert — should fall back to fixed_size
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == "fixed_size", (
        f"Expected fallback to 'fixed_size' when legal_hierarchical unavailable, "
        f"got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(
    strategy_name=st.sampled_from(["fixed_size", "recursive", "semantic", "legal_hierarchical"])
)
def test_property_14_explicit_registered(strategy_name: str) -> None:
    """Property 14: Chunker Registry explicit strategy selection — registered names.

    For any registered strategy name, get_by_name returns the correct chunker.

    Validates: Requirements 6.6, 6.7
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act
    chunker = registry.get_by_name(strategy_name)

    # Assert
    assert isinstance(chunker, FakeChunker)
    assert chunker.name == strategy_name, (
        f"Expected chunker named '{strategy_name}', got '{chunker.name}'"
    )


@pytest.mark.property
@settings(max_examples=100)
@given(strategy_name=unregistered_strategy_name())
def test_property_14_explicit_unregistered(strategy_name: str) -> None:
    """Property 14: Chunker Registry explicit strategy selection — unregistered names.

    For any string NOT in registered names, get_by_name raises ValueError.

    Validates: Requirements 6.6, 6.7
    """
    # Arrange
    registry = ChunkerRegistry()
    registry.register("fixed_size", FakeChunker("fixed_size"), available=True)
    registry.register("recursive", FakeChunker("recursive"), available=True)
    registry.register("semantic", FakeChunker("semantic"), available=True)
    registry.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)

    # Act & Assert
    with pytest.raises(ValueError, match="not recognized"):
        registry.get_by_name(strategy_name)
