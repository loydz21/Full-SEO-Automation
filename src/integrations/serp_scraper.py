"""SERP scraper using Playwright for Google search result extraction."""

import asyncio
import logging
import random
import time
from typing import Any, Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class SERPScraper:
    """Scrape Google SERPs using headless Playwright.

    Usage::

        scraper = SERPScraper()
        results = await scraper.search_google("best seo tools 2025")
        paa = await scraper.get_paa_questions("what is seo")
        autocomplete = await scraper.get_autocomplete("seo")
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        delay_between_requests: float = 3.0,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        proxy_url: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
        user_agents: Optional[list[str]] = None,
    ):
        self._headless = headless
        self._timeout = timeout
        self._delay = delay_between_requests
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._proxy_url = proxy_url
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password
        self._user_agents = user_agents or DEFAULT_USER_AGENTS
        self._browser: Optional[Browser] = None
        self._last_request_time: float = 0.0

    async def _ensure_browser(self) -> Browser:
        """Launch or reuse the Playwright browser."""
        if self._browser and self._browser.is_connected():
            return self._browser
        pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": self._headless}
        if self._proxy_url:
            proxy_config: dict[str, str] = {"server": self._proxy_url}
            if self._proxy_username:
                proxy_config["username"] = self._proxy_username
            if self._proxy_password:
                proxy_config["password"] = self._proxy_password
            launch_kwargs["proxy"] = proxy_config
        self._browser = await pw.chromium.launch(**launch_kwargs)
        return self._browser

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._delay:
            wait = self._delay - elapsed + random.uniform(0.5, 1.5)
            logger.debug("SERP rate limit: sleeping %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = time.monotonic()

    async def _new_page(self) -> Page:
        """Create a new page with a random user-agent."""
        browser = await self._ensure_browser()
        ua = random.choice(self._user_agents)
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()
        page.set_default_timeout(self._timeout)
        return page

    async def search_google(
        self,
        query: str,
        num_results: int = 10,
        lang: str = "en",
        country: str = "",
    ) -> dict[str, Any]:
        """Scrape Google search results for a query.

        Returns:
            Dict with organic_results, featured_snippet, paa, and related_searches.
        """
        await self._rate_limit()
        url = f"https://www.google.com/search?q={quote_plus(query)}&num={num_results}&hl={lang}"
        if country:
            url += f"&gl={country}"

        page = await self._new_page()
        result: dict[str, Any] = {
            "query": query,
            "organic_results": [],
            "featured_snippet": None,
            "people_also_ask": [],
            "related_searches": [],
        }

        try:
            for attempt in range(self._max_retries):
                try:
                    await page.goto(url, wait_until="domcontentloaded")
                    await page.wait_for_selector("#search", timeout=self._timeout)

                    # Parse organic results
                    result["organic_results"] = await self._parse_organic(page)

                    # Parse featured snippet
                    result["featured_snippet"] = await self._parse_featured_snippet(page)

                    # Parse People Also Ask
                    result["people_also_ask"] = await self._parse_paa(page)

                    # Parse related searches
                    result["related_searches"] = await self._parse_related(page)

                    logger.info(
                        "SERP for %r: %d organic, %d PAA",
                        query,
                        len(result["organic_results"]),
                        len(result["people_also_ask"]),
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "SERP attempt %d failed for %r: %s", attempt + 1, query, exc
                    )
                    if attempt < self._max_retries - 1:
                        await asyncio.sleep(self._retry_delay * (attempt + 1))
                    else:
                        logger.error("All SERP attempts failed for %r", query)
        finally:
            await page.context.close()

        return result

    async def get_serp_features(self, query: str) -> dict[str, bool]:
        """Detect SERP features present for a query."""
        serp = await self.search_google(query)
        return {
            "featured_snippet": serp["featured_snippet"] is not None,
            "people_also_ask": len(serp["people_also_ask"]) > 0,
            "related_searches": len(serp["related_searches"]) > 0,
            "organic_count": len(serp["organic_results"]),
        }

    async def get_paa_questions(self, query: str) -> list[str]:
        """Extract People Also Ask questions for a query."""
        serp = await self.search_google(query)
        return serp.get("people_also_ask", [])

    async def get_autocomplete(
        self, query: str, lang: str = "en"
    ) -> list[str]:
        """Get Google autocomplete suggestions."""
        await self._rate_limit()
        page = await self._new_page()
        suggestions: list[str] = []
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded")
            search_input = page.locator('textarea[name="q"], input[name="q"]').first
            await search_input.click()
            await search_input.type(query, delay=80)
            await asyncio.sleep(1.5)

            # Extract suggestions
            suggestion_els = page.locator(
                'ul[role="listbox"] li span, .erkvQe, .G43f7e, .wM6W7d span'
            )
            count = await suggestion_els.count()
            for i in range(min(count, 10)):
                text = (await suggestion_els.nth(i).text_content() or "").strip()
                if text and text.lower() != query.lower():
                    suggestions.append(text)

            logger.info("Autocomplete for %r: %d suggestions", query, len(suggestions))
        except Exception as exc:
            logger.warning("Autocomplete failed for %r: %s", query, exc)
        finally:
            await page.context.close()
        return suggestions

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None

    # ------------------------------------------------------------------
    # Private parsers
    # ------------------------------------------------------------------

    @staticmethod
    async def _parse_organic(page: Page) -> list[dict[str, Any]]:
        """Parse organic search results."""
        results = []
        items = page.locator("#search .g")
        count = await items.count()
        for i in range(min(count, 20)):
            item = items.nth(i)
            try:
                link_el = item.locator("a").first
                href = await link_el.get_attribute("href") or ""
                title_el = item.locator("h3").first
                title = ""
                if await title_el.count():
                    title = (await title_el.text_content() or "").strip()
                snippet_el = item.locator(".VwiC3b, .IsZvec, [data-sncf]").first
                snippet = ""
                if await snippet_el.count():
                    snippet = (await snippet_el.text_content() or "").strip()
                if href and title:
                    results.append({
                        "position": i + 1,
                        "title": title,
                        "url": href,
                        "snippet": snippet,
                    })
            except Exception:
                continue
        return results

    @staticmethod
    async def _parse_featured_snippet(page: Page) -> Optional[dict[str, str]]:
        """Parse featured snippet if present."""
        fs = page.locator(".xpdopen, .kp-blk, .g.kno-result").first
        if await fs.count() == 0:
            return None
        try:
            text = (await fs.text_content() or "").strip()[:500]
            return {"text": text} if text else None
        except Exception:
            return None

    @staticmethod
    async def _parse_paa(page: Page) -> list[str]:
        """Parse People Also Ask questions."""
        questions = []
        paa_items = page.locator('[data-q], .related-question-pair, div.xpc span')
        count = await paa_items.count()
        for i in range(min(count, 10)):
            text = (await paa_items.nth(i).text_content() or "").strip()
            if text and "?" in text:
                questions.append(text)
        return questions

    @staticmethod
    async def _parse_related(page: Page) -> list[str]:
        """Parse related searches."""
        related = []
        items = page.locator('#botstuff .card-section a, a.k8XOCe, .brs_col a')
        count = await items.count()
        for i in range(min(count, 8)):
            text = (await items.nth(i).text_content() or "").strip()
            if text:
                related.append(text)
        return related
