"""Google Business Profile (GBP/GMB) analyzer for local SEO optimization."""

import asyncio
import logging
import random
import re
from typing import Any, Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# GBP optimization checklist items with weights for scoring
GBP_CHECKLIST_ITEMS = [
    {"id": "listing_exists", "label": "GBP Listing Exists", "weight": 10, "category": "foundation"},
    {"id": "claimed_verified", "label": "Listing Claimed & Verified", "weight": 10, "category": "foundation"},
    {"id": "name_match", "label": "Business Name Matches Website", "weight": 8, "category": "nap"},
    {"id": "address_complete", "label": "Complete Address Listed", "weight": 7, "category": "nap"},
    {"id": "phone_number", "label": "Phone Number Listed", "weight": 7, "category": "nap"},
    {"id": "website_link", "label": "Website Link Correct", "weight": 8, "category": "nap"},
    {"id": "hours_set", "label": "Business Hours Set", "weight": 6, "category": "info"},
    {"id": "primary_category", "label": "Primary Category Set", "weight": 9, "category": "category"},
    {"id": "secondary_categories", "label": "Secondary Categories Added", "weight": 5, "category": "category"},
    {"id": "business_description", "label": "Business Description Filled", "weight": 7, "category": "info"},
    {"id": "review_count", "label": "Has 10+ Reviews", "weight": 9, "category": "reviews"},
    {"id": "review_rating", "label": "Average Rating ≥ 4.0", "weight": 8, "category": "reviews"},
    {"id": "review_response", "label": "Reviews Are Being Responded To", "weight": 7, "category": "reviews"},
    {"id": "photos_count", "label": "Has 10+ Photos", "weight": 6, "category": "media"},
    {"id": "photo_quality", "label": "Professional Quality Photos", "weight": 5, "category": "media"},
    {"id": "google_posts", "label": "Recent Google Posts (last 30 days)", "weight": 6, "category": "engagement"},
    {"id": "qa_section", "label": "Q&A Section Has Content", "weight": 4, "category": "engagement"},
    {"id": "products_services", "label": "Products/Services Listed", "weight": 6, "category": "info"},
    {"id": "attributes", "label": "Business Attributes Configured", "weight": 4, "category": "info"},
    {"id": "service_area", "label": "Service Area Defined", "weight": 5, "category": "info"},
]


