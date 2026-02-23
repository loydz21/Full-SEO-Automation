"""Content Quality Checker — readability, SEO, and uniqueness analysis.

Provides comprehensive content quality assessment including readability
scoring (via textstat), SEO compliance checks, heading structure
validation, uniqueness estimation, and AI-powered improvement suggestions.
"""

import collections
import hashlib
import logging
import math
import re
from typing import Any, Optional

try:
    import textstat
except ImportError:
    textstat = None  # type: ignore[assignment]

from src.integrations.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]

_SYSTEM_PROMPT = (
    "You are an expert content quality analyst. "
    "You provide specific, actionable improvement suggestions. "
    "Always respond ONLY with valid JSON."
)


def _score_to_grade(score: float) -> str:
    """Convert a numeric 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def _reading_time(text: str, wpm: int = 238) -> int:
    """Estimated reading time in minutes."""
    return max(1, round(_word_count(text) / wpm))


# ---------------------------------------------------------------------------
# ContentQualityChecker
# ---------------------------------------------------------------------------

class ContentQualityChecker:
    """Comprehensive content quality analysis engine.

    Usage::

        checker = ContentQualityChecker()
        report = checker.check_quality(content, target_keyword="seo tools")
        suggestions = await checker.suggest_improvements(report)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self._llm = llm_client or LLMClient()

    # ------------------------------------------------------------------
    # Main quality check
    # ------------------------------------------------------------------

    def check_quality(
        self,
        content: str,
        target_keyword: str = "",
    ) -> dict[str, Any]:
        """Run a full quality check on content.

        Returns a dict with readability_score, seo_score,
        uniqueness_estimate, grammar_issues, keyword_density,
        word_count, reading_time, heading_structure_ok, has_meta,
        has_faq, overall_score (0-100), grade (A-F), issues list,
        and suggestions list.
        """
        logger.info("Running quality check (keyword=%r)", target_keyword)

        readability = self.check_readability(content)
        seo = self.check_seo(content, target_keyword) if target_keyword else self._empty_seo()
        heading = self.check_heading_structure(content)
        uniqueness = self.estimate_uniqueness(content)

        wc = _word_count(content)
        rt = _reading_time(content)

        # Has FAQ section?
        has_faq = bool(re.search(r"(?i)##\s*(faq|frequently\s+asked)", content))

        # Has meta-like content at top?
        has_meta = bool(
            re.search(r"(?i)(meta_description|description:|keywords?:)", content[:500])
        )

        # Collect issues and suggestions
        issues: list[str] = []
        suggestions: list[str] = []

        # Readability issues
        flesch = readability.get("flesch_reading_ease", 50)
        if flesch < 30:
            issues.append("Content is very difficult to read (Flesch score: " + str(round(flesch)) + ")")
            suggestions.append("Simplify sentence structure and use shorter words")
        elif flesch < 50:
            issues.append("Content is fairly difficult to read (Flesch score: " + str(round(flesch)) + ")")
            suggestions.append("Consider breaking long sentences into shorter ones")

        avg_sent_len = readability.get("avg_sentence_length", 0)
        if avg_sent_len > 25:
            issues.append("Average sentence length is high (" + str(round(avg_sent_len, 1)) + " words)")
            suggestions.append("Aim for 15-20 words per sentence on average")

        # SEO issues
        if target_keyword:
            if not seo.get("keyword_in_title", False):
                issues.append("Target keyword not found in title")
                suggestions.append("Include the target keyword in the H1 title")
            if not seo.get("keyword_in_first_100_words", False):
                issues.append("Target keyword not in first 100 words")
                suggestions.append("Mention the target keyword early in the introduction")
            density = seo.get("keyword_density", 0)
            if density < 0.5:
                issues.append("Keyword density too low (" + str(round(density, 2)) + "%)")
                suggestions.append("Naturally increase keyword usage to 1-2%")
            elif density > 3.0:
                issues.append("Keyword density too high (" + str(round(density, 2)) + "%) — may appear spammy")
                suggestions.append("Reduce keyword repetition to 1-2% density")

        # Heading issues
        if not heading.get("has_h1", False):
            issues.append("No H1 heading found")
            suggestions.append("Add a single H1 heading at the top of the article")
        if heading.get("h1_count", 0) > 1:
            issues.append("Multiple H1 headings found (" + str(heading["h1_count"]) + ")")
            suggestions.append("Use only one H1 heading per article")
        if heading.get("h2_count", 0) < 2:
            issues.append("Too few H2 headings (" + str(heading.get("h2_count", 0)) + ")")
            suggestions.append("Add more H2 section headings for better structure")
        if not heading.get("hierarchy_valid", True):
            issues.append("Heading hierarchy is not sequential (e.g., H1 -> H3 without H2)")
            suggestions.append("Ensure headings follow proper hierarchy: H1 > H2 > H3")

        # Word count issues
        if wc < 300:
            issues.append("Content is very short (" + str(wc) + " words)")
            suggestions.append("Expand content to at least 800 words for better SEO")
        elif wc < 800:
            issues.append("Content is relatively short (" + str(wc) + " words)")
            suggestions.append("Consider expanding to 1200+ words for comprehensive coverage")

        if not has_faq:
            suggestions.append("Consider adding a FAQ section for featured snippet opportunities")

        # Compute component scores
        readability_score = min(100, max(0, flesch))
        seo_score = seo.get("seo_score", 50)
        uniqueness_score = uniqueness.get("uniqueness_score", 70)
        heading_score = 100 if heading.get("hierarchy_valid", False) and heading.get("h2_count", 0) >= 2 else 60
        length_score = min(100, (wc / 1500) * 100) if wc < 1500 else 100

        # Overall weighted score
        overall = (
            readability_score * 0.25
            + seo_score * 0.30
            + uniqueness_score * 0.15
            + heading_score * 0.15
            + length_score * 0.15
        )
        overall = round(min(100, max(0, overall)), 1)

        report = {
            "readability_score": round(readability_score, 1),
            "seo_score": round(seo_score, 1),
            "uniqueness_estimate": round(uniqueness_score, 1),
            "grammar_issues": [],  # placeholder — full grammar check requires NLP library
            "keyword_density": round(seo.get("keyword_density", 0), 2),
            "word_count": wc,
            "reading_time": rt,
            "heading_structure_ok": heading.get("hierarchy_valid", False),
            "has_meta": has_meta,
            "has_faq": has_faq,
            "overall_score": overall,
            "grade": _score_to_grade(overall),
            "issues": issues,
            "suggestions": suggestions,
            "readability_detail": readability,
            "seo_detail": seo,
            "heading_detail": heading,
            "uniqueness_detail": uniqueness,
        }
        logger.info(
            "Quality check complete: score=%.1f grade=%s issues=%d",
            overall, report["grade"], len(issues),
        )
        return report

    # ------------------------------------------------------------------
    # Readability
    # ------------------------------------------------------------------

    def check_readability(self, text: str) -> dict[str, Any]:
        """Compute readability metrics using textstat.

        Returns flesch_reading_ease, flesch_kincaid_grade, gunning_fog,
        avg_sentence_length, avg_word_length, syllable_count.
        """
        # Strip markdown headings and formatting for analysis
        clean = self._strip_markdown(text)

        if textstat is None:
            logger.warning("textstat not installed — returning defaults")
            return self._default_readability(clean)

        try:
            sentences = textstat.sentence_count(clean)
            words = textstat.lexicon_count(clean, removepunct=True)
            syllables = textstat.syllable_count(clean)

            avg_sentence_len = words / max(sentences, 1)
            avg_word_len = sum(len(w) for w in clean.split()) / max(words, 1)

            return {
                "flesch_reading_ease": round(textstat.flesch_reading_ease(clean), 1),
                "flesch_kincaid_grade": round(textstat.flesch_kincaid_grade(clean), 1),
                "gunning_fog": round(textstat.gunning_fog(clean), 1),
                "avg_sentence_length": round(avg_sentence_len, 1),
                "avg_word_length": round(avg_word_len, 1),
                "syllable_count": syllables,
                "sentence_count": sentences,
                "word_count": words,
            }
        except Exception as exc:
            logger.error("Readability check failed: %s", exc)
            return self._default_readability(clean)

    # ------------------------------------------------------------------
    # SEO checks
    # ------------------------------------------------------------------

    def check_seo(self, content: str, keyword: str) -> dict[str, Any]:
        """Check SEO compliance for a target keyword.

        Returns keyword_in_title, keyword_in_first_100_words,
        keyword_density, keyword_in_headings, internal_links_present,
        external_links_present, image_alt_suggestions, meta_description_length,
        title_length, and an overall seo_score.
        """
        if not keyword:
            return self._empty_seo()

        kw_lower = keyword.lower()
        content_lower = content.lower()
        words = content_lower.split()
        total_words = len(words)

        # Extract title (first H1)
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""
        title_lower = title.lower()

        # Keyword in title
        kw_in_title = kw_lower in title_lower

        # Keyword in first 100 words
        first_100 = " ".join(words[:100])
        kw_in_first_100 = kw_lower in first_100

        # Keyword density
        kw_word_count = len(kw_lower.split())
        if kw_word_count == 1:
            kw_occurrences = content_lower.count(kw_lower)
        else:
            kw_occurrences = content_lower.count(kw_lower)
        density = (kw_occurrences * kw_word_count / max(total_words, 1)) * 100

        # Keyword in headings
        headings = re.findall(r"^#{1,6}\s+(.+)$", content, re.MULTILINE)
        kw_in_headings = any(kw_lower in h.lower() for h in headings)

        # Links
        internal_links = re.findall(r"\[.+?\]\(/[^)]+\)", content)
        external_links = re.findall(r"\[.+?\]\(https?://[^)]+\)", content)

        # Images without alt
        images = re.findall(r"!\[([^\]]*)\]\([^)]+\)", content)
        images_without_alt = [img for img in images if not img.strip()]
        alt_suggestions: list[str] = []
        if images_without_alt:
            alt_suggestions.append(
                str(len(images_without_alt)) + " image(s) missing alt text"
            )

        # Meta description check (from brief, check title length)
        title_len = len(title)

        # Compute SEO sub-score
        seo_points = 0
        max_points = 100

        if kw_in_title:
            seo_points += 20
        if kw_in_first_100:
            seo_points += 15
        if 0.8 <= density <= 2.5:
            seo_points += 15
        elif 0.5 <= density <= 3.0:
            seo_points += 8
        if kw_in_headings:
            seo_points += 10
        if internal_links:
            seo_points += 10
        if external_links:
            seo_points += 5
        if not images_without_alt or not images:
            seo_points += 5
        if 50 <= title_len <= 65:
            seo_points += 10
        elif 40 <= title_len <= 75:
            seo_points += 5
        if total_words >= 800:
            seo_points += 10
        elif total_words >= 500:
            seo_points += 5

        return {
            "keyword_in_title": kw_in_title,
            "keyword_in_first_100_words": kw_in_first_100,
            "keyword_density": round(density, 2),
            "keyword_in_headings": kw_in_headings,
            "keyword_occurrences": kw_occurrences,
            "internal_links_present": len(internal_links) > 0,
            "internal_links_count": len(internal_links),
            "external_links_present": len(external_links) > 0,
            "external_links_count": len(external_links),
            "image_alt_suggestions": alt_suggestions,
            "title_length": title_len,
            "title_length_ok": 50 <= title_len <= 65,
            "seo_score": min(100, seo_points),
        }

    # ------------------------------------------------------------------
    # Heading structure
    # ------------------------------------------------------------------

    def check_heading_structure(self, content: str) -> dict[str, Any]:
        """Validate H1/H2/H3 hierarchy and heading counts."""
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = heading_pattern.findall(content)

        levels: list[int] = []
        headings_list: list[dict[str, Any]] = []
        for hashes, text in matches:
            level = len(hashes)
            levels.append(level)
            headings_list.append({"level": level, "text": text.strip()})

        h1_count = levels.count(1)
        h2_count = levels.count(2)
        h3_count = levels.count(3)

        # Check hierarchy: each heading level should not skip (e.g., H1 -> H3)
        hierarchy_valid = True
        for i in range(1, len(levels)):
            if levels[i] > levels[i - 1] + 1:
                hierarchy_valid = False
                break

        return {
            "has_h1": h1_count > 0,
            "h1_count": h1_count,
            "h2_count": h2_count,
            "h3_count": h3_count,
            "total_headings": len(levels),
            "hierarchy_valid": hierarchy_valid,
            "headings": headings_list,
            "logical_flow": hierarchy_valid and h1_count == 1 and h2_count >= 2,
        }

    # ------------------------------------------------------------------
    # Uniqueness estimation
    # ------------------------------------------------------------------

    def estimate_uniqueness(self, content: str) -> dict[str, Any]:
        """Estimate content uniqueness using n-gram fingerprinting.

        Uses overlapping n-gram hashing to detect potentially
        generic/templated sections.
        """
        clean = self._strip_markdown(content)
        words = clean.lower().split()
        total_words = len(words)

        if total_words < 20:
            return {
                "uniqueness_score": 50.0,
                "total_ngrams": 0,
                "unique_ngrams": 0,
                "generic_phrases": [],
                "assessment": "Content too short to assess",
            }

        # Generate 4-gram fingerprints
        n = 4
        ngrams: list[str] = []
        for i in range(len(words) - n + 1):
            ngram = " ".join(words[i : i + n])
            ngrams.append(ngram)

        # Count unique n-grams
        ngram_counts = collections.Counter(ngrams)
        total_ngrams = len(ngrams)
        unique_ngrams = len(ngram_counts)

        # Detect repeated (potentially templated) phrases
        repeated = [
            (phrase, count)
            for phrase, count in ngram_counts.items()
            if count >= 3
        ]
        repeated.sort(key=lambda x: x[1], reverse=True)

        generic_phrases = [phrase for phrase, _ in repeated[:10]]

        # Uniqueness ratio
        uniqueness_ratio = unique_ngrams / max(total_ngrams, 1)
        # Scale to 0-100 score
        # A ratio near 1.0 means highly unique; near 0.5 means repetitive
        uniqueness_score = min(100, uniqueness_ratio * 100)

        # Penalise heavily repeated phrases
        penalty = min(30, len(repeated) * 3)
        uniqueness_score = max(0, uniqueness_score - penalty)

        if uniqueness_score >= 80:
            assessment = "Highly unique content"
        elif uniqueness_score >= 60:
            assessment = "Mostly unique with some common phrases"
        elif uniqueness_score >= 40:
            assessment = "Moderate uniqueness — consider rephrasing repetitive sections"
        else:
            assessment = "Low uniqueness — significant revision recommended"

        return {
            "uniqueness_score": round(uniqueness_score, 1),
            "total_ngrams": total_ngrams,
            "unique_ngrams": unique_ngrams,
            "generic_phrases": generic_phrases[:5],
            "repeated_phrase_count": len(repeated),
            "assessment": assessment,
        }

    # ------------------------------------------------------------------
    # AI improvement suggestions
    # ------------------------------------------------------------------

    async def suggest_improvements(
        self,
        quality_report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """AI generates specific improvement suggestions based on quality report.

        Each suggestion has: area, current_issue, recommendation,
        priority (high/medium/low), estimated_impact (high/medium/low).
        """
        issues = quality_report.get("issues", [])
        basic_suggestions = quality_report.get("suggestions", [])
        overall = quality_report.get("overall_score", 0)
        grade = quality_report.get("grade", "F")

        prompt = (
            "Analyse this content quality report and provide specific improvement suggestions.\n\n"
            "Overall Score: " + str(overall) + "/100 (Grade: " + grade + ")\n"
            "Readability Score: " + str(quality_report.get("readability_score", 0)) + "\n"
            "SEO Score: " + str(quality_report.get("seo_score", 0)) + "\n"
            "Uniqueness: " + str(quality_report.get("uniqueness_estimate", 0)) + "\n"
            "Word Count: " + str(quality_report.get("word_count", 0)) + "\n\n"
            "Current Issues:\n"
            + "\n".join("- " + i for i in issues) + "\n\n"
            "Basic Suggestions:\n"
            + "\n".join("- " + s for s in basic_suggestions) + "\n\n"
            "Return a JSON array of improvement objects:\n"
            '[{"area": "readability|seo|structure|content|uniqueness",'
            ' "current_issue": "...",'
            ' "recommendation": "...",'
            ' "priority": "high|medium|low",'
            ' "estimated_impact": "high|medium|low"}]\n\n'
            "Provide 5-8 specific, actionable suggestions ordered by priority."
        )

        try:
            result = await self._llm.generate_json(
                prompt, system_prompt=_SYSTEM_PROMPT
            )
            if isinstance(result, list):
                return result
            return []
        except Exception as exc:
            logger.error("AI improvement suggestions failed: %s", exc)
            # Fall back to structured version of basic suggestions
            fallback: list[dict[str, Any]] = []
            for i, (issue, suggestion) in enumerate(
                zip(issues, basic_suggestions)
            ):
                fallback.append({
                    "area": "general",
                    "current_issue": issue,
                    "recommendation": suggestion,
                    "priority": "high" if i < 2 else "medium",
                    "estimated_impact": "medium",
                })
            return fallback

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting for text analysis."""
        # Remove headings markers
        clean = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic
        clean = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", clean)
        # Remove links but keep text
        clean = re.sub(r"\[(.+?)\]\([^)]+\)", r"\1", clean)
        # Remove images
        clean = re.sub(r"!\[.*?\]\([^)]+\)", "", clean)
        # Remove inline code
        clean = re.sub(r"`[^`]+`", "", clean)
        # Remove code blocks
        clean = re.sub(r"```[\s\S]*?```", "", clean)
        # Remove horizontal rules
        clean = re.sub(r"^---+$", "", clean, flags=re.MULTILINE)
        # Collapse whitespace
        clean = re.sub(r"\n{3,}", "\n\n", clean)
        return clean.strip()

    @staticmethod
    def _default_readability(text: str) -> dict[str, Any]:
        """Fallback readability metrics when textstat is unavailable."""
        words = text.split()
        sentences = re.split(r"[.!?]+", text)
        sentences = [s for s in sentences if s.strip()]
        wc = len(words)
        sc = max(len(sentences), 1)
        avg_sent = wc / sc
        avg_word = sum(len(w) for w in words) / max(wc, 1)

        # Rough Flesch estimate
        flesch = 206.835 - 1.015 * avg_sent - 84.6 * (avg_word / 4.7)
        flesch = max(0, min(100, flesch))

        return {
            "flesch_reading_ease": round(flesch, 1),
            "flesch_kincaid_grade": 0.0,
            "gunning_fog": 0.0,
            "avg_sentence_length": round(avg_sent, 1),
            "avg_word_length": round(avg_word, 1),
            "syllable_count": 0,
            "sentence_count": sc,
            "word_count": wc,
        }

    @staticmethod
    def _empty_seo() -> dict[str, Any]:
        """Return empty SEO result when no keyword provided."""
        return {
            "keyword_in_title": False,
            "keyword_in_first_100_words": False,
            "keyword_density": 0.0,
            "keyword_in_headings": False,
            "keyword_occurrences": 0,
            "internal_links_present": False,
            "internal_links_count": 0,
            "external_links_present": False,
            "external_links_count": 0,
            "image_alt_suggestions": [],
            "title_length": 0,
            "title_length_ok": False,
            "seo_score": 50,
        }
