import re

from src.domain.models.entities import Section
from src.domain.processing.normalizer import NormalizedContent


class MarkdownNormalizer:
    """Strips Markdown syntax, preserves section headings with offsets."""

    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def normalize(self, content: bytes) -> NormalizedContent:
        text = content.decode("utf-8", errors="replace")
        sections: list[Section] = []

        # Extract headings before stripping
        for match in self.HEADING_PATTERN.finditer(text):
            level = len(match.group(1))
            heading = match.group(2).strip()
            sections.append(
                Section(
                    heading=heading,
                    level=level,
                    start_offset=match.start(),
                    end_offset=match.end(),
                    page_number=None,
                )
            )

        # Strip markdown formatting
        plaintext = self._strip_markdown(text)

        # Recalculate section offsets in stripped text
        stripped_sections = self._recalculate_offsets(plaintext, sections)

        return NormalizedContent(plaintext=plaintext, sections=stripped_sections)

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown formatting while preserving content."""
        # Remove headers markers but keep text
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)
        # Remove inline code
        text = re.sub(r"`(.+?)`", r"\1", text)
        # Remove links, keep text
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        # Remove images
        text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
        # Remove horizontal rules
        text = re.sub(r"^---+$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\*\*\*+$", "", text, flags=re.MULTILINE)
        # Remove blockquotes markers
        text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
        # Remove list markers
        text = re.sub(r"^[\-\*\+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
        # Clean up multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _recalculate_offsets(
        self, plaintext: str, original_sections: list[Section]
    ) -> list[Section]:
        """Find section heading positions in the stripped plaintext."""
        result: list[Section] = []
        for section in original_sections:
            idx = plaintext.find(section.heading)
            if idx >= 0:
                result.append(
                    Section(
                        heading=section.heading,
                        level=section.level,
                        start_offset=idx,
                        end_offset=idx + len(section.heading),
                        page_number=section.page_number,
                    )
                )
            else:
                # Keep original if not found in stripped text
                result.append(section)
        return result
