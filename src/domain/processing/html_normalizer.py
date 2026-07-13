from bs4 import BeautifulSoup, NavigableString

from src.domain.models.entities import Section
from src.domain.processing.normalizer import NormalizedContent


class HTMLNormalizer:
    """Strips HTML tags, preserves heading hierarchy, extracts plaintext."""

    HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def normalize(self, content: bytes) -> NormalizedContent:
        text = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, "lxml")

        # Extract headings with their text before stripping
        headings: list[tuple[int, str]] = []
        for tag in soup.find_all(list(self.HEADING_TAGS.keys())):
            level = self.HEADING_TAGS[tag.name]
            heading_text = tag.get_text(strip=True)
            if heading_text:
                headings.append((level, heading_text))

        # Extract plaintext from the parsed HTML
        plaintext = self._extract_plaintext(soup)

        # Build sections with offsets in the plaintext
        sections = self._build_sections(plaintext, headings)

        return NormalizedContent(plaintext=plaintext, sections=sections)

    def _extract_plaintext(self, soup: BeautifulSoup) -> str:
        """Extract clean plaintext from parsed HTML, preserving logical spacing."""
        # Remove script and style elements entirely
        for element in soup.find_all(["script", "style"]):
            element.decompose()

        # Get text with newline separators for block elements
        lines: list[str] = []
        for element in soup.descendants:
            if isinstance(element, NavigableString):
                text = element.strip()
                if text:
                    lines.append(text)
            elif element.name in (
                "br",
                "p",
                "div",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
                "tr",
                "blockquote",
                "pre",
                "hr",
                "section",
                "article",
                "header",
                "footer",
                "nav",
            ):
                # Add separator for block-level elements
                if lines and lines[-1] != "\n":
                    lines.append("\n")

        # Join and clean up whitespace
        raw = " ".join(lines)
        # Normalize whitespace: collapse multiple spaces/newlines
        import re

        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r" ?\n ?", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()

    def _build_sections(
        self, plaintext: str, headings: list[tuple[int, str]]
    ) -> list[Section]:
        """Find heading positions in the extracted plaintext and build Section objects."""
        sections: list[Section] = []
        search_start = 0

        for level, heading_text in headings:
            idx = plaintext.find(heading_text, search_start)
            if idx >= 0:
                sections.append(
                    Section(
                        heading=heading_text,
                        level=level,
                        start_offset=idx,
                        end_offset=idx + len(heading_text),
                        page_number=None,
                    )
                )
                # Advance search start to avoid matching same text twice
                search_start = idx + len(heading_text)
            else:
                # Fallback: search from the beginning if not found after current position
                idx = plaintext.find(heading_text)
                if idx >= 0:
                    sections.append(
                        Section(
                            heading=heading_text,
                            level=level,
                            start_offset=idx,
                            end_offset=idx + len(heading_text),
                            page_number=None,
                        )
                    )

        return sections