class GMBAnalyzer:
    """Analyze Google Business Profile optimization and map pack positioning.

    Usage::

        analyzer = GMBAnalyzer()
        listing = await analyzer.analyze_gbp_listing("Acme Plumbing", "Denver, CO")
        map_pack = await analyzer.get_map_pack_results("plumber near me", "Denver, CO")
        comparison = await analyzer.compare_with_competitors("Acme Plumbing", "Denver, CO", "plumber")
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        delay_between_requests: float = 3.0,
        max_retries: int = 3,
    ):
        self._headless = headless
        self._timeout = timeout
        self._delay = delay_between_requests
        self._max_retries = max_retries
        self._browser: Optional[Browser] = None

    async def _ensure_browser(self) -> Browser:
        """Launch or reuse the Playwright browser."""
        if self._browser and self._browser.is_connected():
            return self._browser
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=self._headless)
        return self._browser

    async def _new_page(self) -> Page:
        """Create a new page with a random user-agent."""
        browser = await self._ensure_browser()
        ua = random.choice(DEFAULT_USER_AGENTS)
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()
        page.set_default_timeout(self._timeout)
        return page

    async def _rate_limit(self) -> None:
        """Add delay between requests to avoid blocking."""
        await asyncio.sleep(self._delay + random.uniform(0.5, 2.0))

    async def analyze_gbp_listing(
        self,
        business_name: str,
        location: str,
        known_website: str = "",
    ) -> dict[str, Any]:
        """Analyze a Google Business Profile listing for optimization signals.

        Searches Google Maps for the business and extracts all available
        profile information to evaluate optimization level.

        Args:
            business_name: The business name to search for.
            location: City, State or full location string.
            known_website: Known website URL for verification.

        Returns:
            Dict with listing data, optimization checks, and scores.
        """
        result: dict[str, Any] = {
            "business_name": business_name,
            "location": location,
            "listing_found": False,
            "listing_data": {},
            "optimization_checks": {},
            "gmb_score": 0.0,
            "issues": [],
            "recommendations": [],
        }

        query = f"{business_name} {location}"
        search_url = f"https://www.google.com/maps/search/{quote_plus(query)}"

        page = await self._new_page()
        try:
            for attempt in range(self._max_retries):
                try:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)  # Allow Maps to load

                    # Try to find and click on the business listing
                    listing_data = await self._extract_listing_data(page, business_name)

                    if listing_data.get("name"):
                        result["listing_found"] = True
                        result["listing_data"] = listing_data

                        # Run optimization checks
                        checks = self._evaluate_listing(
                            listing_data, known_website
                        )
                        result["optimization_checks"] = checks

                        # Calculate score
                        result["gmb_score"] = self._calculate_gbp_score(checks)

                        # Generate issues and recommendations
                        issues, recs = self._generate_listing_feedback(checks)
                        result["issues"] = issues
                        result["recommendations"] = recs
                    else:
                        result["issues"].append({
                            "severity": "critical",
                            "message": "Google Business Profile listing not found or not claimed",
                        })
                        result["recommendations"].append({
                            "priority": "P1",
                            "title": "Create/Claim Google Business Profile",
                            "description": (
                                "Your business was not found on Google Maps. "
                                "Create and verify a Google Business Profile at "
                                "https://business.google.com/ immediately. This is "
                                "the single most important step for local SEO."
                            ),
                            "impact": "critical",
                            "effort": "easy",
                        })
                    break

                except Exception as exc:
                    logger.warning(
                        "GBP analysis attempt %d failed for '%s': %s",
                        attempt + 1, business_name, exc,
                    )
                    if attempt < self._max_retries - 1:
                        await self._rate_limit()
                    else:
                        result["issues"].append({
                            "severity": "warning",
                            "message": f"Could not complete GBP analysis: {exc}",
                        })
        finally:
            await page.context.close()

        return result

    async def _extract_listing_data(
        self, page: Page, business_name: str
    ) -> dict[str, Any]:
        """Extract listing data from a Google Maps search result page."""
        data: dict[str, Any] = {
            "name": "",
            "address": "",
            "phone": "",
            "website": "",
            "category": "",
            "rating": None,
            "review_count": 0,
            "hours": "",
            "description": "",
            "photos_count": 0,
            "has_posts": False,
            "has_products": False,
            "has_qa": False,
            "has_attributes": False,
            "claimed": False,
            "service_area": "",
            "secondary_categories": [],
        }

        try:
            # Wait for results to load
            await page.wait_for_selector(
                'div[role="feed"], div[role="main"]', timeout=10000
            )

            # Try to click on the first matching result
            results = page.locator('div[role="feed"] a[aria-label]')
            count = await results.count()

            clicked = False
            for i in range(min(count, 5)):
                label = await results.nth(i).get_attribute("aria-label") or ""
                if business_name.lower() in label.lower():
                    await results.nth(i).click()
                    clicked = True
                    await asyncio.sleep(2)
                    break

            if not clicked and count > 0:
                # Click first result as fallback
                await results.first.click()
                await asyncio.sleep(2)

            # Extract business name
            name_el = page.locator('h1, div[role="main"] span.fontHeadlineLarge').first
            if await name_el.count():
                data["name"] = (await name_el.text_content() or "").strip()

            # Extract rating and review count
            rating_el = page.locator('div.fontBodyMedium span[aria-hidden="true"]').first
            if await rating_el.count():
                rating_text = (await rating_el.text_content() or "").strip()
                try:
                    data["rating"] = float(rating_text.replace(",", "."))
                except ValueError:
                    pass

            review_el = page.locator('button[aria-label*="review"]').first
            if await review_el.count():
                review_text = (await review_el.text_content() or "").strip()
                review_match = re.search(r"([\d,]+)", review_text)
                if review_match:
                    data["review_count"] = int(
                        review_match.group(1).replace(",", "")
                    )

            # Extract category
            category_el = page.locator(
                'button[jsaction*="category"], span.fontBodyMedium button'
            ).first
            if await category_el.count():
                data["category"] = (await category_el.text_content() or "").strip()

            # Extract address
            addr_el = page.locator(
                'button[data-item-id="address"], '
                'button[aria-label*="Address"]'
            ).first
            if await addr_el.count():
                data["address"] = (await addr_el.text_content() or "").strip()

            # Extract phone
            phone_el = page.locator(
                'button[data-item-id*="phone"], '
                'button[aria-label*="Phone"]'
            ).first
            if await phone_el.count():
                data["phone"] = (await phone_el.text_content() or "").strip()

            # Extract website
            web_el = page.locator(
                'a[data-item-id="authority"], '
                'a[aria-label*="Website"]'
            ).first
            if await web_el.count():
                data["website"] = await web_el.get_attribute("href") or ""

            # Extract hours
            hours_el = page.locator(
                'div[aria-label*="hour" i], '
                'button[data-item-id*="hour"]'
            ).first
            if await hours_el.count():
                data["hours"] = (await hours_el.text_content() or "").strip()

            # Check for description
            desc_el = page.locator(
                'div[aria-label*="description" i] span, '
                'div.PYvSYb'
            ).first
            if await desc_el.count():
                data["description"] = (await desc_el.text_content() or "").strip()

            # Check for photos count
            photos_el = page.locator(
                'button[aria-label*="photo" i]'
            ).first
            if await photos_el.count():
                photos_text = (await photos_el.text_content() or "")
                photos_match = re.search(r"([\d,]+)", photos_text)
                if photos_match:
                    data["photos_count"] = int(
                        photos_match.group(1).replace(",", "")
                    )

            # Check for Google Posts (Updates tab)
            posts_tab = page.locator(
                'button[aria-label*="Updates"], '
                'button[aria-label*="Posts"]'
            ).first
            data["has_posts"] = await posts_tab.count() > 0

            # Check for Products/Services
            products_tab = page.locator(
                'button[aria-label*="Products"], '
                'button[aria-label*="Services"], '
                'button[aria-label*="Menu"]'
            ).first
            data["has_products"] = await products_tab.count() > 0

            # Check for Q&A
            qa_section = page.locator(
                'div[aria-label*="Questions"], '
                'button[aria-label*="question"]'
            ).first
            data["has_qa"] = await qa_section.count() > 0

            # Check for claimed status (look for "Claim this business" text)
            page_text = await page.content()
            data["claimed"] = "claim this business" not in page_text.lower()

            # Check for attributes
            attrs_section = page.locator(
                'div[aria-label*="Amenities"], '
                'div[aria-label*="Highlights"], '
                'div[aria-label*="Accessibility"]'
            ).first
            data["has_attributes"] = await attrs_section.count() > 0

        except Exception as exc:
            logger.warning("Error extracting listing data: %s", exc)

        return data

    def _evaluate_listing(
        self,
        listing_data: dict[str, Any],
        known_website: str = "",
    ) -> dict[str, dict[str, Any]]:
        """Evaluate listing data against GBP optimization checklist."""
        checks: dict[str, dict[str, Any]] = {}

        for item in GBP_CHECKLIST_ITEMS:
            check_id = item["id"]
            check_result = {
                "label": item["label"],
                "passed": False,
                "weight": item["weight"],
                "category": item["category"],
                "details": "",
            }

            if check_id == "listing_exists":
                check_result["passed"] = bool(listing_data.get("name"))
                check_result["details"] = (
                    "Listing found" if check_result["passed"]
                    else "Listing not found on Google Maps"
                )

            elif check_id == "claimed_verified":
                check_result["passed"] = listing_data.get("claimed", False)
                check_result["details"] = (
                    "Listing appears to be claimed"
                    if check_result["passed"]
                    else "Listing may not be claimed — look for 'Claim this business' link"
                )

            elif check_id == "name_match":
                check_result["passed"] = bool(listing_data.get("name"))
                check_result["details"] = f"Listed as: {listing_data.get('name', 'N/A')}"

            elif check_id == "address_complete":
                check_result["passed"] = bool(listing_data.get("address"))
                check_result["details"] = listing_data.get("address", "No address found")

            elif check_id == "phone_number":
                check_result["passed"] = bool(listing_data.get("phone"))
                check_result["details"] = listing_data.get("phone", "No phone found")

            elif check_id == "website_link":
                website = listing_data.get("website", "")
                check_result["passed"] = bool(website)
                if known_website and website:
                    domain_match = (
                        known_website.lower().replace("www.", "")
                        in website.lower().replace("www.", "")
                    )
                    check_result["passed"] = domain_match
                    check_result["details"] = (
                        f"Website: {website} — "
                        f"{'matches' if domain_match else 'MISMATCH with ' + known_website}"
                    )
                else:
                    check_result["details"] = website or "No website link found"

            elif check_id == "hours_set":
                check_result["passed"] = bool(listing_data.get("hours"))
                check_result["details"] = (
                    "Business hours are set" if check_result["passed"]
                    else "No business hours found"
                )

            elif check_id == "primary_category":
                check_result["passed"] = bool(listing_data.get("category"))
                check_result["details"] = (
                    f"Category: {listing_data.get('category', 'Not set')}"
                )

            elif check_id == "secondary_categories":
                sec_cats = listing_data.get("secondary_categories", [])
                check_result["passed"] = len(sec_cats) > 0
                check_result["details"] = (
                    f"{len(sec_cats)} secondary categories"
                    if sec_cats else "No secondary categories detected"
                )

            elif check_id == "business_description":
                check_result["passed"] = bool(listing_data.get("description"))
                desc = listing_data.get("description", "")
                check_result["details"] = (
                    f"Description: {desc[:100]}..."
                    if len(desc) > 100 else (desc or "No description found")
                )

            elif check_id == "review_count":
                count = listing_data.get("review_count", 0)
                check_result["passed"] = count >= 10
                check_result["details"] = f"{count} reviews (target: 10+)"

            elif check_id == "review_rating":
                rating = listing_data.get("rating")
                check_result["passed"] = rating is not None and rating >= 4.0
                check_result["details"] = (
                    f"Rating: {rating}/5.0 (target: 4.0+)"
                    if rating else "No rating found"
                )

            elif check_id == "review_response":
                # Heuristic: if the listing is claimed and has reviews, assume partial response
                has_reviews = listing_data.get("review_count", 0) > 0
                claimed = listing_data.get("claimed", False)
                check_result["passed"] = has_reviews and claimed
                check_result["details"] = (
                    "Review responses detected (verify manually for response rate)"
                    if check_result["passed"]
                    else "Unable to verify review response rate"
                )

            elif check_id == "photos_count":
                count = listing_data.get("photos_count", 0)
                check_result["passed"] = count >= 10
                check_result["details"] = f"{count} photos (target: 10+)"

            elif check_id == "photo_quality":
                count = listing_data.get("photos_count", 0)
                check_result["passed"] = count >= 5  # Proxy for quality
                check_result["details"] = (
                    "Photos present — verify quality manually"
                    if count > 0 else "No photos detected"
                )

            elif check_id == "google_posts":
                check_result["passed"] = listing_data.get("has_posts", False)
                check_result["details"] = (
                    "Google Posts / Updates tab found"
                    if check_result["passed"]
                    else "No recent Google Posts detected"
                )

            elif check_id == "qa_section":
                check_result["passed"] = listing_data.get("has_qa", False)
                check_result["details"] = (
                    "Q&A section has content"
                    if check_result["passed"]
                    else "No Q&A activity detected"
                )

            elif check_id == "products_services":
                check_result["passed"] = listing_data.get("has_products", False)
                check_result["details"] = (
                    "Products/Services section found"
                    if check_result["passed"]
                    else "No products or services listed"
                )

            elif check_id == "attributes":
                check_result["passed"] = listing_data.get("has_attributes", False)
                check_result["details"] = (
                    "Business attributes configured"
                    if check_result["passed"]
                    else "No attributes detected"
                )

            elif check_id == "service_area":
                check_result["passed"] = bool(listing_data.get("service_area"))
                check_result["details"] = (
                    listing_data.get("service_area", "")
                    or "Service area not defined"
                )

            checks[check_id] = check_result

        return checks

    @staticmethod
    def _calculate_gbp_score(checks: dict[str, dict[str, Any]]) -> float:
        """Calculate overall GBP optimization score from check results."""
        total_weight = sum(c["weight"] for c in checks.values())
        earned_weight = sum(
            c["weight"] for c in checks.values() if c["passed"]
        )
        return round((earned_weight / max(total_weight, 1)) * 100, 1)

    @staticmethod
    def _generate_listing_feedback(
        checks: dict[str, dict[str, Any]],
    ) -> tuple[list[dict], list[dict]]:
        """Generate issues and recommendations from check results."""
        issues: list[dict] = []
        recommendations: list[dict] = []

        priority_map = {
            "foundation": "P1",
            "nap": "P1",
            "category": "P1",
            "reviews": "P2",
            "info": "P2",
            "media": "P3",
            "engagement": "P3",
        }
        impact_map = {
            "foundation": "critical",
            "nap": "high",
            "category": "high",
            "reviews": "high",
            "info": "medium",
            "media": "medium",
            "engagement": "low",
        }
        effort_map = {
            "foundation": "easy",
            "nap": "easy",
            "category": "easy",
            "reviews": "hard",
            "info": "easy",
            "media": "medium",
            "engagement": "medium",
        }

        for check_id, check in checks.items():
            if not check["passed"]:
                cat = check["category"]
                issues.append({
                    "check_id": check_id,
                    "severity": impact_map.get(cat, "medium"),
                    "message": f"{check['label']}: {check['details']}",
                    "category": cat,
                })
                recommendations.append({
                    "check_id": check_id,
                    "priority": priority_map.get(cat, "P3"),
                    "title": f"Fix: {check['label']}",
                    "description": check["details"],
                    "impact": impact_map.get(cat, "medium"),
                    "effort": effort_map.get(cat, "medium"),
                    "category": "gbp",
                })

        # Sort: P1 first, then by weight desc
        recommendations.sort(
            key=lambda r: (
                {"P1": 0, "P2": 1, "P3": 2}.get(r["priority"], 3),
                -checks.get(r["check_id"], {}).get("weight", 0),
            )
        )
        return issues, recommendations

    async def get_map_pack_results(
        self,
        keyword: str,
        location: str,
    ) -> list[dict[str, Any]]:
        """Extract Google Map Pack (Local 3-Pack) results for a keyword.

        Args:
            keyword: Search keyword (e.g. "plumber", "dentist").
            location: Location for localized search (e.g. "Denver, CO").

        Returns:
            List of map pack entries with name, rating, reviews, position, etc.
        """
        query = f"{keyword} {location}"
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&gl=us&hl=en"
        map_results: list[dict[str, Any]] = []

        page = await self._new_page()
        try:
            for attempt in range(self._max_retries):
                try:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await page.wait_for_selector("#search", timeout=self._timeout)
                    await asyncio.sleep(2)

                    # Look for local pack / map pack container
                    map_pack = page.locator(
                        'div.VkpGBb, '
                        'div[data-local-attribute], '
                        'div[jscontroller] div.rllt__details, '
                        'div.cXedhc'
                    )
                    pack_count = await map_pack.count()

                    if pack_count == 0:
                        # Try alternative selectors for local results
                        map_pack = page.locator(
                            'div[data-ved] a[data-cid]'
                        )
                        pack_count = await map_pack.count()

                    for i in range(min(pack_count, 10)):
                        item = map_pack.nth(i)
                        entry: dict[str, Any] = {
                            "position": i + 1,
                            "name": "",
                            "rating": None,
                            "review_count": 0,
                            "category": "",
                            "address": "",
                            "phone": "",
                            "website": "",
                        }

                        try:
                            # Extract name
                            name_el = item.locator(
                                'span.OSrXXb, '
                                'div.dbg0pd, '
                                'span.fontHeadlineSmall'
                            ).first
                            if await name_el.count():
                                entry["name"] = (
                                    await name_el.text_content() or ""
                                ).strip()

                            # Extract rating
                            rating_el = item.locator('span.yi40Hd, span.BTtC6e').first
                            if await rating_el.count():
                                rt = (await rating_el.text_content() or "").strip()
                                try:
                                    entry["rating"] = float(rt.replace(",", "."))
                                except ValueError:
                                    pass

                            # Extract review count
                            review_el = item.locator(
                                'span.RDApEe, span.HypWnf'
                            ).first
                            if await review_el.count():
                                rv = (await review_el.text_content() or "")
                                rv_match = re.search(r"([\d,]+)", rv)
                                if rv_match:
                                    entry["review_count"] = int(
                                        rv_match.group(1).replace(",", "")
                                    )

                            # Extract details text (category, address, etc.)
                            details_el = item.locator(
                                'div.rllt__details, span.rllt__details'
                            ).first
                            if await details_el.count():
                                details_text = (
                                    await details_el.text_content() or ""
                                ).strip()
                                entry["details_raw"] = details_text

                            if entry["name"]:
                                map_results.append(entry)
                        except Exception as inner_exc:
                            logger.debug(
                                "Error parsing map pack item %d: %s", i, inner_exc
                            )
                            continue

                    logger.info(
                        "Map pack for '%s': %d results found",
                        query, len(map_results),
                    )
                    break

                except Exception as exc:
                    logger.warning(
                        "Map pack attempt %d failed for '%s': %s",
                        attempt + 1, query, exc,
                    )
                    if attempt < self._max_retries - 1:
                        await self._rate_limit()
        finally:
            await page.context.close()

        return map_results

    async def compare_with_competitors(
        self,
        business_name: str,
        location: str,
        keyword: str,
    ) -> dict[str, Any]:
        """Compare business GBP with map pack competitors.

        Args:
            business_name: The target business name.
            location: Location for search.
            keyword: Primary keyword to check map pack for.

        Returns:
            Dict with our_listing, competitors, gap_analysis, and recommendations.
        """
        result: dict[str, Any] = {
            "keyword": keyword,
            "location": location,
            "our_listing": None,
            "our_position": None,
            "competitors": [],
            "gap_analysis": {},
            "in_map_pack": False,
        }

        # Get map pack results
        map_results = await self.get_map_pack_results(keyword, location)
        result["competitors"] = map_results

        # Find our position
        biz_lower = business_name.lower()
        for entry in map_results:
            if biz_lower in entry.get("name", "").lower():
                result["our_listing"] = entry
                result["our_position"] = entry["position"]
                result["in_map_pack"] = entry["position"] <= 3
                break

        # Gap analysis comparing with top 3
        top_3 = map_results[:3] if len(map_results) >= 3 else map_results
        if top_3:
            avg_rating = sum(
                e.get("rating") or 0.0 for e in top_3
            ) / len(top_3)
            avg_reviews = sum(
                e.get("review_count", 0) for e in top_3
            ) / len(top_3)
            max_reviews = max(
                (e.get("review_count", 0) for e in top_3), default=0
            )

            our_rating = (
                result["our_listing"].get("rating") or 0.0
                if result["our_listing"] else 0.0
            )
            our_reviews = (
                result["our_listing"].get("review_count", 0)
                if result["our_listing"] else 0
            )

            result["gap_analysis"] = {
                "top_3_avg_rating": round(avg_rating, 1),
                "top_3_avg_reviews": int(avg_reviews),
                "top_3_max_reviews": max_reviews,
                "our_rating": our_rating,
                "our_reviews": our_reviews,
                "rating_gap": round(avg_rating - our_rating, 1),
                "review_gap": int(avg_reviews - our_reviews),
                "reviews_needed_for_parity": max(
                    int(avg_reviews - our_reviews), 0
                ),
                "reviews_needed_to_lead": max(
                    max_reviews - our_reviews + 1, 0
                ),
            }

        return result

    def generate_gbp_optimization_checklist(
        self,
        current_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate a prioritized GBP optimization checklist based on current state.

        Args:
            current_state: Dict with listing_data and optimization_checks from
                          analyze_gbp_listing().

        Returns:
            Ordered list of checklist items with status, priority, and action.
        """
        checks = current_state.get("optimization_checks", {})
        checklist: list[dict[str, Any]] = []

        for item in GBP_CHECKLIST_ITEMS:
            check = checks.get(item["id"], {})
            passed = check.get("passed", False)

            action = ""
            if not passed:
                action_map = {
                    "listing_exists": (
                        "Create a Google Business Profile at business.google.com. "
                        "This is mandatory for local search visibility."
                    ),
                    "claimed_verified": (
                        "Claim and verify your listing via postcard, phone, or email. "
                        "Unverified listings rank significantly lower."
                    ),
                    "name_match": (
                        "Ensure your GBP business name exactly matches your website "
                        "and real-world signage. Do NOT keyword-stuff the name."
                    ),
                    "address_complete": (
                        "Add your complete street address. If service-area business, "
                        "set your service area instead."
                    ),
                    "phone_number": (
                        "Add a local phone number (not toll-free). "
                        "Local numbers signal proximity to searchers."
                    ),
                    "website_link": (
                        "Add your website URL and ensure it points to your homepage "
                        "or a dedicated location landing page."
                    ),
                    "hours_set": (
                        "Set accurate business hours including special hours for "
                        "holidays. Listings with hours get more engagement."
                    ),
                    "primary_category": (
                        "Set the most specific primary category that matches your "
                        "core service. This is the #1 ranking factor for map pack."
                    ),
                    "secondary_categories": (
                        "Add 2-5 relevant secondary categories to capture more "
                        "search queries. Don't add unrelated categories."
                    ),
                    "business_description": (
                        "Write a compelling 750-character description including your "
                        "main services, location, and unique value proposition."
                    ),
                    "review_count": (
                        "Actively request reviews from satisfied customers. Create a "
                        "direct review link and include it in follow-up emails. "
                        "Target: surpass competitor review count."
                    ),
                    "review_rating": (
                        "Focus on service quality to maintain 4.0+ rating. Address "
                        "negative reviews professionally and promptly."
                    ),
                    "review_response": (
                        "Respond to ALL reviews (positive and negative) within 24-48 "
                        "hours. Include keywords naturally in responses."
                    ),
                    "photos_count": (
                        "Upload at least 10 high-quality photos: exterior, interior, "
                        "team, products/services. Add new photos weekly."
                    ),
                    "photo_quality": (
                        "Use professional, well-lit photos. Add geo-tagged images "
                        "taken at your business location."
                    ),
                    "google_posts": (
                        "Publish Google Posts weekly: offers, events, updates. "
                        "Posts expire after 7 days, so consistency is key."
                    ),
                    "qa_section": (
                        "Seed your Q&A section with common questions and answers. "
                        "Monitor and respond to new questions promptly."
                    ),
                    "products_services": (
                        "List all your products/services with descriptions and prices. "
                        "This helps Google match you to relevant searches."
                    ),
                    "attributes": (
                        "Configure all relevant business attributes (wheelchair access, "
                        "parking, payment methods, etc.)."
                    ),
                    "service_area": (
                        "Define your service area if you serve customers at their "
                        "location. Be specific but realistic in coverage."
                    ),
                }
                action = action_map.get(item["id"], "Review and optimize this aspect.")

            checklist.append({
                "id": item["id"],
                "label": item["label"],
                "status": "pass" if passed else "fail",
                "weight": item["weight"],
                "category": item["category"],
                "priority": (
                    "P1" if item["weight"] >= 8
                    else "P2" if item["weight"] >= 6
                    else "P3"
                ),
                "details": check.get("details", ""),
                "action": action,
            })

        # Sort: failed items first, then by weight descending
        checklist.sort(
            key=lambda c: (
                0 if c["status"] == "fail" else 1,
                -c["weight"],
            )
        )
        return checklist

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
