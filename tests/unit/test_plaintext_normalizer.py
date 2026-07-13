"""Unit tests for PlaintextNormalizer."""

import pytest

from src.domain.processing.plaintext_normalizer import PlaintextNormalizer


@pytest.fixture
def normalizer() -> PlaintextNormalizer:
    return PlaintextNormalizer()


class TestPassThrough:
    """Plaintext normalizer should pass content through unchanged."""

    def test_returns_content_as_plaintext(self, normalizer: PlaintextNormalizer):
        content = b"Hello, world!\nThis is a test."
        result = normalizer.normalize(content)
        assert result.plaintext == "Hello, world!\nThis is a test."

    def test_page_count_is_none(self, normalizer: PlaintextNormalizer):
        content = b"Some text content."
        result = normalizer.normalize(content)
        assert result.page_count is None

    def test_handles_utf8_content(self, normalizer: PlaintextNormalizer):
        content = "Héllo wörld café résumé".encode()
        result = normalizer.normalize(content)
        assert result.plaintext == "Héllo wörld café résumé"

    def test_handles_empty_content(self, normalizer: PlaintextNormalizer):
        result = normalizer.normalize(b"")
        assert result.plaintext == ""
        assert result.sections == []

    def test_no_sections_in_plain_paragraph(self, normalizer: PlaintextNormalizer):
        content = b"This is just a normal paragraph with no headings.\nAnother line here."
        result = normalizer.normalize(content)
        assert result.sections == []


class TestAllCapsDetection:
    """Lines that are ALL CAPS should be detected as level 1 headings."""

    def test_all_caps_line_detected(self, normalizer: PlaintextNormalizer):
        content = b"INTRODUCTION\n\nSome paragraph text follows."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "INTRODUCTION"
        assert result.sections[0].level == 1

    def test_all_caps_with_spaces(self, normalizer: PlaintextNormalizer):
        content = b"GETTING STARTED\n\nFirst, install the package."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "GETTING STARTED"
        assert result.sections[0].level == 1

    def test_all_caps_with_numbers(self, normalizer: PlaintextNormalizer):
        content = b"APPENDIX A2\n\nSome appendix content."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "APPENDIX A2"
        assert result.sections[0].level == 1

    def test_short_all_caps_not_detected(self, normalizer: PlaintextNormalizer):
        """Very short all-caps words (< 3 meaningful chars) should not be detected."""
        content = b"OK\n\nSome text."
        result = normalizer.normalize(content)
        # "OK" is too short (only 2 chars)
        assert len(result.sections) == 0


class TestUnderlineHeadings:
    """Lines followed by === or --- underlines should be detected."""

    def test_equals_underline_level_1(self, normalizer: PlaintextNormalizer):
        content = b"Main Title\n==========\n\nSome content."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Main Title"
        assert result.sections[0].level == 1

    def test_dash_underline_level_2(self, normalizer: PlaintextNormalizer):
        content = b"Sub Section\n-----------\n\nSome content."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Sub Section"
        assert result.sections[0].level == 2

    def test_short_underline_still_works(self, normalizer: PlaintextNormalizer):
        content = b"Title\n===\n\nContent."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Title"
        assert result.sections[0].level == 1

    def test_underline_too_short_not_detected(self, normalizer: PlaintextNormalizer):
        content = b"Title\n==\n\nContent."
        result = normalizer.normalize(content)
        # "==" is only 2 chars, not enough
        heading_texts = [s.heading for s in result.sections]
        assert "Title" not in heading_texts or all(
            s.heading != "Title" or s.level != 1
            for s in result.sections
            if s.heading == "Title"
        )


class TestNumberedHeadings:
    """Numbered heading patterns like '1. Title' or '1.1 Subtitle'."""

    def test_single_number_heading(self, normalizer: PlaintextNormalizer):
        content = b"1. Introduction\n\nSome text about the topic."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "1. Introduction"
        assert result.sections[0].level == 1

    def test_dotted_number_level_2(self, normalizer: PlaintextNormalizer):
        content = b"1.1 Background\n\nSome background text."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "1.1 Background"
        assert result.sections[0].level == 2

    def test_deep_numbered_heading(self, normalizer: PlaintextNormalizer):
        content = b"2.3.1 Implementation Details\n\nDetails here."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "2.3.1 Implementation Details"
        assert result.sections[0].level == 3


class TestChapterHeadings:
    """Chapter/Part/Section style headings."""

    def test_chapter_heading(self, normalizer: PlaintextNormalizer):
        content = b"Chapter 1: The Beginning\n\nOnce upon a time."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Chapter 1: The Beginning"
        assert result.sections[0].level == 1

    def test_part_heading(self, normalizer: PlaintextNormalizer):
        content = b"Part II Overview\n\nThis part covers..."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Part II Overview"
        assert result.sections[0].level == 1

    def test_section_keyword_heading(self, normalizer: PlaintextNormalizer):
        content = b"Section 3: Methods\n\nWe used the following methods."
        result = normalizer.normalize(content)
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Section 3: Methods"
        assert result.sections[0].level == 1


class TestOffsets:
    """Section start_offset and end_offset should point to correct positions."""

    def test_first_line_offset(self, normalizer: PlaintextNormalizer):
        content = b"INTRODUCTION\n\nSome text."
        result = normalizer.normalize(content)
        section = result.sections[0]
        assert section.start_offset == 0
        assert section.end_offset == len("INTRODUCTION")

    def test_middle_line_offset(self, normalizer: PlaintextNormalizer):
        content = b"Some preamble.\n\nMETHODS\n\nWe did stuff."
        result = normalizer.normalize(content)
        section = result.sections[0]
        text = content.decode("utf-8")
        assert text[section.start_offset : section.end_offset] == "METHODS"

    def test_underline_heading_offset(self, normalizer: PlaintextNormalizer):
        content = b"Preamble text.\n\nResults\n=======\n\nHere are results."
        result = normalizer.normalize(content)
        section = result.sections[0]
        text = content.decode("utf-8")
        assert text[section.start_offset : section.end_offset] == "Results"


class TestMultipleSections:
    """Documents with multiple headings should detect all of them."""

    def test_mixed_heading_styles(self, normalizer: PlaintextNormalizer):
        content = (
            b"INTRODUCTION\n\n"
            b"Some intro text.\n\n"
            b"Background\n----------\n\n"
            b"Some background.\n\n"
            b"1.1 Details\n\n"
            b"More details here."
        )
        result = normalizer.normalize(content)
        assert len(result.sections) == 3
        assert result.sections[0].heading == "INTRODUCTION"
        assert result.sections[0].level == 1
        assert result.sections[1].heading == "Background"
        assert result.sections[1].level == 2
        assert result.sections[2].heading == "1.1 Details"
        assert result.sections[2].level == 2

    def test_sections_ordered_by_appearance(self, normalizer: PlaintextNormalizer):
        content = (
            b"FIRST\n\ntext\n\n"
            b"SECOND\n\ntext\n\n"
            b"THIRD\n\ntext"
        )
        result = normalizer.normalize(content)
        assert len(result.sections) == 3
        offsets = [s.start_offset for s in result.sections]
        assert offsets == sorted(offsets)
