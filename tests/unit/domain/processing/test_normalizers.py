"""Unit tests for all document normalizers.

Covers: MarkdownNormalizer, HTMLNormalizer, PDFNormalizer,
PlaintextNormalizer, and DocumentNormalizer (dispatcher).

Validates: Requirements 1.1, 1.2, 1.4, 1.5
"""

from datetime import datetime
from uuid import uuid4

from src.domain.models.entities import RawDocument
from src.domain.models.enums import DocumentFormat

# ============================================================
# Helpers
# ============================================================


def _make_raw_document(
    content: bytes,
    fmt: DocumentFormat,
    filename: str = "test.txt",
) -> RawDocument:
    return RawDocument(
        id=uuid4(),
        filename=filename,
        format=fmt,
        content=content,
        uploaded_by="test-user",
        uploaded_at=datetime.utcnow(),
        size_bytes=len(content),
    )


# ============================================================
# MarkdownNormalizer Tests
# ============================================================


@pytest.mark.unit
class TestMarkdownNormalizerStripping:
    """MarkdownNormalizer strips markdown syntax while preserving content."""

    def setup_method(self):
        self.normalizer = MarkdownNormalizer()

    def test_strips_heading_markers(self):
        content = b"# Title\n\nSome body text."
        result = self.normalizer.normalize(content)
        assert "# " not in result.plaintext
        assert "Title" in result.plaintext
        assert "Some body text." in result.plaintext

    def test_strips_bold_markers(self):
        content = b"This is **bold** text."
        result = self.normalizer.normalize(content)
        assert "**" not in result.plaintext
        assert "bold" in result.plaintext

    def test_strips_italic_markers(self):
        content = b"This is *italic* text."
        result = self.normalizer.normalize(content)
        assert result.plaintext.count("*") == 0
        assert "italic" in result.plaintext

    def test_strips_underscore_bold(self):
        content = b"This is __bold__ text."
        result = self.normalizer.normalize(content)
        assert "__" not in result.plaintext
        assert "bold" in result.plaintext

    def test_strips_underscore_italic(self):
        content = b"This is _italic_ text."
        result = self.normalizer.normalize(content)
        assert "italic" in result.plaintext

    def test_strips_inline_code(self):
        content = b"Use `print()` to output."
        result = self.normalizer.normalize(content)
        assert "`" not in result.plaintext
        assert "print()" in result.plaintext

    def test_strips_links_keeps_text(self):
        content = b"See [the docs](https://example.com) for details."
        result = self.normalizer.normalize(content)
        assert "[" not in result.plaintext
        assert "https://example.com" not in result.plaintext
        assert "the docs" in result.plaintext

    def test_strips_images(self):
        content = b"Here: ![alt text](image.png) done."
        result = self.normalizer.normalize(content)
        assert "![" not in result.plaintext
        assert "image.png" not in result.plaintext

    def test_strips_blockquote_markers(self):
        content = b"> This is a quote."
        result = self.normalizer.normalize(content)
        assert result.plaintext.startswith("This is a quote.")

    def test_strips_list_markers(self):
        content = b"- Item one\n- Item two\n* Item three"
        result = self.normalizer.normalize(content)
        assert "- " not in result.plaintext
        assert "* " not in result.plaintext
        assert "Item one" in result.plaintext
        assert "Item two" in result.plaintext

    def test_strips_ordered_list_markers(self):
        content = b"1. First\n2. Second\n3. Third"
        result = self.normalizer.normalize(content)
        assert "1. " not in result.plaintext
        assert "First" in result.plaintext
        assert "Second" in result.plaintext

    def test_strips_horizontal_rules(self):
        content = b"Above\n\n---\n\nBelow"
        result = self.normalizer.normalize(content)
        assert "---" not in result.plaintext
        assert "Above" in result.plaintext
        assert "Below" in result.plaintext


