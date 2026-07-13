import re

from src.domain.models.entities import Section
from src.domain.processing.normalizer import NormalizedContent


class PlaintextNormalizer:
    """Pass-through normalizer with basic section detection for plaintext files."""

    # Pattern: Lines that are ALL CAPS (at least 3 chars, no lowercase)
    ALL_CAPS_PATTERN = re.compile(r"^([A-Z][A-Z0-9 \t]{2,})$", re.MULTILINE)

    # Pattern: Numbered headings like "1. Title", "1.1 Subtitle", "2.3.1 Deep"
    NUMBERED_HEADING_PATTERN = re.compile(
        r"^(\d+(?:\.\d+)*\.?)\s+(.+)$", re.MULTILINE
    )

    # Pattern: "Chapter X:" or "CHAPTER X:" style headings
    CHAPTER_PATTERN = re.compile(
        r"^(Chapter|CHAPTER|Part|PART|Section|SECTION)\s+[\dIVXLCDMivxlcdm]+[:\.]?\s*(.*)$",
        re.MULTILINE,
    )

    def normalize(self, content: bytes) -> NormalizedContent:
        text = content.decode("utf-8", errors="replace")
        sections = self._detect_sections(text)

        return NormalizedContent(plaintext=text, sections=sections, page_count=None)

    def _detect_sections(self, text: str) -> list[Section]:
        """Detect heading-like lines in plaintext using multiple heuristics."""
        sections: list[Section] = []
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check for underline-style headings (next line is === or ---)
            if i + 1 < len(lines) and stripped:
                next_line = lines[i + 1].strip()
                if next_line and all(c == "=" for c in next_line) and len(next_line) >= 3:
                    # Line followed by === → level 1
                    offset = self._line_offset(text, i)
                    sections.append(
                        Section(
                            heading=stripped,
                            level=1,
                            start_offset=offset,
                            end_offset=offset + len(stripped),
                            page_number=None,
                        )
                    )
                    i += 2
                    continue
                elif next_line and all(c == "-" for c in next_line) and len(next_line) >= 3:
                    # Line followed by --- → level 2
                    offset = self._line_offset(text, i)
                    sections.append(
                        Section(
                            heading=stripped,
                            level=2,
                            start_offset=offset,
                            end_offset=offset + len(stripped),
                            page_number=None,
                        )
                    )
                    i += 2
                    continue

            # Check ALL CAPS lines (level 1)
            if stripped and self.ALL_CAPS_PATTERN.match(stripped):
                # Avoid false positives: skip very short all-caps words that may be acronyms
                # within paragraphs by requiring the line to be standalone
                offset = self._line_offset(text, i)
                sections.append(
                    Section(
                        heading=stripped,
                        level=1,
                        start_offset=offset,
                        end_offset=offset + len(stripped),
                        page_number=None,
                    )
                )
                i += 1
                continue

            # Check Chapter/Part/Section patterns
            chapter_match = self.CHAPTER_PATTERN.match(stripped)
            if chapter_match:
                offset = self._line_offset(text, i)
                sections.append(
                    Section(
                        heading=stripped,
                        level=1,
                        start_offset=offset,
                        end_offset=offset + len(stripped),
                        page_number=None,
                    )
                )
                i += 1
                continue

            # Check numbered heading patterns (e.g. "1. Title", "1.1 Subtitle")
            numbered_match = self.NUMBERED_HEADING_PATTERN.match(stripped)
            if numbered_match:
                number_part = numbered_match.group(1)
                # Determine level by counting dots in the number
                dot_count = number_part.count(".")
                # "1." has 1 dot → level 1, "1.1" has 1 dot → level 2, "1.1.1" → level 3
                if number_part.endswith("."):
                    level = max(1, dot_count)
                else:
                    level = dot_count + 1
                offset = self._line_offset(text, i)
                sections.append(
                    Section(
                        heading=stripped,
                        level=level,
                        start_offset=offset,
                        end_offset=offset + len(stripped),
                        page_number=None,
                    )
                )
                i += 1
                continue

            i += 1

        return sections

    def _line_offset(self, text: str, line_index: int) -> int:
        """Calculate the character offset of the start of a line's content in the text."""
        offset = 0
        for idx, line in enumerate(text.split("\n")):
            if idx == line_index:
                # Return offset of the stripped content start
                leading_spaces = len(line) - len(line.lstrip())
                return offset + leading_spaces
            offset += len(line) + 1  # +1 for the \n character
        return offset
