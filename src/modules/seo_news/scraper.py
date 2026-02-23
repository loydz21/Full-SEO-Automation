"""SEO News Scraper — Scrapes authoritative SEO sources for strategy updates.

Scrapes RSS feeds, blogs, and news sites to find new SEO strategies,
algorithm updates, and optimization techniques.
"""

import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import feedparser
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# Default SEO news sources (RSS feeds and blogs)
DEFAULT_SOURCES = [
    # Google Official
    {
        "name": "Google Search Central Blog",
        "url": "https://developers.google.com/search/blog/feed",
        "source_type": "rss",
        "category": "algorithm",
        "reliability_score": 1.0,
    },
    # Major SEO Publications
    {
        "name": "Search Engine Journal",
        "url": "https://www.searchenginejournal.com/feed/",
        "source_type": "rss",
        "category": "general",
        "reliability_score": 0.9,
    },
    {
        "name": "Search Engine Land",
        "url": "https://searchengineland.com/feed",
        "source_type": "rss",
        "category": "general",
        "reliability_score": 0.9,
    },
    {
        "name": "Moz Blog",
        "url": "https://moz.com/blog/feed",
        "source_type": "rss",
        "category": "general",
        "reliability_score": 0.9,
    },
    {
        "name": "Ahrefs Blog",
        "url": "https://ahrefs.com/blog/feed/",
        "source_type": "rss",
        "category": "general",
        "reliability_score": 0.9,
    },
    {
        "name": "Backlinko",
        "url": "https://backlinko.com/feed",
        "source_type": "rss",
        "category": "linkbuilding",
        "reliability_score": 0.85,
    },
    {
        "name": "SEMrush Blog",
        "url": "https://www.semrush.com/blog/feed/",
        "source_type": "rss",
        "category": "general",
        "reliability_score": 0.85,
    },
    {
        "name": "Neil Patel Blog",
        "url": "https://neilpatel.com/blog/feed/",
        "source_type": "rss",
        "category": "content",
        "reliability_score": 0.8,
    },
    {
        "name": "Yoast SEO Blog",
        "url": "https://yoast.com/feed/",
        "source_type": "rss",
        "category": "technical",
        "reliability_score": 0.85,
    },
    {
        "name": "Search Engine Roundtable",
        "url": "https://www.seroundtable.com/feed/",
        "source_type": "rss",
        "category": "algorithm",
        "reliability_score": 0.9,
    },
    {
        "name": "BrightLocal Blog",
        "url": "https://www.brightlocal.com/feed/",
        "source_type": "rss",
        "category": "local",
        "reliability_score": 0.85,
    },
    {
        "name": "Sterling Sky (Local SEO)",
        "url": "https://www.sterlingsky.ca/feed/",
        "source_type": "rss",
        "category": "local",
        "reliability_score": 0.8,
    },
]