@pytest.mark.unit
class TestMarkdownNormalizerHeadings:
    """MarkdownNormalizer preserves heading information in sections."""

    def setup_method(self):
        self.normalizer = MarkdownNormalizer()

    def test_extracts_h1_heading(self):
        content = b"# Main Title\n\nBody text."
        result = self.normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Main Title"
        assert result.sections[0].level == 1

    def test_extracts_multiple_heading_levels(self):
        content = b"# Title\n\n## Subtitle\n\n### Sub-sub\n\nText."
        result = self.normalizer.normalize(content)
        assert len(result.sections) == 3
        assert result.sections[0].level == 1
        assert result.sections[1].level == 2
        assert result.sections[2].level == 3

    def test_heading_offsets_point_to_plaintext(self):
        content = b"# Introduction\n\nSome text.\n\n## Methods\n\nMore text."
        result = self.normalizer.normalize(content)
        for section in result.sections:
            extracted = result.plaintext[section.start_offset:section.end_offset]
            assert extracted == section.heading

    def test_all_six_heading_levels(self):
        content = (
            b"# H1\n## H2\n### H3\n"
            b"#### H4\n##### H5\n###### H6\n"
        )
        result = self.normalizer.normalize(content)
        assert len(result.sections) == 6
        for i, section in enumerate(result.sections, start=1):
            assert section.level == i

    def test_page_count_is_none(self):
        content = b"# Title\n\nContent."
        result = self.normalizer.normalize(content)
        assert result.page_count is None


@pytest.mark.unit
class TestMarkdownNormalizerEdgeCases:
    """MarkdownNormalizer handles edge cases gracefully."""

    def setup_method(self):
        self.normalizer = MarkdownNormalizer()

    def test_empty_content(self):
        result = self.normalizer.normalize(b"")
        assert result.plaintext == ""
        assert result.sections == []

    def test_whitespace_only_content(self):
        result = self.normalizer.normalize(b"   \n\n   ")
        assert result.plaintext.strip() == ""
        assert result.sections == []

    def test_no_headings(self):
        content = b"Just plain text with no headings at all."
        result = self.normalizer.normalize(content)
        assert result.sections == []
        assert "Just plain text" in result.plaintext

    def test_utf8_content(self):
        content = "# Ünïcödé Hëading\n\nCafé résumé naïve".encode()
        result = self.normalizer.normalize(content)
        assert "Ünïcödé Hëading" in result.plaintext
        assert "Café résumé naïve" in result.plaintext

    def test_malformed_heading_no_space(self):
        # '#Title' without space should NOT be treated as heading
        content = b"#NoSpace\n\nSome text."
        result = self.normalizer.normalize(content)
        assert len(result.sections) == 0


# ============================================================
# HTMLNormalizer Tests
# ============================================================


@pytest.mark.unit
class TestHTMLNormalizerBasic:
    """HTMLNormalizer strips tags and preserves content."""

    def setup_method(self):
        self.normalizer = HTMLNormalizer()

    def test_strips_all_tags(self):
        html = b"<p><strong>Bold</strong> and <em>italic</em></p>"
        result = self.normalizer.normalize(html)
        assert "<" not in result.plaintext
        assert "Bold" in result.plaintext
        assert "italic" in result.plaintext

    def test_preserves_heading_hierarchy(self):
        html = b"""
        <html><body>
            <h1>Title</h1>
            <h2>Section A</h2>
            <h3>Subsection</h3>
        </body></html>
        """
        result = self.normalizer.normalize(html)
        assert len(result.sections) == 3
        assert result.sections[0].level == 1
        assert result.sections[1].level == 2
        assert result.sections[2].level == 3

    def test_removes_script_tags(self):
        html = b"<script>alert('xss')</script><p>Safe</p>"
        result = self.normalizer.normalize(html)
        assert "alert" not in result.plaintext
        assert "Safe" in result.plaintext

    def test_removes_style_tags(self):
        html = b"<style>.red{color:red}</style><p>Content</p>"
        result = self.normalizer.normalize(html)
        assert "color" not in result.plaintext
        assert "Content" in result.plaintext

    def test_page_count_is_none(self):
        html = b"<p>Hello</p>"
        result = self.normalizer.normalize(html)
        assert result.page_count is None


