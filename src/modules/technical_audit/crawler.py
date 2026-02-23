"""Site crawler for technical SEO auditing.

Provides async crawling, robots/sitemap parsing, broken-link detection,
redirect-chain analysis, page-speed integration, mobile-friendliness,
security checks, and duplicate-content detection.
"""

import asyncio
import hashlib
import logging
import re
import ssl
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "img": "http://www.google.com/schemas/sitemap-image/1.1",
}


def _normalise_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _same_domain(url: str, domain: str) -> bool:
    try:
        return urlparse(url).netloc.lower().replace("www.", "") == domain.lower().replace("www.", "")
    except Exception:
        return False


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ---------------------------------------------------------------------------
# SiteCrawler
# ---------------------------------------------------------------------------

class SiteCrawler:
    """Async site crawler that gathers technical SEO data."""

    def __init__(
        self,
        max_pages: int = 100,
        max_depth: int = 5,
        respect_robots: bool = True,
        concurrency: int = 5,
        request_timeout: int = 20,
        user_agent: str = "SEOAutomationBot/1.0",
    ) -> None:
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.respect_robots = respect_robots
        self._semaphore = asyncio.Semaphore(concurrency)
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._user_agent = user_agent

        # Internal state reset per crawl
        self._visited: set[str] = set()
        self._disallowed: list[str] = []
        self._pages: list[dict[str, Any]] = []
        self._domain: str = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def crawl_site(self, url: str) -> dict[str, Any]:
        """Crawl *url* and return a comprehensive crawl report."""
        self._visited = set()
        self._pages = []
        self._domain = _extract_domain(url)
        base = _base_url(url)

        robots_data: dict[str, Any] = {}
        if self.respect_robots:
            robots_data = await self.check_robots_txt(self._domain)
            self._disallowed = robots_data.get("disallowed_paths", [])

        sitemap_data = await self.check_sitemap(self._domain)

        start = time.monotonic()
        await self._crawl_page(url, depth=0)
        elapsed = round(time.monotonic() - start, 2)

        crawl_stats = {
            "pages_crawled": len(self._pages),
            "elapsed_seconds": elapsed,
            "domain": self._domain,
            "base_url": base,
            "start_url": url,
        }
        logger.info(
            "Crawl complete: %d pages in %.1fs",
            crawl_stats["pages_crawled"],
            elapsed,
        )
        return {
            "pages": self._pages,
            "crawl_stats": crawl_stats,
            "sitemap_data": sitemap_data,
            "robots_data": robots_data,
        }

    # ------------------------------------------------------------------
    # Recursive page crawler
    # ------------------------------------------------------------------

    async def _crawl_page(self, url: str, depth: int) -> None:
        norm = _normalise_url(url)
        if norm in self._visited or len(self._visited) >= self.max_pages:
            return
        if depth > self.max_depth:
            return
        if self._is_disallowed(url):
            logger.debug("Skipping disallowed URL: %s", url)
            return

        self._visited.add(norm)

        page_data = await self._fetch_page(url)
        if page_data is None:
            return

        self._pages.append(page_data)
        logger.info(
            "[%d/%d] Crawled %s (status=%s depth=%d)",
            len(self._pages), self.max_pages, url,
            page_data.get("status_code"), depth,
        )

        # Follow internal links
        tasks: list[asyncio.Task] = []
        for link in page_data.get("internal_links", []):
            if len(self._visited) >= self.max_pages:
                break
            href = link.get("url", "")
            if _normalise_url(href) not in self._visited:
                tasks.append(asyncio.create_task(self._crawl_page(href, depth + 1)))

        if tasks:
            await asyncio.gather(*tasks)

    async def _fetch_page(self, url: str) -> Optional[dict[str, Any]]:
        """Fetch a single page and extract SEO-relevant data."""
        async with self._semaphore:
            try:
                headers = {"User-Agent": self._user_agent}
                t0 = time.monotonic()
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.get(url, headers=headers, ssl=False, allow_redirects=True) as resp:
                        status = resp.status
                        final_url = str(resp.url)
                        content_type = resp.headers.get("Content-Type", "")
                        if "text/html" not in content_type:
                            return {
                                "url": url,
                                "final_url": final_url,
                                "status_code": status,
                                "content_type": content_type,
                                "is_html": False,
                                "load_time": round(time.monotonic() - t0, 3),
                                "internal_links": [],
                                "external_links": [],
                                "images": [],
                            }
                        html = await resp.text(errors="replace")
                load_time = round(time.monotonic() - t0, 3)
            except asyncio.TimeoutError:
                logger.warning("Timeout fetching %s", url)
                return {"url": url, "status_code": 0, "error": "timeout", "internal_links": [], "external_links": [], "images": []}
            except Exception as exc:
                logger.warning("Error fetching %s: %s", url, exc)
                return {"url": url, "status_code": 0, "error": str(exc), "internal_links": [], "external_links": [], "images": []}

        return self._parse_html(url, final_url, status, html, load_time)

    def _parse_html(self, url: str, final_url: str, status: int, html: str, load_time: float) -> dict[str, Any]:
        """Extract SEO signals from HTML content."""
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        meta_desc = ""
        md_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if md_tag:
            meta_desc = md_tag.get("content", "") or ""

        h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
        h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")]

        # Word count (visible text)
        text_content = soup.get_text(separator=" ", strip=True)
        word_count = len(text_content.split())

        # Links
        internal_links: list[dict[str, str]] = []
        external_links: list[dict[str, str]] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_href = urljoin(final_url, href)
            link_text = a_tag.get_text(strip=True)[:120]
            if _same_domain(abs_href, self._domain):
                internal_links.append({"url": abs_href, "text": link_text})
            else:
                external_links.append({"url": abs_href, "text": link_text})

        # Images
        images: list[dict[str, str]] = []
        for img in soup.find_all("img"):
            src = img.get("src", "") or img.get("data-src", "")
            if src:
                images.append({
                    "src": urljoin(final_url, src),
                    "alt": img.get("alt", "") or "",
                })

        # Canonical
        canonical_tag = soup.find("link", rel="canonical")
        canonical_url = canonical_tag["href"] if canonical_tag and canonical_tag.get("href") else ""

        # Robots meta
        robots_meta = ""
        rm_tag = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
        if rm_tag:
            robots_meta = rm_tag.get("content", "") or ""

        # Hreflang
        hreflang_tags = []
        for link_tag in soup.find_all("link", rel="alternate"):
            hl = link_tag.get("hreflang")
            if hl:
                hreflang_tags.append({"lang": hl, "href": link_tag.get("href", "")})

        # Structured data
        structured_data_types: list[str] = []
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script_tag.string or "{}")
                if isinstance(data, dict):
                    sd_type = data.get("@type", "")
                    if sd_type:
                        structured_data_types.append(sd_type)
                elif isinstance(data, list):
                    for item in data:
                        sd_type = item.get("@type", "") if isinstance(item, dict) else ""
                        if sd_type:
                            structured_data_types.append(sd_type)
            except Exception:
                pass

        return {
            "url": url,
            "final_url": final_url,
            "status_code": status,
            "is_html": True,
            "title": title,
            "meta_description": meta_desc,
            "h1_tags": h1_tags,
            "h2_tags": h2_tags,
            "word_count": word_count,
            "internal_links": internal_links,
            "external_links": external_links,
            "images": images,
            "load_time": load_time,
            "canonical_url": canonical_url,
            "robots_meta": robots_meta,
            "hreflang": hreflang_tags,
            "structured_data_types": structured_data_types,
        }

    def _is_disallowed(self, url: str) -> bool:
        """Check if *url* path is blocked by robots.txt."""
        if not self._disallowed:
            return False
        path = urlparse(url).path
        for pattern in self._disallowed:
            if path.startswith(pattern):
                return True
        return False

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    async def check_robots_txt(self, domain: str) -> dict[str, Any]:
        """Fetch and parse robots.txt for *domain*."""
        url = f"https://{domain}/robots.txt"
        result: dict[str, Any] = {
            "url": url,
            "exists": False,
            "allowed_paths": [],
            "disallowed_paths": [],
            "sitemaps": [],
            "crawl_delay": None,
            "raw": "",
        }
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(url, headers={"User-Agent": self._user_agent}, ssl=False) as resp:
                    if resp.status != 200:
                        logger.info("robots.txt not found at %s (status %d)", url, resp.status)
                        return result
                    text = await resp.text(errors="replace")
        except Exception as exc:
            logger.warning("Error fetching robots.txt: %s", exc)
            return result

        result["exists"] = True
        result["raw"] = text

        current_agent = None
        for raw_line in text.splitlines():
            line = raw_line.split("#")[0].strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("user-agent:"):
                agent_val = line.split(":", 1)[1].strip()
                current_agent = agent_val
            elif lower.startswith("disallow:") and current_agent in ("*", self._user_agent, None):
                path = line.split(":", 1)[1].strip()
                if path:
                    result["disallowed_paths"].append(path)
            elif lower.startswith("allow:") and current_agent in ("*", self._user_agent, None):
                path = line.split(":", 1)[1].strip()
                if path:
                    result["allowed_paths"].append(path)
            elif lower.startswith("sitemap:"):
                sm_url = line.split(":", 1)[1].strip()
                # Rejoin in case of http:// split
                if sm_url and not sm_url.startswith("http"):
                    sm_url = "https:" + sm_url
                else:
                    sm_url = line[len("Sitemap:"):].strip()
                if sm_url:
                    result["sitemaps"].append(sm_url)
            elif lower.startswith("crawl-delay:"):
                try:
                    result["crawl_delay"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

        logger.info(
            "robots.txt: %d disallowed, %d sitemaps",
            len(result["disallowed_paths"]),
            len(result["sitemaps"]),
        )
        return result

    # ------------------------------------------------------------------
    # Sitemap
    # ------------------------------------------------------------------

    async def check_sitemap(self, domain: str) -> dict[str, Any]:
        """Fetch and parse XML sitemap(s) for *domain*."""
        result: dict[str, Any] = {
            "found": False,
            "total_urls": 0,
            "urls": [],
            "sitemaps": [],
            "errors": [],
        }

        sitemap_urls_to_try = [
            f"https://{domain}/sitemap.xml",
            f"https://{domain}/sitemap_index.xml",
        ]

        for sm_url in sitemap_urls_to_try:
            await self._parse_sitemap(sm_url, result)

        if result["total_urls"] > 0:
            result["found"] = True

        logger.info("Sitemap: %d URLs found across %d sitemaps", result["total_urls"], len(result["sitemaps"]))
        return result

    async def _parse_sitemap(self, url: str, result: dict[str, Any], depth: int = 0) -> None:
        """Recursively parse a sitemap or sitemap index."""
        if depth > 3:
            return
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(url, headers={"User-Agent": self._user_agent}, ssl=False) as resp:
                    if resp.status != 200:
                        return
                    xml_text = await resp.text(errors="replace")
        except Exception as exc:
            result["errors"].append(f"Error fetching {url}: {exc}")
            return

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            result["errors"].append(f"XML parse error for {url}: {exc}")
            return

        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if tag == "sitemapindex":
            result["sitemaps"].append(url)
            for sm_el in root.findall("sm:sitemap/sm:loc", _SITEMAP_NS):
                child_url = (sm_el.text or "").strip()
                if child_url:
                    await self._parse_sitemap(child_url, result, depth + 1)
            # Also try without namespace
            for sm_el in root.iter():
                local = sm_el.tag.split("}")[-1] if "}" in sm_el.tag else sm_el.tag
                if local == "loc" and sm_el.text:
                    loc = sm_el.text.strip()
                    if loc.endswith(".xml"):
                        await self._parse_sitemap(loc, result, depth + 1)
        else:
            result["sitemaps"].append(url)
            for url_el in root.iter():
                local = url_el.tag.split("}")[-1] if "}" in url_el.tag else url_el.tag
                if local == "url":
                    entry: dict[str, Any] = {}
                    for child in url_el:
                        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if child_tag == "loc":
                            entry["loc"] = (child.text or "").strip()
                        elif child_tag == "lastmod":
                            entry["lastmod"] = (child.text or "").strip()
                        elif child_tag == "changefreq":
                            entry["changefreq"] = (child.text or "").strip()
                        elif child_tag == "priority":
                            entry["priority"] = (child.text or "").strip()
                    if entry.get("loc"):
                        result["urls"].append(entry)
                        result["total_urls"] += 1

    # ------------------------------------------------------------------
    # Broken links
    # ------------------------------------------------------------------

    async def find_broken_links(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check all discovered links for 4xx/5xx responses."""
        all_links: list[tuple[str, str, str]] = []  # (source, href, text)
        seen_hrefs: set[str] = set()

        for page in pages:
            source = page.get("url", "")
            for link in page.get("internal_links", []):
                href = link.get("url", "")
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    all_links.append((source, href, link.get("text", "")))
            for link in page.get("external_links", []):
                href = link.get("url", "")
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    all_links.append((source, href, link.get("text", "")))

        logger.info("Checking %d unique links for broken responses", len(all_links))
        broken: list[dict[str, Any]] = []

        async def _check(source: str, href: str, text: str) -> Optional[dict[str, Any]]:
            async with self._semaphore:
                try:
                    async with aiohttp.ClientSession(timeout=self._timeout) as session:
                        async with session.head(href, headers={"User-Agent": self._user_agent}, ssl=False, allow_redirects=True) as resp:
                            if resp.status >= 400:
                                return {"source_page": source, "broken_url": href, "status_code": resp.status, "link_text": text}
                except Exception as exc:
                    return {"source_page": source, "broken_url": href, "status_code": 0, "link_text": text, "error": str(exc)}
            return None

        tasks = [_check(s, h, t) for s, h, t in all_links]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                broken.append(r)

        logger.info("Found %d broken links", len(broken))
        return broken

    # ------------------------------------------------------------------
    # Redirects
    # ------------------------------------------------------------------

    async def check_redirects(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identify redirect chains, types (301/302), and loops."""
        redirect_issues: list[dict[str, Any]] = []
        checked: set[str] = set()

        all_urls: set[str] = set()
        for page in pages:
            for link in page.get("internal_links", []):
                href = link.get("url", "")
                if href:
                    all_urls.add(href)

        async def _trace(url: str) -> Optional[dict[str, Any]]:
            if url in checked:
                return None
            checked.add(url)
            chain: list[dict[str, Any]] = []
            current = url
            seen_in_chain: set[str] = set()
            is_loop = False
            async with self._semaphore:
                try:
                    async with aiohttp.ClientSession(
                        timeout=self._timeout,
                    ) as session:
                        for _ in range(10):  # max hops
                            if current in seen_in_chain:
                                is_loop = True
                                break
                            seen_in_chain.add(current)
                            async with session.get(
                                current,
                                headers={"User-Agent": self._user_agent},
                                ssl=False,
                                allow_redirects=False,
                            ) as resp:
                                status = resp.status
                                if status in (301, 302, 303, 307, 308):
                                    location = resp.headers.get("Location", "")
                                    next_url = urljoin(current, location)
                                    chain.append({"url": current, "status": status, "redirects_to": next_url})
                                    current = next_url
                                else:
                                    break
                except Exception as exc:
                    chain.append({"url": current, "status": 0, "error": str(exc)})

            if len(chain) > 0:
                return {
                    "original_url": url,
                    "chain": chain,
                    "chain_length": len(chain),
                    "is_loop": is_loop,
                    "final_url": current,
                    "redirect_type": chain[0].get("status") if chain else None,
                }
            return None

        tasks = [_trace(u) for u in all_urls]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                redirect_issues.append(r)

        logger.info("Found %d redirect chains", len(redirect_issues))
        return redirect_issues

    # ------------------------------------------------------------------
    # Page Speed (via PageSpeedInsights integration)
    # ------------------------------------------------------------------

    async def analyze_page_speed(self, url: str) -> dict[str, Any]:
        """Get Core Web Vitals using Google PageSpeed Insights API."""
        try:
            from src.integrations.google_pagespeed import PageSpeedInsights
            psi = PageSpeedInsights()

            mobile = await psi.analyze_url(url, strategy="mobile", categories=["performance"])
            desktop = await psi.analyze_url(url, strategy="desktop", categories=["performance"])

            mobile_metrics = mobile.get("metrics", {})
            desktop_metrics = desktop.get("metrics", {})

            return {
                "url": url,
                "mobile": {
                    "performance_score": mobile.get("performance_score", 0),
                    "lcp": mobile_metrics.get("largest-contentful-paint"),
                    "inp": mobile_metrics.get("interaction-to-next-paint"),
                    "cls": mobile_metrics.get("cumulative-layout-shift"),
                    "ttfb": mobile_metrics.get("server-response-time"),
                    "fcp": mobile_metrics.get("first-contentful-paint"),
                    "speed_index": mobile_metrics.get("speed-index"),
                },
                "desktop": {
                    "performance_score": desktop.get("performance_score", 0),
                    "lcp": desktop_metrics.get("largest-contentful-paint"),
                    "inp": desktop_metrics.get("interaction-to-next-paint"),
                    "cls": desktop_metrics.get("cumulative-layout-shift"),
                    "ttfb": desktop_metrics.get("server-response-time"),
                    "fcp": desktop_metrics.get("first-contentful-paint"),
                    "speed_index": desktop_metrics.get("speed-index"),
                },
                "opportunities": mobile.get("opportunities", []),
            }
        except Exception as exc:
            logger.error("PageSpeed analysis failed for %s: %s", url, exc)
            return {"url": url, "error": str(exc), "mobile": {}, "desktop": {}}

    # ------------------------------------------------------------------
    # Mobile friendliness
    # ------------------------------------------------------------------

    async def check_mobile_friendly(self, url: str) -> dict[str, Any]:
        """Heuristic mobile-friendliness check on the HTML."""
        result: dict[str, Any] = {
            "url": url,
            "is_mobile_friendly": True,
            "issues": [],
            "viewport_set": False,
            "text_size_ok": True,
            "tap_targets_ok": True,
            "content_width_ok": True,
        }
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(url, headers={"User-Agent": self._user_agent}, ssl=False) as resp:
                    if resp.status != 200:
                        result["issues"].append(f"Page returned status {resp.status}")
                        result["is_mobile_friendly"] = False
                        return result
                    html = await resp.text(errors="replace")
        except Exception as exc:
            result["issues"].append(f"Fetch error: {exc}")
            result["is_mobile_friendly"] = False
            return result

        soup = BeautifulSoup(html, "html.parser")

        # Viewport meta
        vp = soup.find("meta", attrs={"name": "viewport"})
        if vp:
            content = (vp.get("content") or "").lower()
            result["viewport_set"] = True
            if "width=device-width" not in content:
                result["issues"].append("Viewport does not set width=device-width")
                result["content_width_ok"] = False
        else:
            result["viewport_set"] = False
            result["issues"].append("Missing viewport meta tag")
            result["content_width_ok"] = False

        # Check for very small font sizes in inline styles
        small_text_count = 0
        for el in soup.find_all(style=True):
            style = el.get("style", "")
            match = re.search(r"font-size\s*:\s*(\d+)", style)
            if match and int(match.group(1)) < 12:
                small_text_count += 1
        if small_text_count > 5:
            result["text_size_ok"] = False
            result["issues"].append(f"{small_text_count} elements with font-size < 12px")

        # Check for tiny tap targets (links/buttons with very short text and no padding)
        tiny_targets = 0
        for el in soup.find_all(["a", "button"]):
            text = el.get_text(strip=True)
            if len(text) <= 1 and not el.find("img"):
                tiny_targets += 1
        if tiny_targets > 3:
            result["tap_targets_ok"] = False
            result["issues"].append(f"{tiny_targets} potentially too-small tap targets")

        # Check for fixed-width elements
        fixed_width_count = 0
        for el in soup.find_all(style=True):
            style = el.get("style", "")
            if re.search(r"width\s*:\s*\d{4,}px", style):
                fixed_width_count += 1
        if fixed_width_count > 0:
            result["content_width_ok"] = False
            result["issues"].append(f"{fixed_width_count} elements with very wide fixed widths")

        if result["issues"]:
            result["is_mobile_friendly"] = False

        return result

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    async def check_security(self, domain: str) -> dict[str, Any]:
        """Check SSL, HTTPS enforcement, and security headers."""
        result: dict[str, Any] = {
            "domain": domain,
            "ssl_valid": False,
            "ssl_expiry": None,
            "ssl_issuer": None,
            "https_enforced": False,
            "mixed_content": [],
            "security_headers": {},
            "issues": [],
        }

        # SSL check
        try:
            ctx = ssl.create_default_context()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(domain, 443, ssl=ctx),
                timeout=10,
            )
            ssl_obj = writer.get_extra_info("ssl_object")
            if ssl_obj:
                cert = ssl_obj.getpeercert()
                if cert:
                    result["ssl_valid"] = True
                    not_after = cert.get("notAfter", "")
                    if not_after:
                        result["ssl_expiry"] = not_after
                    issuer = cert.get("issuer", ())
                    for field in issuer:
                        for k, v in field:
                            if k == "organizationName":
                                result["ssl_issuer"] = v
            writer.close()
            await writer.wait_closed()
        except Exception as exc:
            result["issues"].append(f"SSL check failed: {exc}")

        # HTTPS enforcement (check if HTTP redirects to HTTPS)
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(
                    f"http://{domain}",
                    headers={"User-Agent": self._user_agent},
                    ssl=False,
                    allow_redirects=False,
                ) as resp:
                    if resp.status in (301, 302, 307, 308):
                        location = resp.headers.get("Location", "")
                        if location.startswith("https://"):
                            result["https_enforced"] = True
        except Exception:
            pass

        # Security headers
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(
                    f"https://{domain}",
                    headers={"User-Agent": self._user_agent},
                    ssl=False,
                ) as resp:
                    headers = resp.headers
                    check_headers = {
                        "Strict-Transport-Security": "HSTS",
                        "X-Frame-Options": "X-Frame-Options",
                        "Content-Security-Policy": "CSP",
                        "X-Content-Type-Options": "X-Content-Type-Options",
                        "Referrer-Policy": "Referrer-Policy",
                        "Permissions-Policy": "Permissions-Policy",
                    }
                    for header_name, label in check_headers.items():
                        val = headers.get(header_name)
                        result["security_headers"][label] = {
                            "present": val is not None,
                            "value": val or "",
                        }
                        if val is None:
                            result["issues"].append(f"Missing security header: {label}")

                    # Mixed content detection
                    html = await resp.text(errors="replace")
                    soup = BeautifulSoup(html, "html.parser")
                    for tag_name, attr in [("img", "src"), ("script", "src"), ("link", "href")]:
                        for el in soup.find_all(tag_name):
                            val = el.get(attr, "")
                            if val.startswith("http://"):
                                result["mixed_content"].append({"tag": tag_name, "url": val})
        except Exception as exc:
            result["issues"].append(f"Security headers check failed: {exc}")

        return result

    # ------------------------------------------------------------------
    # Duplicate content
    # ------------------------------------------------------------------

    async def check_duplicate_content(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect duplicate/near-duplicate titles, descriptions, and thin pages."""
        issues: list[dict[str, Any]] = []

        # Title duplicates
        title_map: dict[str, list[str]] = defaultdict(list)
        for p in pages:
            title = p.get("title", "").strip()
            if title:
                title_map[title.lower()].append(p.get("url", ""))
        for title, urls in title_map.items():
            if len(urls) > 1:
                issues.append({
                    "type": "duplicate_title",
                    "value": title,
                    "urls": urls,
                    "severity": "warning",
                })

        # Meta description duplicates
        desc_map: dict[str, list[str]] = defaultdict(list)
        for p in pages:
            desc = p.get("meta_description", "").strip()
            if desc:
                desc_map[desc.lower()].append(p.get("url", ""))
        for desc, urls in desc_map.items():
            if len(urls) > 1:
                issues.append({
                    "type": "duplicate_description",
                    "value": desc[:100],
                    "urls": urls,
                    "severity": "warning",
                })

        # Thin content (< 300 words)
        for p in pages:
            wc = p.get("word_count", 0)
            if p.get("is_html", True) and wc < 300 and p.get("status_code") == 200:
                issues.append({
                    "type": "thin_content",
                    "url": p.get("url", ""),
                    "word_count": wc,
                    "severity": "info" if wc >= 100 else "warning",
                })

        # Missing titles
        for p in pages:
            if p.get("is_html", True) and p.get("status_code") == 200:
                if not p.get("title", "").strip():
                    issues.append({
                        "type": "missing_title",
                        "url": p.get("url", ""),
                        "severity": "error",
                    })
                if not p.get("meta_description", "").strip():
                    issues.append({
                        "type": "missing_description",
                        "url": p.get("url", ""),
                        "severity": "warning",
                    })
                if not p.get("h1_tags"):
                    issues.append({
                        "type": "missing_h1",
                        "url": p.get("url", ""),
                        "severity": "warning",
                    })
                if len(p.get("h1_tags", [])) > 1:
                    issues.append({
                        "type": "multiple_h1",
                        "url": p.get("url", ""),
                        "count": len(p["h1_tags"]),
                        "severity": "info",
                    })

        # Images missing alt
        for p in pages:
            no_alt = [img for img in p.get("images", []) if not img.get("alt", "").strip()]
            if no_alt:
                issues.append({
                    "type": "images_missing_alt",
                    "url": p.get("url", ""),
                    "count": len(no_alt),
                    "severity": "warning",
                })

        logger.info("Duplicate/content issues found: %d", len(issues))
        return issues
