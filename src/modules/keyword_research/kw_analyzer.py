"""Keyword analyzer -- comparison, quick wins, seasonal analysis, reporting, and export."""

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KeywordAnalyzer:
    """Analyze, compare, and report on keyword research data.

    Provides comparison tables, quick-win identification, seasonal
    trend analysis via Google Trends, structured report generation,
    and CSV/JSON export.

    Usage::

        from src.integrations.llm_client import LLMClient
        from src.integrations.google_trends import GoogleTrendsClient

        analyzer = KeywordAnalyzer(
            llm_client=LLMClient(),
            trends_client=GoogleTrendsClient(),
        )
        quick = await analyzer.find_quick_wins(keywords)
        report = await analyzer.generate_keyword_report(research_data)
    """

    def __init__(
        self,
        llm_client=None,
        trends_client=None,
    ):
        from src.integrations.llm_client import LLMClient
        from src.integrations.google_trends import GoogleTrendsClient

        self._llm = llm_client or LLMClient()
        self._trends = trends_client or GoogleTrendsClient()

    # ------------------------------------------------------------------
    # compare_keywords
    # ------------------------------------------------------------------

    async def compare_keywords(self, keywords: list[dict]) -> list[dict]:
        """Compare keywords side by side with rankings in a comparison table.

        Each keyword dict should have at minimum: keyword, estimated_volume,
        difficulty_estimate, intent, opportunity_score.

        Returns sorted list of keyword dicts enriched with rank fields.
        """
        logger.info("Comparing %d keywords", len(keywords))
        if not keywords:
            return []

        # Sort by opportunity score descending as default ranking
        sorted_kws = sorted(
            keywords,
            key=lambda x: int(x.get("opportunity_score", 0)),
            reverse=True,
        )

        # Add ranking columns
        vol_ranked = sorted(
            range(len(sorted_kws)),
            key=lambda i: int(sorted_kws[i].get("estimated_volume", 0)),
            reverse=True,
        )
        diff_ranked = sorted(
            range(len(sorted_kws)),
            key=lambda i: int(sorted_kws[i].get("difficulty_estimate", 50)),
        )
        score_ranked = sorted(
            range(len(sorted_kws)),
            key=lambda i: int(sorted_kws[i].get("opportunity_score", 0)),
            reverse=True,
        )

        vol_rank_map: dict[int, int] = {}
        for rank, idx in enumerate(vol_ranked, start=1):
            vol_rank_map[idx] = rank

        diff_rank_map: dict[int, int] = {}
        for rank, idx in enumerate(diff_ranked, start=1):
            diff_rank_map[idx] = rank

        score_rank_map: dict[int, int] = {}
        for rank, idx in enumerate(score_ranked, start=1):
            score_rank_map[idx] = rank

        compared: list[dict] = []
        for idx, kw in enumerate(sorted_kws):
            entry = dict(kw)
            entry["overall_rank"] = idx + 1
            entry["volume_rank"] = vol_rank_map.get(idx, 0)
            entry["difficulty_rank"] = diff_rank_map.get(idx, 0)
            entry["score_rank"] = score_rank_map.get(idx, 0)
            # Composite rank: average of all ranks (lower is better)
            ranks = [
                entry["volume_rank"],
                entry["difficulty_rank"],
                entry["score_rank"],
            ]
            entry["composite_rank"] = round(sum(ranks) / len(ranks), 1)
            compared.append(entry)

        # Re-sort by composite rank
        compared.sort(key=lambda x: x["composite_rank"])
        for idx, entry in enumerate(compared):
            entry["overall_rank"] = idx + 1

        logger.info("Comparison complete for %d keywords", len(compared))
        return compared

    # ------------------------------------------------------------------
    # find_quick_wins
    # ------------------------------------------------------------------

    async def find_quick_wins(
        self,
        keywords: list[dict],
        current_rankings: Optional[dict] = None,
    ) -> list[dict]:
        """Identify keywords that are easy to rank for: low difficulty + high opportunity.

        Args:
            keywords: List of keyword dicts with difficulty and opportunity scores.
            current_rankings: Optional dict mapping keyword text to current position.

        Returns:
            List of quick-win keyword dicts sorted by potential, each with
            quick_win_score and quick_win_reason.
        """
        logger.info("Finding quick wins among %d keywords", len(keywords))
        if not keywords:
            return []

        current_rankings = current_rankings or {}
        quick_wins: list[dict] = []

        for kw in keywords:
            kw_text = kw.get("keyword", "")
            difficulty = int(kw.get("difficulty_estimate", 50))
            volume = int(kw.get("estimated_volume", 0))
            opp_score = int(kw.get("opportunity_score", 0))
            intent = kw.get("intent", "informational")

            # Quick win criteria:
            # - Difficulty <= 40 (low competition)
            # - Volume > 0 (some search demand)
            # - Opportunity score > 30
            is_quick_win = difficulty <= 40 and volume > 0 and opp_score > 30

            # Also consider keywords where we already rank (positions 11-30)
            current_pos = current_rankings.get(kw_text)
            if current_pos is not None and 11 <= current_pos <= 30:
                is_quick_win = True

            if not is_quick_win:
                continue

            # Calculate quick win score
            # High volume + low difficulty + good intent = high score
            import math
            vol_factor = min(math.log10(max(volume, 1)) * 15, 50)
            diff_factor = max(0, 50 - difficulty)  # Lower diff = higher factor
            intent_bonus = 0
            if intent in ("transactional", "commercial"):
                intent_bonus = 10
            position_bonus = 0
            if current_pos is not None and 11 <= current_pos <= 30:
                position_bonus = 20  # Already ranking nearby

            qw_score = int(vol_factor + diff_factor + intent_bonus + position_bonus)
            qw_score = max(0, min(100, qw_score))

            # Build reason
            reasons = []
            if difficulty <= 20:
                reasons.append("very low competition")
            elif difficulty <= 40:
                reasons.append("low competition")
            if volume >= 1000:
                reasons.append("high search volume")
            elif volume >= 100:
                reasons.append("decent search volume")
            if intent in ("transactional", "commercial"):
                reasons.append("high-value intent")
            if current_pos is not None and 11 <= current_pos <= 30:
                reasons.append("already ranking at #" + str(current_pos))

            entry = dict(kw)
            entry["quick_win_score"] = qw_score
            entry["quick_win_reason"] = "; ".join(reasons) if reasons else "Good opportunity"
            entry["current_position"] = current_pos
            quick_wins.append(entry)

        # Sort by quick win score descending
        quick_wins.sort(key=lambda x: x["quick_win_score"], reverse=True)

        logger.info("Found %d quick wins", len(quick_wins))
        return quick_wins

    # ------------------------------------------------------------------
    # seasonal_analysis
    # ------------------------------------------------------------------

    async def seasonal_analysis(self, keywords: list[str]) -> list[dict]:
        """Use Google Trends to determine seasonality patterns.

        Returns keywords with peak_months, seasonal_score, best_publish_time.
        """
        logger.info("Analyzing seasonality for %d keywords", len(keywords))
        results: list[dict] = []

        # Process in batches of 5 (Google Trends limit)
        batch_size = 5
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i : i + batch_size]

            try:
                trend_data = await self._trends.get_interest_over_time(
                    batch, timeframe="today 12-m"
                )
            except Exception as exc:
                logger.warning("Trends fetch failed for batch: %s", exc)
                for kw in batch:
                    results.append({
                        "keyword": kw,
                        "peak_months": [],
                        "seasonal_score": 0,
                        "best_publish_time": "anytime",
                        "trend_direction": "unknown",
                        "monthly_data": [],
                    })
                continue

            # Analyze each keyword in the batch
            for kw in batch:
                monthly_values: dict[str, list[int]] = {}
                kw_values: list[int] = []

                for row in trend_data:
                    date_str = str(row.get("date", ""))
                    value = int(row.get(kw, 0))
                    kw_values.append(value)

                    # Extract month from date
                    if len(date_str) >= 7:
                        month = date_str[:7]  # YYYY-MM
                        if month not in monthly_values:
                            monthly_values[month] = []
                        monthly_values[month].append(value)

                if not kw_values:
                    results.append({
                        "keyword": kw,
                        "peak_months": [],
                        "seasonal_score": 0,
                        "best_publish_time": "anytime",
                        "trend_direction": "unknown",
                        "monthly_data": [],
                    })
                    continue

                # Calculate monthly averages
                month_avgs: list[dict] = []
                for month, vals in sorted(monthly_values.items()):
                    avg_val = sum(vals) // len(vals) if vals else 0
                    month_avgs.append({"month": month, "interest": avg_val})

                # Find peak months (top 3)
                sorted_months = sorted(
                    month_avgs, key=lambda x: x["interest"], reverse=True
                )
                peak_months = [m["month"] for m in sorted_months[:3]]

                # Calculate seasonal score (0-100)
                # Higher variance = more seasonal
                mean_val = sum(kw_values) / len(kw_values) if kw_values else 0
                if mean_val > 0:
                    variance = sum(
                        (v - mean_val) ** 2 for v in kw_values
                    ) / len(kw_values)
                    std_dev = variance ** 0.5
                    cv = std_dev / mean_val  # Coefficient of variation
                    seasonal_score = min(int(cv * 100), 100)
                else:
                    seasonal_score = 0

                # Determine trend direction
                trend_direction = "stable"
                if len(kw_values) >= 4:
                    first_quarter = sum(kw_values[:len(kw_values)//4])
                    last_quarter = sum(kw_values[-len(kw_values)//4:])
                    if first_quarter > 0:
                        change = (last_quarter - first_quarter) / first_quarter
                        if change > 0.2:
                            trend_direction = "rising"
                        elif change < -0.2:
                            trend_direction = "declining"

                # Best publish time: 1-2 months before peak
                best_publish = "anytime"
                if peak_months and seasonal_score > 20:
                    # Parse peak month
                    try:
                        peak_date = datetime.strptime(peak_months[0], "%Y-%m")
                        publish_month = peak_date.month - 2
                        if publish_month <= 0:
                            publish_month += 12
                        month_names = [
                            "January", "February", "March", "April",
                            "May", "June", "July", "August",
                            "September", "October", "November", "December",
                        ]
                        best_publish = month_names[publish_month - 1]
                    except (ValueError, IndexError):
                        best_publish = "1-2 months before peak"

                results.append({
                    "keyword": kw,
                    "peak_months": peak_months,
                    "seasonal_score": seasonal_score,
                    "best_publish_time": best_publish,
                    "trend_direction": trend_direction,
                    "monthly_data": month_avgs,
                })

        logger.info("Seasonal analysis complete for %d keywords", len(results))
        return results

    # ------------------------------------------------------------------
    # generate_keyword_report
    # ------------------------------------------------------------------

    async def generate_keyword_report(self, research_data: dict) -> dict:
        """Summarize research into a structured report with top keywords,
        cluster summary, recommendations, and priority actions.
        """
        logger.info("Generating keyword research report")

        summary = research_data.get("summary", {})
        clusters = research_data.get("clusters", [])
        all_keywords = research_data.get("scored_keywords", [])
        if not all_keywords:
            all_keywords = research_data.get("expanded_keywords", [])

        # Top keywords by opportunity
        top_keywords = sorted(
            [kw for kw in all_keywords if kw.get("opportunity_score") is not None],
            key=lambda x: int(x.get("opportunity_score", 0)),
            reverse=True,
        )[:20]

        # Cluster summary
        cluster_summary = []
        for cl in clusters:
            cluster_summary.append({
                "name": cl.get("cluster_name", "Unknown"),
                "intent": cl.get("cluster_intent", "informational"),
                "keyword_count": len(cl.get("keywords", [])),
                "primary_keyword": cl.get("primary_keyword", ""),
                "total_volume": cl.get("estimated_total_volume", 0),
            })
        cluster_summary.sort(
            key=lambda x: x["total_volume"], reverse=True
        )

        # Build AI-powered recommendations
        recommendations = []
        priority_actions = []

        try:
            report_context = (
                "Niche: " + str(research_data.get("niche", "Unknown")) + "\n"
                "Total keywords: " + str(summary.get("total_keywords", 0)) + "\n"
                "Total clusters: " + str(summary.get("total_clusters", 0)) + "\n"
                "Average difficulty: " + str(summary.get("average_difficulty", 0)) + "\n"
                "Average opportunity: " + str(summary.get("average_opportunity_score", 0)) + "\n"
                "Intent distribution: " + json.dumps(summary.get("intent_distribution", {})) + "\n\n"
            )

            top_kw_block = "\n".join(
                "- " + kw.get("keyword", "") + " (vol:"
                + str(kw.get("estimated_volume", 0))
                + ", diff:" + str(kw.get("difficulty_estimate", 50))
                + ", score:" + str(kw.get("opportunity_score", 0)) + ")"
                for kw in top_keywords[:10]
            )

            cluster_block = "\n".join(
                "- " + cl["name"] + ": " + str(cl["keyword_count"])
                + " keywords, vol:" + str(cl["total_volume"])
                for cl in cluster_summary[:10]
            )

            prompt = (
                "You are an SEO strategist. Based on this keyword research data, "
                "provide actionable recommendations.\n\n"
                + report_context
                + "Top keywords:\n" + top_kw_block + "\n\n"
                "Top clusters:\n" + cluster_block + "\n\n"
                "Return a JSON object with:\n"
                "- \"executive_summary\": 3-4 sentence overview of the research findings\n"
                "- \"recommendations\": array of recommendation objects with "
                "\"action\", \"priority\" (high/medium/low), \"impact\" description\n"
                "- \"priority_actions\": array of immediate action strings (top 5)\n"
                "- \"content_strategy\": brief content strategy recommendation\n"
                "- \"risk_factors\": array of risk strings to watch out for\n\n"
                "Return valid JSON object only."
            )

            ai_report = await self._llm.generate_json(prompt)
            recommendations = ai_report.get("recommendations", [])
            priority_actions = ai_report.get("priority_actions", [])
            executive_summary = str(ai_report.get("executive_summary", ""))
            content_strategy = str(ai_report.get("content_strategy", ""))
            risk_factors = ai_report.get("risk_factors", [])
        except Exception as exc:
            logger.warning("AI report generation failed: %s", exc)
            executive_summary = (
                "Research found "
                + str(summary.get("total_keywords", 0))
                + " keywords across "
                + str(summary.get("total_clusters", 0))
                + " clusters."
            )
            content_strategy = "Focus on low-difficulty, high-volume keywords first."
            risk_factors = ["Unable to generate AI analysis."]

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "niche": research_data.get("niche", "Unknown"),
            "executive_summary": executive_summary,
            "statistics": {
                "total_keywords": summary.get("total_keywords", 0),
                "total_estimated_volume": summary.get("total_estimated_volume", 0),
                "average_difficulty": summary.get("average_difficulty", 0),
                "average_opportunity_score": summary.get("average_opportunity_score", 0),
                "total_clusters": summary.get("total_clusters", 0),
                "intent_distribution": summary.get("intent_distribution", {}),
                "source_distribution": summary.get("source_distribution", {}),
            },
            "top_keywords": top_keywords,
            "cluster_summary": cluster_summary,
            "recommendations": recommendations,
            "priority_actions": priority_actions,
            "content_strategy": content_strategy,
            "risk_factors": risk_factors,
        }

        logger.info("Keyword report generated")
        return report

    # ------------------------------------------------------------------
    # export_to_csv
    # ------------------------------------------------------------------

    async def export_to_csv(
        self, keywords: list[dict], filepath: str,
    ) -> str:
        """Export keyword data to CSV file.

        Returns the absolute filepath of the created CSV.
        """
        logger.info("Exporting %d keywords to CSV: %s", len(keywords), filepath)
        if not keywords:
            logger.warning("No keywords to export")
            return filepath

        # Ensure directory exists
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        # Collect all fieldnames from all keyword dicts
        fieldnames_set: set[str] = set()
        for kw in keywords:
            fieldnames_set.update(kw.keys())

        # Preferred column order
        preferred_order = [
            "keyword", "estimated_volume", "difficulty_estimate",
            "intent", "opportunity_score", "source", "reasoning",
            "confidence", "suggested_content_type",
            "quick_win_score", "quick_win_reason",
        ]
        fieldnames = []
        for col in preferred_order:
            if col in fieldnames_set:
                fieldnames.append(col)
                fieldnames_set.discard(col)
        fieldnames.extend(sorted(fieldnames_set))

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for kw in keywords:
                row = {}
                for key in fieldnames:
                    val = kw.get(key, "")
                    if isinstance(val, (list, dict)):
                        row[key] = json.dumps(val, default=str)
                    else:
                        row[key] = val
                writer.writerow(row)

        abs_path = os.path.abspath(filepath)
        logger.info("CSV exported: %s (%d rows)", abs_path, len(keywords))
        return abs_path

    # ------------------------------------------------------------------
    # export_to_json
    # ------------------------------------------------------------------

    async def export_to_json(
        self, research_data: dict, filepath: str,
    ) -> str:
        """Export full research data to JSON file.

        Returns the absolute filepath of the created JSON.
        """
        logger.info("Exporting research data to JSON: %s", filepath)

        # Ensure directory exists
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(research_data, f, indent=2, default=str, ensure_ascii=False)

        abs_path = os.path.abspath(filepath)
        logger.info("JSON exported: %s", abs_path)
        return abs_path

    # ------------------------------------------------------------------
    # Utility: in-memory export for Streamlit downloads
    # ------------------------------------------------------------------

    @staticmethod
    def keywords_to_csv_bytes(keywords: list[dict]) -> bytes:
        """Convert keyword list to CSV bytes for Streamlit download buttons."""
        if not keywords:
            return b"No data"

        fieldnames_set: set[str] = set()
        for kw in keywords:
            fieldnames_set.update(kw.keys())

        preferred_order = [
            "keyword", "estimated_volume", "difficulty_estimate",
            "intent", "opportunity_score", "source", "reasoning",
        ]
        fieldnames = []
        for col in preferred_order:
            if col in fieldnames_set:
                fieldnames.append(col)
                fieldnames_set.discard(col)
        fieldnames.extend(sorted(fieldnames_set))

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for kw in keywords:
            row = {}
            for key in fieldnames:
                val = kw.get(key, "")
                if isinstance(val, (list, dict)):
                    row[key] = json.dumps(val, default=str)
                else:
                    row[key] = val
            writer.writerow(row)
        return output.getvalue().encode("utf-8")

    @staticmethod
    def research_to_json_bytes(research_data: dict) -> bytes:
        """Convert research data dict to JSON bytes for Streamlit download."""
        return json.dumps(
            research_data, indent=2, default=str, ensure_ascii=False
        ).encode("utf-8")