@pytest.mark.unit
class TestHTMLNormalizerEdgeCases:
    """HTMLNormalizer handles malformed and edge-case HTML."""

    def setup_method(self):
        self.normalizer = HTMLNormalizer()

    def test_empty_html(self):
        result = self.normalizer.normalize(b"")
        assert result.plaintext == ""
        assert result.sections == []

    def test_malformed_unclosed_tags(self):
        html = b"<p>Unclosed <b>bold<p>Next paragraph"
        result = self.normalizer.normalize(html)
        assert "Unclosed" in result.plaintext
        assert "bold" in result.plaintext

    def test_malformed_nested_incorrectly(self):
        html = b"<div><p>Text</div></p>"
        result = self.normalizer.normalize(html)
        assert "Text" in result.plaintext

    def test_empty_heading_tags_ignored(self):
        html = b"<h1></h1><h2>Real Heading</h2>"
        result = self.normalizer.normalize(html)
        # Empty headings should not produce sections
        assert all(s.heading != "" for s in result.sections)
        assert any(s.heading == "Real Heading" for s in result.sections)

    def test_entities_decoded(self):
        html = b"<p>&amp; &lt; &gt; &quot;</p>"
        result = self.normalizer.normalize(html)
        assert "&" in result.plaintext
        assert "<" in result.plaintext
        assert ">" in result.plaintext


# ============================================================
# PDFNormalizer Tests
# ============================================================


def _make_span(text: str, size: float = 12.0) -> dict:
    """Helper to create a mock span dict for PDF tests."""
    return {"text": text, "size": size}


def _make_line(spans: list[dict]) -> dict:
    return {"spans": spans}


def _make_text_block(lines: list[dict]) -> dict:
    return {"type": 0, "lines": lines}


