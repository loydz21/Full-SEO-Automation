"""Text processing utilities for SEO content analysis."""

import re
from collections import Counter
from typing import Any


def count_words(text: str) -> int:
    """Count words in text.

    Args:
        text: Input text.

    Returns:
        Word count.
    """
    return len(text.split())


def calculate_readability(text: str) -> dict[str, float]:
    """Calculate readability scores for text.

    Returns:
        Dict with flesch_reading_ease, flesch_kincaid_grade, and
        automated_readability_index.
    """
    sentences = _split_sentences(text)
    words = text.split()
    syllable_count = sum(_count_syllables(w) for w in words)

    num_sentences = max(len(sentences), 1)
    num_words = max(len(words), 1)
    num_syllables = max(syllable_count, 1)

    # Flesch Reading Ease
    fre = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (num_syllables / num_words)

    # Flesch-Kincaid Grade Level
    fkgl = 0.39 * (num_words / num_sentences) + 11.8 * (num_syllables / num_words) - 15.59

    # Automated Readability Index
    num_chars = sum(len(w) for w in words)
    ari = 4.71 * (num_chars / num_words) + 0.5 * (num_words / num_sentences) - 21.43

    return {
        "flesch_reading_ease": round(max(0.0, min(100.0, fre)), 1),
        "flesch_kincaid_grade": round(max(0.0, fkgl), 1),
        "automated_readability_index": round(max(0.0, ari), 1),
    }


def extract_entities(text: str) -> list[dict[str, Any]]:
    """Extract named-entity-like patterns from text (lightweight, no NLP model).

    Finds capitalised multi-word phrases as potential entities.

    Returns:
        List of entity dicts with text, type, and count.
    """
    pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')
    matches = pattern.findall(text)
    counter = Counter(matches)
    entities = []
    for entity_text, count in counter.most_common(50):
        entities.append({"text": entity_text, "type": "ENTITY", "count": count})
    return entities


def calculate_keyword_density(
    text: str, keyword: str
) -> dict[str, float | int]:
    """Calculate keyword density metrics.

    Args:
        text: The full text content.
        keyword: Single or multi-word keyword to measure.

    Returns:
        Dict with density_pct, count, and total_words.
    """
    text_lower = text.lower()
    keyword_lower = keyword.lower().strip()
    words = text_lower.split()
    total_words = len(words)

    if total_words == 0 or not keyword_lower:
        return {"density_pct": 0.0, "count": 0, "total_words": 0}

    kw_words = keyword_lower.split()
    kw_len = len(kw_words)
    count = 0

    if kw_len == 1:
        count = words.count(keyword_lower)
    else:
        for i in range(len(words) - kw_len + 1):
            if words[i : i + kw_len] == kw_words:
                count += 1

    density = (count * kw_len / total_words) * 100
    return {
        "density_pct": round(density, 2),
        "count": count,
        "total_words": total_words,
    }


def extract_headings(html: str) -> list[dict[str, str]]:
    """Extract h1-h6 headings from HTML content.

    Returns:
        List of dicts with level and text.
    """
    pattern = re.compile(r'<h([1-6])[^>]*>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)
    headings = []
    for match in pattern.finditer(html):
        level = match.group(1)
        text = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if text:
            headings.append({"level": f"h{level}", "text": text})
    return headings


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using basic heuristics."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s.strip()]


def _count_syllables(word: str) -> int:
    """Estimate syllable count for an English word."""
    word = word.lower().strip(".,!?;:'\"-()")
    if not word:
        return 0
    if len(word) <= 3:
        return 1

    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    # Adjust for silent 'e'
    if word.endswith("e") and count > 1:
        count -= 1
    # Adjust for 'le' ending
    if word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
        count += 1

    return max(1, count)