class SEONewsScraper:
    """Scrapes SEO news sources for strategy updates and algorithm changes."""

    def __init__(self, sources: Optional[list[dict]] = None, max_age_days: int = 30):
        """Initialize scraper with news sources.

        Args:
            sources: List of source dicts. Uses DEFAULT_SOURCES if None.
            max_age_days: Only fetch articles from the last N days.
        """
        self.sources = sources or DEFAULT_SOURCES
        self.max_age_days = max_age_days
        self.session: Optional[aiohttp.ClientSession] = None
        self._scraped_articles: list[dict] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def scrape_all_sources(self) -> list[dict]:
        """Scrape all configured news sources.

        Returns:
            List of article dicts with keys:
                title, url, summary, author, published_at,
                source_name, category, full_content
        """
        all_articles = []
        tasks = []

        for source in self.sources:
            if not source.get("is_active", True):
                continue
            tasks.append(self._scrape_source(source))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            source_name = self.sources[i]["name"]
            if isinstance(result, Exception):
                logger.warning("Failed to scrape %s: %s", source_name, result)
                continue
            if result:
                logger.info("Scraped %d articles from %s", len(result), source_name)
                all_articles.extend(result)

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            url = article.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)

        self._scraped_articles = unique_articles
        logger.info("Total unique articles scraped: %d", len(unique_articles))
        return unique_articles

    async def _scrape_source(self, source: dict) -> list[dict]:
        """Scrape a single news source."""
        source_type = source.get("source_type", "rss")

        if source_type == "rss":
            return await self._scrape_rss(source)
        elif source_type == "blog":
            return await self._scrape_blog(source)
        else:
            logger.warning("Unknown source type: %s", source_type)
            return []

    async def _scrape_rss(self, source: dict) -> list[dict]:
        """Scrape an RSS feed."""
        articles = []
        session = await self._get_session()

        try:
            async with session.get(source["url"]) as response:
                if response.status != 200:
                    logger.warning(
                        "RSS fetch failed for %s: HTTP %d",
                        source["name"], response.status
                    )
                    return []
                content = await response.text()
        except Exception as e:
            logger.warning("RSS fetch error for %s: %s", source["name"], e)
            return []

        feed = feedparser.parse(content)
        cutoff = datetime.utcnow() - timedelta(days=self.max_age_days)

        for entry in feed.entries:
            # Parse published date
            published = None
            for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
                parsed = getattr(entry, date_field, None)
                if parsed:
                    try:
                        published = datetime(*parsed[:6])
                        break
                    except (TypeError, ValueError):
                        continue

            # Skip old articles
            if published and published < cutoff:
                continue

            # Extract summary
            summary = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                summary = soup.get_text(strip=True)[:500]

            article = {
                "title": getattr(entry, "title", "Untitled"),
                "url": getattr(entry, "link", ""),
                "summary": summary,
                "author": getattr(entry, "author", None),
                "published_at": published,
                "source_name": source["name"],
                "source_url": source["url"],
                "category": source.get("category", "general"),
                "reliability_score": source.get("reliability_score", 0.5),
                "full_content": None,  # Fetched on demand
                "tags": [t.get("term", "") for t in getattr(entry, "tags", [])],
            }
            articles.append(article)

        return articles

    async def _scrape_blog(self, source: dict) -> list[dict]:
        """Scrape a blog page for articles."""
        articles = []
        session = await self._get_session()

        try:
            async with session.get(source["url"]) as response:
                if response.status != 200:
                    return []
                html = await response.text()
        except Exception as e:
            logger.warning("Blog fetch error for %s: %s", source["name"], e)
            return []

        soup = BeautifulSoup(html, "html.parser")
        base_domain = urlparse(source["url"]).scheme + "://" + urlparse(source["url"]).netloc

        # Find article links
        for article_tag in soup.find_all("article"):
            link_tag = article_tag.find("a", href=True)
            title_tag = article_tag.find(["h1", "h2", "h3"])

            if not link_tag:
                continue

            href = link_tag["href"]
            if href.startswith("/"):
                href = base_domain + href

            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
            if not title:
                continue

            summary_tag = article_tag.find("p")
            summary = summary_tag.get_text(strip=True)[:500] if summary_tag else ""

            articles.append({
                "title": title,
                "url": href,
                "summary": summary,
                "author": None,
                "published_at": None,
                "source_name": source["name"],
                "source_url": source["url"],
                "category": source.get("category", "general"),
                "reliability_score": source.get("reliability_score", 0.5),
                "full_content": None,
                "tags": [],
            })

        return articles

    async def fetch_full_content(self, article_url: str) -> str:
        """Fetch full article content for deeper analysis."""
        session = await self._get_session()

        try:
            async with session.get(article_url) as response:
                if response.status != 200:
                    return ""
                html = await response.text()
        except Exception as e:
            logger.warning("Content fetch error for %s: %s", article_url, e)
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts, styles, navs, footers
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try common article content selectors
        content_selectors = [
            "article", ".post-content", ".entry-content", ".article-content",
            ".blog-post-content", ".post-body", "[itemprop=articleBody]",
            ".content-area", "main", ".main-content",
        ]

        for selector in content_selectors:
            content_el = soup.select_one(selector)
            if content_el:
                text = content_el.get_text(separator="\n", strip=True)
                if len(text) > 200:  # Minimum content length
                    return text[:10000]  # Cap at 10k chars

        # Fallback to body text
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)[:10000]

        return ""

    async def scrape_and_extract(self) -> list[dict]:
        """Full pipeline: scrape all sources and fetch content for promising articles."""
        articles = await self.scrape_all_sources()

        # Fetch full content for articles that look promising
        seo_keywords = [
            "algorithm", "ranking", "seo", "search", "google", "serp",
            "backlink", "content", "technical", "core web vitals",
            "local seo", "map pack", "schema", "e-e-a-t", "helpful content",
            "indexing", "crawling", "site speed", "mobile", "ai overview",
            "optimization", "strategy", "update", "penalty", "manual action",
        ]

        promising = []
        for article in articles:
            title_lower = (article.get("title", "") or "").lower()
            summary_lower = (article.get("summary", "") or "").lower()
            combined = title_lower + " " + summary_lower

            # Score by keyword relevance
            relevance = sum(1 for kw in seo_keywords if kw in combined)
            article["relevance_score"] = min(relevance / 5, 1.0)  # Normalize to 0-1
            article["is_actionable"] = relevance >= 2

            if relevance >= 2:
                promising.append(article)

        # Fetch full content for top promising articles (limit to avoid rate limits)
        fetch_limit = min(len(promising), 20)
        for article in promising[:fetch_limit]:
            try:
                content = await self.fetch_full_content(article["url"])
                article["full_content"] = content
                await asyncio.sleep(1)  # Rate limit
            except Exception as e:
                logger.warning("Failed to fetch content for %s: %s", article["url"], e)

        return articles

    def get_article_hash(self, url: str) -> str:
        """Generate a unique hash for deduplication."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def filter_by_category(self, articles: list[dict], category: str) -> list[dict]:
        """Filter articles by category."""
        return [a for a in articles if a.get("category") == category]

    def filter_actionable(self, articles: list[dict]) -> list[dict]:
        """Return only actionable articles with strategies."""
        return [a for a in articles if a.get("is_actionable", False)]

    def sort_by_relevance(self, articles: list[dict]) -> list[dict]:
        """Sort articles by relevance score descending."""
        return sorted(articles, key=lambda a: a.get("relevance_score", 0), reverse=True)
