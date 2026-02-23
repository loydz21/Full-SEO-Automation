"""Link prospecting engine for discovering link building opportunities.

Provides multiple strategies: guest posts, resource pages, broken links,
competitor backlinks, unlinked mentions, and local link opportunities.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper
from src.models.backlink import OutreachProspect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GUEST_POST_FOOTPRINTS = [
    '"write for us"',
    '"guest post"',
    '"guest article"',
    '"contribute"',
    '"become a contributor"',
    '"submit a post"',
    '"accepting guest posts"',
    '"guest blogging guidelines"',
]

RESOURCE_PAGE_FOOTPRINTS = [
    '"best resources"',
    '"useful resources"',
    '"helpful links"',
    '"recommended tools"',
    '"link roundup"',
    '"weekly roundup"',
    '"top tools"',
    '"resource page"',
    '"best of"',
]

LOCAL_LINK_FOOTPRINTS = [
    '"chamber of commerce"',
    '"business directory"',
    '"local sponsors"',
    '"community partners"',
    '"local events"',
    '"business association"',
]

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

DEFAULT_STRATEGIES = [
    "guest_post",
    "resource_page",
    "broken_link",
    "competitor_backlinks",
    "unlinked_mentions",
]

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _extract_domain(url: str) -> str:
    """Extract domain from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        domain = domain.lower().lstrip("www.")
        return domain
    except Exception:
        return url


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LinkProspector:
    """Discovers link building opportunities using multiple strategies.

    Usage::

        prospector = LinkProspector()
        prospects = await prospector.find_prospects(
            domain="example.com",
            keywords=["seo tools", "digital marketing"],
            strategies=["guest_post", "resource_page"],
        )
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        serp_scraper: Optional[SERPScraper] = None,
        max_results_per_strategy: int = 20,
    ):
        self._llm = llm_client or LLMClient()
        self._serp = serp_scraper or SERPScraper(headless=True)
        self._max_results = max_results_per_strategy
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Lazily create and return an aiohttp session."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=HTTP_TIMEOUT, headers=DEFAULT_HEADERS
            )
        return self._http_session

    async def close(self) -> None:
        """Clean up resources."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        await self._serp.close()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def find_prospects(
        self,
        domain: str,
        keywords: list[str],
        strategies: Optional[list[str]] = None,
    ) -> list[dict]:
        """Find link building opportunities using multiple strategies.

        Args:
            domain: The target domain we are building links for.
            keywords: Niche keywords to search with.
            strategies: List of strategy names to use. Defaults to all.

        Returns:
            List of prospect dicts with url, domain, contact_email,
            da_estimate, relevance_score, strategy_type, notes.
        """
        strategies = strategies or DEFAULT_STRATEGIES
        all_prospects: list[dict] = []
        seen_domains: set[str] = set()

        strategy_map = {
            "guest_post": self.find_guest_post_opportunities,
            "resource_page": self.find_resource_page_links,
            "broken_link": lambda kw: self.find_broken_link_opportunities([domain]),
            "competitor_backlinks": lambda kw: self.find_competitor_backlinks(domain),
            "unlinked_mentions": lambda kw: self.find_unlinked_mentions(domain),
        }

        for strategy_name in strategies:
            handler = strategy_map.get(strategy_name)
            if handler is None:
                logger.warning("Unknown strategy: %s", strategy_name)
                continue

            logger.info("Running strategy: %s", strategy_name)
            try:
                if strategy_name in ("guest_post", "resource_page"):
                    results = await handler(keywords)
                else:
                    results = await handler(keywords)
            except Exception as exc:
                logger.error("Strategy %s failed: %s", strategy_name, exc)
                continue

            for prospect in results:
                p_domain = _extract_domain(prospect.get("url", ""))
                if p_domain and p_domain != domain and p_domain not in seen_domains:
                    seen_domains.add(p_domain)
                    prospect["strategy_type"] = strategy_name
                    all_prospects.append(prospect)

        # Score all prospects
        for prospect in all_prospects:
            if not prospect.get("relevance_score"):
                try:
                    prospect["relevance_score"] = await self.score_prospect(prospect)
                except Exception as exc:
                    logger.warning("Scoring failed for %s: %s", prospect.get("url"), exc)
                    prospect["relevance_score"] = 0.5

        all_prospects.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)
        logger.info(
            "Found %d total prospects across %d strategies",
            len(all_prospects), len(strategies),
        )
        return all_prospects

    # ------------------------------------------------------------------
    # Strategy: Guest Post Opportunities
    # ------------------------------------------------------------------

    async def find_guest_post_opportunities(
        self, keywords: list[str]
    ) -> list[dict]:
        """Search for guest post opportunities using SERP footprints."""
        prospects: list[dict] = []

        for keyword in keywords[:5]:
            for footprint in GUEST_POST_FOOTPRINTS[:4]:
                query = keyword + " " + footprint
                try:
                    serp_data = await self._serp.search_google(query, num_results=10)
                    organic = serp_data.get("organic_results", [])
                    for result in organic[: self._max_results]:
                        url = result.get("url", "")
                        if not url:
                            continue
                        fp_clean = footprint.strip('"')
                        prospect = {
                            "url": url,
                            "domain": _extract_domain(url),
                            "title": result.get("title", ""),
                            "snippet": result.get("snippet", ""),
                            "contact_email": None,
                            "da_estimate": None,
                            "relevance_score": 0.0,
                            "strategy_type": "guest_post",
                            "notes": "Guest post opportunity found via: " + fp_clean,
                        }
                        prospects.append(prospect)
                except Exception as exc:
                    logger.warning("SERP search failed for query %r: %s", query, exc)

                await asyncio.sleep(1.0)

        logger.info("Guest post search yielded %d raw prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    # ------------------------------------------------------------------
    # Strategy: Resource Page Links
    # ------------------------------------------------------------------

    async def find_resource_page_links(
        self, keywords: list[str]
    ) -> list[dict]:
        """Search for resource pages and link roundups."""
        prospects: list[dict] = []

        for keyword in keywords[:5]:
            for footprint in RESOURCE_PAGE_FOOTPRINTS[:4]:
                query = keyword + " " + footprint
                try:
                    serp_data = await self._serp.search_google(query, num_results=10)
                    organic = serp_data.get("organic_results", [])
                    for result in organic[: self._max_results]:
                        url = result.get("url", "")
                        if not url:
                            continue
                        fp_clean = footprint.strip('"')
                        prospect = {
                            "url": url,
                            "domain": _extract_domain(url),
                            "title": result.get("title", ""),
                            "snippet": result.get("snippet", ""),
                            "contact_email": None,
                            "da_estimate": None,
                            "relevance_score": 0.0,
                            "strategy_type": "resource_page",
                            "notes": "Resource page found via: " + fp_clean,
                        }
                        prospects.append(prospect)
                except Exception as exc:
                    logger.warning("Resource page search failed for %r: %s", query, exc)

                await asyncio.sleep(1.0)

        logger.info("Resource page search yielded %d raw prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    # ------------------------------------------------------------------
    # Strategy: Broken Link Building
    # ------------------------------------------------------------------

    async def find_broken_link_opportunities(
        self, competitor_domains: list[str]
    ) -> list[dict]:
        """Find broken outbound links on relevant pages."""
        prospects: list[dict] = []
        session = await self._get_http_session()

        for comp_domain in competitor_domains[:5]:
            query = "site:" + comp_domain
            try:
                serp_data = await self._serp.search_google(query, num_results=10)
                organic = serp_data.get("organic_results", [])

                for result in organic[:10]:
                    page_url = result.get("url", "")
                    if not page_url:
                        continue
                    broken = await self._check_outbound_links(session, page_url)
                    for broken_link in broken:
                        prospect = {
                            "url": page_url,
                            "domain": _extract_domain(page_url),
                            "title": result.get("title", ""),
                            "snippet": "",
                            "contact_email": None,
                            "da_estimate": None,
                            "relevance_score": 0.0,
                            "strategy_type": "broken_link",
                            "notes": "Broken outbound link: " + broken_link,
                            "broken_url": broken_link,
                        }
                        prospects.append(prospect)
            except Exception as exc:
                logger.warning("Broken link scan failed for %s: %s", comp_domain, exc)

        logger.info("Broken link search yielded %d prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    async def _check_outbound_links(
        self, session: aiohttp.ClientSession, page_url: str
    ) -> list[str]:
        """Fetch a page and check its outbound links for 404s."""
        broken: list[str] = []
        try:
            async with session.get(page_url) as resp:
                if resp.status != 200:
                    return broken
                html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            page_domain = _extract_domain(page_url)
            links = soup.find_all("a", href=True)

            tasks = []
            for tag in links[:50]:
                href = tag["href"]
                if not href.startswith("http"):
                    continue
                link_domain = _extract_domain(href)
                if link_domain == page_domain:
                    continue
                tasks.append(self._check_single_link(session, href))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, tuple):
                    href_val, is_broken = item
                    if is_broken:
                        broken.append(href_val)
        except Exception as exc:
            logger.debug("Failed to check outbound links on %s: %s", page_url, exc)
        return broken

    @staticmethod
    async def _check_single_link(
        session: aiohttp.ClientSession, url: str
    ) -> tuple[str, bool]:
        """Return (url, is_broken) tuple."""
        try:
            async with session.head(url, allow_redirects=True) as resp:
                return (url, resp.status >= 400)
        except Exception:
            return (url, True)

    # ------------------------------------------------------------------
    # Strategy: Competitor Backlink Analysis
    # ------------------------------------------------------------------

    async def find_competitor_backlinks(
        self, competitor_domain: str
    ) -> list[dict]:
        """Analyze competitor backlinks via SERP footprints."""
        prospects: list[dict] = []

        queries = [
            "link:" + competitor_domain,
            '"' + competitor_domain + '"' + " -site:" + competitor_domain,
            '"' + competitor_domain + '"' + " inurl:resources",
            '"' + competitor_domain + '"' + " inurl:links",
        ]

        for query in queries:
            try:
                serp_data = await self._serp.search_google(query, num_results=10)
                organic = serp_data.get("organic_results", [])
                for result in organic[: self._max_results]:
                    url = result.get("url", "")
                    if not url:
                        continue
                    result_domain = _extract_domain(url)
                    if result_domain == competitor_domain:
                        continue
                    prospect = {
                        "url": url,
                        "domain": result_domain,
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "contact_email": None,
                        "da_estimate": None,
                        "relevance_score": 0.0,
                        "strategy_type": "competitor_backlinks",
                        "notes": "Links to competitor: " + competitor_domain,
                    }
                    prospects.append(prospect)
            except Exception as exc:
                logger.warning("Competitor backlink query failed: %s", exc)
            await asyncio.sleep(1.0)

        logger.info("Competitor analysis yielded %d prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    # ------------------------------------------------------------------
    # Strategy: Unlinked Mentions
    # ------------------------------------------------------------------

    async def find_unlinked_mentions(
        self, brand_name: str
    ) -> list[dict]:
        """Find pages mentioning the brand without linking to it."""
        prospects: list[dict] = []
        if "." in brand_name:
            brand_domain = _extract_domain(brand_name)
        else:
            brand_domain = brand_name

        queries = [
            '"' + brand_name + '"' + " -site:" + brand_domain + " -link:" + brand_domain,
            '"' + brand_name + '"' + " -site:" + brand_domain,
        ]

        for query in queries:
            try:
                serp_data = await self._serp.search_google(query, num_results=10)
                organic = serp_data.get("organic_results", [])
                for result in organic[: self._max_results]:
                    url = result.get("url", "")
                    if not url:
                        continue
                    result_domain = _extract_domain(url)
                    if result_domain == brand_domain:
                        continue
                    prospect = {
                        "url": url,
                        "domain": result_domain,
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "contact_email": None,
                        "da_estimate": None,
                        "relevance_score": 0.0,
                        "strategy_type": "unlinked_mentions",
                        "notes": "Mentions brand without linking",
                    }
                    prospects.append(prospect)
            except Exception as exc:
                logger.warning("Unlinked mentions query failed: %s", exc)
            await asyncio.sleep(1.0)

        logger.info("Unlinked mentions search yielded %d prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    # ------------------------------------------------------------------
    # Strategy: Local Link Opportunities
    # ------------------------------------------------------------------

    async def find_local_link_opportunities(
        self, business_name: str, location: str
    ) -> list[dict]:
        """Find local directories, chambers of commerce, and community orgs."""
        prospects: list[dict] = []

        for footprint in LOCAL_LINK_FOOTPRINTS:
            query = location + " " + footprint
            try:
                serp_data = await self._serp.search_google(query, num_results=10)
                organic = serp_data.get("organic_results", [])
                for result in organic[: self._max_results]:
                    url = result.get("url", "")
                    if not url:
                        continue
                    prospect = {
                        "url": url,
                        "domain": _extract_domain(url),
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "contact_email": None,
                        "da_estimate": None,
                        "relevance_score": 0.0,
                        "strategy_type": "local_links",
                        "notes": "Local opportunity in " + location,
                    }
                    prospects.append(prospect)
            except Exception as exc:
                logger.warning("Local link search failed: %s", exc)
            await asyncio.sleep(1.0)

        # Also search for local news/events
        news_queries = [
            location + " local news submit story",
            location + " events sponsorship opportunities",
            location + " " + business_name + " directory listing",
        ]
        for query in news_queries:
            try:
                serp_data = await self._serp.search_google(query, num_results=5)
                organic = serp_data.get("organic_results", [])
                for result in organic[:5]:
                    url = result.get("url", "")
                    if not url:
                        continue
                    prospect = {
                        "url": url,
                        "domain": _extract_domain(url),
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "contact_email": None,
                        "da_estimate": None,
                        "relevance_score": 0.0,
                        "strategy_type": "local_links",
                        "notes": "Local news/event opportunity",
                    }
                    prospects.append(prospect)
            except Exception as exc:
                logger.warning("Local news search failed: %s", exc)
            await asyncio.sleep(1.0)

        logger.info("Local link search yielded %d prospects", len(prospects))
        return self._dedupe_prospects(prospects)

    # ------------------------------------------------------------------
    # AI-Powered Scoring
    # ------------------------------------------------------------------

    async def score_prospect(self, prospect: dict) -> float:
        """Score a prospect 0.0-1.0 using AI analysis."""
        prompt_parts = [
            "Score this link building prospect from 0.0 to 1.0 based on:",
            "- Relevance and authority of the domain",
            "- Likelihood of getting a link",
            "- Effort required vs potential value",
            "- Quality signals from title and snippet",
            "",
            "Prospect details:",
            "URL: " + prospect.get("url", ""),
            "Domain: " + prospect.get("domain", ""),
            "Title: " + prospect.get("title", ""),
            "Snippet: " + prospect.get("snippet", ""),
            "Strategy: " + prospect.get("strategy_type", ""),
            "Notes: " + prospect.get("notes", ""),
            "",
            'Respond with ONLY a JSON object: {"score": 0.75, "reasoning": "brief reason"}',
        ]
        prompt = "\n".join(prompt_parts)

        try:
            result = await self._llm.generate_json(prompt)
            score = float(result.get("score", 0.5))
            return max(0.0, min(1.0, score))
        except Exception as exc:
            logger.warning("AI scoring failed: %s", exc)
            return self._heuristic_score(prospect)

    @staticmethod
    def _heuristic_score(prospect: dict) -> float:
        """Fallback heuristic scoring when AI is unavailable."""
        score = 0.5
        title = prospect.get("title", "").lower()
        strategy = prospect.get("strategy_type", "")

        # Boost for explicit guest post / resource pages
        boost_terms = ["write for us", "guest post", "contribute"]
        if any(term in title for term in boost_terms):
            score += 0.15
        resource_terms = ["resources", "tools", "best of"]
        if any(term in title for term in resource_terms):
            score += 0.1

        # Strategy-based adjustments
        strategy_bonuses = {
            "guest_post": 0.05,
            "resource_page": 0.05,
            "broken_link": 0.1,
            "unlinked_mentions": 0.15,
            "competitor_backlinks": 0.05,
        }
        score += strategy_bonuses.get(strategy, 0)

        # Penalize social media and forums
        domain = prospect.get("domain", "").lower()
        low_value = [
            "facebook.com", "twitter.com", "reddit.com", "quora.com",
            "youtube.com", "linkedin.com", "pinterest.com", "instagram.com",
        ]
        if any(lv in domain for lv in low_value):
            score -= 0.3

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Contact Info Extraction
    # ------------------------------------------------------------------

    async def extract_contact_info(self, url: str) -> dict:
        """Scrape a page for contact information."""
        contact: dict[str, Any] = {
            "emails": [],
            "contact_page": None,
            "social_profiles": [],
        }

        session = await self._get_http_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return contact
                html = await resp.text()
        except Exception as exc:
            logger.warning("Failed to fetch %s for contact extraction: %s", url, exc)
            return contact

        soup = BeautifulSoup(html, "html.parser")

        # Extract emails from page text
        page_text = soup.get_text(" ", strip=True)
        emails_found = EMAIL_PATTERN.findall(page_text)
        # Filter out common non-personal emails
        ignore_patterns = ["@example.", "@sentry.", "@wixpress.", ".png", ".jpg"]
        for email in emails_found:
            email_lower = email.lower()
            if not any(pat in email_lower for pat in ignore_patterns):
                contact["emails"].append(email)

        # Also check mailto links
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.startswith("mailto:"):
                email_val = href.replace("mailto:", "").split("?")[0].strip()
                if email_val and email_val not in contact["emails"]:
                    contact["emails"].append(email_val)

        # Find contact page links
        contact_keywords = ["contact", "about", "reach-us", "get-in-touch"]
        for a_tag in soup.find_all("a", href=True):
            link_text = (a_tag.get_text() or "").lower().strip()
            link_href = a_tag["href"].lower()
            if any(kw in link_text or kw in link_href for kw in contact_keywords):
                contact_href = a_tag["href"]
                if contact_href.startswith("/"):
                    parsed = urlparse(url)
                    base = parsed.scheme + "://" + parsed.netloc
                    contact_href = base + contact_href
                contact["contact_page"] = contact_href
                break

        # Extract social profiles
        social_domains = [
            "twitter.com", "x.com", "linkedin.com", "facebook.com",
            "instagram.com", "youtube.com",
        ]
        for a_tag in soup.find_all("a", href=True):
            href_val = a_tag["href"]
            for sd in social_domains:
                if sd in href_val:
                    contact["social_profiles"].append(href_val)
                    break

        contact["emails"] = list(set(contact["emails"]))[:5]
        contact["social_profiles"] = list(set(contact["social_profiles"]))[:10]

        logger.info(
            "Contact extraction for %s: %d emails, contact page=%s",
            url, len(contact["emails"]), contact.get("contact_page"),
        )
        return contact

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_prospects_to_db(
        self, prospects: list[dict], campaign_id: Optional[int] = None
    ) -> list[int]:
        """Save prospect dicts to the database as OutreachProspect rows."""
        ids: list[int] = []
        with get_session() as session:
            for p in prospects:
                emails_list = p.get("emails") or []
                first_email = emails_list[0] if emails_list else None
                obj = OutreachProspect(
                    campaign_id=campaign_id,
                    url=p.get("url", ""),
                    domain=p.get("domain", ""),
                    contact_email=p.get("contact_email") or first_email,
                    da_estimate=p.get("da_estimate"),
                    relevance_score=p.get("relevance_score"),
                    strategy_type=p.get("strategy_type"),
                    status="new",
                    notes=p.get("notes"),
                )
                session.add(obj)
                session.flush()
                ids.append(obj.id)
        logger.info("Saved %d prospects to database", len(ids))
        return ids

    def get_saved_prospects(
        self,
        campaign_id: Optional[int] = None,
        strategy_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Load prospects from the database with optional filters."""
        with get_session() as session:
            query = session.query(OutreachProspect)
            if campaign_id is not None:
                query = query.filter(OutreachProspect.campaign_id == campaign_id)
            if strategy_type:
                query = query.filter(OutreachProspect.strategy_type == strategy_type)
            if status:
                query = query.filter(OutreachProspect.status == status)
            rows = query.order_by(OutreachProspect.relevance_score.desc()).all()
            return [
                {
                    "id": r.id,
                    "url": r.url,
                    "domain": r.domain,
                    "contact_email": r.contact_email,
                    "da_estimate": r.da_estimate,
                    "relevance_score": r.relevance_score,
                    "strategy_type": r.strategy_type,
                    "status": r.status,
                    "notes": r.notes,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _dedupe_prospects(prospects: list[dict]) -> list[dict]:
        """Remove duplicate prospects by domain."""
        seen: set[str] = set()
        unique: list[dict] = []
        for p in prospects:
            domain = p.get("domain", "")
            if domain and domain not in seen:
                seen.add(domain)
                unique.append(p)
        return unique
