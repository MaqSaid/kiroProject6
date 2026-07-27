"""Output sanitization for generated answer text.

Strips HTML tags, JavaScript code, and control characters to ensure
no executable content is returned to the client.
"""

import re


def sanitize_output(text: str) -> str:
    """Sanitize generated answer text by removing HTML, JS, and control chars.

    Args:
        text: Raw generated answer text.

    Returns:
        Sanitized text safe for API response.
    """
    # Strip script tags and their content first (before generic HTML removal)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip style tags and their content
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Strip inline JavaScript event handlers that may have survived
    text = re.sub(r"javascript:", "", text, flags=re.IGNORECASE)
    # Strip control characters (except newline \n=0x0a and tab \t=0x09)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()
