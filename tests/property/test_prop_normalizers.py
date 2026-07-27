"""Property tests for document normalizers.

# Feature: production-rag-pipeline-hybrid-search, Property 1: Normalization preserves document metadata
"""

from datetime import datetime
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.models.entities import RawDocument
from src.domain.models.enums import DocumentFormat
from src.domain.processing.html_normalizer import HTMLNormalizer
from src.domain.processing.markdown_normalizer import MarkdownNormalizer
from src.domain.processing.normalizer import DocumentNormalizer
from src.domain.processing.plaintext_normalizer import PlaintextNormalizer

# --- Custom Strategies ---

# Generate heading text: must start with a letter, contains letters/digits/spaces
# Filtered to avoid headings that are all digits/spaces (which parsers may not recognize)
# Also filtered to avoid consecutive spaces (HTML collapses whitespace)
heading_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" "),
    min_size=3,
    max_size=40,
).map(str.strip).filter(
    lambda s: len(s) >= 3 and any(c.isalpha() for c in s) and "  " not in s
)

# Generate a list of unique section headings
unique_headings = st.lists(
    heading_text,
    min_size=1,
    max_size=5,
    unique=True,
)


def build_markdown_document(headings: list[str]) -> bytes:
    """Build a markdown document with the given section headings."""
    parts = []
    for i, heading in enumerate(headings):
        level = (i % 3) + 1  # Cycle through h1, h2, h3
        parts.append(f"{'#' * level} {heading}")
        parts.append(f"This is content under the {heading} section.")
        parts.append("")  # blank line
    return "\n".join(parts).encode("utf-8")


def build_html_document(headings: list[str]) -> bytes:
    """Build an HTML document with the given section headings."""
    parts = ["<html><body>"]
    for i, heading in enumerate(headings):
        level = (i % 3) + 1  # Cycle through h1, h2, h3
        parts.append(f"<h{level}>{heading}</h{level}>")
        parts.append(f"<p>This is content under the {heading} section.</p>")
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


def build_plaintext_document(headings: list[str]) -> bytes:
    """Build a plaintext document with headings using ALL CAPS convention."""
    parts = []
    for heading in headings:
        # Use uppercase headings which PlaintextNormalizer detects
        parts.append(heading.upper())
        parts.append(f"This is content under the {heading} section.")
        parts.append("")  # blank line
    return "\n".join(parts).encode("utf-8")


# --- Property Tests ---


@pytest.mark.property
@settings(max_examples=100)
@given(headings=unique_headings)
def test_markdown_normalization_preserves_section_headings(headings: list[str]) -> None:
    """Property 1: Normalization preserves document metadata.

    For any Markdown document with known section headings, normalization
    SHALL produce output containing all section headings from the original.

    **Validates: Requirements 1.2**
    """
    content = build_markdown_document(headings)
    normalizer = MarkdownNormalizer()

    result = normalizer.normalize(content)

    # All headings from input must appear in the normalized sections
    extracted_headings = {section.heading for section in result.sections}
    for heading in headings:
        assert heading in extracted_headings, (
            f"Heading '{heading}' was not preserved after markdown normalization. "
            f"Extracted headings: {extracted_headings}"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(headings=unique_headings)
def test_html_normalization_preserves_section_headings(headings: list[str]) -> None:
    """Property 1: Normalization preserves document metadata.

    For any HTML document with known section headings, normalization
    SHALL produce output containing all section headings from the original.

    **Validates: Requirements 1.2**
    """
    content = build_html_document(headings)
    normalizer = HTMLNormalizer()

    result = normalizer.normalize(content)

    # All headings from input must appear in the normalized sections
    extracted_headings = {section.heading for section in result.sections}
    for heading in headings:
        assert heading in extracted_headings, (
            f"Heading '{heading}' was not preserved after HTML normalization. "
            f"Extracted headings: {extracted_headings}"
        )


# Strategy for plaintext headings: must start with a letter and contain only uppercase
# letters, digits, and spaces (matching PlaintextNormalizer.ALL_CAPS_PATTERN)
plaintext_heading_text = st.from_regex(r"[A-Z][A-Z0-9 ]{2,20}", fullmatch=True).map(
    str.strip
).filter(lambda s: len(s) >= 3)

unique_plaintext_headings = st.lists(
    plaintext_heading_text,
    min_size=1,
    max_size=5,
    unique=True,
)


@pytest.mark.property
@settings(max_examples=100)
@given(headings=unique_plaintext_headings)
def test_plaintext_normalization_preserves_section_headings(headings: list[str]) -> None:
    """Property 1: Normalization preserves document metadata.

    For any plaintext document with known section headings (ALL CAPS pattern),
    normalization SHALL produce output containing all section headings from the original.

    **Validates: Requirements 1.2**
    """
    # Build document with headings already in ALL CAPS format
    parts = []
    for heading in headings:
        parts.append(heading)
        parts.append("This is content under the section.")
        parts.append("")  # blank line
    content = "\n".join(parts).encode("utf-8")

    normalizer = PlaintextNormalizer()
    result = normalizer.normalize(content)

    # All uppercase headings from input must appear in the normalized sections
    extracted_headings = {section.heading for section in result.sections}
    for heading in headings:
        assert heading in extracted_headings, (
            f"Heading '{heading}' was not preserved after plaintext normalization. "
            f"Extracted headings: {extracted_headings}"
        )


@pytest.mark.property
@settings(max_examples=100)
@given(headings=unique_headings)
def test_document_normalizer_preserves_section_headings_markdown(
    headings: list[str],
) -> None:
    """Property 1: Normalization preserves document metadata.

    For any valid document processed through the DocumentNormalizer orchestrator,
    the output NormalizedDocument SHALL contain all section headings from the original.

    **Validates: Requirements 1.2**
    """
    content = build_markdown_document(headings)

    raw_doc = RawDocument(
        id=uuid4(),
        filename="test_doc.md",
        format=DocumentFormat.MARKDOWN,
        content=content,
        uploaded_by="test_user",
        uploaded_at=datetime.utcnow(),
        size_bytes=len(content),
    )

    normalizer = DocumentNormalizer()
    normalizer.register(DocumentFormat.MARKDOWN, MarkdownNormalizer())

    result = normalizer.normalize(raw_doc)

    # All headings must be preserved in the NormalizedDocument sections
    extracted_headings = {section.heading for section in result.sections}
    for heading in headings:
        assert heading in extracted_headings, (
            f"Heading '{heading}' was not preserved in NormalizedDocument. "
            f"Extracted headings: {extracted_headings}"
        )
    # Source document ID must be preserved
    assert result.source_document_id == raw_doc.id
    # Metadata must contain the source path
    assert result.metadata.source_path == raw_doc.filename
    assert result.metadata.format == DocumentFormat.MARKDOWN
