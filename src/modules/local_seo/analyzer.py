"""Local SEO Analyzer - Core orchestration module.

This module provides comprehensive Local SEO analysis by coordinating
multiple sub-analyzers: on-page crawling, Google Business Profile signals,
citation consistency, local content quality, backlinks, reviews, and
competitor map-pack analysis. Results are scored, stored in the database,
and augmented with AI-generated prioritised recommendations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from sqlalchemy import select

from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper
from src.modules.local_seo.citation_checker import CitationChecker
from src.modules.local_seo.gmb_analyzer import GMBAnalyzer
from src.database import get_session
from src.models.local_seo import (
    LocalBusinessProfile,
    LocalSEOAudit,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_TIMEOUT = 15_000  # ms for Playwright navigations
_MAX_CRAWL_PAGES = 20  # cap pages crawled per site
_WEIGHT_MAP: dict[str, float] = {
    "onpage_score": 0.25,
    "gmb_score": 0.25,
    "citation_score": 0.15,
    "review_score": 0.15,
    "content_score": 0.10,
    "backlink_score": 0.10,
}


def _safe_score(value: Any, default: float = 0.0) -> float:
    """Coerce *value* to a float score in [0, 100]."""
    try:
        v = float(value)
        return max(0.0, min(100.0, v))
    except (TypeError, ValueError):
        return default


def _normalise_url(base: str, href: str) -> str:
    """Return an absolute URL given a *base* and a potentially relative *href*."""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)


class LocalSEOAnalyzer:
    """Orchestrates a full Local SEO audit for a single business."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialise the analyser and its sub-components.

        Args:
            llm_client: Optional pre-configured LLMClient. A fresh instance
                        is created when *None*.
        """
        self.llm_client = llm_client or LLMClient()
        self.serp_scraper = SERPScraper()
        self.citation_checker = CitationChecker()
        self.gmb_analyzer = GMBAnalyzer()
        logger.info("LocalSEOAnalyzer initialised.")

    # ------------------------------------------------------------------
    # 1. Main orchestrator
    # ------------------------------------------------------------------
    async def analyze_business(
        self,
        domain: str,
        business_name: str,
        location: str,
        target_keywords: list[str] | None = None,
    ) -> dict:
        """Run every analysis sub-routine and return a unified report.

        Args:
            domain: The business website domain (e.g. ``example.com``).
            business_name: Official business name.
            location: City / region string used for local queries.
            target_keywords: Optional seed keywords; auto-generated when absent.

        Returns:
            A comprehensive dict containing scores, issues, checks, and
            AI-generated recommendations.
        """
        logger.info(
            "Starting full Local SEO analysis for %s (%s) in %s",
            business_name, domain, location,
        )
        start_ts = time.monotonic()

        # Ensure domain has scheme
        base_url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"

        # Derive keywords when not provided
        if not target_keywords:
            target_keywords = [f"{business_name} {location}"]

        # -- Run analyses concurrently where possible ----------------------
        onpage_task = asyncio.create_task(
            self._analyze_onpage_local_seo(base_url)
        )
        gbp_task = asyncio.create_task(
            self._analyze_gbp_signals(business_name, location)
        )
        citation_task = asyncio.create_task(
            self._analyze_citations(business_name, location)
        )
        content_task = asyncio.create_task(
            self._analyze_local_content(base_url, location)
        )
        backlink_task = asyncio.create_task(
            self._analyze_local_backlinks(base_url, location)
        )
        reviews_task = asyncio.create_task(
            self._analyze_reviews(business_name, location)
        )

        # Gather, tolerating individual failures
        results_raw = await asyncio.gather(
            onpage_task, gbp_task, citation_task,
            content_task, backlink_task, reviews_task,
            return_exceptions=True,
        )

        labels = [
            "onpage", "gbp", "citations",
            "content", "backlinks", "reviews",
        ]
        all_results: dict[str, dict] = {}
        for label, res in zip(labels, results_raw):
            if isinstance(res, BaseException):
                logger.error("Analysis '%s' failed: %s", label, res, exc_info=res)
                all_results[label] = {"score": 0, "checks": [], "issues": [], "error": str(res)}
            else:
                all_results[label] = res

        # Competitor map-pack (sequential — depends on keywords)
        try:
            primary_kw = target_keywords[0] if target_keywords else business_name
            all_results["competitors"] = await self._analyze_competitors_map_pack(
                primary_kw, location,
            )
        except Exception as exc:
            logger.error("Competitor map-pack analysis failed: %s", exc, exc_info=True)
            all_results["competitors"] = {"score": 0, "checks": [], "issues": [], "error": str(exc)}

        # -- Scoring -------------------------------------------------------
        scores = self._calculate_scores(all_results)

        # -- Collect top issues across all modules -------------------------
        top_issues: list[dict] = []
        for label, data in all_results.items():
            for issue in data.get("issues", []):
                top_issues.append({"module": label, **issue} if isinstance(issue, dict) else {"module": label, "description": str(issue)})
        top_issues.sort(key=lambda i: i.get("severity", 50), reverse=True)

        # -- AI recommendations --------------------------------------------
        try:
            recommendations = await self._generate_prioritized_recommendations(all_results)
        except Exception as exc:
            logger.error("Recommendation generation failed: %s", exc, exc_info=True)
            recommendations = []

        # -- Persist --------------------------------------------------------
        try:
            audit_id = await self._save_audit_to_db(
                business_name=business_name,
                domain=domain,
                location=location,
                scores=scores,
                issues=top_issues,
                recommendations=recommendations,
            )
        except Exception as exc:
            logger.error("DB save failed: %s", exc, exc_info=True)
            audit_id = None

        elapsed = round(time.monotonic() - start_ts, 2)
        logger.info("Local SEO analysis completed in %.2fs (audit id=%s)", elapsed, audit_id)

        return {
            "business_name": business_name,
            "domain": domain,
            "location": location,
            "target_keywords": target_keywords,
            "scores": scores,
            "top_issues": top_issues[:25],
            "recommendations": recommendations,
            "details": all_results,
            "audit_id": audit_id,
            "analysis_duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # 2. On-page local SEO (Playwright crawl)
    # ------------------------------------------------------------------
    async def _analyze_onpage_local_seo(self, base_url: str) -> dict:
        """Crawl the business website and evaluate on-page local SEO signals.

        Checks performed:
        - NAP consistency in footer/contact
        - JSON-LD LocalBusiness / Organization schema
        - Location keywords in title, meta description, H1, H2
        - Embedded Google Map
        - Mobile responsiveness (viewport meta)
        - SSL / HTTPS
        - Click-to-call tel: links
        - Contact page existence & optimisation
        - About page local trust signals
        - Service area pages
        - Local images with geo-relevant alt text
        - Internal linking to location pages
        - Basic page speed (load time)

        Returns:
            dict with ``checks`` list, ``score``, and ``issues``.
        """
        checks: list[dict] = []
        issues: list[dict] = []
        pages_html: dict[str, str] = {}  # url -> html
        page_load_times: dict[str, float] = {}

        parsed = urlparse(base_url)
        domain_root = parsed.netloc or parsed.path

        # -- Helper: add a check -------------------------------------------
        def _add(name: str, status: str, details: str, category: str, weight: float = 1.0) -> None:
            checks.append({
                "name": name,
                "status": status,  # pass / fail / warning
                "details": details,
                "category": category,
                "weight": weight,
            })
            if status in ("fail", "warning"):
                issues.append({"description": f"{name}: {details}", "severity": weight * 100})

        try:
            async with async_playwright() as pw:
                browser: Browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )

                try:
                    # -- Crawl key pages -----------------------------------
                    target_paths = [
                        "/", "/contact", "/contact-us", "/about",
                        "/about-us", "/services", "/locations",
                        "/areas-we-serve", "/service-areas",
                        "/testimonials", "/reviews", "/faq",
                    ]
                    for path in target_paths:
                        url = urljoin(base_url, path)
                        try:
                            page: Page = await context.new_page()
                            t0 = time.monotonic()
                            resp = await page.goto(url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT)
                            load_time = round(time.monotonic() - t0, 2)
                            if resp and resp.ok:
                                html = await page.content()
                                pages_html[url] = html
                                page_load_times[url] = load_time
                            await page.close()
                        except (PlaywrightTimeout, Exception) as exc:
                            logger.debug("Could not load %s: %s", url, exc)
                            try:
                                await page.close()
                            except Exception:
                                pass

                    # Discover additional internal links from homepage
                    homepage_html = pages_html.get(base_url) or pages_html.get(base_url + "/", "")
                    if homepage_html:
                        internal_links = re.findall(r'''href=["']([^"']+)["']''', homepage_html)
                        for href in internal_links[:50]:
                            abs_url = _normalise_url(base_url, href)
                            if domain_root in abs_url and abs_url not in pages_html and len(pages_html) < _MAX_CRAWL_PAGES:
                                try:
                                    page = await context.new_page()
                                    t0 = time.monotonic()
                                    resp = await page.goto(abs_url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT)
                                    load_time = round(time.monotonic() - t0, 2)
                                    if resp and resp.ok:
                                        pages_html[abs_url] = await page.content()
                                        page_load_times[abs_url] = load_time
                                    await page.close()
                                except Exception:
                                    try:
                                        await page.close()
                                    except Exception:
                                        pass
                finally:
                    await context.close()
                    await browser.close()

        except Exception as exc:
            logger.error("Playwright crawl failed: %s", exc, exc_info=True)
            _add("Website Crawl", "fail", f"Could not crawl website: {exc}", "technical", 1.0)
            return {"checks": checks, "score": 0, "issues": issues}

        if not pages_html:
            _add("Website Crawl", "fail", "No pages could be loaded from the website.", "technical", 1.0)
            return {"checks": checks, "score": 0, "issues": issues}

        # Combine all HTML for broad checks
        all_html = "\n".join(pages_html.values())
        homepage_html = pages_html.get(base_url) or pages_html.get(base_url + "/", "")
        all_urls_lower = [u.lower() for u in pages_html.keys()]

        # ---- Check: SSL / HTTPS ------------------------------------------
        if base_url.startswith("https://"):
            _add("HTTPS / SSL", "pass", "Site is served over HTTPS.", "technical", 0.8)
        else:
            _add("HTTPS / SSL", "fail", "Site is NOT served over HTTPS.", "technical", 0.8)

        # ---- Check: Viewport meta (mobile) -------------------------------
        viewport_pattern = re.compile(r'''<meta[^>]+name=["']viewport["']''', re.I)
        if viewport_pattern.search(homepage_html):
            _add("Mobile Viewport Meta", "pass", "Viewport meta tag found on homepage.", "technical", 0.7)
        else:
            _add("Mobile Viewport Meta", "fail", "No viewport meta tag — poor mobile experience.", "technical", 0.7)

        # ---- Check: Page Speed (basic) -----------------------------------
        home_load = page_load_times.get(base_url) or page_load_times.get(base_url + "/")
        if home_load is not None:
            if home_load < 2.0:
                _add("Page Load Time", "pass", f"Homepage loaded in {home_load}s (good).", "technical", 0.6)
            elif home_load < 4.0:
                _add("Page Load Time", "warning", f"Homepage loaded in {home_load}s (could be faster).", "technical", 0.6)
            else:
                _add("Page Load Time", "fail", f"Homepage loaded in {home_load}s (slow).", "technical", 0.6)
        else:
            _add("Page Load Time", "warning", "Could not measure homepage load time.", "technical", 0.6)

        # ---- Check: NAP in footer / contact page -------------------------
        phone_pattern = re.compile(r'''(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})''')
        address_pattern = re.compile(r'''\d{1,5}\s+\w+.*(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Cir)\b''', re.I)

        contact_pages = {u: h for u, h in pages_html.items() if "contact" in u.lower()}
        nap_html = "\n".join(contact_pages.values()) if contact_pages else homepage_html

        found_phone = bool(phone_pattern.search(nap_html))
        found_address = bool(address_pattern.search(nap_html))

        if found_phone and found_address:
            _add("NAP on Contact/Footer", "pass", "Phone and address found on contact page / footer.", "onpage", 1.0)
        elif found_phone or found_address:
            _add("NAP on Contact/Footer", "warning", "Only partial NAP found (phone or address missing).", "onpage", 1.0)
        else:
            _add("NAP on Contact/Footer", "fail", "No phone or address detected on contact page / footer.", "onpage", 1.0)

        # ---- Check: JSON-LD LocalBusiness / Organization Schema ----------
        jsonld_pattern = re.compile(r'''<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>''', re.S | re.I)
        jsonld_blocks = jsonld_pattern.findall(all_html)
        local_schema_found = False
        for block in jsonld_blocks:
            try:
                data = json.loads(block)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    t = str(item.get("@type", "")).lower()
                    if any(kw in t for kw in ("localbusiness", "organization", "store", "restaurant", "professional")):
                        local_schema_found = True
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

        if local_schema_found:
            _add("Local Schema Markup", "pass", "LocalBusiness/Organization JSON-LD schema found.", "onpage", 1.0)
        else:
            _add("Local Schema Markup", "fail", "No LocalBusiness / Organization schema markup detected.", "onpage", 1.0)

        # ---- Check: Location keywords in title/meta/h1/h2 ----------------
        # Extract location tokens (city, state)
        loc_tokens = [t.strip().lower() for t in re.split(r'''[,\s]+''', domain_root.replace("www.", ""))] + \
                     [t.strip().lower() for t in re.split(r'''[,\s]+''', base_url.split("//")[-1].split("/")[0])]
        # Better: use the fact we don\'t know location here; we rely on caller
        # We\'ll check if any reasonable geo term appears
        title_match = re.findall(r'''<title[^>]*>(.*?)</title>''', homepage_html, re.I | re.S)
        meta_desc_match = re.findall(r'''<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)''', homepage_html, re.I)
        h1_match = re.findall(r'''<h1[^>]*>(.*?)</h1>''', homepage_html, re.I | re.S)
        h2_match = re.findall(r'''<h2[^>]*>(.*?)</h2>''', homepage_html, re.I | re.S)

        combined_header_text = " ".join(
            title_match + meta_desc_match + h1_match + h2_match
        ).lower()
        # A rough heuristic: check for common geo patterns or digits that look like zip
        geo_signals = bool(re.search(r'''\b(\d{5})\b''', combined_header_text)) or \
                      bool(re.search(r'''\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,?\s*[A-Z]{2})\b''', " ".join(title_match + meta_desc_match + h1_match)))

        if geo_signals:
            _add("Location Keywords in Head", "pass", "Location-related keywords found in title/meta/headings.", "onpage", 0.9)
        else:
            _add("Location Keywords in Head", "warning", "No obvious location keywords in title, meta description, or headings.", "onpage", 0.9)

        # ---- Check: Embedded Google Map -----------------------------------
        map_pattern = re.compile(r'''(maps\.google\.com|google\.com/maps|maps\.googleapis\.com)''', re.I)
        map_iframe = re.compile(r'''<iframe[^>]+(google\.com/maps|maps\.google)''', re.I)
        if map_pattern.search(all_html) or map_iframe.search(all_html):
            _add("Embedded Google Map", "pass", "Google Map embed detected.", "onpage", 0.7)
        else:
            _add("Embedded Google Map", "fail", "No Google Map embed found on the site.", "onpage", 0.7)

        # ---- Check: Click-to-call tel: links ------------------------------
        tel_links = re.findall(r'''href=["']tel:[^"']+["']''', all_html, re.I)
        if tel_links:
            _add("Click-to-Call Links", "pass", f"{len(tel_links)} tel: link(s) found.", "onpage", 0.8)
        else:
            _add("Click-to-Call Links", "fail", "No click-to-call (tel:) links found.", "onpage", 0.8)

        # ---- Check: Contact page existence --------------------------------
        contact_exists = any("contact" in u.lower() for u in pages_html)
        if contact_exists:
            _add("Contact Page", "pass", "Dedicated contact page found.", "onpage", 0.8)
        else:
            _add("Contact Page", "fail", "No dedicated contact page detected.", "onpage", 0.8)

        # ---- Check: About page with local trust signals -------------------
        about_pages = {u: h for u, h in pages_html.items() if "about" in u.lower()}
        if about_pages:
            about_text = " ".join(about_pages.values()).lower()
            trust_words = ["years", "community", "local", "family", "founded", "established", "serving"]
            trust_count = sum(1 for w in trust_words if w in about_text)
            if trust_count >= 3:
                _add("About Page Trust Signals", "pass", f"About page has {trust_count} local trust signals.", "onpage", 0.6)
            elif trust_count >= 1:
                _add("About Page Trust Signals", "warning", f"About page has only {trust_count} local trust signal(s).", "onpage", 0.6)
            else:
                _add("About Page Trust Signals", "warning", "About page lacks local trust language.", "onpage", 0.6)
        else:
            _add("About Page Trust Signals", "fail", "No about page found.", "onpage", 0.6)

        # ---- Check: Service area / location pages -------------------------
        area_keywords = ["service-area", "areas-we-serve", "locations", "service-region", "coverage"]
        area_pages = [u for u in pages_html if any(kw in u.lower() for kw in area_keywords)]
        if area_pages:
            _add("Service Area Pages", "pass", f"{len(area_pages)} service-area / location page(s) found.", "onpage", 0.7)
        else:
            _add("Service Area Pages", "warning", "No dedicated service-area or location pages detected.", "onpage", 0.7)

        # ---- Check: Local images with geo alt text ------------------------
        img_alts = re.findall(r'''<img[^>]+alt=["']([^"']+)["']''', all_html, re.I)
        geo_alt_count = sum(
            1 for alt in img_alts if re.search(r'''\b(\d{5}|city|town|local|area|region)\b''', alt, re.I)
        )
        if geo_alt_count >= 3:
            _add("Local Image Alt Text", "pass", f"{geo_alt_count} images with geo-relevant alt text.", "onpage", 0.5)
        elif geo_alt_count >= 1:
            _add("Local Image Alt Text", "warning", f"Only {geo_alt_count} image(s) with geo-relevant alt text.", "onpage", 0.5)
        else:
            _add("Local Image Alt Text", "fail", "No images with geo-relevant alt text found.", "onpage", 0.5)

        # ---- Check: Internal links to location pages ----------------------
        internal_location_links = 0
        for html in pages_html.values():
            links = re.findall(r'''href=["']([^"']+)["']''', html, re.I)
            for lnk in links:
                lnk_lower = lnk.lower()
                if domain_root in lnk_lower or lnk.startswith("/"):
                    if any(kw in lnk_lower for kw in area_keywords + ["location", "near-me"]):
                        internal_location_links += 1

        if internal_location_links >= 5:
            _add("Internal Linking to Locations", "pass", f"{internal_location_links} internal links to location content.", "onpage", 0.6)
        elif internal_location_links >= 1:
            _add("Internal Linking to Locations", "warning", f"Only {internal_location_links} internal link(s) to location content.", "onpage", 0.6)
        else:
            _add("Internal Linking to Locations", "fail", "No internal links pointing to location pages.", "onpage", 0.6)

        # ---- Compute score -----------------------------------------------
        total_weight = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / total_weight) * 100, 1)

        logger.info("On-page local SEO score: %.1f (crawled %d pages)", score, len(pages_html))
        return {"checks": checks, "score": score, "issues": issues, "pages_crawled": len(pages_html)}

    # ------------------------------------------------------------------
    # 3. GBP signals
    # ------------------------------------------------------------------
    async def _analyze_gbp_signals(self, business_name: str, location: str) -> dict:
        """Evaluate Google Business Profile signals via :class:`GMBAnalyzer`.

        Returns:
            dict with ``checks``, ``score``, ``issues``, and raw GBP data.
        """
        checks: list[dict] = []
        issues: list[dict] = []
        score = 0.0

        try:
            gbp_data = await self.gmb_analyzer.analyze_gbp_listing(
                business_name=business_name,
                location=location,
                known_website=None,
            )
        except Exception as exc:
            logger.error("GMBAnalyzer.analyze_gbp_listing failed: %s", exc, exc_info=True)
            checks.append({"name": "GBP Listing Analysis", "status": "fail", "details": str(exc), "category": "gbp", "weight": 1.0})
            return {"checks": checks, "score": 0, "issues": [{"description": f"GBP analysis error: {exc}", "severity": 100}], "raw": {}}

        # Process the returned data
        if isinstance(gbp_data, dict):
            listing_found = gbp_data.get("found", gbp_data.get("listing_found", False))
            if listing_found:
                checks.append({"name": "GBP Listing Found", "status": "pass", "details": "Google Business Profile listing was found.", "category": "gbp", "weight": 1.0})
            else:
                checks.append({"name": "GBP Listing Found", "status": "fail", "details": "Could not find a Google Business Profile listing.", "category": "gbp", "weight": 1.0})
                issues.append({"description": "No GBP listing found — critical for local SEO.", "severity": 100})

            # Completeness / optimisation score from sub-analyser
            completeness = gbp_data.get("completeness_score", gbp_data.get("score", 0))
            score = _safe_score(completeness)

            # Optimisation checklist
            try:
                checklist = self.gmb_analyzer.generate_gbp_optimization_checklist(gbp_data)
                for item in checklist:
                    status = "pass" if item.get("completed", False) else "fail"
                    checks.append({
                        "name": item.get("name", item.get("task", "GBP Item")),
                        "status": status,
                        "details": item.get("description", item.get("details", "")),
                        "category": "gbp",
                        "weight": 0.7,
                    })
                    if status == "fail":
                        issues.append({"description": item.get("name", "GBP optimisation gap"), "severity": 70})
            except Exception as exc:
                logger.warning("GBP checklist generation error: %s", exc)
        else:
            checks.append({"name": "GBP Data", "status": "warning", "details": "Unexpected GBP data format.", "category": "gbp", "weight": 1.0})

        # Re-calculate score from checks if we have them
        if checks:
            tw = sum(c["weight"] for c in checks) or 1
            earned = sum(c["weight"] for c in checks if c["status"] == "pass")
            partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
            score = round(((earned + partial) / tw) * 100, 1)

        logger.info("GBP signals score: %.1f", score)
        return {"checks": checks, "score": score, "issues": issues, "raw": gbp_data}

    # ------------------------------------------------------------------
    # 4. Citations
    # ------------------------------------------------------------------
    async def _analyze_citations(
        self,
        business_name: str,
        location: str,
        known_phone: str = "",
        known_address: str = "",
    ) -> dict:
        """Analyse NAP citation consistency across major directories.

        Returns:
            dict with ``checks``, ``score``, ``issues``, and ``summary``.
        """
        checks: list[dict] = []
        issues: list[dict] = []

        try:
            citations = await self.citation_checker.check_all_citations(
                business_name=business_name,
                location=location,
                known_phone=known_phone,
                known_address=known_address,
            )
        except Exception as exc:
            logger.error("CitationChecker failed: %s", exc, exc_info=True)
            return {"checks": [{"name": "Citation Check", "status": "fail", "details": str(exc), "category": "citations", "weight": 1.0}], "score": 0, "issues": [{"description": f"Citation analysis error: {exc}", "severity": 80}], "summary": {}}

        # NAP consistency
        try:
            nap_score = self.citation_checker.calculate_nap_consistency(citations)
        except Exception:
            nap_score = 0.0

        try:
            summary = self.citation_checker.generate_citation_summary(citations)
        except Exception:
            summary = {}

        total_citations = len(citations) if citations else 0

        # Citation count check
        if total_citations >= 30:
            checks.append({"name": "Citation Volume", "status": "pass", "details": f"{total_citations} citations found.", "category": "citations", "weight": 0.8})
        elif total_citations >= 15:
            checks.append({"name": "Citation Volume", "status": "warning", "details": f"Only {total_citations} citations — aim for 30+.", "category": "citations", "weight": 0.8})
            issues.append({"description": f"Low citation count ({total_citations}). Build more directory listings.", "severity": 60})
        else:
            checks.append({"name": "Citation Volume", "status": "fail", "details": f"Only {total_citations} citations — well below recommended minimum.", "category": "citations", "weight": 0.8})
            issues.append({"description": f"Very low citation count ({total_citations}).", "severity": 80})

        # NAP consistency check
        nap_pct = round(nap_score * 100, 1) if isinstance(nap_score, (int, float)) else 0
        if nap_pct >= 90:
            checks.append({"name": "NAP Consistency", "status": "pass", "details": f"NAP consistency is {nap_pct}%.", "category": "citations", "weight": 1.0})
        elif nap_pct >= 70:
            checks.append({"name": "NAP Consistency", "status": "warning", "details": f"NAP consistency is {nap_pct}% — some inconsistencies.", "category": "citations", "weight": 1.0})
            issues.append({"description": f"NAP consistency {nap_pct}%. Fix inconsistent listings.", "severity": 70})
        else:
            checks.append({"name": "NAP Consistency", "status": "fail", "details": f"NAP consistency is only {nap_pct}% — major problem.", "category": "citations", "weight": 1.0})
            issues.append({"description": f"Poor NAP consistency ({nap_pct}%). Critical to fix.", "severity": 90})

        # Individual citation platform checks
        for cit in (citations or []):
            platform = cit.get("platform", cit.get("source", "Unknown"))
            consistent = cit.get("nap_consistent", cit.get("consistent", True))
            status = "pass" if consistent else "fail"
            checks.append({"name": f"Citation: {platform}", "status": status, "details": f"NAP {'consistent' if consistent else 'INCONSISTENT'} on {platform}.", "category": "citations", "weight": 0.3})

        tw = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / tw) * 100, 1)

        logger.info("Citation score: %.1f (%d citations, NAP %.1f%%)", score, total_citations, nap_pct)
        return {"checks": checks, "score": score, "issues": issues, "summary": summary, "citation_count": total_citations, "nap_consistency": nap_pct}

    # ------------------------------------------------------------------
    # 5. Local content
    # ------------------------------------------------------------------
    async def _analyze_local_content(self, base_url: str, location: str) -> dict:
        """Evaluate the quality and depth of local content on the website.

        Checks: local landing pages, location-specific blog posts, local
        events/news, FAQ pages, testimonials from local clients, and
        local resource guides.

        Returns:
            dict with ``checks``, ``score``, ``issues``.
        """
        checks: list[dict] = []
        issues: list[dict] = []
        pages_html: dict[str, str] = {}

        parsed = urlparse(base_url)
        domain_root = parsed.netloc or parsed.path
        location_lower = location.lower()
        loc_tokens = [t.strip() for t in re.split(r'''[,\s]+''', location_lower) if len(t.strip()) > 2]

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    # Crawl pages that tend to host local content
                    paths = [
                        "/", "/blog", "/news", "/events",
                        "/faq", "/faqs", "/testimonials", "/reviews",
                        "/resources", "/guides", "/services",
                    ]
                    for path in paths:
                        url = urljoin(base_url, path)
                        try:
                            page = await context.new_page()
                            resp = await page.goto(url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT)
                            if resp and resp.ok:
                                pages_html[url] = await page.content()
                            await page.close()
                        except Exception:
                            try:
                                await page.close()
                            except Exception:
                                pass

                    # Discover blog/resource links from crawled pages
                    for html in list(pages_html.values()):
                        hrefs = re.findall(r'''href=["']([^"']+)["']''', html)
                        for href in hrefs[:60]:
                            abs_url = _normalise_url(base_url, href)
                            if domain_root in abs_url and abs_url not in pages_html and len(pages_html) < _MAX_CRAWL_PAGES:
                                if any(kw in abs_url.lower() for kw in ["blog", "news", "event", "guide", "area", "location", "faq"]):
                                    try:
                                        page = await context.new_page()
                                        resp = await page.goto(abs_url, wait_until="domcontentloaded", timeout=_DEFAULT_TIMEOUT)
                                        if resp and resp.ok:
                                            pages_html[abs_url] = await page.content()
                                        await page.close()
                                    except Exception:
                                        try:
                                            await page.close()
                                        except Exception:
                                            pass
                finally:
                    await context.close()
                    await browser.close()
        except Exception as exc:
            logger.error("Local content crawl failed: %s", exc, exc_info=True)
            return {"checks": [{"name": "Local Content Crawl", "status": "fail", "details": str(exc), "category": "content", "weight": 1.0}], "score": 0, "issues": [{"description": f"Could not crawl for local content: {exc}", "severity": 60}]}

        all_text = " ".join(pages_html.values()).lower()

        # ---- Local landing pages -----------------------------------------
        service_pages = [u for u in pages_html if any(kw in u.lower() for kw in ["service", "area", "location", "near"])]
        if len(service_pages) >= 3:
            checks.append({"name": "Local Landing Pages", "status": "pass", "details": f"{len(service_pages)} local landing / service-area pages found.", "category": "content", "weight": 1.0})
        elif service_pages:
            checks.append({"name": "Local Landing Pages", "status": "warning", "details": f"Only {len(service_pages)} local landing page(s).", "category": "content", "weight": 1.0})
            issues.append({"description": "Few local landing pages — create more for each service area.", "severity": 60})
        else:
            checks.append({"name": "Local Landing Pages", "status": "fail", "details": "No dedicated local landing / service-area pages.", "category": "content", "weight": 1.0})
            issues.append({"description": "Missing local landing pages.", "severity": 70})

        # ---- Location-specific blog posts --------------------------------
        blog_pages = [u for u in pages_html if "blog" in u.lower()]
        local_blog_count = 0
        for bp in blog_pages:
            bp_text = pages_html[bp].lower()
            if any(tok in bp_text for tok in loc_tokens):
                local_blog_count += 1

        if local_blog_count >= 3:
            checks.append({"name": "Local Blog Posts", "status": "pass", "details": f"{local_blog_count} location-relevant blog posts.", "category": "content", "weight": 0.8})
        elif local_blog_count >= 1:
            checks.append({"name": "Local Blog Posts", "status": "warning", "details": f"Only {local_blog_count} local blog post(s).", "category": "content", "weight": 0.8})
            issues.append({"description": "Publish more location-specific blog content.", "severity": 50})
        else:
            checks.append({"name": "Local Blog Posts", "status": "fail", "details": "No location-specific blog posts found.", "category": "content", "weight": 0.8})
            issues.append({"description": "No local blog content.", "severity": 60})

        # ---- Local event / news content ----------------------------------
        event_pages = [u for u in pages_html if any(kw in u.lower() for kw in ["event", "news"])]
        if event_pages:
            checks.append({"name": "Local Events/News", "status": "pass", "details": f"{len(event_pages)} events/news page(s) found.", "category": "content", "weight": 0.5})
        else:
            checks.append({"name": "Local Events/News", "status": "warning", "details": "No local events or news section.", "category": "content", "weight": 0.5})
            issues.append({"description": "Consider adding a local news/events section.", "severity": 30})

        # ---- FAQ pages ---------------------------------------------------
        faq_found = any("faq" in u.lower() for u in pages_html) or "frequently asked" in all_text
        if faq_found:
            checks.append({"name": "FAQ Page", "status": "pass", "details": "FAQ page or section detected.", "category": "content", "weight": 0.7})
        else:
            checks.append({"name": "FAQ Page", "status": "fail", "details": "No FAQ page found.", "category": "content", "weight": 0.7})
            issues.append({"description": "Add an FAQ page targeting local search queries.", "severity": 50})

        # ---- Testimonials from local clients -----------------------------
        testimonial_pages = [u for u in pages_html if any(kw in u.lower() for kw in ["testimonial", "review"])]
        testimonial_in_text = "testimonial" in all_text or "customer review" in all_text
        if testimonial_pages or testimonial_in_text:
            checks.append({"name": "Local Testimonials", "status": "pass", "details": "Testimonials / review section found.", "category": "content", "weight": 0.7})
        else:
            checks.append({"name": "Local Testimonials", "status": "fail", "details": "No testimonials section found.", "category": "content", "weight": 0.7})
            issues.append({"description": "Add a testimonials page with local client reviews.", "severity": 50})

        # ---- Local resource guides ----------------------------------------
        resource_pages = [u for u in pages_html if any(kw in u.lower() for kw in ["resource", "guide"])]
        if resource_pages:
            checks.append({"name": "Local Resource Guides", "status": "pass", "details": f"{len(resource_pages)} resource/guide page(s).", "category": "content", "weight": 0.5})
        else:
            checks.append({"name": "Local Resource Guides", "status": "warning", "details": "No local resource or guide pages.", "category": "content", "weight": 0.5})
            issues.append({"description": "Create local resource guides to attract links and traffic.", "severity": 30})

        # Score
        tw = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / tw) * 100, 1)

        logger.info("Local content score: %.1f", score)
        return {"checks": checks, "score": score, "issues": issues}

    # ------------------------------------------------------------------
    # 6. Local backlinks
    # ------------------------------------------------------------------
    async def _analyze_local_backlinks(self, base_url: str, location: str) -> dict:
        """Evaluate off-page local link signals.

        Checks local directory links, chamber-of-commerce, local media,
        .gov/.edu links, and general backlink diversity heuristics.

        Returns:
            dict with ``checks``, ``score``, ``issues``.
        """
        checks: list[dict] = []
        issues: list[dict] = []
        domain = urlparse(base_url).netloc or base_url

        # Use SERP to find mentions / backlink signals
        queries = [
            f'"{domain}" site:chamberofcommerce.com OR site:bbb.org',
            f'"{domain}" local directory',
            f'"{domain}" site:.gov OR site:.edu',
            f'"{domain}" {location} news OR press',
        ]

        serp_results: dict[str, dict] = {}
        for q in queries:
            try:
                result = await self.serp_scraper.search_google(query=q, num_results=10)
                serp_results[q] = result
            except Exception as exc:
                logger.warning("SERP query failed for '%s': %s", q, exc)
                serp_results[q] = {}

        # ---- Chamber / BBB links -----------------------------------------
        chamber_q = queries[0]
        chamber_hits = len(serp_results.get(chamber_q, {}).get("organic_results", []))
        if chamber_hits >= 1:
            checks.append({"name": "Chamber/BBB Links", "status": "pass", "details": f"{chamber_hits} chamber/BBB mention(s) found.", "category": "backlinks", "weight": 0.8})
        else:
            checks.append({"name": "Chamber/BBB Links", "status": "fail", "details": "No chamber of commerce / BBB links found.", "category": "backlinks", "weight": 0.8})
            issues.append({"description": "Get listed on local Chamber of Commerce and BBB.", "severity": 60})

        # ---- Local directory links ----------------------------------------
        dir_q = queries[1]
        dir_hits = len(serp_results.get(dir_q, {}).get("organic_results", []))
        if dir_hits >= 5:
            checks.append({"name": "Local Directory Links", "status": "pass", "details": f"{dir_hits} local directory mentions.", "category": "backlinks", "weight": 0.7})
        elif dir_hits >= 2:
            checks.append({"name": "Local Directory Links", "status": "warning", "details": f"Only {dir_hits} directory mentions.", "category": "backlinks", "weight": 0.7})
            issues.append({"description": "Expand local directory presence.", "severity": 50})
        else:
            checks.append({"name": "Local Directory Links", "status": "fail", "details": "Minimal local directory backlinks.", "category": "backlinks", "weight": 0.7})
            issues.append({"description": "Build links from local directories.", "severity": 60})

        # ---- .gov / .edu links --------------------------------------------
        gov_q = queries[2]
        gov_hits = len(serp_results.get(gov_q, {}).get("organic_results", []))
        if gov_hits >= 1:
            checks.append({"name": ".gov/.edu Backlinks", "status": "pass", "details": f"{gov_hits} .gov/.edu mention(s) detected.", "category": "backlinks", "weight": 0.9})
        else:
            checks.append({"name": ".gov/.edu Backlinks", "status": "warning", "details": "No .gov or .edu backlinks detected.", "category": "backlinks", "weight": 0.9})
            issues.append({"description": "Pursue .gov/.edu backlinks for authority.", "severity": 40})

        # ---- Local media mentions ----------------------------------------
        media_q = queries[3]
        media_hits = len(serp_results.get(media_q, {}).get("organic_results", []))
        if media_hits >= 2:
            checks.append({"name": "Local Media Mentions", "status": "pass", "details": f"{media_hits} local media/press mention(s).", "category": "backlinks", "weight": 0.8})
        elif media_hits >= 1:
            checks.append({"name": "Local Media Mentions", "status": "warning", "details": "Only 1 local media mention.", "category": "backlinks", "weight": 0.8})
            issues.append({"description": "Seek more local press coverage.", "severity": 40})
        else:
            checks.append({"name": "Local Media Mentions", "status": "fail", "details": "No local media mentions found.", "category": "backlinks", "weight": 0.8})
            issues.append({"description": "No local press coverage. Consider PR outreach.", "severity": 50})

        # Score
        tw = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / tw) * 100, 1)

        logger.info("Local backlinks score: %.1f", score)
        return {"checks": checks, "score": score, "issues": issues}

    # ------------------------------------------------------------------
    # 7. Reviews
    # ------------------------------------------------------------------
    async def _analyze_reviews(self, business_name: str, location: str) -> dict:
        """Assess the review profile using GBP and competitor data.

        Returns:
            dict with ``checks``, ``score``, ``issues``.
        """
        checks: list[dict] = []
        issues: list[dict] = []

        # Fetch GBP data for review info
        try:
            gbp_data = await self.gmb_analyzer.analyze_gbp_listing(
                business_name=business_name,
                location=location,
                known_website=None,
            )
        except Exception as exc:
            logger.error("Review analysis — GBP fetch failed: %s", exc)
            gbp_data = {}

        review_count = gbp_data.get("review_count", gbp_data.get("reviews", {}).get("count", 0)) or 0
        avg_rating = gbp_data.get("rating", gbp_data.get("reviews", {}).get("average", 0)) or 0

        # Fetch competitor data for benchmarking
        try:
            comp_data = await self.gmb_analyzer.compare_with_competitors(
                business_name=business_name,
                location=location,
                keyword=business_name,
            )
        except Exception as exc:
            logger.warning("Competitor comparison for reviews failed: %s", exc)
            comp_data = {}

        competitor_reviews = []
        for comp in comp_data.get("competitors", comp_data.get("results", [])):
            if isinstance(comp, dict):
                competitor_reviews.append({
                    "name": comp.get("name", "Unknown"),
                    "count": comp.get("review_count", comp.get("reviews", 0)) or 0,
                    "rating": comp.get("rating", 0) or 0,
                })

        avg_comp_count = (sum(c["count"] for c in competitor_reviews) / len(competitor_reviews)) if competitor_reviews else 0
        avg_comp_rating = (sum(c["rating"] for c in competitor_reviews) / len(competitor_reviews)) if competitor_reviews else 0

        # ---- Review count vs competitors ----------------------------------
        if review_count >= avg_comp_count and review_count >= 20:
            checks.append({"name": "Review Count", "status": "pass", "details": f"{review_count} reviews (competitors avg: {avg_comp_count:.0f}).", "category": "reviews", "weight": 1.0})
        elif review_count >= 10:
            checks.append({"name": "Review Count", "status": "warning", "details": f"Only {review_count} reviews (competitors avg: {avg_comp_count:.0f}).", "category": "reviews", "weight": 1.0})
            issues.append({"description": f"Review count ({review_count}) is below competitor average ({avg_comp_count:.0f}).", "severity": 60})
        else:
            checks.append({"name": "Review Count", "status": "fail", "details": f"Only {review_count} reviews — far below average.", "category": "reviews", "weight": 1.0})
            issues.append({"description": f"Very low review count ({review_count}). Implement review generation strategy.", "severity": 80})

        # ---- Rating vs competitors ----------------------------------------
        if avg_rating >= 4.5:
            checks.append({"name": "Average Rating", "status": "pass", "details": f"Rating: {avg_rating:.1f} stars (competitors avg: {avg_comp_rating:.1f}).", "category": "reviews", "weight": 0.9})
        elif avg_rating >= 4.0:
            checks.append({"name": "Average Rating", "status": "warning", "details": f"Rating: {avg_rating:.1f} stars — room for improvement.", "category": "reviews", "weight": 0.9})
            issues.append({"description": f"Rating ({avg_rating:.1f}) could be higher.", "severity": 40})
        elif avg_rating > 0:
            checks.append({"name": "Average Rating", "status": "fail", "details": f"Rating: {avg_rating:.1f} stars — below 4.0 threshold.", "category": "reviews", "weight": 0.9})
            issues.append({"description": f"Low rating ({avg_rating:.1f}). Address negative feedback urgently.", "severity": 80})
        else:
            checks.append({"name": "Average Rating", "status": "fail", "details": "No rating data available.", "category": "reviews", "weight": 0.9})

        # ---- Review velocity (heuristic: reviews per month estimate) ------
        # Without direct data we use a proxy
        if review_count >= 50:
            checks.append({"name": "Review Velocity", "status": "pass", "details": "Strong review volume suggests healthy velocity.", "category": "reviews", "weight": 0.6})
        elif review_count >= 20:
            checks.append({"name": "Review Velocity", "status": "warning", "details": "Moderate review volume — consider boosting velocity.", "category": "reviews", "weight": 0.6})
            issues.append({"description": "Improve review acquisition rate.", "severity": 40})
        else:
            checks.append({"name": "Review Velocity", "status": "fail", "details": "Low review volume suggests poor velocity.", "category": "reviews", "weight": 0.6})
            issues.append({"description": "Very low review velocity. Automate review requests.", "severity": 60})

        # ---- Review diversity (check for Yelp, Facebook mentions) ---------
        try:
            serp_result = await self.serp_scraper.search_google(
                query=f'"{business_name}" {location} reviews',
                num_results=10,
            )
            review_platforms_found: set[str] = set()
            for r in serp_result.get("organic_results", []):
                url = (r.get("url", "") or r.get("link", "")).lower()
                for platform in ["yelp", "facebook", "bbb", "trustpilot", "angi", "homeadvisor", "thumbtack", "nextdoor"]:
                    if platform in url:
                        review_platforms_found.add(platform)

            if len(review_platforms_found) >= 3:
                checks.append({"name": "Review Platform Diversity", "status": "pass", "details": f"Reviews found on: {', '.join(review_platforms_found)}.", "category": "reviews", "weight": 0.7})
            elif review_platforms_found:
                checks.append({"name": "Review Platform Diversity", "status": "warning", "details": f"Reviews only on: {', '.join(review_platforms_found)}.", "category": "reviews", "weight": 0.7})
                issues.append({"description": "Diversify review presence across more platforms.", "severity": 40})
            else:
                checks.append({"name": "Review Platform Diversity", "status": "fail", "details": "No reviews found on third-party platforms.", "category": "reviews", "weight": 0.7})
                issues.append({"description": "No third-party review presence detected.", "severity": 60})
        except Exception as exc:
            logger.warning("Review diversity SERP check failed: %s", exc)
            checks.append({"name": "Review Platform Diversity", "status": "warning", "details": "Could not check review diversity.", "category": "reviews", "weight": 0.7})

        # ---- Negative review handling (heuristic) -------------------------
        if avg_rating >= 4.0 and review_count >= 10:
            checks.append({"name": "Negative Review Management", "status": "pass", "details": "Rating maintained despite volume — likely good management.", "category": "reviews", "weight": 0.5})
        elif avg_rating > 0:
            checks.append({"name": "Negative Review Management", "status": "warning", "details": "Rating suggests potential unaddressed negative reviews.", "category": "reviews", "weight": 0.5})
            issues.append({"description": "Respond to all negative reviews promptly.", "severity": 50})
        else:
            checks.append({"name": "Negative Review Management", "status": "warning", "details": "Cannot assess — no rating data.", "category": "reviews", "weight": 0.5})

        # Score
        tw = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / tw) * 100, 1)

        logger.info("Reviews score: %.1f", score)
        return {"checks": checks, "score": score, "issues": issues, "review_count": review_count, "avg_rating": avg_rating, "competitors": competitor_reviews}

    # ------------------------------------------------------------------
    # 8. Competitor map-pack analysis
    # ------------------------------------------------------------------
    async def _analyze_competitors_map_pack(self, keyword: str, location: str) -> dict:
        """Analyse the local map-pack for *keyword* and identify competitive gaps.

        Returns:
            dict with ``checks``, ``score``, ``issues``, and ``gap_analysis``.
        """
        checks: list[dict] = []
        issues: list[dict] = []
        gap_analysis: list[dict] = []

        try:
            comp_data = await self.gmb_analyzer.compare_with_competitors(
                business_name=keyword,
                location=location,
                keyword=keyword,
            )
        except Exception as exc:
            logger.error("Competitor map-pack analysis failed: %s", exc, exc_info=True)
            return {
                "checks": [{"name": "Map Pack Analysis", "status": "fail", "details": str(exc), "category": "competitors", "weight": 1.0}],
                "score": 0,
                "issues": [{"description": f"Map pack analysis failed: {exc}", "severity": 70}],
                "gap_analysis": [],
            }

        competitors = comp_data.get("competitors", comp_data.get("results", []))
        business_in_pack = comp_data.get("in_map_pack", comp_data.get("found", False))
        business_position = comp_data.get("position", None)

        # ---- Map pack presence -------------------------------------------
        if business_in_pack:
            pos_str = f" at position {business_position}" if business_position else ""
            checks.append({"name": "Map Pack Presence", "status": "pass", "details": f"Business appears in map pack{pos_str}.", "category": "competitors", "weight": 1.0})
        else:
            checks.append({"name": "Map Pack Presence", "status": "fail", "details": "Business NOT in local map pack.", "category": "competitors", "weight": 1.0})
            issues.append({"description": "Not appearing in Google Map Pack — highest priority local SEO issue.", "severity": 100})

        # ---- Competitive gap analysis ------------------------------------
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            comp_name = comp.get("name", "Unknown")
            comp_reviews = comp.get("review_count", comp.get("reviews", 0)) or 0
            comp_rating = comp.get("rating", 0) or 0
            gap_analysis.append({
                "competitor": comp_name,
                "reviews": comp_reviews,
                "rating": round(comp_rating, 1),
                "strengths": [],
                "weaknesses": [],
            })
            # Simple gap identification
            if comp_reviews > 50:
                gap_analysis[-1]["strengths"].append(f"Strong review count ({comp_reviews})")
            if comp_rating >= 4.5:
                gap_analysis[-1]["strengths"].append(f"Excellent rating ({comp_rating:.1f})")

        if competitors:
            checks.append({"name": "Competitor Data", "status": "pass", "details": f"Analysed {len(competitors)} competitors.", "category": "competitors", "weight": 0.5})
        else:
            checks.append({"name": "Competitor Data", "status": "warning", "details": "No competitor data retrieved.", "category": "competitors", "weight": 0.5})

        # Score
        tw = sum(c["weight"] for c in checks) or 1
        earned = sum(c["weight"] for c in checks if c["status"] == "pass")
        partial = sum(c["weight"] * 0.5 for c in checks if c["status"] == "warning")
        score = round(((earned + partial) / tw) * 100, 1)

        logger.info("Competitor map-pack score: %.1f", score)
        return {"checks": checks, "score": score, "issues": issues, "gap_analysis": gap_analysis, "raw": comp_data}

    # ------------------------------------------------------------------
    # 9. AI-powered recommendations
    # ------------------------------------------------------------------
    async def _generate_prioritized_recommendations(self, all_results: dict) -> list[dict]:
        """Use the LLM to synthesise a prioritised action plan.

        Returns:
            Sorted list of recommendation dicts.
        """
        # Build a condensed summary for the prompt
        summary_parts: list[str] = []
        for module, data in all_results.items():
            if not isinstance(data, dict):
                continue
            module_score = data.get("score", "N/A")
            module_issues = data.get("issues", [])
            issue_texts = [i.get("description", str(i)) if isinstance(i, dict) else str(i) for i in module_issues[:10]]
            summary_parts.append(
                f"## {module.upper()} (Score: {module_score}/100)\n"
                f"Issues:\n" + "\n".join(f"- {t}" for t in issue_texts) if issue_texts else f"## {module.upper()} (Score: {module_score}/100)\nNo major issues."
            )

        audit_summary = "\n\n".join(summary_parts)

        system_prompt = (
            "You are an expert Local SEO consultant with 15+ years of experience. "
            "You generate specific, actionable recommendations based on audit data. "
            "Always respond with valid JSON only — an array of recommendation objects."
        )

        user_prompt = f"""Based on the following Local SEO audit results, generate a prioritised list of 10-20 specific, actionable recommendations.

