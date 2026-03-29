"""Text processing utilities: HTML stripping and summary extraction."""

import re


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities from a string.

    Args:
        html: HTML string to clean.

    Returns:
        Plain text string.
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_summary(text: str, max_len: int = 200) -> str:
    """Extract a summary from text, truncating at max_len characters.

    Args:
        text: Input text.
        max_len: Maximum length of the summary.

    Returns:
        Truncated text with ellipsis if needed.
    """
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."
