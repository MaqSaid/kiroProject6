"""Unit tests for output sanitization.

Tests cover:
- HTML tag stripping
- JavaScript/script tag removal
- Control character removal
- Preservation of legitimate text content
"""

from src.sanitizer import sanitize_output


def test_strips_html_tags():
    """HTML tags should be completely removed."""
    text = "Section <b>45</b> states that <em>vehicles</em> must comply."
    result = sanitize_output(text)
    assert "<b>" not in result
    assert "<em>" not in result
    assert "Section 45 states that vehicles must comply." == result


def test_strips_script_tags_with_content():
    """Script tags and their content should be removed entirely."""
    text = "Answer text<script>alert('xss')</script> continues here."
    result = sanitize_output(text)
    assert "<script>" not in result
    assert "alert" not in result
    assert "Answer text continues here." == result


def test_strips_script_tags_multiline():
    """Multiline script content should be removed."""
    text = "Before<script type='text/javascript'>\nvar x = 1;\nconsole.log(x);\n</script>After"
    result = sanitize_output(text)
    assert "var x" not in result
    assert "BeforeAfter" == result


def test_strips_style_tags():
    """Style tags and their content should be removed."""
    text = "Text<style>.hidden { display: none; }</style>More text"
    result = sanitize_output(text)
    assert "<style>" not in result
    assert "display" not in result
    assert "TextMore text" == result


def test_strips_javascript_protocol():
    """javascript: protocol should be removed."""
    text = "Click javascript:void(0) for more info"
    result = sanitize_output(text)
    assert "javascript:" not in result


def test_strips_control_characters():
    """Control characters (except newline and tab) should be removed."""
    text = "Normal\x00text\x01with\x07control\x1fchars"
    result = sanitize_output(text)
    assert "\x00" not in result
    assert "\x01" not in result
    assert "\x07" not in result
    assert "\x1f" not in result
    assert "Normaltextwithcontrolchars" == result


def test_preserves_newlines_and_tabs():
    """Newlines and tabs should be preserved."""
    text = "Line 1\nLine 2\tTabbed"
    result = sanitize_output(text)
    assert "\n" in result
    assert "\t" in result


def test_preserves_normal_text():
    """Normal text without HTML/JS/control chars should pass through."""
    text = "Transport Infrastructure Act 2024, Section 45(2) requires minimum lane widths."
    result = sanitize_output(text)
    assert result == text


def test_strips_and_trims():
    """Leading/trailing whitespace should be stripped."""
    text = "   Some answer text   "
    result = sanitize_output(text)
    assert result == "Some answer text"


def test_empty_string():
    """Empty string input should return empty string."""
    assert sanitize_output("") == ""


def test_only_html_tags():
    """Input that's only HTML should return empty string."""
    text = "<div><p><span></span></p></div>"
    result = sanitize_output(text)
    assert result == ""


def test_complex_xss_payload():
    """Complex XSS payloads should be neutralized."""
    text = 'Answer <img src=x onerror="alert(1)"> text <a href="javascript:alert(1)">click</a>'
    result = sanitize_output(text)
    assert "<img" not in result
    assert "onerror" not in result
    assert "javascript:" not in result
    assert "Answer" in result
    assert "text" in result
