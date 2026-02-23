"""Backlink monitoring, profile analysis, and toxic link detection.

Tracks backlink health, detects changes, analyses link profiles,
and generates Google Disavow files.
"""

import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.models.backlink import Backlink, BacklinkCheck

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return domain.lower().lstrip("www.")
    except Exception:
        return url


class BacklinkMonitor:
    """Monitor backlink health and analyse link profiles.

    Usage::

        monitor = BacklinkMonitor()
        report = await monitor.check_backlinks("example.com")
        profile = await monitor.analyze_backlink_profile("example.com")
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client or LLMClient()
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

    # ------------------------------------------------------------------
    # Check all backlinks
    # ------------------------------------------------------------------

    async def check_backlinks(self, domain: str) -> dict:
        """Check status of all known backlinks for a domain.

        Returns a summary dict with total, alive, lost, changed counts
        plus a list of individual changes detected.
        """
        with get_session() as session:
            backlinks = (
                session.query(Backlink)
                .filter(Backlink.target_url.contains(domain))
                .all()
            )
            # Detach from session for async processing
            bl_data = [
                {
                    "id": bl.id,
                    "source_url": bl.source_url,
                    "target_url": bl.target_url,
                    "anchor_text": bl.anchor_text,
                    "dofollow": bl.dofollow,
                    "status": bl.status,
                }
                for bl in backlinks
            ]

        if not bl_data:
            logger.info("No backlinks found for domain: %s", domain)
            return {
                "domain": domain,
                "total": 0,
                "alive": 0,
                "lost": 0,
                "changed": 0,
                "changes": [],
                "checked_at": _utcnow().isoformat(),
            }

        session_http = await self._get_http_session()
        changes: list[dict] = []
        alive_count = 0
        lost_count = 0
        changed_count = 0

        for bl in bl_data:
            check_result = await self._check_single_backlink(
                session_http, bl["source_url"], bl["target_url"], bl["anchor_text"]
            )

            new_status = check_result["status"]
            old_status = bl["status"]

            if new_status == "active":
                alive_count += 1
            else:
                lost_count += 1

            # Detect changes
            change_info: Optional[dict] = None
            if new_status != old_status:
                changed_count += 1
                change_info = {
                    "backlink_id": bl["id"],
                    "source_url": bl["source_url"],
                    "change_type": "status_changed",
                    "old_value": old_status,
                    "new_value": new_status,
                    "http_status": check_result.get("http_status"),
                }
                changes.append(change_info)

            if check_result.get("dofollow_changed"):
                changed_count += 1
                change_info = {
                    "backlink_id": bl["id"],
                    "source_url": bl["source_url"],
                    "change_type": "dofollow_changed",
                    "old_value": str(bl["dofollow"]),
                    "new_value": str(check_result.get("is_dofollow", True)),
                }
                changes.append(change_info)

            # Update DB
            self._save_check_result(bl["id"], check_result)

        summary = {
            "domain": domain,
            "total": len(bl_data),
            "alive": alive_count,
            "lost": lost_count,
            "changed": changed_count,
            "changes": changes,
            "checked_at": _utcnow().isoformat(),
        }

        logger.info(
            "Backlink check for %s: %d total, %d alive, %d lost, %d changed",
            domain, len(bl_data), alive_count, lost_count, changed_count,
        )
        return summary

    async def _check_single_backlink(
        self,
        session: aiohttp.ClientSession,
        source_url: str,
        target_url: str,
        expected_anchor: Optional[str] = None,
    ) -> dict:
        """Check if a single backlink is still alive and unchanged."""
        result: dict[str, Any] = {
            "status": "unknown",
            "http_status": None,
            "is_dofollow": True,
            "anchor_text_found": None,
            "dofollow_changed": False,
        }

        try:
            async with session.get(source_url) as resp:
                result["http_status"] = resp.status
                if resp.status >= 400:
                    result["status"] = "lost_" + str(resp.status)
                    return result

                html = await resp.text()

                # Check if target URL is still linked
                target_domain = _extract_domain(target_url)
                if target_url in html or target_domain in html:
                    result["status"] = "active"
                else:
                    result["status"] = "lost_removed"
                    return result

                # Check nofollow status
                html_lower = html.lower()
                # Simple check: find the link and check for nofollow
                link_pos = html_lower.find(target_domain)
                if link_pos >= 0:
                    # Look backwards to find the <a tag
                    tag_start = html_lower.rfind("<a ", 0, link_pos)
                    if tag_start >= 0:
                        tag_end = html_lower.find(">", tag_start)
                        tag_content = html_lower[tag_start:tag_end + 1]
                        if 'rel="nofollow"' in tag_content or "rel='nofollow'" in tag_content:
                            result["is_dofollow"] = False
                        if 'rel="sponsored"' in tag_content:
                            result["is_dofollow"] = False
                        if 'rel="ugc"' in tag_content:
                            result["is_dofollow"] = False

        except aiohttp.ClientError as exc:
            logger.debug("HTTP error checking %s: %s", source_url, exc)
            result["status"] = "lost_error"
        except Exception as exc:
            logger.debug("Error checking backlink %s: %s", source_url, exc)
            result["status"] = "check_failed"

        return result

    def _save_check_result(self, backlink_id: int, check_result: dict) -> None:
        """Save check result to DB and update backlink record."""
        try:
            with get_session() as session:
                # Create check record
                check = BacklinkCheck(
                    backlink_id=backlink_id,
                    status=check_result["status"],
                    http_status=check_result.get("http_status"),
                    is_dofollow=check_result.get("is_dofollow", True),
                    anchor_text_found=check_result.get("anchor_text_found"),
                )
                session.add(check)

                # Update backlink record
                bl = session.query(Backlink).filter_by(id=backlink_id).first()
                if bl:
                    bl.status = check_result["status"]
                    bl.last_checked = _utcnow()
                    if check_result.get("is_dofollow") is not None:
                        bl.dofollow = check_result["is_dofollow"]
        except Exception as exc:
            logger.error("Failed to save check result for backlink %d: %s", backlink_id, exc)

    # ------------------------------------------------------------------
    # Add backlink
    # ------------------------------------------------------------------

    def add_backlink(
        self,
        url: str,
        source_domain: str,
        anchor_text: str = "",
        link_type: str = "dofollow",
        target_url: str = "",
    ) -> dict:
        """Register a new backlink for monitoring."""
        is_dofollow = link_type.lower() in ("dofollow", "follow")

        with get_session() as session:
            backlink = Backlink(
                source_url=url,
                source_domain=source_domain,
                target_url=target_url or url,
                anchor_text=anchor_text,
                link_type=link_type,
                dofollow=is_dofollow,
                status="active",
            )
            session.add(backlink)
            session.flush()
            result = {
                "id": backlink.id,
                "source_url": backlink.source_url,
                "source_domain": source_domain,
                "anchor_text": anchor_text,
                "link_type": link_type,
                "status": "active",
            }

        logger.info("Added backlink from %s (id=%d)", source_domain, result["id"])
        return result

    # ------------------------------------------------------------------
    # Profile Analysis
    # ------------------------------------------------------------------

    async def analyze_backlink_profile(self, domain: str) -> dict:
        """Comprehensive backlink profile analysis."""
        with get_session() as session:
            backlinks = (
                session.query(Backlink)
                .filter(Backlink.target_url.contains(domain))
                .all()
            )
            bl_list = [
                {
                    "id": bl.id,
                    "source_url": bl.source_url,
                    "source_domain": bl.source_domain or _extract_domain(bl.source_url),
                    "anchor_text": bl.anchor_text or "",
                    "dofollow": bl.dofollow,
                    "status": bl.status,
                    "domain_authority": bl.domain_authority,
                    "is_toxic": bl.is_toxic,
                    "discovered_at": bl.discovered_at,
                }
                for bl in backlinks
            ]

        total = len(bl_list)
        if total == 0:
            return {
                "domain": domain,
                "total_backlinks": 0,
                "referring_domains": 0,
                "dofollow_ratio": 0.0,
                "anchor_text_distribution": {},
                "link_velocity": {"new_30d": 0, "lost_30d": 0},
                "toxic_count": 0,
                "status_breakdown": {},
            }

        # Referring domains
        ref_domains = set()
        for bl in bl_list:
            ref_domains.add(bl["source_domain"])

        # Dofollow ratio
        dofollow_count = sum(1 for bl in bl_list if bl["dofollow"])
        dofollow_ratio = round((dofollow_count / total) * 100, 1) if total else 0.0

        # Anchor text distribution
        anchor_counter: Counter = Counter()
        for bl in bl_list:
            anchor = bl["anchor_text"].strip().lower() if bl["anchor_text"] else "[empty]"
            anchor_counter[anchor] += 1
        top_anchors = dict(anchor_counter.most_common(20))

        # Status breakdown
        status_counter: Counter = Counter()
        for bl in bl_list:
            status_counter[bl["status"]] += 1

        # Toxic count
        toxic_count = sum(1 for bl in bl_list if bl["is_toxic"])

        # Link velocity (30 days)
        cutoff = _utcnow() - timedelta(days=30)
        new_30d = sum(
            1 for bl in bl_list
            if bl["discovered_at"] and bl["discovered_at"] >= cutoff
        )
        lost_30d = sum(
            1 for bl in bl_list
            if bl["status"].startswith("lost") and bl["discovered_at"]
        )

        profile = {
            "domain": domain,
            "total_backlinks": total,
            "referring_domains": len(ref_domains),
            "dofollow_count": dofollow_count,
            "nofollow_count": total - dofollow_count,
            "dofollow_ratio": dofollow_ratio,
            "anchor_text_distribution": top_anchors,
            "link_velocity": {"new_30d": new_30d, "lost_30d": lost_30d},
            "toxic_count": toxic_count,
            "status_breakdown": dict(status_counter),
            "active_count": status_counter.get("active", 0),
        }

        logger.info(
            "Profile analysis for %s: %d backlinks, %d ref domains, %.1f%% dofollow",
            domain, total, len(ref_domains), dofollow_ratio,
        )
        return profile

    # ------------------------------------------------------------------
    # Toxic Link Detection
    # ------------------------------------------------------------------

    async def detect_toxic_links(self, backlinks: list[dict]) -> list[dict]:
        """AI-powered toxic link detection."""
        if not backlinks:
            return []

        # Prepare batch for AI analysis
        batch_size = 20
        toxic_links: list[dict] = []

        for i in range(0, len(backlinks), batch_size):
            batch = backlinks[i : i + batch_size]
            batch_descriptions = []
            for idx, bl in enumerate(batch):
                desc = (
                    str(idx + 1) + ". Domain: " + str(bl.get("source_domain", ""))
                    + " | URL: " + str(bl.get("source_url", ""))
                    + " | Anchor: " + str(bl.get("anchor_text", ""))
                    + " | DA: " + str(bl.get("domain_authority", "N/A"))
                )
                batch_descriptions.append(desc)

            prompt_parts = [
                "Analyze these backlinks for toxicity signals.",
                "A toxic backlink is one from:",
                "- Spammy or low-quality domains (PBNs, link farms)",
                "- Unnatural anchor text patterns (exact match spam)",
                "- Irrelevant or foreign-language sites with no relation",
                "- Known link scheme domains",
                "- Auto-generated or scraped content sites",
                "",
                "Backlinks to analyze:",
            ]
            prompt_parts.extend(batch_descriptions)
            prompt_parts.extend([
                "",
                "Return a JSON array of objects for ONLY the toxic links.",
                'Each object: {"index": 1, "reason": "brief reason", "severity": "high|medium|low"}',
                "If none are toxic, return an empty array [].",
            ])

            prompt = "\n".join(prompt_parts)

            try:
                result = await self._llm.generate_json(prompt)
                if isinstance(result, list):
                    for item in result:
                        idx = item.get("index", 0) - 1
                        if 0 <= idx < len(batch):
                            toxic_entry = dict(batch[idx])
                            toxic_entry["toxic_reason"] = item.get("reason", "Unknown")
                            toxic_entry["toxic_severity"] = item.get("severity", "medium")
                            toxic_links.append(toxic_entry)
            except Exception as exc:
                logger.warning("AI toxic link detection failed for batch: %s", exc)
                # Fallback: heuristic detection
                for bl in batch:
                    if self._heuristic_toxic_check(bl):
                        toxic_entry = dict(bl)
                        toxic_entry["toxic_reason"] = "Heuristic detection"
                        toxic_entry["toxic_severity"] = "medium"
                        toxic_links.append(toxic_entry)

        # Update DB
        self._mark_toxic_in_db(toxic_links)

        logger.info("Detected %d toxic links out of %d", len(toxic_links), len(backlinks))
        return toxic_links

    @staticmethod
    def _heuristic_toxic_check(backlink: dict) -> bool:
        """Simple heuristic to flag potentially toxic links."""
        domain = str(backlink.get("source_domain", "")).lower()
        anchor = str(backlink.get("anchor_text", "")).lower()

        # Check for suspicious TLDs
        suspicious_tlds = [".xyz", ".top", ".pw", ".tk", ".ml", ".ga", ".cf"]
        if any(domain.endswith(tld) for tld in suspicious_tlds):
            return True

        # Check for very long domains (often auto-generated)
        if len(domain) > 50:
            return True

        # Check for spammy anchor patterns
        spam_anchors = [
            "buy ", "cheap ", "casino", "poker", "viagra", "cialis",
            "payday loan", "essay writing", "click here to buy",
        ]
        if any(sa in anchor for sa in spam_anchors):
            return True

        return False

    def _mark_toxic_in_db(self, toxic_links: list[dict]) -> None:
        """Mark backlinks as toxic in the database."""
        if not toxic_links:
            return
        try:
            with get_session() as session:
                for tl in toxic_links:
                    bl_id = tl.get("id")
                    if bl_id:
                        bl = session.query(Backlink).filter_by(id=bl_id).first()
                        if bl:
                            bl.is_toxic = True
                            bl.toxic_reason = tl.get("toxic_reason", "")
        except Exception as exc:
            logger.error("Failed to mark toxic links in DB: %s", exc)

    # ------------------------------------------------------------------
    # Disavow File Generation
    # ------------------------------------------------------------------

    def generate_disavow_file(self, toxic_links: list[dict]) -> str:
        """Generate a Google Disavow format file."""
        lines = [
            "# Google Disavow File",
            "# Generated by Full SEO Automation",
            "# Date: " + _utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "# Total entries: " + str(len(toxic_links)),
            "",
        ]

        # Group by domain for domain-level disavow
        domain_reasons: dict[str, str] = {}
        url_entries: list[tuple[str, str]] = []

        for tl in toxic_links:
            source_domain = tl.get("source_domain", "")
            source_url = tl.get("source_url", "")
            reason = tl.get("toxic_reason", "Toxic link detected")

            if source_domain:
                domain_reasons[source_domain] = reason
            elif source_url:
                url_entries.append((source_url, reason))

        # Domain-level disavows
        if domain_reasons:
            lines.append("# Domain-level disavows")
            for domain, reason in sorted(domain_reasons.items()):
                lines.append("# Reason: " + reason)
                lines.append("domain:" + domain)
            lines.append("")

        # URL-level disavows
        if url_entries:
            lines.append("# URL-level disavows")
            for url, reason in url_entries:
                lines.append("# Reason: " + reason)
                lines.append(url)

        content = "\n".join(lines) + "\n"
        logger.info(
            "Generated disavow file: %d domains, %d URLs",
            len(domain_reasons), len(url_entries),
        )
        return content

    # ------------------------------------------------------------------
    # Link Velocity
    # ------------------------------------------------------------------

    def get_link_velocity(self, domain: str, days: int = 30) -> dict:
        """Track new and lost links over time."""
        cutoff = _utcnow() - timedelta(days=days)

        with get_session() as session:
            all_backlinks = (
                session.query(Backlink)
                .filter(Backlink.target_url.contains(domain))
                .all()
            )

            # New links in period
            new_links = [
                bl for bl in all_backlinks
                if bl.discovered_at and bl.discovered_at >= cutoff
            ]

            # Lost links (check history)
            checks = (
                session.query(BacklinkCheck)
                .filter(BacklinkCheck.checked_at >= cutoff)
                .filter(BacklinkCheck.status.like("lost%"))
                .all()
            )
            lost_bl_ids = set(c.backlink_id for c in checks)

            # Daily breakdown
            daily_new: dict[str, int] = {}
            for bl in new_links:
                day_key = bl.discovered_at.strftime("%Y-%m-%d")
                daily_new[day_key] = daily_new.get(day_key, 0) + 1

            daily_lost: dict[str, int] = {}
            for c in checks:
                day_key = c.checked_at.strftime("%Y-%m-%d")
                daily_lost[day_key] = daily_lost.get(day_key, 0) + 1

        total_new = len(new_links)
        total_lost = len(lost_bl_ids)
        weekly_avg_new = round(total_new / max(days / 7, 1), 1)
        weekly_avg_lost = round(total_lost / max(days / 7, 1), 1)

        velocity = {
            "domain": domain,
            "period_days": days,
            "total_new": total_new,
            "total_lost": total_lost,
            "net_change": total_new - total_lost,
            "weekly_avg_new": weekly_avg_new,
            "weekly_avg_lost": weekly_avg_lost,
            "daily_new": daily_new,
            "daily_lost": daily_lost,
        }

        logger.info(
            "Link velocity for %s (%dd): +%d / -%d (net %+d)",
            domain, days, total_new, total_lost, total_new - total_lost,
        )
        return velocity

    # ------------------------------------------------------------------
    # Utility: get all backlinks
    # ------------------------------------------------------------------

    def get_all_backlinks(
        self,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        toxic_only: bool = False,
    ) -> list[dict]:
        """Load backlinks from the database with optional filters."""
        with get_session() as session:
            query = session.query(Backlink)
            if domain:
                query = query.filter(Backlink.target_url.contains(domain))
            if status:
                query = query.filter(Backlink.status == status)
            if toxic_only:
                query = query.filter(Backlink.is_toxic.is_(True))
            rows = query.order_by(Backlink.discovered_at.desc()).all()
            return [
                {
                    "id": r.id,
                    "source_url": r.source_url,
                    "source_domain": r.source_domain or _extract_domain(r.source_url),
                    "target_url": r.target_url,
                    "anchor_text": r.anchor_text or "",
                    "link_type": r.link_type,
                    "dofollow": r.dofollow,
                    "domain_authority": r.domain_authority,
                    "status": r.status,
                    "is_toxic": r.is_toxic,
                    "toxic_reason": r.toxic_reason or "",
                    "discovered_at": str(r.discovered_at) if r.discovered_at else None,
                    "last_checked": str(r.last_checked) if r.last_checked else None,
                }
                for r in rows
            ]