@pytest.mark.unit
class TestPDFNormalizerExtraction:
    """PDFNormalizer extracts text and preserves page numbers."""

    def setup_method(self):
        self.normalizer = PDFNormalizer()

    def _mock_single_page_doc(self, blocks: list[dict]) -> MagicMock:
        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        return mock_doc

    def test_extracts_text_from_single_page(self):
        blocks = [
            _make_text_block([
                _make_line([_make_span("Hello from PDF.", 12.0)]),
            ])
        ]
        mock_doc = self._mock_single_page_doc(blocks)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1
            result = self.normalizer.normalize(b"fake pdf")

        assert "Hello from PDF." in result.plaintext
        assert result.page_count == 1

    def test_multi_page_preserves_page_numbers(self):
        page1_blocks = [
            _make_text_block([
                _make_line([_make_span("Chapter 1", 24.0)]),
                _make_line([_make_span("Page one content.", 12.0)]),
            ])
        ]
        page2_blocks = [
            _make_text_block([
                _make_line([_make_span("Chapter 2", 24.0)]),
                _make_line([_make_span("Page two content.", 12.0)]),
            ])
        ]

        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = {"blocks": page1_blocks}
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = {"blocks": page2_blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.__getitem__ = MagicMock(
            side_effect=[mock_page1, mock_page2, mock_page1, mock_page2]
        )

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1
            result = self.normalizer.normalize(b"fake pdf")

        assert result.page_count == 2
        assert len(result.sections) == 2
        assert result.sections[0].page_number == 1
        assert result.sections[1].page_number == 2

    def test_empty_pdf_no_pages(self):
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1
            result = self.normalizer.normalize(b"fake pdf")

        assert result.plaintext == ""
        assert result.sections == []
        assert result.page_count == 0

    def test_heading_detected_by_font_size(self):
        blocks = [
            _make_text_block([
                _make_line([_make_span("Big Title", 24.0)]),
                _make_line([
                    _make_span(
                        "Body text that is longer to dominate font stats.", 12.0
                    )
                ]),
            ])
        ]
        mock_doc = self._mock_single_page_doc(blocks)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1
            result = self.normalizer.normalize(b"fake pdf")

        assert len(result.sections) == 1
        assert result.sections[0].heading == "Big Title"
        assert result.sections[0].level == 1


# ============================================================
# PlaintextNormalizer Tests
# ============================================================


@pytest.mark.unit
class TestPlaintextNormalizerPassThrough:
    """PlaintextNormalizer passes content through unchanged."""

    def setup_method(self):
        self.normalizer = PlaintextNormalizer()

    def test_content_unchanged(self):
        content = b"Hello, world!\nSecond line."
        result = self.normalizer.normalize(content)
        assert result.plaintext == "Hello, world!\nSecond line."

    def test_page_count_is_none(self):
        result = self.normalizer.normalize(b"Some text.")
        assert result.page_count is None

    def test_empty_content(self):
        result = self.normalizer.normalize(b"")
        assert result.plaintext == ""
        assert result.sections == []

    def test_utf8_decoding(self):
        content = "Ñoño café".encode()
        result = self.normalizer.normalize(content)
        assert result.plaintext == "Ñoño café"


@pytest.mark.unit
class TestPlaintextNormalizerHeadingDetection:
    """PlaintextNormalizer detects heading patterns in plaintext."""

    def setup_method(self):
        self.normalizer = PlaintextNormalizer()

    def test_all_caps_detected(self):
        content = b"INTRODUCTION\n\nBody text here."
        result = self.normalizer.normalize(content)
        assert len(result.sections) >= 1
        assert result.sections[0].heading == "INTRODUCTION"
        assert result.sections[0].level == 1

    def test_underline_equals_heading(self):
        content = b"Main Title\n==========\n\nBody."
        result = self.normalizer.normalize(content)
        assert len(result.sections) >= 1
        assert result.sections[0].heading == "Main Title"
        assert result.sections[0].level == 1

    def test_underline_dashes_heading(self):
        content = b"Subsection\n----------\n\nBody."
        result = self.normalizer.normalize(content)
        assert len(result.sections) >= 1
        assert result.sections[0].heading == "Subsection"
        assert result.sections[0].level == 2

    def test_numbered_heading(self):
        content = b"1.2 Background\n\nSome text."
        result = self.normalizer.normalize(content)
        assert len(result.sections) >= 1
        assert result.sections[0].heading == "1.2 Background"

    def test_chapter_heading(self):
        content = b"Chapter 3: Methods\n\nWe used..."
        result = self.normalizer.normalize(content)
        assert len(result.sections) >= 1
        assert "Chapter 3" in result.sections[0].heading


# ============================================================
# DocumentNormalizer Tests (Dispatcher)
# ============================================================


@pytest.mark.unit
class TestDocumentNormalizerDispatch:
    """DocumentNormalizer dispatches to the correct format-specific normalizer."""

    def setup_method(self):
        self.doc_normalizer = DocumentNormalizer()
        self.doc_normalizer.register(DocumentFormat.MARKDOWN, MarkdownNormalizer())
        self.doc_normalizer.register(DocumentFormat.HTML, HTMLNormalizer())
        self.doc_normalizer.register(DocumentFormat.PLAINTEXT, PlaintextNormalizer())
        # PDF requires mocking, tested separately

    def test_dispatches_to_markdown(self):
        raw = _make_raw_document(
            content=b"# Hello\n\nWorld.",
            fmt=DocumentFormat.MARKDOWN,
            filename="readme.md",
        )
        result = self.doc_normalizer.normalize(raw)
        assert "Hello" in result.plaintext
        assert result.metadata.format == DocumentFormat.MARKDOWN
        assert result.source_document_id == raw.id

    def test_dispatches_to_html(self):
        raw = _make_raw_document(
            content=b"<p>Hello HTML</p>",
            fmt=DocumentFormat.HTML,
            filename="page.html",
        )
        result = self.doc_normalizer.normalize(raw)
        assert "Hello HTML" in result.plaintext
        assert result.metadata.format == DocumentFormat.HTML

    def test_dispatches_to_plaintext(self):
        raw = _make_raw_document(
            content=b"Plain text content.",
            fmt=DocumentFormat.PLAINTEXT,
            filename="notes.txt",
        )
        result = self.doc_normalizer.normalize(raw)
        assert result.plaintext == "Plain text content."
        assert result.metadata.format == DocumentFormat.PLAINTEXT

    def test_preserves_source_document_id(self):
        raw = _make_raw_document(
            content=b"Content.",
            fmt=DocumentFormat.PLAINTEXT,
        )
        result = self.doc_normalizer.normalize(raw)
        assert result.source_document_id == raw.id

    def test_sets_source_path_from_filename(self):
        raw = _make_raw_document(
            content=b"Content.",
            fmt=DocumentFormat.PLAINTEXT,
            filename="docs/guide.txt",
        )
        result = self.doc_normalizer.normalize(raw)
        assert result.metadata.source_path == "docs/guide.txt"

    def test_sets_ingested_at_timestamp(self):
        raw = _make_raw_document(
            content=b"Content.",
            fmt=DocumentFormat.PLAINTEXT,
        )
        before = datetime.utcnow()
        result = self.doc_normalizer.normalize(raw)
        after = datetime.utcnow()
        assert before <= result.metadata.ingested_at <= after