AUDIT RESULTS:
{audit_summary}

For each recommendation return a JSON object with EXACTLY these keys:
- "title": short action title (max 80 chars)
- "description": detailed explanation of what to do and why (2-4 sentences)
- "category": one of ["onpage", "gbp", "citations", "reviews", "content", "backlinks", "technical"]
- "priority": one of ["P1", "P2", "P3"] (P1 = critical, P2 = important, P3 = nice to have)
- "estimated_impact": one of ["high", "medium", "low"]
- "effort": one of ["easy", "medium", "hard"]
- "estimated_time": human-readable time estimate (e.g. "2-4 hours", "1-2 weeks")
- "group": one of ["Quick Wins", "High Impact", "Long Term"]

Rules:
1. Quick Wins = high/medium impact AND easy effort
2. High Impact = high impact AND medium/hard effort
3. Long Term = medium/low impact AND hard effort OR ongoing tasks
4. Sort by priority (P1 first), then by estimated_impact (high first), then by effort (easy first)
5. Be SPECIFIC — reference actual issues from the audit data
6. Do NOT include generic advice — every recommendation must relate to a finding

Return ONLY a JSON array, no markdown, no explanation."""

        try:
            recommendations = await self.llm_client.generate_json(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=4000,
                temperature=0.3,
            )
        except Exception as exc:
            logger.error("LLM recommendation generation failed: %s", exc, exc_info=True)
            # Fallback: generate basic recommendations from issues
            return self._fallback_recommendations(all_results)

        # Validate and normalise
        if isinstance(recommendations, dict) and "recommendations" in recommendations:
            recommendations = recommendations["recommendations"]
        if not isinstance(recommendations, list):
            logger.warning("LLM returned non-list recommendations; using fallback.")
            return self._fallback_recommendations(all_results)

        # Sort: P1 > P2 > P3, high > medium > low, easy > medium > hard
        priority_order = {"P1": 0, "P2": 1, "P3": 2}
        impact_order = {"high": 0, "medium": 1, "low": 2}
        effort_order = {"easy": 0, "medium": 1, "hard": 2}

        def sort_key(rec: dict) -> tuple:
            return (
                priority_order.get(rec.get("priority", "P3"), 9),
                impact_order.get(rec.get("estimated_impact", "low"), 9),
                effort_order.get(rec.get("effort", "hard"), 9),
            )

        recommendations.sort(key=sort_key)
        logger.info("Generated %d AI recommendations.", len(recommendations))
        return recommendations

    def _fallback_recommendations(self, all_results: dict) -> list[dict]:
        """Produce basic recommendations when the LLM is unavailable."""
        recs: list[dict] = []
        for module, data in all_results.items():
            if not isinstance(data, dict):
                continue
            for issue in data.get("issues", [])[:3]:
                desc = issue.get("description", str(issue)) if isinstance(issue, dict) else str(issue)
                severity = issue.get("severity", 50) if isinstance(issue, dict) else 50
                priority = "P1" if severity >= 80 else ("P2" if severity >= 50 else "P3")
                recs.append({
                    "title": f"Fix: {desc[:70]}",
                    "description": desc,
                    "category": module,
                    "priority": priority,
                    "estimated_impact": "high" if severity >= 80 else "medium",
                    "effort": "medium",
                    "estimated_time": "1-3 hours",
                    "group": "Quick Wins" if severity >= 70 else "High Impact",
                })
        recs.sort(key=lambda r: {"P1": 0, "P2": 1, "P3": 2}.get(r.get("priority", "P3"), 9))
        return recs[:15]

    # ------------------------------------------------------------------
    # 10. Score calculation
    # ------------------------------------------------------------------
    def _calculate_scores(self, all_results: dict) -> dict:
        """Compute weighted scores across all analysis modules.

        Weight map:
            onpage_score  : 0.25
            gmb_score     : 0.25
            citation_score: 0.15
            review_score  : 0.15
            content_score : 0.10
            backlink_score: 0.10

        Returns:
            dict with individual and overall scores (0-100 scale).
        """
        module_to_key = {
            "onpage": "onpage_score",
            "gbp": "gmb_score",
            "citations": "citation_score",
            "reviews": "review_score",
            "content": "content_score",
            "backlinks": "backlink_score",
        }

        scores: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for module_key, score_key in module_to_key.items():
            raw = all_results.get(module_key, {}).get("score", 0)
            s = _safe_score(raw)
            scores[score_key] = round(s, 1)

            weight = _WEIGHT_MAP.get(score_key, 0.0)
            weighted_sum += s * weight
            total_weight += weight

        overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0
        scores["overall_score"] = overall

        logger.info("Calculated scores — overall: %.1f", overall)
        return scores

    # ------------------------------------------------------------------
    # 11. Database persistence
    # ------------------------------------------------------------------
    async def _save_audit_to_db(
        self,
        business_name: str,
        domain: str,
        location: str,
        scores: dict,
        issues: list[dict],
        recommendations: list[dict],
    ) -> int:
        """Persist audit results to the database.

        Creates or updates a :class:`LocalBusinessProfile` and inserts a new
        :class:`LocalSEOAudit` row.

        Returns:
            The id of the newly created ``LocalSEOAudit`` row.
        """
        # Parse location into city/state heuristically
        loc_parts = [p.strip() for p in location.split(",")]
        city = loc_parts[0] if loc_parts else location
        state = loc_parts[1] if len(loc_parts) > 1 else ""

        with get_session() as session:
            # Upsert business profile
            stmt = select(LocalBusinessProfile).where(
                LocalBusinessProfile.business_name == business_name,
                LocalBusinessProfile.domain == domain,
            )
            profile = session.execute(stmt).scalar_one_or_none()

            if profile is None:
                profile = LocalBusinessProfile(
                    business_name=business_name,
                    domain=domain,
                    city=city,
                    state=state,
                )
                session.add(profile)
                session.flush()  # get the id
                logger.info("Created new LocalBusinessProfile id=%s", profile.id)
            else:
                profile.city = city or profile.city
                profile.state = state or profile.state
                profile.updated_at = datetime.now(timezone.utc)
                logger.info("Updated existing LocalBusinessProfile id=%s", profile.id)

            # Serialise issues and recommendations
            try:
                top_issues_json = json.dumps(issues[:50])
            except (TypeError, ValueError):
                top_issues_json = "[]"

            try:
                recommendations_json = json.dumps(recommendations[:30])
            except (TypeError, ValueError):
                recommendations_json = "[]"

            audit = LocalSEOAudit(
                business_id=profile.id,
                audit_date=datetime.now(timezone.utc),
                overall_score=scores.get("overall_score", 0),
                serp_score=scores.get("onpage_score", 0),
                gmb_score=scores.get("gmb_score", 0),
                onpage_score=scores.get("onpage_score", 0),
                offpage_score=scores.get("backlink_score", 0),
                citation_score=scores.get("citation_score", 0),
                top_issues_json=top_issues_json,
                recommendations_json=recommendations_json,
            )
            session.add(audit)
            session.commit()
            audit_id = audit.id
            logger.info("Saved LocalSEOAudit id=%s for business id=%s", audit_id, profile.id)

        return audit_id
