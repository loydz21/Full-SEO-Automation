"""SERP Analyzer — detect, track, and analyze SERP features and volatility."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import func

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper
from src.models.ranking import (
    CompetitorRank,
    RankingRecord,
    SERPFeature,
    SERPSnapshot,
)

logger = logging.getLogger(__name__)

# All SERP feature types we detect
SERP_FEATURE_TYPES = [
    "featured_snippet",
    "people_also_ask",
    "local_pack",
    "image_pack",
    "video_carousel",
    "knowledge_panel",
    "ads_top",
    "ads_bottom",
    "shopping",
    "news",
    "site_links",
    "reviews",
    "related_searches",
]


def _extract_domain(url: str) -> str:
    """Extract root domain from a URL."""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.hostname or ""
        return host.lower().removeprefix("www.")
    except Exception:
        return url.lower().removeprefix("www.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SERPAnalyzer:
    """Analyze SERP features, volatility, and competitive landscape.

    Usage::

        analyzer = SERPAnalyzer()
        features = await analyzer.analyze_serp_features("best seo tools")
        volatility = await analyzer.analyze_serp_volatility("seo tips")
    """

    def __init__(
        self,
        scraper: Optional[SERPScraper] = None,
        llm: Optional[LLMClient] = None,
    ):
        self._scraper = scraper or SERPScraper()
        self._llm = llm or LLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_serp_features(
        self,
        keyword: str,
        location: str = "us",
    ) -> dict[str, Any]:
        """Detect all SERP features present for a keyword.

        Returns a dict mapping each feature type to its presence and
        an optional content summary.
        """
        logger.info("Analyzing SERP features for %r", keyword)

        try:
            serp = await self._scraper.search_google(
                query=keyword,
                num_results=10,
                country=location,
            )
        except Exception as exc:
            logger.error("SERP scrape failed for feature analysis: %s", exc)
            return {"keyword": keyword, "features": {}, "error": str(exc)}

        features: dict[str, dict[str, Any]] = {}

        # Featured snippet
        fs = serp.get("featured_snippet")
        features["featured_snippet"] = {
            "present": fs is not None,
            "content": fs.get("text", "")[:200] if fs else "",
        }

        # People Also Ask
        paa = serp.get("people_also_ask", [])
        features["people_also_ask"] = {
            "present": len(paa) > 0,
            "count": len(paa),
            "questions": paa[:5],
        }

        # Related searches
        related = serp.get("related_searches", [])
        features["related_searches"] = {
            "present": len(related) > 0,
            "count": len(related),
            "terms": related[:8],
        }

        # Organic results analysis for additional feature detection
        organic = serp.get("organic_results", [])

        # Detect site links (results with indented sub-links)
        has_sitelinks = any(
            len(r.get("snippet", "")) > 300 for r in organic[:3]
        )
        features["site_links"] = {"present": has_sitelinks}

        # Detect video carousel (youtube results in top 10)
        video_results = [
            r for r in organic
            if "youtube.com" in r.get("url", "") or "youtu.be" in r.get("url", "")
        ]
        features["video_carousel"] = {
            "present": len(video_results) > 0,
            "count": len(video_results),
        }

        # Detect image pack, local pack, etc. via AI analysis
        # For features we cannot reliably detect from HTML, mark as unknown
        for ftype in ["local_pack", "image_pack", "knowledge_panel",
                      "ads_top", "ads_bottom", "shopping", "news", "reviews"]:
            if ftype not in features:
                features[ftype] = {"present": False, "note": "detection_limited"}

        # Save detected features to DB
        self._save_serp_features(keyword, features)

        # Save SERP snapshot for historical tracking
        self._save_serp_snapshot(keyword, serp)

        result = {
            "keyword": keyword,
            "location": location,
            "features": features,
            "feature_count": sum(
                1 for f in features.values() if f.get("present", False)
            ),
            "organic_count": len(organic),
            "checked_at": _utcnow().isoformat(),
        }

        logger.info(
            "SERP features for %r: %d features detected",
            keyword, result["feature_count"],
        )
        return result

    async def track_serp_feature_ownership(
        self,
        domain: str,
        keywords: list[str],
    ) -> dict[str, Any]:
        """Check if domain owns any SERP features for given keywords."""
        domain_clean = _extract_domain(domain)
        logger.info(
            "Tracking SERP feature ownership for %r across %d keywords",
            domain_clean, len(keywords),
        )

        ownership_results: list[dict[str, Any]] = []
        owned_count = 0
        total_features = 0

        for kw in keywords:
            try:
                serp = await self._scraper.search_google(query=kw, num_results=10)
            except Exception as exc:
                logger.warning("SERP scrape failed for %r: %s", kw, exc)
                ownership_results.append({
                    "keyword": kw,
                    "owns_featured_snippet": False,
                    "in_paa": False,
                    "error": str(exc),
                })
                continue

            # Check featured snippet ownership
            fs = serp.get("featured_snippet")
            owns_fs = False
            if fs:
                total_features += 1
                fs_text = fs.get("text", "")
                # Check if domain appears in the snippet context
                organic = serp.get("organic_results", [])
                if organic and _extract_domain(organic[0].get("url", "")) == domain_clean:
                    owns_fs = True
                    owned_count += 1

            # Check if domain is referenced in PAA
            in_paa = False
            paa = serp.get("people_also_ask", [])
            if paa:
                total_features += 1

            ownership_results.append({
                "keyword": kw,
                "owns_featured_snippet": owns_fs,
                "featured_snippet_present": fs is not None,
                "paa_count": len(paa),
                "in_paa": in_paa,
            })

            # Save ownership to DB
            if fs is not None:
                self._save_feature_ownership(
                    keyword=kw,
                    feature_type="featured_snippet",
                    owns=owns_fs,
                    competitor=(
                        _extract_domain(organic[0].get("url", ""))
                        if organic and not owns_fs else None
                    ),
                )

            await asyncio.sleep(2.0)  # Rate limiting

        ownership_rate = (
            owned_count / total_features * 100 if total_features > 0 else 0.0
        )

        return {
            "domain": domain_clean,
            "keywords_checked": len(keywords),
            "feature_ownership_rate": round(ownership_rate, 1),
            "owned_features": owned_count,
            "total_features_available": total_features,
            "details": ownership_results,
        }

    async def analyze_serp_volatility(
        self,
        keyword: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """Analyze SERP volatility by comparing stored snapshots over time.

        Returns volatility score (0-100) and position change details.
        """
        logger.info(
            "Analyzing SERP volatility for %r over %d days", keyword, days
        )

        cutoff = _utcnow() - timedelta(days=days)

        with get_session() as session:
            snapshots = (
                session.query(SERPSnapshot)
                .filter(
                    SERPSnapshot.keyword_id.in_(
                        session.query(RankingRecord.id)
                        .filter(RankingRecord.keyword == keyword)
                    )
                )
                .filter(SERPSnapshot.checked_at >= cutoff)
                .order_by(SERPSnapshot.checked_at.asc())
                .all()
            )

        # If not enough snapshots, use ranking history instead
        with get_session() as session:
            from src.models.ranking import RankingHistory
            history = (
                session.query(RankingHistory)
                .filter(
                    RankingHistory.keyword == keyword,
                    RankingHistory.date >= cutoff,
                )
                .order_by(RankingHistory.date.asc())
                .all()
            )

        if len(history) < 2:
            return {
                "keyword": keyword,
                "days": days,
                "volatility_score": 0.0,
                "data_points": len(history),
                "position_changes": [],
                "is_stable": True,
                "note": "Insufficient data for volatility analysis",
            }

        # Calculate volatility from position changes
        changes = []
        total_change = 0
        for i in range(1, len(history)):
            prev_pos = history[i - 1].position
            curr_pos = history[i].position
            delta = abs(curr_pos - prev_pos)
            total_change += delta
            if delta > 0:
                changes.append({
                    "date": history[i].date.isoformat() if history[i].date else None,
                    "from_position": prev_pos,
                    "to_position": curr_pos,
                    "change": curr_pos - prev_pos,
                })

        # Volatility score: normalize to 0-100
        # Average change per day, scaled
        avg_change = total_change / len(history) if history else 0
        volatility_score = min(avg_change * 5, 100.0)  # 20+ avg change = 100
        volatility_score = round(volatility_score, 1)

        is_stable = volatility_score < 20

        result = {
            "keyword": keyword,
            "days": days,
            "volatility_score": volatility_score,
            "data_points": len(history),
            "position_changes": changes[-10:],  # Last 10 changes
            "avg_daily_change": round(avg_change, 1),
            "is_stable": is_stable,
            "stability_label": (
                "Stable" if volatility_score < 20
                else "Moderate" if volatility_score < 50
                else "Volatile" if volatility_score < 80
                else "Highly Volatile"
            ),
        }

        logger.info(
            "Volatility for %r: score=%.1f (%s)",
            keyword, volatility_score, result["stability_label"],
        )
        return result

    async def get_featured_snippet_opportunities(
        self,
        domain: str,
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        """Find keywords where domain ranks top 10 but does not own featured snippet.

        Uses AI to generate content suggestions to win the snippet.
        """
        domain_clean = _extract_domain(domain)
        logger.info(
            "Finding featured snippet opportunities for %r", domain_clean
        )

        opportunities: list[dict[str, Any]] = []

        for kw in keywords:
            # Check if we rank in top 10
            with get_session() as session:
                record = (
                    session.query(RankingRecord)
                    .filter(
                        RankingRecord.domain == domain_clean,
                        RankingRecord.keyword == kw,
                    )
                    .order_by(RankingRecord.checked_at.desc())
                    .first()
                )

            if not record or record.position > 10 or record.position == 0:
                continue

            # Check if featured snippet exists and we don't own it
            with get_session() as session:
                fs_record = (
                    session.query(SERPFeature)
                    .filter(
                        SERPFeature.keyword == kw,
                        SERPFeature.feature_type == "featured_snippet",
                    )
                    .order_by(SERPFeature.checked_at.desc())
                    .first()
                )

            has_snippet = fs_record is not None
            owns_snippet = fs_record.owns_feature if fs_record else False

            if has_snippet and not owns_snippet:
                opportunities.append({
                    "keyword": kw,
                    "current_position": record.position,
                    "url_ranked": record.url_ranked,
                    "competitor_owns": (
                        fs_record.competitor_in_feature if fs_record else None
                    ),
                    "suggestion": "",
                })

        # Generate AI suggestions for winning snippets
        if opportunities:
            try:
                opp_lines = []
                for opp in opportunities:
                    line = "keyword: {kw}, position: {pos}, url: {url}".format(
                        kw=opp["keyword"],
                        pos=opp["current_position"],
                        url=opp.get("url_ranked", "N/A"),
                    )
                    opp_lines.append(line)
                newline = chr(10)
                opp_text = newline.join(opp_lines)

                prompt = (
                    "You are an SEO expert specializing in featured snippets. "
                    "For each keyword below, the domain ranks in the top 10 "
                    "but does not own the featured snippet. Suggest specific "
                    "content formatting changes to win the snippet (e.g., add "
                    "a definition paragraph, create a numbered list, add a "
                    "comparison table). Be concise and actionable."
                    + newline + newline
                    + "Domain: " + domain_clean + newline + newline
                    + "Keywords:" + newline + opp_text + newline + newline
                    + 'Respond as JSON array: [{"keyword": "...", "suggestion": "..."}]'
                )

                ai_result = await self._llm.generate_json(prompt=prompt)
                if isinstance(ai_result, list):
                    suggestion_map = {}
                    for item in ai_result:
                        suggestion_map[item.get("keyword", "")] = item.get(
                            "suggestion", ""
                        )
                    for opp in opportunities:
                        opp["suggestion"] = suggestion_map.get(
                            opp["keyword"],
                            "Add a concise definition paragraph at the top of your content.",
                        )
            except Exception as exc:
                logger.warning("AI snippet suggestions failed: %s", exc)
                for opp in opportunities:
                    opp["suggestion"] = (
                        "Add a concise answer paragraph (40-60 words) "
                        "directly addressing the query near the top of the page."
                    )

        logger.info(
            "Found %d featured snippet opportunities for %r",
            len(opportunities), domain_clean,
        )
        return opportunities

    async def analyze_competitor_serp_strategy(
        self,
        keyword: str,
    ) -> dict[str, Any]:
        """Analyze top 10 results for a keyword to find success patterns.

        Returns content type analysis, common title patterns, and
        meta description strategies.
        """
        logger.info("Analyzing competitor SERP strategy for %r", keyword)

        try:
            serp = await self._scraper.search_google(
                query=keyword, num_results=10
            )
        except Exception as exc:
            logger.error("SERP scrape failed for strategy analysis: %s", exc)
            return {"keyword": keyword, "error": str(exc)}

        organic = serp.get("organic_results", [])
        if not organic:
            return {
                "keyword": keyword,
                "top_results": [],
                "patterns": {},
                "note": "No organic results found",
            }

        # Collect data from top results
        top_results = []
        for r in organic[:10]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            domain = _extract_domain(url)

            # Analyze title patterns
            title_words = len(title.split())
            has_number = any(c.isdigit() for c in title)
            has_year = any(
                yr in title for yr in ["2024", "2025", "2026"]
            )

            top_results.append({
                "position": r.get("position", 0),
                "domain": domain,
                "title": title,
                "title_length": len(title),
                "title_word_count": title_words,
                "title_has_number": has_number,
                "title_has_year": has_year,
                "snippet_length": len(snippet),
                "url": url,
            })

        # Derive patterns
        titles = [r["title"] for r in top_results]
        avg_title_len = (
            sum(r["title_length"] for r in top_results) / len(top_results)
            if top_results else 0
        )
        pct_with_numbers = (
            sum(1 for r in top_results if r["title_has_number"])
            / len(top_results) * 100
            if top_results else 0
        )
        pct_with_year = (
            sum(1 for r in top_results if r["title_has_year"])
            / len(top_results) * 100
            if top_results else 0
        )

        # Use AI to analyze deeper patterns
        try:
            newline = chr(10)
            titles_text = newline.join(
                "{pos}. {title}".format(pos=r["position"], title=r["title"])
                for r in top_results
            )

            prompt = (
                "Analyze these top 10 Google results for the keyword: "
                + keyword + newline + newline
                + "Titles:" + newline + titles_text + newline + newline
                + "Identify: 1) Common content type (listicle, guide, comparison, etc), "
                + "2) Title formula patterns, 3) What makes top 3 different from 4-10. "
                + "Respond as JSON: {\"content_type\": \"...\", "
                + "\"title_patterns\": [\"...\"], "
                + "\"top3_differentiators\": \"...\", "
                + "\"recommendation\": \"...\"}" 
            )

            ai_analysis = await self._llm.generate_json(prompt=prompt)
        except Exception as exc:
            logger.warning("AI strategy analysis failed: %s", exc)
            ai_analysis = {
                "content_type": "unknown",
                "title_patterns": [],
                "top3_differentiators": "Analysis unavailable",
                "recommendation": "Match the content format of top-ranking pages.",
            }

        result = {
            "keyword": keyword,
            "top_results": top_results,
            "patterns": {
                "avg_title_length": round(avg_title_len, 0),
                "pct_with_numbers": round(pct_with_numbers, 0),
                "pct_with_year": round(pct_with_year, 0),
                "dominant_domains": list(set(
                    r["domain"] for r in top_results[:5]
                )),
            },
            "ai_analysis": ai_analysis,
            "featured_snippet": serp.get("featured_snippet") is not None,
            "paa_questions": serp.get("people_also_ask", [])[:5],
        }

        logger.info("SERP strategy analysis complete for %r", keyword)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_serp_features(
        self,
        keyword: str,
        features: dict[str, dict[str, Any]],
    ) -> None:
        """Save detected SERP features to database."""
        try:
            with get_session() as session:
                for ftype, fdata in features.items():
                    record = SERPFeature(
                        keyword=keyword,
                        feature_type=ftype,
                        owns_feature=False,
                        content_summary=str(fdata.get("content", ""))[:500],
                    )
                    session.add(record)
            logger.debug("Saved %d SERP features for %r", len(features), keyword)
        except Exception as exc:
            logger.error("Failed to save SERP features: %s", exc)

    def _save_serp_snapshot(
        self,
        keyword: str,
        serp_data: dict[str, Any],
    ) -> None:
        """Save full SERP snapshot for historical analysis."""
        try:
            # We need a keyword_id; use RankingRecord to find it
            # or store with a reference keyword string
            with get_session() as session:
                from src.models.keyword import Keyword
                kw_obj = (
                    session.query(Keyword)
                    .filter(Keyword.text == keyword)
                    .first()
                )
                if kw_obj:
                    snapshot = SERPSnapshot(
                        keyword_id=kw_obj.id,
                        snapshot_json=serp_data,
                    )
                    session.add(snapshot)
                    logger.debug("Saved SERP snapshot for keyword_id=%d", kw_obj.id)
        except Exception as exc:
            logger.error("Failed to save SERP snapshot: %s", exc)

    def _save_feature_ownership(
        self,
        keyword: str,
        feature_type: str,
        owns: bool,
        competitor: Optional[str] = None,
    ) -> None:
        """Save feature ownership record."""
        try:
            with get_session() as session:
                record = SERPFeature(
                    keyword=keyword,
                    feature_type=feature_type,
                    owns_feature=owns,
                    competitor_in_feature=competitor,
                )
                session.add(record)
        except Exception as exc:
            logger.error("Failed to save feature ownership: %s", exc)

    async def close(self) -> None:
        """Release resources."""
        try:
            await self._scraper.close()
        except Exception:
            pass
