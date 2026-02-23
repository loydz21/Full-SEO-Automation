"""On-Page SEO Optimizer — comprehensive page analysis and optimization.

Fetches, parses, and evaluates web pages across multiple SEO dimensions:
meta tags, schema markup, internal linking, images, content quality,
and E-E-A-T signals.  Uses AI (LLMClient) for intelligent suggestions.
"""

import asyncio
import json
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights and grade map
# ---------------------------------------------------------------------------

_CATEGORY_WEIGHTS: dict[str, float] = {
    "meta_tags": 0.15,
    "content": 0.25,
    "images": 0.10,
    "internal_links": 0.10,
    "schema": 0.10,
    "eeat": 0.15,
    "technical": 0.15,
}

_GRADE_MAP = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


def _grade_for(score: float) -> str:
    for threshold, letter in _GRADE_MAP:
        if score >= threshold:
            return letter
    return "F"


# ---------------------------------------------------------------------------
# Readability helpers
# ---------------------------------------------------------------------------

def _count_syllables(word: str) -> int:
    """Rough syllable count for English words."""
    word = word.lower().strip()
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    vowel_groups = re.findall(r"[aeiouy]+", word)
    return max(1, len(vowel_groups))


def _flesch_reading_ease(text: str) -> float:
    """Compute Flesch Reading Ease score (0–100, higher = easier)."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"[a-zA-Z]+", text)
    if not sentences or not words:
        return 0.0
    total_syllables = sum(_count_syllables(w) for w in words)
    asl = len(words) / len(sentences)
    asw = total_syllables / len(words)
    score = 206.835 - 1.015 * asl - 84.6 * asw
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# OnPageOptimizer
# ---------------------------------------------------------------------------

class OnPageOptimizer:
    """Comprehensive on-page SEO analyser and optimizer.

    Usage::

        optimizer = OnPageOptimizer(llm_client=llm, serp_scraper=serp)
        result = await optimizer.analyze_page("https://example.com", "seo tools")
    """

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        serp_scraper: Optional[Any] = None,
        timeout: int = 30,
    ) -> None:
        self._llm = llm_client
        self._serp = serp_scraper
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    # ------------------------------------------------------------------
    # Fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_page(self, url: str) -> tuple[str, int, dict]:
        """Fetch a URL and return (html, status_code, headers)."""
        try:
            async with aiohttp.ClientSession(
                timeout=self._timeout, headers=self._HEADERS
            ) as session:
                async with session.get(url, allow_redirects=True, ssl=False) as resp:
                    html = await resp.text(errors="replace")
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    return html, resp.status, headers
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            return "", 0, {}

    def _parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    def _visible_text(self, soup: BeautifulSoup) -> str:
        """Extract visible body text from parsed HTML."""
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            comment.extract()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def analyze_page(
        self, url: str, target_keyword: str = ""
    ) -> dict[str, Any]:
        """Run all on-page checks and return a comprehensive analysis dict."""
        start = time.monotonic()
        logger.info("Starting on-page analysis for %s (keyword: %s)", url, target_keyword or "none")

        html, status, headers = await self._fetch_page(url)
        if not html:
            return {
                "url": url,
                "error": "Failed to fetch page",
                "status_code": status,
                "overall_score": 0,
                "grade": "F",
            }

        soup = self._parse_html(html)
        visible = self._visible_text(self._parse_html(html))  # fresh copy
        keyword = target_keyword.strip().lower()

        # Run all checks
        meta = self._check_meta_tags(soup, keyword)
        tech = self._check_technical(soup, html, headers, status)
        content = self._check_content(soup, visible, keyword)
        images = self._check_images(soup, keyword)
        links = self._check_internal_links(soup, url)
        schema = self._check_schema(soup)
        eeat = self._check_eeat(soup, visible)

        # Compute category scores
        categories = {
            "meta_tags": meta.get("score", 0),
            "content": content.get("score", 0),
            "images": images.get("score", 0),
            "internal_links": links.get("score", 0),
            "schema": schema.get("score", 0),
            "eeat": eeat.get("score", 0),
            "technical": tech.get("score", 0),
        }

        overall = sum(
            categories[cat] * _CATEGORY_WEIGHTS[cat] for cat in categories
        )
        overall = round(overall, 1)

        elapsed = round(time.monotonic() - start, 2)
        logger.info("On-page analysis complete for %s: score=%.1f (%s) in %.2fs",
                    url, overall, _grade_for(overall), elapsed)

        return {
            "url": url,
            "target_keyword": target_keyword,
            "status_code": status,
            "overall_score": overall,
            "grade": _grade_for(overall),
            "categories": categories,
            "meta_tags": meta,
            "technical": tech,
            "content": content,
            "images": images,
            "internal_links": links,
            "schema": schema,
            "eeat": eeat,
            "elapsed_seconds": elapsed,
        }

    # ------------------------------------------------------------------
    # Meta tags
    # ------------------------------------------------------------------

    def _check_meta_tags(self, soup: BeautifulSoup, keyword: str) -> dict:
        """Evaluate title tag, meta description, and other head meta."""
        issues: list[dict] = []
        score = 100

        # Title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        title_len = len(title)

        if not title:
            issues.append({"type": "error", "msg": "Missing title tag"})
            score -= 25
        else:
            if title_len < 30:
                issues.append({"type": "warning", "msg": "Title too short (< 30 chars)"})
                score -= 10
            elif title_len > 60:
                issues.append({"type": "warning", "msg": "Title too long (> 60 chars)"})
                score -= 5
            if keyword and keyword not in title.lower():
                issues.append({"type": "warning", "msg": "Target keyword not in title"})
                score -= 15

        # Meta description
        desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        description = desc_tag.get("content", "") if desc_tag else ""
        desc_len = len(description)

        if not description:
            issues.append({"type": "error", "msg": "Missing meta description"})
            score -= 20
        else:
            if desc_len < 70:
                issues.append({"type": "warning", "msg": "Meta description too short (< 70 chars)"})
                score -= 5
            elif desc_len > 160:
                issues.append({"type": "warning", "msg": "Meta description too long (> 160 chars)"})
                score -= 5
            if keyword and keyword not in description.lower():
                issues.append({"type": "info", "msg": "Target keyword not in meta description"})
                score -= 10

        # Canonical
        canonical = soup.find("link", rel="canonical")
        if not canonical:
            issues.append({"type": "warning", "msg": "Missing canonical tag"})
            score -= 5

        # Viewport
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            issues.append({"type": "warning", "msg": "Missing viewport meta tag"})
            score -= 5

        # Robots
        robots_tag = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        robots_content = robots_tag.get("content", "") if robots_tag else ""
        if "noindex" in robots_content.lower():
            issues.append({"type": "error", "msg": "Page is set to noindex"})
            score -= 20

        # Open Graph
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        if not og_title:
            issues.append({"type": "info", "msg": "Missing Open Graph title"})
            score -= 3
        if not og_desc:
            issues.append({"type": "info", "msg": "Missing Open Graph description"})
            score -= 2

        return {
            "score": max(0, score),
            "title": title,
            "title_length": title_len,
            "description": description,
            "description_length": desc_len,
            "has_canonical": canonical is not None,
            "has_viewport": viewport is not None,
            "robots": robots_content,
            "has_og_tags": og_title is not None,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Technical signals
    # ------------------------------------------------------------------

    def _check_technical(
        self, soup: BeautifulSoup, html: str, headers: dict, status: int
    ) -> dict:
        """Check technical on-page factors."""
        issues: list[dict] = []
        score = 100

        # Status code
        if status != 200:
            issues.append({"type": "error", "msg": "Non-200 status code: " + str(status)})
            score -= 20

        # HTML size
        html_size_kb = len(html.encode("utf-8")) / 1024
        if html_size_kb > 500:
            issues.append({"type": "warning", "msg": "HTML size exceeds 500KB"})
            score -= 10

        # Doctype
        has_doctype = html.strip().lower().startswith("<!doctype")
        if not has_doctype:
            issues.append({"type": "warning", "msg": "Missing DOCTYPE declaration"})
            score -= 5

        # Lang attribute
        html_tag = soup.find("html")
        has_lang = bool(html_tag and html_tag.get("lang"))
        if not has_lang:
            issues.append({"type": "warning", "msg": "Missing lang attribute on <html>"})
            score -= 5

        # Heading hierarchy
        h1_tags = soup.find_all("h1")
        h1_count = len(h1_tags)
        if h1_count == 0:
            issues.append({"type": "error", "msg": "Missing H1 tag"})
            score -= 15
        elif h1_count > 1:
            issues.append({"type": "warning", "msg": "Multiple H1 tags (" + str(h1_count) + ")"})
            score -= 5

        # Scripts and styles count
        scripts = soup.find_all("script", src=True)
        stylesheets = soup.find_all("link", rel="stylesheet")
        if len(scripts) > 20:
            issues.append({"type": "warning", "msg": "Too many external scripts (" + str(len(scripts)) + ")"})
            score -= 5
        if len(stylesheets) > 10:
            issues.append({"type": "info", "msg": "Many external stylesheets (" + str(len(stylesheets)) + ")"})
            score -= 3

        # Security headers
        has_https = headers.get(":scheme") == "https" or "strict-transport-security" in headers
        if "x-frame-options" not in headers and "content-security-policy" not in headers:
            issues.append({"type": "info", "msg": "Missing X-Frame-Options / CSP header"})
            score -= 2

        return {
            "score": max(0, score),
            "status_code": status,
            "html_size_kb": round(html_size_kb, 1),
            "has_doctype": has_doctype,
            "has_lang": has_lang,
            "h1_count": h1_count,
            "h1_text": h1_tags[0].get_text(strip=True) if h1_tags else "",
            "external_scripts": len(scripts),
            "external_stylesheets": len(stylesheets),
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Content analysis
    # ------------------------------------------------------------------

    def _check_content(
        self, soup: BeautifulSoup, visible_text: str, keyword: str
    ) -> dict:
        """Analyse content quality: length, keyword usage, readability."""
        issues: list[dict] = []
        score = 100

        words = re.findall(r"[a-zA-Z]+", visible_text)
        word_count = len(words)

        # Content length
        if word_count < 300:
            issues.append({"type": "error", "msg": "Very thin content (< 300 words)"})
            score -= 25
        elif word_count < 600:
            issues.append({"type": "warning", "msg": "Short content (< 600 words)"})
            score -= 10

        # Readability
        readability = _flesch_reading_ease(visible_text)
        if readability < 30:
            issues.append({"type": "warning", "msg": "Content is very difficult to read"})
            score -= 10
        elif readability < 50:
            issues.append({"type": "info", "msg": "Content readability could be improved"})
            score -= 5

        # Keyword analysis
        kw_density = 0.0
        kw_in_first_100 = False
        kw_in_headings = False
        heading_kw_list: list[str] = []

        if keyword:
            lower_text = visible_text.lower()
            kw_count = lower_text.count(keyword)
            kw_density = (kw_count / max(word_count, 1)) * 100 if word_count else 0.0

            # Keyword in first 100 words
            first_100 = " ".join(words[:100]).lower()
            kw_in_first_100 = keyword in first_100
            if not kw_in_first_100:
                issues.append({"type": "warning", "msg": "Keyword not in first 100 words"})
                score -= 10

            # Keyword density
            if kw_density == 0:
                issues.append({"type": "error", "msg": "Target keyword not found in content"})
                score -= 20
            elif kw_density > 3.0:
                issues.append({"type": "warning", "msg": "Keyword density too high (possible stuffing)"})
                score -= 10
            elif kw_density < 0.5:
                issues.append({"type": "info", "msg": "Keyword density is low (< 0.5%)"})
                score -= 5

            # Keywords in headings
            for tag_name in ["h1", "h2", "h3"]:
                for heading in soup.find_all(tag_name):
                    h_text = heading.get_text(strip=True).lower()
                    if keyword in h_text:
                        kw_in_headings = True
                        heading_kw_list.append(tag_name + ": " + heading.get_text(strip=True))
            if not kw_in_headings:
                issues.append({"type": "warning", "msg": "Target keyword not in any heading (H1-H3)"})
                score -= 10

        # Paragraph length check
        paragraphs = soup.find_all("p")
        long_paragraphs = 0
        for p in paragraphs:
            p_words = len(re.findall(r"[a-zA-Z]+", p.get_text()))
            if p_words > 150:
                long_paragraphs += 1
        if long_paragraphs > 3:
            issues.append({"type": "info", "msg": "Multiple long paragraphs (> 150 words each)"})
            score -= 5

        # Heading structure
        headings = []
        for level in range(1, 7):
            tag = "h" + str(level)
            for h in soup.find_all(tag):
                headings.append({"tag": tag, "text": h.get_text(strip=True)[:80]})

        return {
            "score": max(0, score),
            "word_count": word_count,
            "readability_score": round(readability, 1),
            "keyword_density": round(kw_density, 2),
            "keyword_count": int(kw_density * word_count / 100) if kw_density else 0,
            "keyword_in_first_100": kw_in_first_100,
            "keyword_in_headings": kw_in_headings,
            "heading_keywords": heading_kw_list,
            "headings": headings,
            "paragraph_count": len(paragraphs),
            "long_paragraphs": long_paragraphs,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def _check_images(self, soup: BeautifulSoup, keyword: str) -> dict:
        """Audit all images for SEO best practices."""
        issues: list[dict] = []
        images_data: list[dict] = []

        imgs = soup.find_all("img")
        if not imgs:
            return {"score": 100, "total_images": 0, "images": [], "issues": []}

        missing_alt = 0
        missing_dimensions = 0
        missing_lazy = 0
        non_webp = 0
        alt_with_keyword = 0

        for img in imgs:
            src = img.get("src", "") or img.get("data-src", "")
            alt = img.get("alt", None)
            width = img.get("width")
            height = img.get("height")
            loading = img.get("loading", "")

            img_info: dict[str, Any] = {
                "src": src[:200],
                "alt": alt,
                "has_dimensions": bool(width and height),
                "has_lazy_loading": loading == "lazy",
                "issues": [],
            }

            if alt is None or alt.strip() == "":
                missing_alt += 1
                img_info["issues"].append("Missing alt text")
            elif keyword and keyword in alt.lower():
                alt_with_keyword += 1

            if not width or not height:
                missing_dimensions += 1
                img_info["issues"].append("Missing width/height attributes")

            if loading != "lazy":
                missing_lazy += 1

            # Format check
            src_lower = src.lower()
            if not any(src_lower.endswith(ext) for ext in (".webp", ".avif", ".svg")):
                non_webp += 1
                img_info["format_suggestion"] = "Consider converting to WebP"

            images_data.append(img_info)

        total = len(imgs)
        score = 100

        if missing_alt > 0:
            pct = round(missing_alt / total * 100)
            issues.append({"type": "error", "msg": str(missing_alt) + " images missing alt text (" + str(pct) + "%)"})
            score -= min(30, missing_alt * 5)

        if missing_dimensions > total // 2:
            issues.append({"type": "warning", "msg": "Many images missing width/height attributes"})
            score -= 10

        if missing_lazy > total // 2:
            issues.append({"type": "info", "msg": "Many images without lazy loading"})
            score -= 5

        if non_webp > total // 2:
            issues.append({"type": "info", "msg": "Most images not in modern format (WebP/AVIF)"})
            score -= 5

        if keyword and total > 0 and alt_with_keyword == 0:
            issues.append({"type": "warning", "msg": "No image alt text contains target keyword"})
            score -= 10

        return {
            "score": max(0, score),
            "total_images": total,
            "missing_alt": missing_alt,
            "missing_dimensions": missing_dimensions,
            "missing_lazy_loading": missing_lazy,
            "non_modern_format": non_webp,
            "alt_with_keyword": alt_with_keyword,
            "images": images_data[:50],  # cap for large pages
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Internal links
    # ------------------------------------------------------------------

    def _check_internal_links(self, soup: BeautifulSoup, page_url: str) -> dict:
        """Analyse internal linking structure on the page."""
        issues: list[dict] = []
        parsed = urlparse(page_url)
        domain = parsed.netloc

        internal: list[dict] = []
        external: list[dict] = []
        anchor_texts: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)[:100]
            full_url = urljoin(page_url, href)
            link_parsed = urlparse(full_url)

            link_data = {
                "href": full_url,
                "anchor_text": text,
                "nofollow": "nofollow" in a.get("rel", []),
            }

            if link_parsed.netloc == domain or not link_parsed.netloc:
                internal.append(link_data)
                if text:
                    anchor_texts.append(text.lower())
            else:
                external.append(link_data)

        # Analyse anchor text distribution
        anchor_counter = Counter(anchor_texts)
        generic_anchors = sum(
            1 for t in anchor_texts
            if t in ("click here", "read more", "learn more", "here", "link", "this")
        )

        score = 100

        if len(internal) < 3:
            issues.append({"type": "warning", "msg": "Very few internal links (< 3)"})
            score -= 15
        elif len(internal) < 5:
            issues.append({"type": "info", "msg": "Consider adding more internal links"})
            score -= 5

        if len(internal) > 100:
            issues.append({"type": "warning", "msg": "Excessive internal links (> 100)"})
            score -= 10

        if generic_anchors > len(anchor_texts) * 0.3 and len(anchor_texts) > 3:
            issues.append({"type": "warning", "msg": "Too many generic anchor texts"})
            score -= 10

        # Check for broken looking links
        empty_href = sum(1 for a in soup.find_all("a", href=True) if a["href"].strip() in ("", "#", "javascript:void(0)"))
        if empty_href > 3:
            issues.append({"type": "warning", "msg": str(empty_href) + " links with empty/placeholder href"})
            score -= 5

        return {
            "score": max(0, score),
            "internal_count": len(internal),
            "external_count": len(external),
            "internal_links": internal[:50],
            "external_links": external[:20],
            "anchor_distribution": dict(anchor_counter.most_common(20)),
            "generic_anchor_count": generic_anchors,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # Schema / structured data
    # ------------------------------------------------------------------

    def _check_schema(self, soup: BeautifulSoup) -> dict:
        """Check for existing structured data on the page."""
        issues: list[dict] = []
        schemas_found: list[dict] = []

        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        schemas_found.append({
                            "format": "JSON-LD",
                            "type": item.get("@type", "Unknown"),
                        })
                elif isinstance(data, dict):
                    schemas_found.append({
                        "format": "JSON-LD",
                        "type": data.get("@type", "Unknown"),
                    })
            except (json.JSONDecodeError, TypeError):
                issues.append({"type": "error", "msg": "Invalid JSON-LD found on page"})

        # Microdata
        for elem in soup.find_all(attrs={"itemtype": True}):
            item_type = elem.get("itemtype", "")
            type_name = item_type.split("/")[-1] if item_type else "Unknown"
            schemas_found.append({"format": "Microdata", "type": type_name})

        score = 100
        if not schemas_found:
            issues.append({"type": "warning", "msg": "No structured data found on page"})
            score = 40
        else:
            types = [s["type"] for s in schemas_found]
            if "BreadcrumbList" not in types:
                issues.append({"type": "info", "msg": "Consider adding BreadcrumbList schema"})
                score -= 10

        return {
            "score": max(0, score),
            "schemas_found": schemas_found,
            "schema_count": len(schemas_found),
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # E-E-A-T signals
    # ------------------------------------------------------------------

    def _check_eeat(self, soup: BeautifulSoup, visible_text: str) -> dict:
        """Check Experience, Expertise, Authoritativeness, Trustworthiness signals."""
        signals: dict[str, bool] = {}
        issues: list[dict] = []
        score = 100

        lower = visible_text.lower()

        # Author info
        author_tag = soup.find(attrs={"class": re.compile(r"author", re.I)})
        author_meta = soup.find("meta", attrs={"name": "author"})
        author_rel = soup.find("a", rel="author")
        has_author = bool(author_tag or author_meta or author_rel)
        signals["author_byline"] = has_author
        if not has_author:
            issues.append({"type": "warning", "msg": "No author byline or attribution found"})
            score -= 15

        # Author credentials
        credential_words = ["phd", "md", "expert", "specialist", "certified", "professor",
                           "researcher", "editor", "contributor", "journalist"]
        has_credentials = any(w in lower for w in credential_words)
        signals["author_credentials"] = has_credentials
        if not has_credentials:
            issues.append({"type": "info", "msg": "No author credentials detected"})
            score -= 5

        # Dates
        date_published = soup.find("time", attrs={"datetime": True})
        meta_date = soup.find("meta", attrs={"property": re.compile(r"published_time|date", re.I)})
        has_date = bool(date_published or meta_date)
        signals["date_published"] = has_date
        if not has_date:
            issues.append({"type": "warning", "msg": "No publication date found"})
            score -= 10

        # Updated date
        modified_meta = soup.find("meta", attrs={"property": re.compile(r"modified_time", re.I)})
        date_modified_cls = soup.find(attrs={"class": re.compile(r"updated|modified", re.I)})
        has_updated = bool(modified_meta or date_modified_cls or "updated" in lower[:500])
        signals["date_updated"] = has_updated
        if not has_updated:
            issues.append({"type": "info", "msg": "No last-updated date found"})
            score -= 5

        # Citations and references
        cite_tags = soup.find_all("cite")
        reference_links = soup.find_all("a", href=re.compile(r"(doi\.org|pubmed|scholar\.google|ncbi|arxiv)", re.I))
        ref_section = bool(re.search(r"(references|sources|bibliography|citations)", lower))
        has_citations = bool(cite_tags or reference_links or ref_section)
        signals["citations_references"] = has_citations
        if not has_citations:
            issues.append({"type": "info", "msg": "No citations or references detected"})
            score -= 5

        # About page link
        about_link = soup.find("a", href=re.compile(r"/about", re.I))
        signals["about_page_link"] = bool(about_link)
        if not about_link:
            issues.append({"type": "info", "msg": "No link to About page found"})
            score -= 5

        # Trust signals
        trust_keywords = ["testimonial", "review", "certified", "award",
                         "accredited", "verified", "trust", "guarantee"]
        has_trust = any(kw in lower for kw in trust_keywords)
        signals["trust_signals"] = has_trust

        # Contact info
        has_contact = bool(
            soup.find("a", href=re.compile(r"mailto:")) or
            soup.find("a", href=re.compile(r"tel:")) or
            re.search(r"contact\s*us", lower)
        )
        signals["contact_info"] = has_contact
        if not has_contact:
            issues.append({"type": "info", "msg": "No contact information found on page"})
            score -= 3

        # Privacy/Terms links
        has_privacy = bool(soup.find("a", href=re.compile(r"privacy|terms|legal", re.I)))
        signals["privacy_terms"] = has_privacy

        passed = sum(1 for v in signals.values() if v)
        total = len(signals)

        return {
            "score": max(0, score),
            "signals": signals,
            "passed": passed,
            "total": total,
            "issues": issues,
        }

    # ------------------------------------------------------------------
    # AI-powered: optimize meta tags
    # ------------------------------------------------------------------

    async def optimize_meta_tags(
        self, url: str, keyword: str
    ) -> dict[str, Any]:
        """AI-generate optimized title tags and meta descriptions."""
        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        title_tag = soup.find("title")
        current_title = title_tag.get_text(strip=True) if title_tag else ""
        desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        current_desc = desc_tag.get("content", "") if desc_tag else ""

        result = {
            "url": url,
            "keyword": keyword,
            "current": {
                "title": current_title,
                "title_length": len(current_title),
                "description": current_desc,
                "description_length": len(current_desc),
            },
            "suggestions": [],
        }

        if not self._llm:
            result["suggestions"] = [{"note": "LLM client not configured"}]
            return result

        visible = self._visible_text(self._parse_html(html))
        snippet = visible[:800]

        prompt = (
            "You are an expert SEO copywriter. Analyze this page and generate "
            "3 optimized title tags and 3 optimized meta descriptions.\n\n"
            "Target keyword: " + keyword + "\n"
            "Current title: " + current_title + "\n"
            "Current description: " + current_desc + "\n"
            "Content snippet: " + snippet + "\n\n"
            "Requirements:\n"
            "- Titles: 50-60 chars, keyword near front, compelling, unique\n"
            "- Descriptions: 140-155 chars, keyword included, call-to-action\n"
            "- Optimize for CTR in search results\n\n"
            "Return JSON: {\"titles\": [{\"text\": \"...\", \"length\": N}], "
            "\"descriptions\": [{\"text\": \"...\", \"length\": N}]}"
        )

        try:
            ai_result = await self._llm.generate_json(
                prompt,
                system_prompt="You are an SEO expert. Return only valid JSON.",
                temperature=0.7,
            )
            if isinstance(ai_result, dict):
                result["suggestions"] = ai_result
        except Exception as exc:
            logger.warning("AI meta tag optimization failed: %s", exc)
            result["suggestions"] = [{"error": str(exc)}]

        return result

    # ------------------------------------------------------------------
    # AI-powered: generate schema markup
    # ------------------------------------------------------------------

    async def generate_schema_markup(
        self, url: str, schema_type: str = "auto"
    ) -> dict[str, Any]:
        """Analyze page content and generate appropriate JSON-LD schema."""
        from src.modules.onpage_seo.schema_generator import SchemaGenerator

        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        visible = self._visible_text(self._parse_html(html))
        gen = SchemaGenerator(llm_client=self._llm)

        # Auto-detect page type if needed
        detected_type = schema_type
        if schema_type == "auto":
            detected_type = await gen.detect_page_type(url, visible)

        # Extract page data for schema generation
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        description = desc_tag.get("content", "") if desc_tag else ""

        # Find author
        author_meta = soup.find("meta", attrs={"name": "author"})
        author = author_meta.get("content", "") if author_meta else ""
        if not author:
            author_elem = soup.find(attrs={"class": re.compile(r"author", re.I)})
            author = author_elem.get_text(strip=True) if author_elem else "Unknown"

        # Find date
        time_tag = soup.find("time", attrs={"datetime": True})
        date_pub = time_tag["datetime"] if time_tag else ""

        # Find image
        og_image = soup.find("meta", property="og:image")
        image = og_image.get("content", "") if og_image else ""

        schema = {}
        if detected_type == "Article":
            schema = gen.generate_article_schema(
                title=title, author=author, date_published=date_pub,
                description=description, image_url=image, url=url,
            )
        elif detected_type == "FAQPage":
            # Try to extract Q&A pairs
            qas = self._extract_faq_pairs(soup)
            schema = gen.generate_faq_schema(qas)
        elif detected_type == "HowTo":
            steps = self._extract_howto_steps(soup)
            schema = gen.generate_howto_schema(
                name=title, description=description, steps=steps,
            )
        elif detected_type == "LocalBusiness":
            schema = gen.generate_local_business_schema(
                name=title, url=url,
            )
        elif detected_type == "Product":
            schema = gen.generate_product_schema(
                name=title, description=description, image=image, url=url,
            )
        elif detected_type == "Organization":
            schema = gen.generate_organization_schema(
                name=title, url=url, logo=image,
            )
        elif detected_type == "BreadcrumbList":
            crumbs = self._extract_breadcrumbs(soup, url)
            schema = gen.generate_breadcrumb_schema(crumbs)
        else:
            # Default to Article
            schema = gen.generate_article_schema(
                title=title, author=author, date_published=date_pub,
                description=description, url=url,
            )

        validation = gen.validate_schema(schema)

        return {
            "url": url,
            "detected_type": detected_type,
            "requested_type": schema_type,
            "schema": schema,
            "json_ld": json.dumps(schema, indent=2),
            "validation": validation,
        }

    # ------------------------------------------------------------------
    # AI-powered: internal link suggestions
    # ------------------------------------------------------------------

    async def analyze_internal_links(
        self, url: str, site_pages: list[str] | None = None
    ) -> dict[str, Any]:
        """Analyse internal linking with optional site-wide context."""
        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        links = self._check_internal_links(soup, url)

        # AI suggestions for new internal links
        suggestions: list[dict] = []
        if self._llm and site_pages:
            visible = self._visible_text(self._parse_html(html))
            snippet = visible[:600]
            pages_str = "\n".join(site_pages[:30])
            prompt = (
                "Given this page content and list of site pages, suggest 5 "
                "internal links to add. For each, provide the target URL and "
                "suggested anchor text.\n\n"
                "Page content snippet: " + snippet + "\n\n"
                "Available pages:\n" + pages_str + "\n\n"
                "Return JSON: {\"suggestions\": [{\"target_url\": \"...\", "
                "\"anchor_text\": \"...\", \"reason\": \"...\"}]}"
            )
            try:
                ai = await self._llm.generate_json(prompt, temperature=0.5)
                if isinstance(ai, dict):
                    suggestions = ai.get("suggestions", [])
            except Exception as exc:
                logger.warning("AI internal link suggestions failed: %s", exc)

        links["suggested_links"] = suggestions
        links["url"] = url
        return links

    # ------------------------------------------------------------------
    # AI-powered: image optimization
    # ------------------------------------------------------------------

    async def optimize_images(self, url: str) -> dict[str, Any]:
        """Audit images and generate AI alt text for those missing it."""
        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        audit = self._check_images(soup, "")

        # Generate alt text with AI
        if self._llm:
            images_needing_alt = [
                img for img in audit.get("images", [])
                if img.get("alt") is None or img["alt"].strip() == ""
            ][:10]  # limit to 10

            if images_needing_alt:
                visible = self._visible_text(self._parse_html(html))
                context_snippet = visible[:400]
                srcs = [img["src"] for img in images_needing_alt]
                srcs_str = "\n".join("- " + s for s in srcs)

                prompt = (
                    "Generate descriptive, SEO-friendly alt text for these images "
                    "on a web page. Keep each alt text under 125 characters.\n\n"
                    "Page context: " + context_snippet + "\n\n"
                    "Images needing alt text:\n" + srcs_str + "\n\n"
                    "Return JSON: {\"alt_texts\": [{\"src\": \"...\", \"alt\": \"...\"}]}"
                )
                try:
                    ai = await self._llm.generate_json(prompt, temperature=0.5)
                    if isinstance(ai, dict):
                        audit["ai_alt_suggestions"] = ai.get("alt_texts", [])
                except Exception as exc:
                    logger.warning("AI alt text generation failed: %s", exc)
                    audit["ai_alt_suggestions"] = []
            else:
                audit["ai_alt_suggestions"] = []

        audit["url"] = url
        return audit

    # ------------------------------------------------------------------
    # AI-powered: content optimization
    # ------------------------------------------------------------------

    async def analyze_content_optimization(
        self, url: str, keyword: str
    ) -> dict[str, Any]:
        """Deep content analysis with LSI keywords and SERP comparison."""
        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        visible = self._visible_text(self._parse_html(html))
        content_check = self._check_content(soup, visible, keyword.lower())

        # LSI / semantic keywords via AI
        lsi_keywords: list[str] = []
        content_suggestions: list[str] = []

        if self._llm:
            snippet = visible[:1000]
            prompt = (
                "For the target keyword '" + keyword + "', analyze this content "
                "and provide:\n"
                "1. 10 LSI/semantic keywords that should be present\n"
                "2. 5 specific content improvement suggestions\n\n"
                "Content snippet: " + snippet + "\n\n"
                "Return JSON: {\"lsi_keywords\": [\"...\"], "
                "\"suggestions\": [\"...\"]}"
            )
            try:
                ai = await self._llm.generate_json(prompt, temperature=0.5)
                if isinstance(ai, dict):
                    lsi_keywords = ai.get("lsi_keywords", [])
                    content_suggestions = ai.get("suggestions", [])
            except Exception as exc:
                logger.warning("AI content analysis failed: %s", exc)

        # Check which LSI keywords are present
        lower_text = visible.lower()
        lsi_present = [kw for kw in lsi_keywords if kw.lower() in lower_text]
        lsi_missing = [kw for kw in lsi_keywords if kw.lower() not in lower_text]

        content_check["lsi_keywords"] = lsi_keywords
        content_check["lsi_present"] = lsi_present
        content_check["lsi_missing"] = lsi_missing
        content_check["content_suggestions"] = content_suggestions
        content_check["url"] = url
        content_check["keyword"] = keyword
        return content_check

    # ------------------------------------------------------------------
    # E-E-A-T analysis (public)
    # ------------------------------------------------------------------

    async def check_eeat_signals(self, url: str) -> dict[str, Any]:
        """Public method for E-E-A-T signal analysis."""
        html, status, _ = await self._fetch_page(url)
        if not html:
            return {"error": "Failed to fetch page", "url": url}

        soup = self._parse_html(html)
        visible = self._visible_text(self._parse_html(html))
        result = self._check_eeat(soup, visible)
        result["url"] = url
        return result

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    async def generate_optimization_report(
        self, analysis: dict
    ) -> dict[str, Any]:
        """Compile all checks into a prioritized report with action items."""
        if "error" in analysis:
            return analysis

        overall = analysis.get("overall_score", 0)
        grade = analysis.get("grade", "F")

        # Collect all issues by priority
        all_issues: list[dict] = []
        priority_map = {"error": "high", "warning": "medium", "info": "low"}

        for section_key in ("meta_tags", "technical", "content", "images",
                           "internal_links", "schema", "eeat"):
            section = analysis.get(section_key, {})
            for issue in section.get("issues", []):
                all_issues.append({
                    "section": section_key,
                    "priority": priority_map.get(issue.get("type", "info"), "low"),
                    "type": issue.get("type", "info"),
                    "message": issue.get("msg", ""),
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        all_issues.sort(key=lambda x: priority_order.get(x["priority"], 3))

        high = [i for i in all_issues if i["priority"] == "high"]
        medium = [i for i in all_issues if i["priority"] == "medium"]
        low = [i for i in all_issues if i["priority"] == "low"]

        # Generate AI action items
        action_items: list[str] = []
        if self._llm and all_issues:
            issues_text = "\n".join(
                "- [" + i["priority"].upper() + "] " + i["section"] + ": " + i["message"]
                for i in all_issues[:20]
            )
            prompt = (
                "Based on these SEO issues, generate 5-7 prioritized action items "
                "with specific steps to fix each.\n\n"
                "Issues:\n" + issues_text + "\n\n"
                "Return JSON: {\"action_items\": [\"...\"]}"
            )
            try:
                ai = await self._llm.generate_json(prompt, temperature=0.5)
                if isinstance(ai, dict):
                    action_items = ai.get("action_items", [])
            except Exception as exc:
                logger.warning("AI action items generation failed: %s", exc)

        return {
            "url": analysis.get("url", ""),
            "target_keyword": analysis.get("target_keyword", ""),
            "overall_score": overall,
            "grade": grade,
            "categories": analysis.get("categories", {}),
            "issues_summary": {
                "total": len(all_issues),
                "high_priority": len(high),
                "medium_priority": len(medium),
                "low_priority": len(low),
            },
            "issues": all_issues,
            "action_items": action_items,
        }

    # ------------------------------------------------------------------
    # HTML extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_faq_pairs(soup: BeautifulSoup) -> list[dict]:
        """Try to extract FAQ Q&A pairs from page structure."""
        pairs: list[dict] = []

        # Look for FAQ schema patterns in HTML
        # Pattern 1: details/summary
        for details in soup.find_all("details"):
            summary = details.find("summary")
            if summary:
                q = summary.get_text(strip=True)
                # Get answer: all text except the summary
                a_parts = []
                for child in details.children:
                    if child != summary and hasattr(child, "get_text"):
                        a_parts.append(child.get_text(strip=True))
                a = " ".join(a_parts).strip()
                if q and a:
                    pairs.append({"question": q, "answer": a})

        # Pattern 2: headings with class containing faq/question
        if not pairs:
            faq_headings = soup.find_all(
                re.compile(r"h[2-4]"),
                class_=re.compile(r"faq|question", re.I),
            )
            for h in faq_headings:
                q = h.get_text(strip=True)
                # Get next sibling that is a paragraph
                nxt = h.find_next_sibling(["p", "div"])
                a = nxt.get_text(strip=True) if nxt else ""
                if q and a:
                    pairs.append({"question": q, "answer": a})

        # Pattern 3: headings ending with ?
        if not pairs:
            for h in soup.find_all(re.compile(r"h[2-4]")):
                text = h.get_text(strip=True)
                if text.endswith("?"):
                    nxt = h.find_next_sibling(["p", "div"])
                    a = nxt.get_text(strip=True) if nxt else ""
                    if a:
                        pairs.append({"question": text, "answer": a})

        return pairs[:20]  # limit

    @staticmethod
    def _extract_howto_steps(soup: BeautifulSoup) -> list[dict]:
        """Try to extract how-to steps from page structure."""
        steps: list[dict] = []

        # Pattern 1: ordered list items
        for ol in soup.find_all("ol"):
            for li in ol.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    steps.append({"text": text})
            if steps:
                break

        # Pattern 2: headings with step numbering
        if not steps:
            for h in soup.find_all(re.compile(r"h[2-4]")):
                text = h.get_text(strip=True)
                if re.match(r"step\s*\d", text, re.I):
                    nxt = h.find_next_sibling(["p", "div"])
                    desc = nxt.get_text(strip=True) if nxt else ""
                    steps.append({"name": text, "text": desc or text})

        return steps[:20]

    @staticmethod
    def _extract_breadcrumbs(soup: BeautifulSoup, url: str) -> list[dict]:
        """Try to extract breadcrumbs from page."""
        crumbs: list[dict] = []

        # Look for breadcrumb nav
        nav = soup.find(attrs={"class": re.compile(r"breadcrumb", re.I)})
        if nav:
            for a in nav.find_all("a", href=True):
                crumbs.append({
                    "name": a.get_text(strip=True),
                    "url": urljoin(url, a["href"]),
                })

        if not crumbs:
            # Build from URL path
            parsed = urlparse(url)
            parts = [p for p in parsed.path.split("/") if p]
            base = parsed.scheme + "://" + parsed.netloc
            crumbs.append({"name": "Home", "url": base + "/"})
            path = ""
            for part in parts:
                path += "/" + part
                name = part.replace("-", " ").replace("_", " ").title()
                crumbs.append({"name": name, "url": base + path})

        return crumbs
