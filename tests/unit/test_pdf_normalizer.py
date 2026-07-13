"""Unit tests for PDFNormalizer.

Since creating real PDF bytes in tests is complex, we mock PyMuPDF (fitz)
to simulate various PDF structures and validate the normalizer's behavior.
"""

from unittest.mock import MagicMock, patch

from src.domain.processing.pdf_normalizer import PDFNormalizer


def _make_span(text: str, size: float = 12.0) -> dict:
    """Helper to create a mock span dict."""
    return {"text": text, "size": size}


def _make_line(spans: list[dict]) -> dict:
    """Helper to create a mock line dict."""
    return {"spans": spans}


def _make_text_block(lines: list[dict]) -> dict:
    """Helper to create a mock text block."""
    return {"type": 0, "lines": lines}


def _make_image_block() -> dict:
    """Helper to create a mock image block (non-text)."""
    return {"type": 1}


class TestPDFNormalizerBasic:
    """Test basic PDF normalization functionality."""

    def test_single_page_plain_text(self):
        """A single-page PDF with only body text produces correct plaintext."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_text_block([
                _make_line([_make_span("Hello world.", 12.0)]),
                _make_line([_make_span("This is body text.", 12.0)]),
            ])
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert "Hello world." in result.plaintext
        assert "This is body text." in result.plaintext
        assert result.page_count == 1
        assert result.sections == []

    def test_heading_detection_by_font_size(self):
        """Text with larger font size is detected as a heading."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_text_block([
                _make_line([_make_span("Chapter One", 24.0)]),  # Large = heading
                _make_line([_make_span("Some paragraph text here.", 12.0)]),
            ])
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert len(result.sections) == 1
        assert result.sections[0].heading == "Chapter One"
        assert result.sections[0].level == 1  # ratio 24/12 = 2.0
        assert result.sections[0].page_number == 1

    def test_multiple_heading_levels(self):
        """Different font sizes map to different heading levels."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_text_block([
                _make_line([_make_span("Main Title", 24.0)]),  # ratio 2.0 -> level 1
                _make_line([_make_span("Subtitle", 20.0)]),    # ratio ~1.67 -> level 2
                _make_line([_make_span("Section", 17.0)]),     # ratio ~1.42 -> level 3
                _make_line([_make_span("This is body text that is much longer than any heading to ensure it dominates the font size detection.", 12.0)]),
            ])
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert len(result.sections) == 3
        assert result.sections[0].heading == "Main Title"
        assert result.sections[0].level == 1
        assert result.sections[1].heading == "Subtitle"
        assert result.sections[1].level in (2, 3)  # ratio 1.67
        assert result.sections[2].heading == "Section"
        assert result.sections[2].level in (3, 4)  # ratio 1.42


class TestPDFNormalizerMultiPage:
    """Test multi-page PDF handling."""

    def test_multi_page_preserves_page_numbers(self):
        """Headings on different pages get the correct page_number."""
        normalizer = PDFNormalizer()

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
        mock_doc.__getitem__ = MagicMock(side_effect=[
            # First 2 calls for body font detection (samples first 5 pages)
            mock_page1, mock_page2,
            # Next 2 calls for content extraction
            mock_page1, mock_page2,
        ])

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert result.page_count == 2
        assert len(result.sections) == 2
        assert result.sections[0].heading == "Chapter 1"
        assert result.sections[0].page_number == 1
        assert result.sections[1].heading == "Chapter 2"
        assert result.sections[1].page_number == 2

    def test_page_count_reflects_document_length(self):
        """page_count should match the total number of pages."""
        normalizer = PDFNormalizer()

        blocks = [_make_text_block([_make_line([_make_span("Text", 12.0)])])]
        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=5)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert result.page_count == 5


class TestPDFNormalizerEdgeCases:
    """Test edge cases and robustness."""

    def test_empty_pdf(self):
        """An empty PDF (no pages) produces empty output."""
        normalizer = PDFNormalizer()

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert result.plaintext == ""
        assert result.sections == []
        assert result.page_count == 0

    def test_image_blocks_are_skipped(self):
        """Non-text blocks (images) should not appear in plaintext."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_image_block(),
            _make_text_block([
                _make_line([_make_span("Visible text.", 12.0)]),
            ]),
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert "Visible text." in result.plaintext
        assert result.page_count == 1

    def test_whitespace_only_lines_are_ignored(self):
        """Lines with only whitespace should not produce heading entries."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_text_block([
                _make_line([_make_span("   ", 24.0)]),  # Whitespace-only with big font
                _make_line([_make_span("Real content.", 12.0)]),
            ])
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert result.sections == []
        assert "Real content." in result.plaintext

    def test_section_offsets_are_correct(self):
        """Section start_offset and end_offset point to heading position in plaintext."""
        normalizer = PDFNormalizer()

        blocks = [
            _make_text_block([
                _make_line([_make_span("Introduction", 18.0)]),
                _make_line([_make_span("Some content here.", 12.0)]),
            ])
        ]

        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            result = normalizer.normalize(b"fake pdf bytes")

        assert len(result.sections) == 1
        section = result.sections[0]
        # Verify offset points to actual text in plaintext
        assert result.plaintext[section.start_offset:section.end_offset] == "Introduction"

    def test_document_is_closed_after_processing(self):
        """The fitz document is closed after normalization."""
        normalizer = PDFNormalizer()

        blocks = [_make_text_block([_make_line([_make_span("Text", 12.0)])])]
        mock_page = MagicMock()
        mock_page.get_text.return_value = {"blocks": blocks}

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        with patch("src.domain.processing.pdf_normalizer.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.TEXT_PRESERVE_WHITESPACE = 1

            normalizer.normalize(b"fake pdf bytes")

        mock_doc.close.assert_called_once()
