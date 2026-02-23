"""Comprehensive SEO report engine aggregating data across all modules.

Provides full-domain reporting, executive summaries (AI-powered),
module-level summaries, period comparison, competitor analysis,
and scheduled report configuration.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, func

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.models.audit import AuditCheck, SiteAudit
from src.models.backlink import Backlink
from src.models.content import BlogPost, ContentBrief
from src.models.keyword import Keyword
from src.models.local_seo import LocalBusinessProfile, LocalSEOAudit
from src.models.ranking import (
    CompetitorRank,
    RankingHistory,
    RankingRecord,
    SERPFeature,
    VisibilityScore,
)
from src.models.report import Report

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division returning *default* when denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def _pct_change(current: float, previous: float) -> float:
    """Calculate percentage change between two values."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / abs(previous)) * 100, 2)


def _letter_grade(score: float) -> str:
    """Map a 0-100 score to a letter grade A-F."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Weight configuration for overall score
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "technical": 0.20,
    "onpage": 0.15,
    "local": 0.10,
    "content": 0.20,
    "backlink": 0.15,
    "visibility": 0.20,
}


class ReportEngine:
    """Centralised report engine that pulls data from every SEO module,
    scores the domain, and optionally generates AI-powered executive summaries.
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()
        logger.info("ReportEngine initialised (LLM available: %s)", self.llm is not None)

    # ------------------------------------------------------------------
    # 1. Full report
    # ------------------------------------------------------------------

    async def generate_full_report(
        self, domain: str, date_range: tuple = None
    ) -> dict:
        """Gather data from **all** modules and compile a comprehensive report.

        Sections produced:
            executive_summary, technical_audit, onpage_seo, local_seo,
            keyword_rankings, content_performance, link_building,
            serp_features, recommendations.

        The report is persisted via the Report model and the full
        dictionary is returned.
        """
        logger.info(
            "Generating full report for domain=%s date_range=%s", domain, date_range
        )
        start_date, end_date = self._resolve_date_range(date_range)

        # Parallel data fetching ------------------------------------------
        (
            scores_data,
            technical_data,
            onpage_data,
            local_data,
            rankings_data,
            content_data,
            backlink_data,
            serp_data,
            keyword_data,
        ) = await asyncio.gather(
            asyncio.to_thread(self.aggregate_scores, domain),
            asyncio.to_thread(self._fetch_technical_data, domain, start_date, end_date),
            asyncio.to_thread(self._fetch_onpage_data, domain, start_date, end_date),
            asyncio.to_thread(self._fetch_local_data, domain, start_date, end_date),
            asyncio.to_thread(self._fetch_rankings_data, domain, start_date, end_date),
            asyncio.to_thread(self._fetch_content_data, start_date, end_date),
            asyncio.to_thread(self._fetch_backlink_data, start_date, end_date),
            asyncio.to_thread(self._fetch_serp_data, domain, start_date, end_date),
            asyncio.to_thread(self._fetch_keyword_data),
        )

        all_data = {
            "domain": domain,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "scores": scores_data,
            "technical": technical_data,
            "onpage": onpage_data,
            "local": local_data,
            "rankings": rankings_data,
            "content": content_data,
            "backlinks": backlink_data,
            "serp_features": serp_data,
            "keywords": keyword_data,
        }

        # AI executive summary -------------------------------------------
        executive_summary = await self.generate_executive_summary(all_data)

        # Compile recommendations ----------------------------------------
        recommendations = self._compile_recommendations(all_data)

        report = {
            "generated_at": _utcnow().isoformat(),
            "domain": domain,
            "date_range": all_data["date_range"],
            "executive_summary": executive_summary,
            "technical_audit": technical_data,
            "onpage_seo": onpage_data,
            "local_seo": local_data,
            "keyword_rankings": rankings_data,
            "content_performance": content_data,
            "link_building": backlink_data,
            "serp_features": serp_data,
            "keywords": keyword_data,
            "scores": scores_data,
            "recommendations": recommendations,
        }

        # Persist ---------------------------------------------------------
        await asyncio.to_thread(self._save_report, domain, report)
        logger.info("Full report for %s generated and saved", domain)
        return report

    # ------------------------------------------------------------------
    # 2. Executive summary (AI-powered with rule-based fallback)
    # ------------------------------------------------------------------

    async def generate_executive_summary(self, all_data: dict) -> dict:
        """Produce an AI-generated executive summary.

        Falls back to a deterministic rule-based summary when the LLM
        is unavailable or errors out.
        """
        scores = all_data.get("scores", {})
        overall = scores.get("overall", 0)

        try:
            summary_prompt = self._build_summary_prompt(all_data)
            system_prompt = (
                "You are an expert SEO analyst. Respond ONLY with valid JSON. "
                "Provide actionable, data-driven insights. All scores 0-100."
            )
            raw = await self.llm.generate_json(
                prompt=summary_prompt,
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.4,
            )
            summary = self._validate_executive_summary(raw, overall)
            logger.info("AI executive summary generated successfully")
            return summary
        except Exception as exc:
            logger.warning(
                "LLM executive summary failed (%s), using rule-based fallback", exc
            )
            return self._rule_based_summary(all_data)

    # ------------------------------------------------------------------
    # 3. Aggregate scores
    # ------------------------------------------------------------------

    def aggregate_scores(self, domain: str) -> dict:
        """Pull latest scores from every module and compute a weighted overall."""
        technical = self._get_technical_score(domain)
        onpage = self._get_onpage_score(domain)
        local = self._get_local_score(domain)
        content = self._get_content_score()
        backlink = self._get_backlink_score()
        visibility = self._get_visibility_score(domain)

        current_scores = {
            "technical": technical,
            "onpage": onpage,
            "local": local,
            "content": content,
            "backlink": backlink,
            "visibility": visibility,
        }

        overall = sum(
            current_scores[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS
        )
        overall = round(overall, 2)

        # Previous period scores (30 days ago) for trend
        cutoff = _utcnow() - timedelta(days=30)
        prev_technical = self._get_technical_score(domain, before=cutoff)
        prev_visibility = self._get_visibility_score(domain, before=cutoff)
        prev_overall = round(
            prev_technical * SCORE_WEIGHTS["technical"]
            + onpage * SCORE_WEIGHTS["onpage"]
            + local * SCORE_WEIGHTS["local"]
            + content * SCORE_WEIGHTS["content"]
            + backlink * SCORE_WEIGHTS["backlink"]
            + prev_visibility * SCORE_WEIGHTS["visibility"],
            2,
        )

        return {
            "overall": overall,
            "grade": _letter_grade(overall),
            "modules": current_scores,
            "trend": {
                "current_overall": overall,
                "previous_overall": prev_overall,
                "change_pct": _pct_change(overall, prev_overall),
            },
        }

    # ------------------------------------------------------------------
    # 4. Module summary
    # ------------------------------------------------------------------

    def get_module_summary(
        self, module_name: str, domain: str, date_range: tuple = None
    ) -> dict:
        """Return a focused summary for a single module."""
        start_date, end_date = self._resolve_date_range(date_range)
        dispatch = {
            "technical": self._summary_technical,
            "onpage": self._summary_onpage,
            "local": self._summary_local,
            "content": self._summary_content,
            "backlinks": self._summary_backlinks,
            "rankings": self._summary_rankings,
            "keywords": self._summary_keywords,
        }
        handler = dispatch.get(module_name)
        if handler is None:
            valid = ", ".join(sorted(dispatch.keys()))
            logger.error("Unknown module %s. Valid: %s", module_name, valid)
            return {"error": "Unknown module: " + module_name, "valid_modules": valid}
        return handler(domain, start_date, end_date)

    # ------------------------------------------------------------------
    # 5. Period comparison
    # ------------------------------------------------------------------

    def compare_periods(
        self, domain: str, period1: tuple, period2: tuple
    ) -> dict:
        """Compare metrics between two date ranges and surface improvements/regressions."""
        p1_start, p1_end = self._parse_dates(period1)
        p2_start, p2_end = self._parse_dates(period2)

        comparison: dict[str, Any] = {
            "period1": {"start": p1_start.isoformat(), "end": p1_end.isoformat()},
            "period2": {"start": p2_start.isoformat(), "end": p2_end.isoformat()},
            "modules": {},
        }

        for label, s, e in [
            ("period1", p1_start, p1_end),
            ("period2", p2_start, p2_end),
        ]:
            with get_session() as session:
                avg_tech = (
                    session.query(func.avg(SiteAudit.overall_score))
                    .filter(
                        SiteAudit.domain == domain,
                        SiteAudit.created_at >= s,
                        SiteAudit.created_at <= e,
                    )
                    .scalar()
                ) or 0
                vis_row = (
                    session.query(VisibilityScore)
                    .filter(
                        VisibilityScore.domain == domain,
                        VisibilityScore.date >= s,
                        VisibilityScore.date <= e,
                    )
                    .order_by(desc(VisibilityScore.date))
                    .first()
                )
                avg_rank = (
                    session.query(func.avg(RankingRecord.position))
                    .filter(
                        RankingRecord.domain == domain,
                        RankingRecord.checked_at >= s,
                        RankingRecord.checked_at <= e,
                    )
                    .scalar()
                ) or 0
                backlink_count = (
                    session.query(func.count(Backlink.id))
                    .filter(
                        Backlink.status == "active",
                        Backlink.first_seen >= s,
                        Backlink.first_seen <= e,
                    )
                    .scalar()
                ) or 0
                content_count = (
                    session.query(func.count(BlogPost.id))
                    .filter(
                        BlogPost.created_at >= s,
                        BlogPost.created_at <= e,
                    )
                    .scalar()
                ) or 0

            comparison["modules"][label] = {
                "avg_technical_score": round(float(avg_tech), 2),
                "visibility_score": vis_row.score if vis_row else 0,
                "avg_position": round(float(avg_rank), 2),
                "new_backlinks": backlink_count,
                "new_content": content_count,
            }

        # Deltas
        p1m = comparison["modules"]["period1"]
        p2m = comparison["modules"]["period2"]
        comparison["changes"] = {}
        for key in p1m:
            comparison["changes"][key] = {
                "absolute": round(p2m[key] - p1m[key], 2),
                "pct_change": _pct_change(p2m[key], p1m[key]),
            }

        return comparison

    # ------------------------------------------------------------------
    # 6. Competitor comparison (async)
    # ------------------------------------------------------------------

    async def generate_competitor_comparison(
        self, domain: str, competitors: list[str]
    ) -> dict:
        """Cross-module competitor analysis."""
        result: dict[str, Any] = {"domain": domain, "competitors": {}}

        tasks = [
            asyncio.to_thread(self._fetch_competitor_data, domain, comp)
            for comp in competitors
        ]
        comp_results = await asyncio.gather(*tasks)
        for comp, data in zip(competitors, comp_results):
            result["competitors"][comp] = data

        # Summary
        result["summary"] = await asyncio.to_thread(
            self._competitor_summary, domain, competitors
        )
        return result

    # ------------------------------------------------------------------
    # 7. Schedule report
    # ------------------------------------------------------------------

    def schedule_report(
        self, domain: str, frequency: str, email_to: str = None
    ) -> dict:
        """Persist a recurring report configuration."""
        valid_freqs = ("daily", "weekly", "biweekly", "monthly")
        if frequency not in valid_freqs:
            raise ValueError(
                "frequency must be one of: " + ", ".join(valid_freqs)
            )

        next_run = self._calc_next_run(frequency)
        config = {
            "domain": domain,
            "frequency": frequency,
            "email_to": email_to,
            "next_run": next_run.isoformat(),
            "created_at": _utcnow().isoformat(),
        }

        with get_session() as session:
            report = Report(
                report_type="scheduled_config",
                title="Scheduled report config for " + domain,
                data_json=config,
            )
            session.add(report)
            session.flush()
            config["report_id"] = report.id

        logger.info(
            "Scheduled %s report for %s (next_run=%s)", frequency, domain, next_run
        )
        return config

    # ==================================================================
    # PRIVATE: data fetching helpers
    # ==================================================================

    @staticmethod
    def _resolve_date_range(date_range: tuple = None) -> tuple:
        """Normalise an optional date range to concrete datetimes."""
        if date_range and len(date_range) == 2:
            return ReportEngine._parse_dates(date_range)
        end = _utcnow()
        start = end - timedelta(days=30)
        return start, end

    @staticmethod
    def _parse_dates(pair: tuple) -> tuple:
        """Convert a pair of date-like values to datetimes."""
        out = []
        for d in pair:
            if isinstance(d, datetime):
                out.append(d)
            elif isinstance(d, str):
                out.append(datetime.fromisoformat(d))
            else:
                out.append(d)
        return out[0], out[1]

    # --- technical ----------------------------------------------------

    def _fetch_technical_data(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        """Fetch latest technical audit data for the domain."""
        with get_session() as session:
            audits = (
                session.query(SiteAudit)
                .filter(
                    SiteAudit.domain == domain,
                    SiteAudit.created_at >= start,
                    SiteAudit.created_at <= end,
                )
                .order_by(desc(SiteAudit.created_at))
                .all()
            )
            if not audits:
                return self._empty_section()

            latest = audits[0]
            high_issues = (
                session.query(AuditCheck)
                .filter(
                    AuditCheck.audit_id == latest.id,
                    AuditCheck.status == "fail",
                    AuditCheck.priority == "high",
                )
                .all()
            )
            warning_count = (
                session.query(func.count(AuditCheck.id))
                .filter(
                    AuditCheck.audit_id == latest.id,
                    AuditCheck.status == "warning",
                )
                .scalar()
            ) or 0
            passed_count = (
                session.query(func.count(AuditCheck.id))
                .filter(
                    AuditCheck.audit_id == latest.id,
                    AuditCheck.status == "pass",
                )
                .scalar()
            ) or 0
            total_checks = (
                session.query(func.count(AuditCheck.id))
                .filter(AuditCheck.audit_id == latest.id)
                .scalar()
            ) or 0

        return {
            "score": latest.overall_score or 0,
            "key_metrics": {
                "total_audits_in_period": len(audits),
                "latest_audit_date": latest.created_at.isoformat(),
                "audit_type": latest.audit_type,
                "total_checks": total_checks,
                "passed": passed_count,
                "warnings": warning_count,
                "high_priority_fails": len(high_issues),
            },
            "issues": [
                {
                    "check": c.check_name,
                    "category": c.category,
                    "details": c.details or "",
                    "priority": c.priority,
                }
                for c in high_issues
            ],
            "improvements": [],
        }

    # --- on-page ------------------------------------------------------

    def _fetch_onpage_data(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        """Fetch on-page SEO data from audits and content scores."""
        with get_session() as session:
            onpage_audit = (
                session.query(SiteAudit)
                .filter(
                    SiteAudit.domain == domain,
                    SiteAudit.audit_type == "onpage",
                    SiteAudit.created_at >= start,
                    SiteAudit.created_at <= end,
                )
                .order_by(desc(SiteAudit.created_at))
                .first()
            )
            avg_seo = (
                session.query(func.avg(BlogPost.seo_score))
                .filter(BlogPost.seo_score.isnot(None))
                .scalar()
            ) or 0

        score = 0.0
        issues: list = []
        if onpage_audit:
            score = onpage_audit.overall_score or 0
            raw_issues = onpage_audit.issues_json or []
            if isinstance(raw_issues, list):
                issues = raw_issues[:20]
            elif isinstance(raw_issues, dict):
                issues = raw_issues.get("issues", [])[:20]
        else:
            score = float(avg_seo)

        return {
            "score": round(score, 2),
            "key_metrics": {
                "avg_content_seo_score": round(float(avg_seo), 2),
                "has_dedicated_audit": onpage_audit is not None,
            },
            "issues": issues,
            "improvements": [],
        }

    # --- local SEO ----------------------------------------------------

    def _fetch_local_data(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        """Fetch local SEO audit data for the domain."""
        with get_session() as session:
            business = (
                session.query(LocalBusinessProfile)
                .filter(LocalBusinessProfile.domain == domain)
                .first()
            )
            if not business:
                return self._empty_section()

            audit = (
                session.query(LocalSEOAudit)
                .filter(
                    LocalSEOAudit.business_id == business.id,
                    LocalSEOAudit.audit_date >= start,
                    LocalSEOAudit.audit_date <= end,
                )
                .order_by(desc(LocalSEOAudit.audit_date))
                .first()
            )

        if not audit:
            return {
                "score": 0,
                "key_metrics": {"business_name": business.business_name},
                "issues": [],
                "improvements": [],
            }

        return {
            "score": audit.overall_score or 0,
            "key_metrics": {
                "business_name": business.business_name,
                "serp_score": audit.serp_score or 0,
                "gmb_score": audit.gmb_score or 0,
                "onpage_score": audit.onpage_score or 0,
                "offpage_score": audit.offpage_score or 0,
                "citation_score": audit.citation_score or 0,
            },
            "issues": audit.top_issues_json or [],
            "improvements": audit.recommendations_json or [],
        }

    # --- rankings -----------------------------------------------------

    def _fetch_rankings_data(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        """Fetch ranking and visibility data for the domain."""
        with get_session() as session:
            vis = (
                session.query(VisibilityScore)
                .filter(VisibilityScore.domain == domain)
                .order_by(desc(VisibilityScore.date))
                .first()
            )
            avg_pos = (
                session.query(func.avg(RankingRecord.position))
                .filter(
                    RankingRecord.domain == domain,
                    RankingRecord.checked_at >= start,
                    RankingRecord.checked_at <= end,
                )
                .scalar()
            )
            total_kws = (
                session.query(func.count(func.distinct(RankingRecord.keyword)))
                .filter(RankingRecord.domain == domain)
                .scalar()
            ) or 0
            recent_changes = (
                session.query(RankingHistory)
                .filter(
                    RankingHistory.domain == domain,
                    RankingHistory.date >= start,
                )
                .order_by(desc(RankingHistory.date))
                .limit(20)
                .all()
            )

        vis_score = vis.score if vis else 0
        return {
            "score": round(vis_score, 2),
            "key_metrics": {
                "visibility_score": vis_score,
                "avg_position": round(float(avg_pos), 2) if avg_pos else 0,
                "tracked_keywords": total_kws,
                "top3_count": vis.top3_count if vis else 0,
                "top10_count": vis.top10_count if vis else 0,
                "top20_count": vis.top20_count if vis else 0,
            },
            "issues": [],
            "improvements": [
                {
                    "keyword": c.keyword,
                    "position": c.position,
                    "change": c.change,
                    "date": c.date.isoformat(),
                }
                for c in recent_changes
            ],
        }

    # --- content ------------------------------------------------------

    def _fetch_content_data(self, start: datetime, end: datetime) -> dict:
        """Fetch content performance data."""
        with get_session() as session:
            total = session.query(func.count(BlogPost.id)).scalar() or 0
            published = (
                session.query(func.count(BlogPost.id))
                .filter(BlogPost.status == "published")
                .scalar()
            ) or 0
            avg_score = (
                session.query(func.avg(BlogPost.seo_score))
                .filter(BlogPost.seo_score.isnot(None))
                .scalar()
            ) or 0
            avg_words = (
                session.query(func.avg(BlogPost.word_count))
                .filter(BlogPost.word_count > 0)
                .scalar()
            ) or 0
            recent = (
                session.query(BlogPost)
                .filter(
                    BlogPost.created_at >= start,
                    BlogPost.created_at <= end,
                )
                .order_by(desc(BlogPost.created_at))
                .limit(10)
                .all()
            )
            briefs_pending = (
                session.query(func.count(ContentBrief.id))
                .filter(ContentBrief.status == "draft")
                .scalar()
            ) or 0

        low_score_posts = [
            p for p in recent if p.seo_score is not None and p.seo_score < 60
        ]
        return {
            "score": round(float(avg_score), 2),
            "key_metrics": {
                "total_posts": total,
                "published": published,
                "avg_seo_score": round(float(avg_score), 2),
                "avg_word_count": round(float(avg_words)),
                "new_in_period": len(recent),
                "pending_briefs": briefs_pending,
            },
            "issues": [
                {
                    "post": p.title,
                    "seo_score": p.seo_score,
                    "slug": p.slug,
                }
                for p in low_score_posts
            ],
            "improvements": [],
        }

    # --- backlinks ----------------------------------------------------

    def _fetch_backlink_data(self, start: datetime, end: datetime) -> dict:
        """Fetch backlink profile data."""
        with get_session() as session:
            total = session.query(func.count(Backlink.id)).scalar() or 0
            active = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.status == "active")
                .scalar()
            ) or 0
            lost = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.status == "lost")
                .scalar()
            ) or 0
            toxic = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.is_toxic == True)  # noqa: E712
                .scalar()
            ) or 0
            avg_da = (
                session.query(func.avg(Backlink.domain_authority))
                .filter(
                    Backlink.status == "active",
                    Backlink.domain_authority.isnot(None),
                )
                .scalar()
            ) or 0
            dofollow = (
                session.query(func.count(Backlink.id))
                .filter(
                    Backlink.status == "active",
                    Backlink.dofollow == True,  # noqa: E712
                )
                .scalar()
            ) or 0
            new_in_period = (
                session.query(func.count(Backlink.id))
                .filter(
                    Backlink.first_seen >= start,
                    Backlink.first_seen <= end,
                )
                .scalar()
            ) or 0
            unique_domains = (
                session.query(func.count(func.distinct(Backlink.source_domain)))
                .filter(Backlink.status == "active")
                .scalar()
            ) or 0

        health = _safe_div(active - toxic, max(active, 1)) * 100
        return {
            "score": round(health, 2),
            "key_metrics": {
                "total_backlinks": total,
                "active": active,
                "lost": lost,
                "toxic": toxic,
                "avg_domain_authority": round(float(avg_da), 2),
                "dofollow_count": dofollow,
                "new_in_period": new_in_period,
                "unique_referring_domains": unique_domains,
            },
            "issues": [],
            "improvements": [],
        }

    # --- SERP features ------------------------------------------------

    def _fetch_serp_data(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        """Fetch SERP feature data."""
        with get_session() as session:
            features = (
                session.query(SERPFeature)
                .filter(
                    SERPFeature.checked_at >= start,
                    SERPFeature.checked_at <= end,
                )
                .all()
            )

        owned = [f for f in features if f.owns_feature]
        types_present = list(set(f.feature_type for f in features))
        total_feat = max(len(features), 1)

        return {
            "score": round(_safe_div(len(owned), total_feat) * 100, 2),
            "key_metrics": {
                "total_features_tracked": len(features),
                "features_owned": len(owned),
                "feature_types": types_present,
            },
            "issues": [],
            "improvements": [],
        }

    # --- keywords -----------------------------------------------------

    def _fetch_keyword_data(self) -> dict:
        """Fetch keyword portfolio data."""
        with get_session() as session:
            total = session.query(func.count(Keyword.id)).scalar() or 0
            avg_vol = (
                session.query(func.avg(Keyword.volume))
                .filter(Keyword.volume.isnot(None))
                .scalar()
            ) or 0
            avg_diff = (
                session.query(func.avg(Keyword.difficulty))
                .filter(Keyword.difficulty.isnot(None))
                .scalar()
            ) or 0
            high_opp = (
                session.query(func.count(Keyword.id))
                .filter(
                    Keyword.opportunity_score.isnot(None),
                    Keyword.opportunity_score >= 70,
                )
                .scalar()
            ) or 0

        raw_score = _safe_div(high_opp, max(total, 1)) * 100 + 50
        return {
            "score": min(round(raw_score, 2), 100),
            "key_metrics": {
                "total_keywords": total,
                "avg_volume": round(float(avg_vol)),
                "avg_difficulty": round(float(avg_diff), 2),
                "high_opportunity_count": high_opp,
            },
            "issues": [],
            "improvements": [],
        }

    # ==================================================================
    # PRIVATE: individual score helpers
    # ==================================================================

    def _get_technical_score(
        self, domain: str, before: datetime = None
    ) -> float:
        """Get latest technical audit score."""
        with get_session() as session:
            q = session.query(SiteAudit).filter(SiteAudit.domain == domain)
            if before:
                q = q.filter(SiteAudit.created_at <= before)
            audit = q.order_by(desc(SiteAudit.created_at)).first()
        if audit and audit.overall_score:
            return float(audit.overall_score)
        return 0.0

    def _get_onpage_score(self, domain: str) -> float:
        """Get on-page score from dedicated audit or content average."""
        with get_session() as session:
            audit = (
                session.query(SiteAudit)
                .filter(
                    SiteAudit.domain == domain,
                    SiteAudit.audit_type == "onpage",
                )
                .order_by(desc(SiteAudit.created_at))
                .first()
            )
            if audit and audit.overall_score:
                return float(audit.overall_score)
            avg = (
                session.query(func.avg(BlogPost.seo_score))
                .filter(BlogPost.seo_score.isnot(None))
                .scalar()
            )
        return float(avg) if avg else 0.0

    def _get_local_score(self, domain: str) -> float:
        """Get latest local SEO audit score."""
        with get_session() as session:
            business = (
                session.query(LocalBusinessProfile)
                .filter(LocalBusinessProfile.domain == domain)
                .first()
            )
            if not business:
                return 0.0
            audit = (
                session.query(LocalSEOAudit)
                .filter(LocalSEOAudit.business_id == business.id)
                .order_by(desc(LocalSEOAudit.audit_date))
                .first()
            )
        if audit and audit.overall_score:
            return float(audit.overall_score)
        return 0.0

    def _get_content_score(self) -> float:
        """Get average blog post SEO score."""
        with get_session() as session:
            avg = (
                session.query(func.avg(BlogPost.seo_score))
                .filter(BlogPost.seo_score.isnot(None))
                .scalar()
            )
        return round(float(avg), 2) if avg else 0.0

    def _get_backlink_score(self) -> float:
        """Calculate backlink health score from active/toxic ratio."""
        with get_session() as session:
            active = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.status == "active")
                .scalar()
            ) or 0
            toxic = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.is_toxic == True)  # noqa: E712
                .scalar()
            ) or 0
        return round(_safe_div(active - toxic, max(active, 1)) * 100, 2)

    def _get_visibility_score(
        self, domain: str, before: datetime = None
    ) -> float:
        """Get latest visibility score."""
        with get_session() as session:
            q = session.query(VisibilityScore).filter(
                VisibilityScore.domain == domain
            )
            if before:
                q = q.filter(VisibilityScore.date <= before)
            vis = q.order_by(desc(VisibilityScore.date)).first()
        return float(vis.score) if vis else 0.0

    # ==================================================================
    # PRIVATE: module summary dispatchers
    # ==================================================================

    def _summary_technical(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_technical_data(domain, start, end)
        data["module"] = "technical"
        data["issues_count"] = len(data.get("issues", []))
        return data

    def _summary_onpage(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_onpage_data(domain, start, end)
        data["module"] = "onpage"
        data["issues_count"] = len(data.get("issues", []))
        return data

    def _summary_local(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_local_data(domain, start, end)
        data["module"] = "local"
        data["issues_count"] = len(data.get("issues", []))
        return data

    def _summary_content(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_content_data(start, end)
        data["module"] = "content"
        data["issues_count"] = len(data.get("issues", []))
        return data

    def _summary_backlinks(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_backlink_data(start, end)
        data["module"] = "backlinks"
        data["issues_count"] = data["key_metrics"].get("toxic", 0)
        return data

    def _summary_rankings(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_rankings_data(domain, start, end)
        data["module"] = "rankings"
        data["issues_count"] = 0
        return data

    def _summary_keywords(
        self, domain: str, start: datetime, end: datetime
    ) -> dict:
        data = self._fetch_keyword_data()
        data["module"] = "keywords"
        data["issues_count"] = 0
        return data

    # ==================================================================
    # PRIVATE: competitor helpers
    # ==================================================================

    def _fetch_competitor_data(self, domain: str, competitor: str) -> dict:
        """Gather cross-module data for a single competitor."""
        with get_session() as session:
            comp_ranks = (
                session.query(CompetitorRank)
                .filter(CompetitorRank.competitor_domain == competitor)
                .all()
            )
            our_ranks = (
                session.query(RankingRecord)
                .filter(RankingRecord.domain == domain)
                .all()
            )
            comp_backlinks = (
                session.query(func.count(Backlink.id))
                .filter(
                    Backlink.source_domain == competitor,
                    Backlink.status == "active",
                )
                .scalar()
            ) or 0

        our_kw_map = {r.keyword: r.position for r in our_ranks}
        comp_kw_map = {r.keyword: r.position for r in comp_ranks}

        shared_keywords = set(our_kw_map.keys()) & set(comp_kw_map.keys())
        we_win = sum(
            1 for kw in shared_keywords if our_kw_map[kw] < comp_kw_map[kw]
        )
        they_win = sum(
            1 for kw in shared_keywords if comp_kw_map[kw] < our_kw_map[kw]
        )
        content_gaps = set(comp_kw_map.keys()) - set(our_kw_map.keys())

        comp_positions = list(comp_kw_map.values())
        avg_comp_pos = _safe_div(
            sum(comp_positions), max(len(comp_positions), 1)
        )

        return {
            "competitor_domain": competitor,
            "shared_keywords": len(shared_keywords),
            "we_outrank": we_win,
            "they_outrank": they_win,
            "their_unique_keywords": len(content_gaps),
            "content_gap_keywords": sorted(list(content_gaps))[:50],
            "their_backlink_count": comp_backlinks,
            "avg_their_position": round(avg_comp_pos, 2),
        }

    def _competitor_summary(
        self, domain: str, competitors: list[str]
    ) -> dict:
        """Build a high-level competitor summary."""
        with get_session() as session:
            our_vis = (
                session.query(VisibilityScore)
                .filter(VisibilityScore.domain == domain)
                .order_by(desc(VisibilityScore.date))
                .first()
            )
            our_backlinks = (
                session.query(func.count(Backlink.id))
                .filter(Backlink.status == "active")
                .scalar()
            ) or 0

        return {
            "our_visibility": our_vis.score if our_vis else 0,
            "our_backlinks": our_backlinks,
            "competitor_count": len(competitors),
        }

    # ==================================================================
    # PRIVATE: AI prompt & fallback helpers
    # ==================================================================

    def _build_summary_prompt(self, all_data: dict) -> str:
        """Construct the prompt for the AI executive summary."""
        scores = all_data.get("scores", {})
        modules = scores.get("modules", {})
        tech = all_data.get("technical", {})
        bl = all_data.get("backlinks", {})
        content = all_data.get("content", {})
        rankings = all_data.get("rankings", {})

        bl_metrics = bl.get("key_metrics", {})
        content_metrics = content.get("key_metrics", {})
        rank_metrics = rankings.get("key_metrics", {})

        parts = [
            "Analyse the following SEO data for domain: " + all_data.get("domain", "unknown"),
            "",
            "SCORES:",
            "  Overall: " + str(scores.get("overall", 0)),
            "  Technical: " + str(modules.get("technical", 0)),
            "  On-Page: " + str(modules.get("onpage", 0)),
            "  Content: " + str(modules.get("content", 0)),
            "  Backlinks: " + str(modules.get("backlink", 0)),
            "  Visibility: " + str(modules.get("visibility", 0)),
            "  Local: " + str(modules.get("local", 0)),
            "",
            "TECHNICAL ISSUES: " + str(len(tech.get("issues", []))),
            "BACKLINK METRICS: active=" + str(bl_metrics.get("active", 0))
                + " toxic=" + str(bl_metrics.get("toxic", 0)),
            "CONTENT: posts=" + str(content_metrics.get("total_posts", 0))
                + " avg_score=" + str(content_metrics.get("avg_seo_score", 0)),
            "RANKINGS: visibility=" + str(rank_metrics.get("visibility_score", 0))
                + " avg_pos=" + str(rank_metrics.get("avg_position", 0)),
            "",
            "Return JSON with these exact keys:",
            "  overall_health_score (0-100 integer),",
            "  grade (string A-F),",
            "  top_5_wins (array of strings),",
            "  top_5_issues (array of strings),",
            "  month_over_month_trend (string: improving/stable/declining),",
            "  estimated_organic_traffic_impact (string description),",
            "  priority_action_items (array of objects with keys: action, impact, estimated_roi)",
        ]
        return "\n".join(parts)

    @staticmethod
    def _validate_executive_summary(raw: Any, fallback_score: float) -> dict:
        """Ensure the AI response contains all required fields."""
        if not isinstance(raw, dict):
            raw = {}
        defaults = {
            "overall_health_score": int(fallback_score),
            "grade": _letter_grade(fallback_score),
            "top_5_wins": [],
            "top_5_issues": [],
            "month_over_month_trend": "stable",
            "estimated_organic_traffic_impact": "Unable to estimate",
            "priority_action_items": [],
        }
        for key, default in defaults.items():
            if key not in raw:
                raw[key] = default
        return raw

    @staticmethod
    def _rule_based_summary(all_data: dict) -> dict:
        """Deterministic fallback when LLM is unavailable."""
        scores = all_data.get("scores", {})
        modules = scores.get("modules", {})
        overall = scores.get("overall", 0)
        trend_info = scores.get("trend", {})

        wins: list[str] = []
        issues: list[str] = []

        tech_score = modules.get("technical", 0)
        if tech_score >= 80:
            wins.append("Strong technical SEO foundation (score: " + str(tech_score) + ")")
        elif tech_score > 0:
            issues.append("Technical SEO needs improvement (score: " + str(tech_score) + ")")

        content_score = modules.get("content", 0)
        if content_score >= 70:
            wins.append("Good content quality (avg SEO score: " + str(content_score) + ")")
        elif content_score > 0:
            issues.append("Content quality below target (score: " + str(content_score) + ")")

        bl_score = modules.get("backlink", 0)
        if bl_score >= 80:
            wins.append("Healthy backlink profile (score: " + str(bl_score) + ")")
        elif bl_score > 0:
            issues.append("Backlink health needs attention (score: " + str(bl_score) + ")")

        vis_score = modules.get("visibility", 0)
        if vis_score >= 60:
            wins.append("Solid search visibility (score: " + str(vis_score) + ")")
        elif vis_score > 0:
            issues.append("Low search visibility (score: " + str(vis_score) + ")")

        local_score = modules.get("local", 0)
        if local_score >= 70:
            wins.append("Good local SEO presence (score: " + str(local_score) + ")")
        elif local_score > 0:
            issues.append("Local SEO needs work (score: " + str(local_score) + ")")

        change = trend_info.get("change_pct", 0)
        if change > 5:
            trend = "improving"
        elif change < -5:
            trend = "declining"
        else:
            trend = "stable"

        priority_items = []
        sorted_modules = sorted(modules.items(), key=lambda x: x[1])
        for mod_name, mod_score in sorted_modules[:3]:
            if mod_score < 70:
                impact = "high" if mod_score < 50 else "medium"
                roi_desc = (
                    "Improving from " + str(mod_score)
                    + " to 80+ could yield 20-40% traffic gain"
                )
                priority_items.append({
                    "action": "Improve " + mod_name + " SEO",
                    "impact": impact,
                    "estimated_roi": roi_desc,
                })

        return {
            "overall_health_score": int(overall),
            "grade": _letter_grade(overall),
            "top_5_wins": wins[:5],
            "top_5_issues": issues[:5],
            "month_over_month_trend": trend,
            "estimated_organic_traffic_impact": (
                "Overall score " + str(int(overall)) + "/100 -- " + trend + " trend"
            ),
            "priority_action_items": priority_items,
        }

    # ==================================================================
    # PRIVATE: recommendations compiler
    # ==================================================================

    @staticmethod
    def _compile_recommendations(all_data: dict) -> list:
        """Synthesise cross-module recommendations from collected data."""
        recs: list[dict] = []

        # Technical issues
        tech = all_data.get("technical", {})
        for issue in tech.get("issues", [])[:5]:
            recs.append({
                "module": "technical",
                "priority": issue.get("priority", "medium"),
                "recommendation": "Fix: " + issue.get("check", "unknown issue"),
                "details": issue.get("details", ""),
            })

        # Backlink issues
        bl_metrics = all_data.get("backlinks", {}).get("key_metrics", {})
        toxic_count = bl_metrics.get("toxic", 0)
        if toxic_count > 0:
            recs.append({
                "module": "backlinks",
                "priority": "high",
                "recommendation": "Disavow " + str(toxic_count) + " toxic backlinks",
                "details": "Toxic links can hurt domain authority and rankings.",
            })
        lost_count = bl_metrics.get("lost", 0)
        if lost_count > 5:
            recs.append({
                "module": "backlinks",
                "priority": "medium",
                "recommendation": "Investigate " + str(lost_count) + " lost backlinks",
                "details": "Consider outreach to recover valuable lost links.",
            })

        # Content issues
        content_issues = all_data.get("content", {}).get("issues", [])
        for ci in content_issues[:3]:
            post_name = ci.get("post", "unknown") if isinstance(ci, dict) else str(ci)
            score_val = ci.get("seo_score", "N/A") if isinstance(ci, dict) else "N/A"
            recs.append({
                "module": "content",
                "priority": "medium",
                "recommendation": "Optimise content: " + str(post_name),
                "details": "SEO score " + str(score_val) + " is below threshold.",
            })

        # Local issues
        local_issues = all_data.get("local", {}).get("issues", [])
        if isinstance(local_issues, list):
            for li in local_issues[:3]:
                text = li if isinstance(li, str) else str(li)
                recs.append({
                    "module": "local",
                    "priority": "medium",
                    "recommendation": text,
                    "details": "",
                })

        # Rankings
        rank_metrics = all_data.get("rankings", {}).get("key_metrics", {})
        avg_position = rank_metrics.get("avg_position", 0)
        if avg_position > 20:
            recs.append({
                "module": "rankings",
                "priority": "high",
                "recommendation": (
                    "Average position is " + str(avg_position)
                    + " -- focus on top-20 keywords"
                ),
                "details": "Target striking-distance keywords (positions 11-20) for quick wins.",
            })

        return recs

    # ==================================================================
    # PRIVATE: persistence
    # ==================================================================

    @staticmethod
    def _save_report(domain: str, report_data: dict) -> int:
        """Persist the report to the database."""
        title = (
            "Full SEO Report -- " + domain
            + " -- " + _utcnow().strftime("%Y-%m-%d")
        )
        with get_session() as session:
            report = Report(
                report_type="full_report",
                title=title,
                data_json=report_data,
            )
            session.add(report)
            session.flush()
            report_id = report.id
        logger.info("Report saved with id=%d", report_id)
        return report_id

    # ==================================================================
    # PRIVATE: scheduling helpers
    # ==================================================================

    @staticmethod
    def _calc_next_run(frequency: str) -> datetime:
        """Calculate the next run datetime for a scheduled report."""
        now = _utcnow()
        deltas = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "biweekly": timedelta(weeks=2),
            "monthly": timedelta(days=30),
        }
        return now + deltas.get(frequency, timedelta(days=1))

    # ==================================================================
    # PRIVATE: empty section helper
    # ==================================================================

    @staticmethod
    def _empty_section() -> dict:
        """Return an empty section structure for modules with no data."""
        return {
            "score": 0,
            "key_metrics": {},
            "issues": [],
            "improvements": [],
        }
