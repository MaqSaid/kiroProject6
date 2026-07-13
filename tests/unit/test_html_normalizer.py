"""Unit tests for HTMLNormalizer."""

from src.domain.processing.html_normalizer import HTMLNormalizer


class TestHTMLNormalizer:
    def setup_method(self):
        self.normalizer = HTMLNormalizer()

    def test_basic_html_to_plaintext(self):
        html = b"<html><body><p>Hello world</p></body></html>"
        result = self.normalizer.normalize(html)
        assert "Hello world" in result.plaintext

    def test_strips_html_tags(self):
        html = b"<p><strong>Bold</strong> and <em>italic</em> text</p>"
        result = self.normalizer.normalize(html)
        assert "<strong>" not in result.plaintext
        assert "<em>" not in result.plaintext
        assert "Bold" in result.plaintext
        assert "italic" in result.plaintext

    def test_extracts_heading_hierarchy(self):
        html = b"""
        <html><body>
            <h1>Main Title</h1>
            <p>Some content here.</p>
            <h2>Subsection</h2>
            <p>More content.</p>
            <h3>Sub-subsection</h3>
            <p>Even more.</p>
        </body></html>
        """
        result = self.normalizer.normalize(html)

        assert len(result.sections) == 3
        assert result.sections[0].heading == "Main Title"
        assert result.sections[0].level == 1
        assert result.sections[1].heading == "Subsection"
        assert result.sections[1].level == 2
        assert result.sections[2].heading == "Sub-subsection"
        assert result.sections[2].level == 3

    def test_section_offsets_are_valid(self):
        html = b"""
        <html><body>
            <h1>Introduction</h1>
            <p>Welcome to the guide.</p>
            <h2>Getting Started</h2>
            <p>Follow these steps.</p>
        </body></html>
        """
        result = self.normalizer.normalize(html)

        for section in result.sections:
            # Verify offset points to the heading text in plaintext
            extracted = result.plaintext[section.start_offset : section.end_offset]
            assert extracted == section.heading

    def test_removes_script_and_style(self):
        html = b"""
        <html><head><style>body { color: red; }</style></head>
        <body>
            <script>alert('xss');</script>
            <p>Safe content</p>
        </body></html>
        """
        result = self.normalizer.normalize(html)
        assert "alert" not in result.plaintext
        assert "color: red" not in result.plaintext
        assert "Safe content" in result.plaintext

    def test_empty_html(self):
        html = b"<html><body></body></html>"
        result = self.normalizer.normalize(html)
        assert result.plaintext == ""
        assert result.sections == []

    def test_preserves_text_content(self):
        html = b"""
        <html><body>
            <h1>Title</h1>
            <p>First paragraph with some text.</p>
            <p>Second paragraph with more text.</p>
        </body></html>
        """
        result = self.normalizer.normalize(html)
        assert "First paragraph with some text." in result.plaintext
        assert "Second paragraph with more text." in result.plaintext

    def test_handles_nested_elements(self):
        html = b"""
        <div>
            <ul>
                <li>Item <strong>one</strong></li>
                <li>Item two</li>
            </ul>
        </div>
        """
        result = self.normalizer.normalize(html)
        assert "Item one" in result.plaintext
        assert "Item two" in result.plaintext

    def test_all_heading_levels(self):
        html = b"""
        <h1>Level 1</h1>
        <h2>Level 2</h2>
        <h3>Level 3</h3>
        <h4>Level 4</h4>
        <h5>Level 5</h5>
        <h6>Level 6</h6>
        """
        result = self.normalizer.normalize(html)
        assert len(result.sections) == 6
        for i, section in enumerate(result.sections, start=1):
            assert section.level == i
            assert section.heading == f"Level {i}"

    def test_page_count_is_none(self):
        html = b"<p>Hello</p>"
        result = self.normalizer.normalize(html)
        assert result.page_count is None

    def test_decodes_utf8(self):
        html = "<p>Héllo wörld — «quotes»</p>".encode()
        result = self.normalizer.normalize(html)
        assert "Héllo wörld" in result.plaintext
        assert "«quotes»" in result.plaintext

    def test_handles_malformed_html(self):
        html = b"<p>Unclosed paragraph<div>Mixed <b>nesting</p></div>"
        result = self.normalizer.normalize(html)
        # Should still extract text without crashing
        assert "Unclosed paragraph" in result.plaintext
        assert "nesting" in result.plaintext
