"""Citation checker for local business directory presence and NAP consistency."""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DirectoryInfo:
    """Metadata for a business directory."""
    name: str
    url_template: str
    authority_score: int  # 1-100
    category: str  # general, industry, social, map
    check_url: str = ""  # direct search URL template


# Top 50+ business directories organized by authority
TOP_DIRECTORIES: list[DirectoryInfo] = [
    # Tier 1 — Critical (authority 90-100)
    DirectoryInfo("Google Business Profile", "https://www.google.com/maps/search/{query}", 100, "map"),
    DirectoryInfo("Apple Maps", "https://maps.apple.com/?q={query}", 95, "map"),
    DirectoryInfo("Bing Places", "https://www.bing.com/maps?q={query}", 93, "map"),
    DirectoryInfo("Yelp", "https://www.yelp.com/search?find_desc={query}&find_loc={location}", 92, "general"),
    DirectoryInfo("Facebook", "https://www.facebook.com/search/pages/?q={query}", 91, "social"),
    DirectoryInfo("Better Business Bureau", "https://www.bbb.org/search?find_text={query}&find_loc={location}", 90, "general"),

    # Tier 2 — High Priority (authority 80-89)
    DirectoryInfo("Yellow Pages", "https://www.yellowpages.com/search?search_terms={query}&geo_location_terms={location}", 88, "general"),
    DirectoryInfo("Foursquare", "https://foursquare.com/explore?near={location}&q={query}", 86, "general"),
    DirectoryInfo("TripAdvisor", "https://www.tripadvisor.com/Search?q={query}&geo={location}", 85, "industry"),
    DirectoryInfo("Angi (Angie\'s List)", "https://www.angi.com/search?query={query}&location={location}", 85, "industry"),
    DirectoryInfo("Nextdoor", "https://nextdoor.com/find-business/{query}/", 84, "social"),
    DirectoryInfo("MapQuest", "https://www.mapquest.com/search/{query}-{location}", 83, "map"),
    DirectoryInfo("HERE WeGo", "https://wego.here.com/search/{query}", 82, "map"),
    DirectoryInfo("Superpages", "https://www.superpages.com/search?search_terms={query}&geo_location_terms={location}", 81, "general"),
    DirectoryInfo("Whitepages", "https://www.whitepages.com/business/{query}/{location}", 80, "general"),

    # Tier 3 — Important (authority 70-79)
    DirectoryInfo("Manta", "https://www.manta.com/search?search_source=nav&search={query}&search_location={location}", 78, "general"),
    DirectoryInfo("Hotfrog", "https://www.hotfrog.com/search/{location}/{query}", 77, "general"),
    DirectoryInfo("CitySearch", "https://www.citysearch.com/search?what={query}&where={location}", 76, "general"),
    DirectoryInfo("DexKnows", "https://www.dexknows.com/search?query={query}&where={location}", 75, "general"),
    DirectoryInfo("Chamberofcommerce.com", "https://www.chamberofcommerce.com/search?q={query}&l={location}", 75, "general"),
    DirectoryInfo("Thumbtack", "https://www.thumbtack.com/search/{query}/{location}", 74, "industry"),
    DirectoryInfo("Alignable", "https://www.alignable.com/search?q={query}", 73, "social"),
    DirectoryInfo("Local.com", "https://www.local.com/business/results/?keyword={query}&location={location}", 72, "general"),
    DirectoryInfo("Brownbook", "https://www.brownbook.net/business/search/{query}/{location}", 71, "general"),
    DirectoryInfo("EZlocal", "https://ezlocal.com/search/?q={query}&loc={location}", 70, "general"),

    # Tier 4 — Valuable (authority 60-69)
    DirectoryInfo("Spoke", "https://www.spoke.com/search?q={query}", 68, "general"),
    DirectoryInfo("YellowBot", "https://www.yellowbot.com/search?q={query}&place={location}", 67, "general"),
    DirectoryInfo("iBegin", "https://www.ibegin.com/search/?q={query}&l={location}", 66, "general"),
    DirectoryInfo("US City", "https://www.uscity.net/search?q={query}&location={location}", 65, "general"),
    DirectoryInfo("ShowMeLocal", "https://www.showmelocal.com/search?q={query}&l={location}", 64, "general"),
    DirectoryInfo("MerchantCircle", "https://www.merchantcircle.com/search?q={query}&where={location}", 63, "general"),
    DirectoryInfo("n49", "https://www.n49.com/search/?q={query}&l={location}", 62, "general"),
    DirectoryInfo("2FindLocal", "https://www.2findlocal.com/search?q={query}&l={location}", 61, "general"),
    DirectoryInfo("eLocal", "https://www.elocal.com/search?q={query}&l={location}", 60, "general"),

    # Tier 5 — Supporting (authority 50-59)
    DirectoryInfo("Tupalo", "https://tupalo.com/en/search/{query}-{location}", 58, "general"),
    DirectoryInfo("Cylex", "https://www.cylex.us.com/search/{query}-{location}", 57, "general"),
    DirectoryInfo("Hub.biz", "https://www.hub.biz/search?q={query}&l={location}", 56, "general"),
    DirectoryInfo("FindOpen", "https://www.findopen.com/search?q={query}&l={location}", 55, "general"),
    DirectoryInfo("B2BYellowpages", "https://www.b2byellowpages.com/search?q={query}&l={location}", 54, "general"),
    DirectoryInfo("LocalStack", "https://www.localstack.com/search?q={query}&l={location}", 53, "general"),
    DirectoryInfo("Yasabe", "https://www.yasabe.com/en/search?q={query}&l={location}", 52, "general"),
    DirectoryInfo("Opendi", "https://www.opendi.us/search?q={query}&l={location}", 51, "general"),
    DirectoryInfo("GoLocal247", "https://www.golocal247.com/search?q={query}&l={location}", 50, "general"),

    # Social & Review Platforms
    DirectoryInfo("LinkedIn Company", "https://www.linkedin.com/search/results/companies/?keywords={query}", 92, "social"),
    DirectoryInfo("Instagram Business", "https://www.instagram.com/explore/tags/{query}", 88, "social"),
    DirectoryInfo("Twitter/X", "https://twitter.com/search?q={query}", 85, "social"),
    DirectoryInfo("Pinterest Business", "https://www.pinterest.com/search/pins/?q={query}", 78, "social"),
    DirectoryInfo("Trustpilot", "https://www.trustpilot.com/search?query={query}", 82, "general"),

    # Industry-Specific
    DirectoryInfo("HomeAdvisor", "https://www.homeadvisor.com/c.{query}.{location}.html", 80, "industry"),
    DirectoryInfo("Avvo (Legal)", "https://www.avvo.com/search?q={query}&loc={location}", 78, "industry"),
    DirectoryInfo("Healthgrades", "https://www.healthgrades.com/find-a-doctor?q={query}&l={location}", 78, "industry"),
    DirectoryInfo("Houzz", "https://www.houzz.com/professionals/search/{query}/{location}", 77, "industry"),
    DirectoryInfo("Zillow (Real Estate)", "https://www.zillow.com/professionals/{query}/{location}", 76, "industry"),
]


