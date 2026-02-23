"""General-purpose helper utilities for the SEO automation project."""

import math
import re
import unicodedata
from typing import Optional


def slugify(text: str, max_length: int = 75) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Input text to slugify.
        max_length: Maximum slug length.

    Returns:
        Lowercase hyphen-separated slug.

    Examples:
        >>> slugify("Hello World Test")
        'hello-world-test'
        >>> slugify("  Best SEO Tools (2025)!  ")
        'best-seo-tools-2025'
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rsplit("-", 1)[0]
    return text


def truncate_text(text: str, max_length: int = 160, suffix: str = "...") -> str:
    """Truncate text to a maximum length, breaking at word boundaries.

    Args:
        text: Input text.
        max_length: Maximum allowed length including suffix.
        suffix: String appended when truncation occurs.

    Returns:
        Truncated text with suffix if it was shortened.
    """
    if len(text) <= max_length:
        return text
    truncated = text[: max_length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:!? ") + suffix


def calculate_reading_time(text: str, wpm: int = 238) -> int:
    """Estimate reading time in minutes.

    Args:
        text: The text content.
        wpm: Average words per minute (default 238 for web content).

    Returns:
        Reading time in minutes (minimum 1).
    """
    word_count = len(text.split())
    minutes = math.ceil(word_count / wpm)
    return max(1, minutes)


def format_number(n: int | float) -> str:
    """Format a number with human-readable suffixes.

    Args:
        n: Numeric value.

    Returns:
        Formatted string (e.g. 1500 -> '1.5K', 2500000 -> '2.5M').

    Examples:
        >>> format_number(1500)
        '1.5K'
        >>> format_number(2500000)
        '2.5M'
        >>> format_number(999)
        '999'
    """
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1_000_000_000:
        return f"{sign}{abs_n / 1_000_000_000:.1f}B"
    if abs_n >= 1_000_000:
        return f"{sign}{abs_n / 1_000_000:.1f}M"
    if abs_n >= 1_000:
        return f"{sign}{abs_n / 1_000:.1f}K"
    if isinstance(n, float):
        return f"{sign}{abs_n:.1f}"
    return f"{sign}{abs_n}"


def extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Args:
        url: Full URL string.

    Returns:
        Domain name without protocol or path.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.hostname or "").lower()


def clean_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
