"""Rank Tracker — core module for tracking keyword rankings across SERPs."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import desc, func

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper
from src.models.ranking import (
    CompetitorRank,
    RankingHistory,
    RankingRecord,
    SERPFeature,
    VisibilityScore,
)

logger = logging.getLogger(__name__)


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


class RankTracker:
    """Track keyword rankings, visibility scores, and competitor positions.

    Usage::

        tracker = RankTracker()
        result = await tracker.track_keyword("example.com", "best seo tools")
        bulk = await tracker.track_keywords_bulk("example.com", ["seo", "sem"])
    """

    def __init__(
        self,
        scraper: Optional[SERPScraper] = None,
        llm: Optional[LLMClient] = None,
        rate_limit_delay: float = 3.0,
    ):
        self._scraper = scraper or SERPScraper()
        self._llm = llm or LLMClient()
        self._rate_limit_delay = rate_limit_delay

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def track_keyword(
        self,
        domain: str,
        keyword: str,
        location: str = "us",
        device: str = "desktop",
    ) -> dict[str, Any]:
        """Check current SERP position for a single keyword.

        Returns dict with keyword, position, url_ranked, serp_features,
        and competitors_in_top10.
        """
        domain_clean = _extract_domain(domain)
        logger.info("Tracking keyword %r for domain %r", keyword, domain_clean)

        try:
            serp = await self._scraper.search_google(
                query=keyword,
                num_results=20,
                country=location,
            )
        except Exception as exc:
            logger.error("SERP scrape failed for %r: %s", keyword, exc)
            return {
                "keyword": keyword,
                "position": 0,
                "url_ranked": None,
                "serp_features": {},
                "competitors_in_top10": [],
                "error": str(exc),
            }

        organic = serp.get("organic_results", [])
        position = 0
        url_ranked = None
        competitors_top10: list[dict[str, Any]] = []

        for item in organic:
            item_domain = _extract_domain(item.get("url", ""))
            item_pos = item.get("position", 0)
            if item_domain == domain_clean and position == 0:
                position = item_pos
                url_ranked = item.get("url", "")
            if item_pos <= 10 and item_domain != domain_clean:
                competitors_top10.append({
                    "domain": item_domain,
                    "position": item_pos,
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                })

        serp_features = {
            "featured_snippet": serp.get("featured_snippet") is not None,
            "people_also_ask": len(serp.get("people_also_ask", [])) > 0,
            "related_searches": len(serp.get("related_searches", [])) > 0,
        }

        # Persist to database
        self._save_ranking_record(
            keyword=keyword,
            domain=domain_clean,
            position=position,
            url_ranked=url_ranked,
            serp_features=serp_features,
            device=device,
            location=location,
        )
        self._save_ranking_history(keyword, domain_clean, position)
        self._save_competitor_ranks(keyword, competitors_top10)

        result = {
            "keyword": keyword,
            "position": position,
            "url_ranked": url_ranked,
            "serp_features": serp_features,
            "competitors_in_top10": competitors_top10,
        }
        logger.info(
            "Keyword %r position=%d for %r", keyword, position, domain_clean
        )
        return result

    async def track_keywords_bulk(
        self,
        domain: str,
        keywords: list[str],
        location: str = "us",
    ) -> list[dict[str, Any]]:
        """Track multiple keywords with rate limiting and progress tracking."""
        results: list[dict[str, Any]] = []
        total = len(keywords)
        logger.info("Bulk tracking %d keywords for %r", total, domain)

        for idx, kw in enumerate(keywords, 1):
            logger.info("Tracking keyword %d/%d: %r", idx, total, kw)
            result = await self.track_keyword(domain, kw, location=location)
            result["progress"] = idx
            result["total"] = total
            results.append(result)

            if idx < total:
                await asyncio.sleep(self._rate_limit_delay)

        logger.info("Bulk tracking complete: %d keywords processed", total)
        return results

    def get_ranking_history(
        self,
        domain: str,
        keyword: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return daily position history for a keyword with change deltas."""
        domain_clean = _extract_domain(domain)
        cutoff = _utcnow() - timedelta(days=days)

        with get_session() as session:
            rows = (
                session.query(RankingHistory)
                .filter(
                    RankingHistory.keyword == keyword,
                    RankingHistory.domain == domain_clean,
                    RankingHistory.date >= cutoff,
                )
                .order_by(RankingHistory.date.asc())
                .all()
            )

        history = []
        for row in rows:
            history.append({
                "keyword": row.keyword,
                "position": row.position,
                "change": row.change,
                "date": row.date.isoformat() if row.date else None,
            })

        logger.info(
            "History for %r / %r: %d records over %d days",
            keyword, domain_clean, len(history), days,
        )
        return history

    def calculate_visibility_score(
        self,
        domain: str,
    ) -> dict[str, Any]:
        """Calculate aggregated visibility score based on all tracked keywords.

        Score 0-100 weighted by position brackets. Returns score, avg_position,
        top3/top10/top20 counts, and total keyword count.
        """
        domain_clean = _extract_domain(domain)

        with get_session() as session:
            # Get latest ranking for each keyword
            subq = (
                session.query(
                    RankingRecord.keyword,
                    func.max(RankingRecord.checked_at).label("latest"),
                )
                .filter(RankingRecord.domain == domain_clean)
                .group_by(RankingRecord.keyword)
                .subquery()
            )

            records = (
                session.query(RankingRecord)
                .join(
                    subq,
                    (RankingRecord.keyword == subq.c.keyword)
                    & (RankingRecord.checked_at == subq.c.latest),
                )
                .filter(RankingRecord.domain == domain_clean)
                .all()
            )

        if not records:
            return {
                "domain": domain_clean,
                "score": 0.0,
                "keyword_count": 0,
                "avg_position": 0.0,
                "top3_count": 0,
                "top10_count": 0,
                "top20_count": 0,
            }

        positions = [r.position for r in records if r.position > 0]
        total_kw = len(records)
        ranked_kw = len(positions)

        top3 = sum(1 for p in positions if p <= 3)
        top10 = sum(1 for p in positions if p <= 10)
        top20 = sum(1 for p in positions if p <= 20)
        avg_pos = sum(positions) / ranked_kw if ranked_kw else 0.0

        # Visibility score: weighted by position
        # Position 1 = 10 pts, 2 = 9, 3 = 8, ... 10 = 1, >10 = 0
        max_possible = total_kw * 10
        earned = 0.0
        for p in positions:
            if 1 <= p <= 10:
                earned += 11 - p
        score = (earned / max_possible * 100) if max_possible > 0 else 0.0
        score = round(min(score, 100.0), 1)

        result = {
            "domain": domain_clean,
            "score": score,
            "keyword_count": total_kw,
            "avg_position": round(avg_pos, 1),
            "top3_count": top3,
            "top10_count": top10,
            "top20_count": top20,
        }

        # Persist visibility score
        self._save_visibility_score(domain_clean, result)
        logger.info("Visibility score for %r: %.1f", domain_clean, score)
        return result

    def detect_ranking_changes(
        self,
        domain: str,
        threshold: int = 5,
    ) -> list[dict[str, Any]]:
        """Find keywords with position changes >= threshold since last check."""
        domain_clean = _extract_domain(domain)

        with get_session() as session:
            # Get the two most recent records per keyword
            subq = (
                session.query(
                    RankingRecord.keyword,
                    RankingRecord.position,
                    RankingRecord.checked_at,
                    func.row_number()
                    .over(
                        partition_by=RankingRecord.keyword,
                        order_by=RankingRecord.checked_at.desc(),
                    )
                    .label("rn"),
                )
                .filter(RankingRecord.domain == domain_clean)
                .subquery()
            )

            # Get rows with rn=1 (latest) and rn=2 (previous)
            latest_rows = (
                session.query(subq)
                .filter(subq.c.rn <= 2)
                .all()
            )

        # Group by keyword
        kw_data: dict[str, list] = {}
        for row in latest_rows:
            kw = row[0]
            pos = row[1]
            checked = row[2]
            if kw not in kw_data:
                kw_data[kw] = []
            kw_data[kw].append({"position": pos, "checked_at": checked})

        changes = []
        for kw, entries in kw_data.items():
            entries.sort(key=lambda x: x["checked_at"], reverse=True)
            if len(entries) < 2:
                continue
            current_pos = entries[0]["position"]
            prev_pos = entries[1]["position"]
            delta = prev_pos - current_pos  # positive = improved
            if abs(delta) >= threshold:
                direction = "improved" if delta > 0 else "dropped"
                changes.append({
                    "keyword": kw,
                    "current_position": current_pos,
                    "previous_position": prev_pos,
                    "change": delta,
                    "direction": direction,
                })

        changes.sort(key=lambda x: abs(x["change"]), reverse=True)
        logger.info(
            "Detected %d ranking changes (threshold=%d) for %r",
            len(changes), threshold, domain_clean,
        )
        return changes

    async def get_top_opportunities(
        self,
        domain: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find keywords ranking 4-20 (striking distance) with AI suggestions."""
        domain_clean = _extract_domain(domain)

        with get_session() as session:
            subq = (
                session.query(
                    RankingRecord.keyword,
                    func.max(RankingRecord.checked_at).label("latest"),
                )
                .filter(RankingRecord.domain == domain_clean)
                .group_by(RankingRecord.keyword)
                .subquery()
            )

            records = (
                session.query(RankingRecord)
                .join(
                    subq,
                    (RankingRecord.keyword == subq.c.keyword)
                    & (RankingRecord.checked_at == subq.c.latest),
                )
                .filter(
                    RankingRecord.domain == domain_clean,
                    RankingRecord.position >= 4,
                    RankingRecord.position <= 20,
                )
                .order_by(RankingRecord.position.asc())
                .limit(limit)
                .all()
            )

        if not records:
            logger.info("No striking-distance keywords found for %r", domain_clean)
            return []

        opportunities = []
        for rec in records:
            opportunities.append({
                "keyword": rec.keyword,
                "position": rec.position,
                "url_ranked": rec.url_ranked,
                "suggestion": "",
            })

        # Generate AI suggestions in batch
        try:
            opp_lines = []
            for opp in opportunities:
                line = "keyword: {kw}, position: {pos}".format(
                    kw=opp["keyword"], pos=opp["position"]
                )
                opp_lines.append(line)
            newline = chr(10)
            opp_text = newline.join(opp_lines)

            prompt = (
                "You are an SEO expert. For each keyword below that ranks in "
                "positions 4-20 (striking distance), suggest a specific, "
                "actionable optimization to improve ranking. Be concise."
                + newline + newline
                + "Domain: " + domain_clean + newline + newline
                + "Keywords:" + newline + opp_text + newline + newline
                + "Respond as JSON array: "
                + '[{"keyword": "...", "suggestion": "..."}]'
            )

            ai_result = await self._llm.generate_json(prompt=prompt)
            if isinstance(ai_result, list):
                suggestion_map = {}
                for item in ai_result:
                    kw_key = item.get("keyword", "")
                    suggestion_map[kw_key] = item.get("suggestion", "")
                for opp in opportunities:
                    opp["suggestion"] = suggestion_map.get(
                        opp["keyword"], "Optimize content and internal links."
                    )
        except Exception as exc:
            logger.warning("AI suggestion generation failed: %s", exc)
            for opp in opportunities:
                opp["suggestion"] = "Optimize on-page SEO and add internal links."

        logger.info(
            "Found %d striking-distance opportunities for %r",
            len(opportunities), domain_clean,
        )
        return opportunities

    async def compare_with_competitors(
        self,
        domain: str,
        competitors: list[str],
        keywords: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Side-by-side ranking comparison across domains.

        Returns position matrix, winner per keyword, and visibility comparison.
        """
        domain_clean = _extract_domain(domain)
        comp_clean = [_extract_domain(c) for c in competitors]
        all_domains = [domain_clean] + comp_clean

        # Determine keywords to compare
        if not keywords:
            with get_session() as session:
                kw_rows = (
                    session.query(RankingRecord.keyword)
                    .filter(RankingRecord.domain == domain_clean)
                    .distinct()
                    .limit(50)
                    .all()
                )
            keywords = [r[0] for r in kw_rows]

        if not keywords:
            return {
                "domains": all_domains,
                "keywords": [],
                "matrix": {},
                "winners": {},
                "visibility": {},
            }

        # Build comparison matrix
        matrix: dict[str, dict[str, int]] = {}
        winners: dict[str, str] = {}

        for kw in keywords:
            matrix[kw] = {}
            # Get our latest position
            our_pos = self._get_latest_position(domain_clean, kw)
            matrix[kw][domain_clean] = our_pos

            # Get competitor positions from DB or track fresh
            for comp in comp_clean:
                comp_pos = self._get_latest_position(comp, kw)
                if comp_pos == 0:
                    # Track fresh for competitor
                    try:
                        result = await self.track_keyword(comp, kw)
                        comp_pos = result.get("position", 0)
                    except Exception:
                        comp_pos = 0
                matrix[kw][comp] = comp_pos

            # Determine winner (lowest position > 0)
            ranked = {
                d: p for d, p in matrix[kw].items() if p > 0
            }
            if ranked:
                winner = min(ranked, key=ranked.get)
                winners[kw] = winner
            else:
                winners[kw] = "none"

        # Calculate visibility per domain
        visibility: dict[str, dict[str, Any]] = {}
        for d in all_domains:
            positions = [matrix[kw].get(d, 0) for kw in keywords]
            ranked_positions = [p for p in positions if p > 0]
            top10 = sum(1 for p in ranked_positions if p <= 10)
            avg_p = (
                sum(ranked_positions) / len(ranked_positions)
                if ranked_positions else 0.0
            )
            visibility[d] = {
                "avg_position": round(avg_p, 1),
                "top10_count": top10,
                "ranked_count": len(ranked_positions),
                "total_keywords": len(keywords),
            }

        result = {
            "domains": all_domains,
            "keywords": keywords,
            "matrix": matrix,
            "winners": winners,
            "visibility": visibility,
        }
        logger.info(
            "Competitor comparison: %d domains, %d keywords",
            len(all_domains), len(keywords),
        )
        return result

    def schedule_tracking(
        self,
        domain: str,
        keywords: list[str],
        frequency: str = "daily",
    ) -> dict[str, Any]:
        """Set up recurring rank checks (metadata only — execution by scheduler)."""
        domain_clean = _extract_domain(domain)
        schedule_info = {
            "domain": domain_clean,
            "keywords": keywords,
            "keyword_count": len(keywords),
            "frequency": frequency,
            "created_at": _utcnow().isoformat(),
            "status": "scheduled",
        }

        # Persist as a JSON file for the scheduler to pick up
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        schedule_dir = os.path.join(base_dir, "data", "schedules")
        os.makedirs(schedule_dir, exist_ok=True)
        fname = "rank_tracking_" + domain_clean.replace(".", "_") + ".json"
        schedule_file = os.path.join(schedule_dir, fname)
        with open(schedule_file, "w") as f:
            json.dump(schedule_info, f, indent=2)

        logger.info(
            "Scheduled %s tracking for %r (%d keywords)",
            frequency, domain_clean, len(keywords),
        )
        return schedule_info

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_ranking_record(
        self,
        keyword: str,
        domain: str,
        position: int,
        url_ranked: Optional[str],
        serp_features: dict,
        device: str = "desktop",
        location: str = "us",
    ) -> None:
        """Persist a ranking record to the database."""
        try:
            with get_session() as session:
                record = RankingRecord(
                    keyword=keyword,
                    domain=domain,
                    position=position,
                    url_ranked=url_ranked,
                    serp_features_json=serp_features,
                    device=device,
                    location=location,
                )
                session.add(record)
            logger.debug("Saved ranking record: %r pos=%d", keyword, position)
        except Exception as exc:
            logger.error("Failed to save ranking record: %s", exc)

    def _save_ranking_history(
        self,
        keyword: str,
        domain: str,
        position: int,
    ) -> None:
        """Save daily history entry with change delta from previous."""
        try:
            with get_session() as session:
                prev = (
                    session.query(RankingHistory)
                    .filter(
                        RankingHistory.keyword == keyword,
                        RankingHistory.domain == domain,
                    )
                    .order_by(RankingHistory.date.desc())
                    .first()
                )
                prev_pos = prev.position if prev else 0
                change = prev_pos - position if prev_pos > 0 else 0

                entry = RankingHistory(
                    keyword=keyword,
                    domain=domain,
                    position=position,
                    change=change,
                )
                session.add(entry)
            logger.debug(
                "Saved history: %r pos=%d change=%d", keyword, position, change
            )
        except Exception as exc:
            logger.error("Failed to save ranking history: %s", exc)

    def _save_competitor_ranks(
        self,
        keyword: str,
        competitors: list[dict[str, Any]],
    ) -> None:
        """Persist competitor ranking data."""
        try:
            with get_session() as session:
                for comp in competitors:
                    record = CompetitorRank(
                        keyword=keyword,
                        competitor_domain=comp.get("domain", ""),
                        position=comp.get("position", 0),
                        url_ranked=comp.get("url", ""),
                    )
                    session.add(record)
            logger.debug(
                "Saved %d competitor ranks for %r", len(competitors), keyword
            )
        except Exception as exc:
            logger.error("Failed to save competitor ranks: %s", exc)

    def _save_visibility_score(
        self,
        domain: str,
        data: dict[str, Any],
    ) -> None:
        """Persist visibility score snapshot."""
        try:
            with get_session() as session:
                vs = VisibilityScore(
                    domain=domain,
                    score=data.get("score", 0.0),
                    keyword_count=data.get("keyword_count", 0),
                    avg_position=data.get("avg_position", 0.0),
                    top3_count=data.get("top3_count", 0),
                    top10_count=data.get("top10_count", 0),
                    top20_count=data.get("top20_count", 0),
                )
                session.add(vs)
            logger.debug("Saved visibility score for %r: %.1f", domain, data.get("score", 0))
        except Exception as exc:
            logger.error("Failed to save visibility score: %s", exc)

    def _get_latest_position(
        self,
        domain: str,
        keyword: str,
    ) -> int:
        """Get the most recent position for a domain-keyword pair."""
        try:
            with get_session() as session:
                record = (
                    session.query(RankingRecord)
                    .filter(
                        RankingRecord.domain == domain,
                        RankingRecord.keyword == keyword,
                    )
                    .order_by(RankingRecord.checked_at.desc())
                    .first()
                )
                return record.position if record else 0
        except Exception:
            return 0

    async def close(self) -> None:
        """Release resources."""
        try:
            await self._scraper.close()
        except Exception:
            pass
