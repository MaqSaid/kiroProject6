from __future__ import annotations

import fitz  # PyMuPDF

from src.domain.models.entities import Section
from src.domain.processing.normalizer import NormalizedContent


class PDFNormalizer:
    """Extracts text from PDF documents, preserving page numbers and section headings.

    Heading detection uses font-size analysis: text spans with font size significantly
    larger than the document's body font size are treated as headings. The heading level
    is determined by relative font size (larger = higher level heading).
    """

    # Font size must be at least this factor above the body font to be a heading
    HEADING_FONT_RATIO = 1.2

    def normalize(self, content: bytes) -> NormalizedContent:
        doc = fitz.open(stream=content, filetype="pdf")

        try:
            body_font_size = self._detect_body_font_size(doc)
            page_texts: list[str] = []
            raw_headings: list[tuple[int, str, int]] = []  # (level, text, page_number)

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text, headings = self._extract_page_content(
                    page, page_num + 1, body_font_size
                )
                page_texts.append(page_text)
                raw_headings.extend(headings)

            plaintext = "\n\n".join(page_texts).strip()
            sections = self._build_sections(plaintext, raw_headings)

            return NormalizedContent(
                plaintext=plaintext,
                sections=sections,
                page_count=len(doc),
            )
        finally:
            doc.close()

    def _detect_body_font_size(self, doc: fitz.Document) -> float:
        """Determine the most common font size in the document (the body font size).

        Analyzes font sizes across all pages and returns the most frequent one.
        Falls back to 12.0 if the document has no text.
        """
        font_size_counts: dict[float, int] = {}

        for page_num in range(min(len(doc), 5)):  # Sample first 5 pages
            page = doc[page_num]
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block in blocks:
                if block.get("type") != 0:  # Skip non-text blocks
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            size = round(span.get("size", 12.0), 1)
                            font_size_counts[size] = font_size_counts.get(size, 0) + len(text)

        if not font_size_counts:
            return 12.0

        # The body font is the one covering the most characters
        return max(font_size_counts, key=lambda s: font_size_counts[s])

    def _extract_page_content(
        self, page: fitz.Page, page_number: int, body_font_size: float
    ) -> tuple[str, list[tuple[int, str, int]]]:
        """Extract text and headings from a single page.

        Returns:
            A tuple of (page_text, headings) where headings is a list of
            (level, heading_text, page_number).
        """
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        lines_text: list[str] = []
        headings: list[tuple[int, str, int]] = []

        for block in blocks:
            if block.get("type") != 0:  # Skip non-text blocks (images, etc.)
                continue

            for line in block.get("lines", []):
                line_text_parts: list[str] = []
                max_font_size = 0.0

                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text.strip():
                        max_font_size = max(max_font_size, span.get("size", 12.0))
                    line_text_parts.append(text)

                line_text = "".join(line_text_parts).strip()
                if not line_text:
                    continue

                lines_text.append(line_text)

                # Check if this line is a heading based on font size
                if max_font_size >= body_font_size * self.HEADING_FONT_RATIO:
                    level = self._font_size_to_level(max_font_size, body_font_size)
                    headings.append((level, line_text, page_number))

        page_text = "\n".join(lines_text)
        return page_text, headings

    def _font_size_to_level(self, font_size: float, body_font_size: float) -> int:
        """Map font size to heading level (1-6). Larger font = lower level number."""
        ratio = font_size / body_font_size if body_font_size > 0 else 1.0

        if ratio >= 2.0:
            return 1
        elif ratio >= 1.7:
            return 2
        elif ratio >= 1.4:
            return 3
        elif ratio >= 1.2:
            return 4
        else:
            return 5

    def _build_sections(
        self, plaintext: str, headings: list[tuple[int, str, int]]
    ) -> list[Section]:
        """Build Section objects by finding heading positions in the extracted plaintext."""
        sections: list[Section] = []
        search_start = 0

        for level, heading_text, page_number in headings:
            idx = plaintext.find(heading_text, search_start)
            if idx >= 0:
                sections.append(
                    Section(
                        heading=heading_text,
                        level=level,
                        start_offset=idx,
                        end_offset=idx + len(heading_text),
                        page_number=page_number,
                    )
                )
                search_start = idx + len(heading_text)
            else:
                # Fallback: search from the beginning
                idx = plaintext.find(heading_text)
                if idx >= 0:
                    sections.append(
                        Section(
                            heading=heading_text,
                            level=level,
                            start_offset=idx,
                            end_offset=idx + len(heading_text),
                            page_number=page_number,
                        )
                    )

        return sections