class CitationChecker:
    """Check local business citation presence and NAP consistency across directories.

    Usage::

        checker = CitationChecker()
        result = await checker.check_all_citations("Acme Plumbing", "Denver, CO")
        nap_score = checker.calculate_nap_consistency(result)
    """

    def __init__(
        self,
        timeout: int = 15,
        max_concurrent: int = 5,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
    ):
        self._timeout = timeout
        self._max_concurrent = max_concurrent
        self._user_agent = user_agent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def directories(self) -> list[DirectoryInfo]:
        """Return the list of tracked directories."""
        return TOP_DIRECTORIES

    async def check_citation(
        self,
        business_name: str,
        directory: DirectoryInfo,
        location: str = "",
        known_phone: str = "",
        known_address: str = "",
    ) -> dict[str, Any]:
        """Check if a business is listed on a specific directory.

        Args:
            business_name: The business name to search for.
            directory: The directory to check.
            location: City, State or full location string.
            known_phone: Known phone number for NAP verification.
            known_address: Known address for NAP verification.

        Returns:
            Dict with keys: directory_name, url, found, nap_consistent,
            status, authority_score, category, details.
        """
        result: dict[str, Any] = {
            "directory_name": directory.name,
            "search_url": "",
            "listing_url": None,
            "found": False,
            "nap_consistent": None,
            "status": "unknown",
            "authority_score": directory.authority_score,
            "category": directory.category,
            "details": "",
        }

        query = quote_plus(business_name)
        loc = quote_plus(location) if location else ""
        search_url = directory.url_template.replace("{query}", query).replace("{location}", loc)
        result["search_url"] = search_url

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self._user_agent},
                ) as client:
                    resp = await client.get(search_url)

                    if resp.status_code == 200:
                        page_text = resp.text.lower()
                        biz_name_lower = business_name.lower()
                        name_parts = biz_name_lower.split()

                        # Check if business name appears on the page
                        full_match = biz_name_lower in page_text
                        partial_match = sum(
                            1 for part in name_parts if len(part) > 2 and part in page_text
                        )
                        match_ratio = partial_match / max(len(name_parts), 1)

                        if full_match or match_ratio >= 0.7:
                            result["found"] = True
                            result["status"] = "found"

                            # NAP consistency check
                            nap_checks = {"name": full_match}
                            if known_phone:
                                phone_clean = re.sub(r"[^\d]", "", known_phone)
                                phone_variants = [
                                    phone_clean,
                                    f"({phone_clean[:3]}) {phone_clean[3:6]}-{phone_clean[6:]}",
                                    f"{phone_clean[:3]}-{phone_clean[3:6]}-{phone_clean[6:]}",
                                    f"{phone_clean[:3]}.{phone_clean[3:6]}.{phone_clean[6:]}",
                                ]
                                nap_checks["phone"] = any(
                                    v in page_text for v in phone_variants
                                )
                            if known_address:
                                addr_parts = known_address.lower().split()
                                addr_match = sum(
                                    1 for p in addr_parts if len(p) > 2 and p in page_text
                                )
                                nap_checks["address"] = (
                                    addr_match / max(len(addr_parts), 1) >= 0.5
                                )

                            checks_done = [v for v in nap_checks.values()]
                            result["nap_consistent"] = all(checks_done)
                            result["details"] = (
                                f"NAP checks: {nap_checks}. "
                                f"Name match: {"full" if full_match else f"partial ({match_ratio:.0%})"}"
                            )
                        else:
                            result["status"] = "not_found"
                            result["details"] = (
                                f"Business name not found on page. "
                                f"Partial match ratio: {match_ratio:.0%}"
                            )
                    elif resp.status_code == 403:
                        result["status"] = "blocked"
                        result["details"] = "Access blocked by directory (403)"
                    elif resp.status_code == 429:
                        result["status"] = "rate_limited"
                        result["details"] = "Rate limited by directory (429)"
                    else:
                        result["status"] = "error"
                        result["details"] = f"HTTP {resp.status_code}"

            except httpx.TimeoutException:
                result["status"] = "timeout"
                result["details"] = f"Request timed out after {self._timeout}s"
            except httpx.ConnectError as exc:
                result["status"] = "connection_error"
                result["details"] = f"Connection failed: {exc}"
            except Exception as exc:
                result["status"] = "error"
                result["details"] = f"Unexpected error: {type(exc).__name__}: {exc}"
                logger.warning(
                    "Citation check failed for %s on %s: %s",
                    business_name, directory.name, exc,
                )

        return result

    async def check_all_citations(
        self,
        business_name: str,
        location: str = "",
        known_phone: str = "",
        known_address: str = "",
        directories: Optional[list[DirectoryInfo]] = None,
    ) -> list[dict[str, Any]]:
        """Check citation presence across all tracked directories.

        Args:
            business_name: The business name to check.
            location: City, State or full location.
            known_phone: Known phone for NAP verification.
            known_address: Known address for NAP verification.
            directories: Optionally override the directories list.

        Returns:
            List of citation check results sorted by authority score (desc).
        """
        dirs = directories or TOP_DIRECTORIES
        logger.info(
            "Checking %d directories for '%s' in '%s'",
            len(dirs), business_name, location,
        )

        tasks = [
            self.check_citation(
                business_name=business_name,
                directory=d,
                location=location,
                known_phone=known_phone,
                known_address=known_address,
            )
            for d in dirs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[dict[str, Any]] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append({
                    "directory_name": dirs[i].name,
                    "found": False,
                    "status": "error",
                    "authority_score": dirs[i].authority_score,
                    "category": dirs[i].category,
                    "details": f"Task error: {r}",
                    "nap_consistent": None,
                })
            else:
                processed.append(r)

        # Sort by authority score descending
        processed.sort(key=lambda x: x.get("authority_score", 0), reverse=True)

        found = sum(1 for r in processed if r.get("found"))
        logger.info(
            "Citation check complete: %d/%d found for '%s'",
            found, len(processed), business_name,
        )
        return processed

    @staticmethod
    def calculate_nap_consistency(citations: list[dict[str, Any]]) -> float:
        """Calculate NAP consistency score across all found citations.

        Args:
            citations: List of citation check results.

        Returns:
            Float 0.0-1.0 representing NAP consistency ratio.
        """
        found_citations = [
            c for c in citations
            if c.get("found") and c.get("nap_consistent") is not None
        ]
        if not found_citations:
            return 0.0

        consistent = sum(1 for c in found_citations if c["nap_consistent"])
        return consistent / len(found_citations)

    @staticmethod
    def get_missing_high_authority(
        citations: list[dict[str, Any]],
        min_authority: int = 70,
    ) -> list[dict[str, Any]]:
        """Identify missing citations on high-authority directories.

        Args:
            citations: List of citation check results.
            min_authority: Minimum authority score threshold.

        Returns:
            List of directories where the business is not found.
        """
        return [
            c for c in citations
            if not c.get("found")
            and c.get("authority_score", 0) >= min_authority
            and c.get("status") != "blocked"
        ]

    @staticmethod
    def get_inconsistent_citations(
        citations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find citations with NAP inconsistencies."""
        return [
            c for c in citations
            if c.get("found") and c.get("nap_consistent") is False
        ]

    @staticmethod
    def generate_citation_summary(citations: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate a comprehensive citation health summary.

        Returns:
            Dict with total, found, missing, nap stats, tier breakdown,
            and an overall score.
        """
        total = len(citations)
        found = [c for c in citations if c.get("found")]
        missing = [c for c in citations if not c.get("found") and c.get("status") != "blocked"]
        blocked = [c for c in citations if c.get("status") == "blocked"]
        consistent = [c for c in found if c.get("nap_consistent") is True]
        inconsistent = [c for c in found if c.get("nap_consistent") is False]

        # Tier breakdown
        tiers = {
            "tier_1_critical": {"total": 0, "found": 0, "min_authority": 90},
            "tier_2_high": {"total": 0, "found": 0, "min_authority": 80},
            "tier_3_important": {"total": 0, "found": 0, "min_authority": 70},
            "tier_4_valuable": {"total": 0, "found": 0, "min_authority": 60},
            "tier_5_supporting": {"total": 0, "found": 0, "min_authority": 0},
        }
        for c in citations:
            score = c.get("authority_score", 0)
            if score >= 90:
                tier = "tier_1_critical"
            elif score >= 80:
                tier = "tier_2_high"
            elif score >= 70:
                tier = "tier_3_important"
            elif score >= 60:
                tier = "tier_4_valuable"
            else:
                tier = "tier_5_supporting"
            tiers[tier]["total"] += 1
            if c.get("found"):
                tiers[tier]["found"] += 1

        # Calculate weighted score (higher authority = more weight)
        max_possible = sum(c.get("authority_score", 0) for c in citations if c.get("status") != "blocked")
        actual = sum(c.get("authority_score", 0) for c in found)
        weighted_score = (actual / max_possible * 100) if max_possible > 0 else 0.0

        # NAP consistency score
        nap_score = (
            len(consistent) / max(len(consistent) + len(inconsistent), 1) * 100
        )

        # Combined citation score
        citation_score = (weighted_score * 0.6) + (nap_score * 0.4)

        return {
            "total_directories": total,
            "found_count": len(found),
            "missing_count": len(missing),
            "blocked_count": len(blocked),
            "nap_consistent_count": len(consistent),
            "nap_inconsistent_count": len(inconsistent),
            "presence_rate": len(found) / max(total - len(blocked), 1) * 100,
            "nap_consistency_rate": nap_score,
            "weighted_score": round(weighted_score, 1),
            "citation_score": round(citation_score, 1),
            "tier_breakdown": tiers,
            "missing_high_authority": [
                {"name": c["directory_name"], "authority": c.get("authority_score", 0)}
                for c in missing if c.get("authority_score", 0) >= 70
            ],
            "inconsistent_listings": [
                {"name": c["directory_name"], "details": c.get("details", "")}
                for c in inconsistent
            ],
        }
