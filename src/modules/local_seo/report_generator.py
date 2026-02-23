
"""
Local SEO Report Generator
==========================
Generates professional HTML and structured JSON reports from Local SEO audit data.
"""

import json
import logging
import os
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class LocalSEOReportGenerator:
    """Generates beautiful HTML and JSON reports from Local SEO audit data."""

    def __init__(self, output_dir: str = "data/exports") -> None:
        """Initialize the report generator.

        Args:
            output_dir: Directory where reports will be saved.
        """
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("LocalSEOReportGenerator initialized. Output dir: %s", self.output_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _esc(value: Any) -> str:
        """HTML-escape a value, converting to string first."""
        return escape(str(value)) if value is not None else ""

    @staticmethod
    def _score_color(score: float) -> str:
        """Return CSS colour class name based on score threshold."""
        if score > 70:
            return "green"
        if score > 40:
            return "yellow"
        return "red"

    @staticmethod
    def _score_hex(score: float) -> str:
        if score > 70:
            return "#22c55e"
        if score > 40:
            return "#eab308"
        return "#ef4444"

    @staticmethod
    def _severity_badge_color(severity: str) -> str:
        s = severity.lower()
        if s in ("critical", "high"):
            return "#ef4444"
        if s == "medium":
            return "#eab308"
        return "#3b82f6"

    @staticmethod
    def _priority_color(priority: str) -> str:
        p = priority.upper()
        if p == "P1":
            return "#ef4444"
        if p == "P2":
            return "#eab308"
        return "#3b82f6"

    @staticmethod
    def _status_icon(status: str) -> str:
        s = status.lower()
        if s == "pass":
            return "&#x2705;"  # ✅
        if s == "fail":
            return "&#x274C;"  # ❌
        return "&#x26A0;&#xFE0F;"  # ⚠️

    @staticmethod
    def _bool_icon(val: Optional[bool]) -> str:
        if val is True:
            return "&#x2705;"
        if val is False:
            return "&#x274C;"
        return "&#x2796;"  # —

    def _safe_scores(self, audit_data: dict) -> dict:
        """Return scores dict with safe defaults."""
        scores = audit_data.get("scores", {})
        return {
            "overall_score": scores.get("overall_score", 0),
            "onpage_score": scores.get("onpage_score", 0),
            "gmb_score": scores.get("gmb_score", 0),
            "citation_score": scores.get("citation_score", 0),
            "review_score": scores.get("review_score", 0),
            "content_score": scores.get("content_score", 0),
            "backlink_score": scores.get("backlink_score", 0),
        }

    # ------------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------------

    def _build_css(self) -> str:
        return """
        <style>
            /* === RESET & BASE === */
            *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
                             Ubuntu, Cantarell, "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif;
                background: #f1f5f9;
                color: #334155;
                line-height: 1.6;
                -webkit-font-smoothing: antialiased;
            }
            .container { max-width: 1100px; margin: 0 auto; padding: 0 24px 48px; }

            /* === HEADER === */
            .report-header {
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                color: #fff;
                padding: 48px 0 56px;
                text-align: center;
                position: relative;
                overflow: hidden;
            }
            .report-header::after {
                content: "";
                position: absolute; bottom: 0; left: 0; right: 0; height: 6px;
                background: linear-gradient(90deg, #3b82f6, #22c55e, #eab308, #ef4444);
            }
            .report-header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 4px; }
            .report-header .subtitle { opacity: .75; font-size: .95rem; margin-bottom: 24px; }

            /* Circular gauge */
            .gauge-wrap { display: inline-block; position: relative; width: 140px; height: 140px; margin-top: 8px; }
            .gauge-circle {
                width: 140px; height: 140px; border-radius: 50%;
                background: conic-gradient(
                    var(--gauge-color) calc(var(--gauge-pct) * 1%),
                    rgba(255,255,255,.15) calc(var(--gauge-pct) * 1%)
                );
                display: flex; align-items: center; justify-content: center;
            }
            .gauge-inner {
                width: 110px; height: 110px; border-radius: 50%; background: #1e293b;
                display: flex; align-items: center; justify-content: center;
                flex-direction: column;
            }
            .gauge-value { font-size: 2.2rem; font-weight: 800; line-height: 1; }
            .gauge-label { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; opacity: .7; margin-top: 4px; }

            /* === SECTION === */
            .section { margin-top: 32px; }
            .section-title {
                font-size: 1.25rem; font-weight: 700; color: #0f172a;
                border-bottom: 3px solid #3b82f6; display: inline-block;
                padding-bottom: 4px; margin-bottom: 16px;
            }

            /* === CARDS GRID === */
            .score-grid {
                display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: 16px;
            }
            .score-card {
                background: #fff; border-radius: 12px; padding: 20px 16px;
                box-shadow: 0 1px 3px rgba(0,0,0,.08); text-align: center;
                transition: transform .15s;
            }
            .score-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.1); }
            .score-card .card-label { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: #64748b; margin-bottom: 8px; }
            .score-card .card-value { font-size: 1.6rem; font-weight: 800; }
            .progress-bar-bg {
                height: 6px; border-radius: 3px; background: #e2e8f0; margin-top: 10px; overflow: hidden;
            }
            .progress-bar-fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
            .progress-bar-fill.green { background: #22c55e; }
            .progress-bar-fill.yellow { background: #eab308; }
            .progress-bar-fill.red { background: #ef4444; }

            /* === TABLE === */
            .data-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
            .data-table th {
                background: #f8fafc; text-align: left; padding: 12px 16px;
                font-size: .75rem; text-transform: uppercase; letter-spacing: .05em;
                color: #64748b; border-bottom: 2px solid #e2e8f0;
            }
            .data-table td { padding: 10px 16px; border-bottom: 1px solid #f1f5f9; font-size: .9rem; }
            .data-table tr:last-child td { border-bottom: none; }
            .data-table tr:hover td { background: #f8fafc; }

            /* === BADGES === */
            .badge {
                display: inline-block; padding: 2px 10px; border-radius: 999px;
                font-size: .72rem; font-weight: 600; color: #fff; text-transform: uppercase;
                letter-spacing: .04em;
            }

            /* === ISSUES LIST === */
            .issue-item {
                background: #fff; border-radius: 10px; padding: 14px 18px;
                margin-bottom: 10px; display: flex; align-items: center; gap: 12px;
                box-shadow: 0 1px 2px rgba(0,0,0,.05);
            }
            .issue-item .issue-text { flex: 1; font-size: .9rem; }
            .issue-item .issue-cat { font-size: .75rem; color: #94a3b8; }

            /* === STAT ROW === */
            .stat-row {
                display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 20px;
            }
            .stat-box {
                background: #fff; border-radius: 10px; padding: 16px 20px;
                box-shadow: 0 1px 3px rgba(0,0,0,.06); flex: 1; min-width: 140px; text-align: center;
            }
            .stat-box .stat-val { font-size: 1.4rem; font-weight: 800; color: #0f172a; }
            .stat-box .stat-lbl { font-size: .75rem; color: #64748b; text-transform: uppercase; letter-spacing: .04em; margin-top: 2px; }

            /* === RECOMMENDATIONS === */
            .rec-group-title { font-size: 1.1rem; font-weight: 700; margin: 24px 0 12px; }
            .rec-card {
                background: #fff; border-radius: 10px; padding: 16px 20px;
                margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,.06);
            }
            .rec-card .rec-title { font-weight: 700; font-size: .95rem; margin-bottom: 4px; }
            .rec-card .rec-desc { font-size: .85rem; color: #64748b; margin-bottom: 8px; }
            .rec-meta { display: flex; flex-wrap: wrap; gap: 8px; }
            .rec-meta .tag {
                font-size: .72rem; padding: 2px 8px; border-radius: 6px;
                background: #f1f5f9; color: #475569;
            }

            /* === FOOTER === */
            .report-footer {
                margin-top: 48px; padding-top: 24px; border-top: 1px solid #e2e8f0;
                text-align: center; font-size: .78rem; color: #94a3b8;
            }

            /* === RESPONSIVE === */
            @media (max-width: 640px) {
                .score-grid { grid-template-columns: repeat(2, 1fr); }
                .stat-row { flex-direction: column; }
                .data-table { font-size: .82rem; }
                .data-table th, .data-table td { padding: 8px 10px; }
            }

            @media print {
                body { background: #fff; }
                .report-header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                .score-card, .data-table, .issue-item, .rec-card { break-inside: avoid; }
            }
        </style>
"""

    # ------------------------------------------------------------------
    # HTML section builders
    # ------------------------------------------------------------------

    def _build_header(self, audit_data: dict, scores: dict) -> str:
        overall = scores["overall_score"]
        color = self._score_hex(overall)
        return f"""
        <div class="report-header">
            <div class="container">
                <h1>{self._esc(audit_data.get("business_name", "Business"))} &mdash; Local SEO Audit</h1>
                <div class="subtitle">
                    {self._esc(audit_data.get("domain", ""))}
                    {(" &bull; " + self._esc(audit_data.get("location", ""))) if audit_data.get("location") else ""}
                    &bull; {self._esc(audit_data.get("audit_date", datetime.now().strftime("%Y-%m-%d")))}
                </div>
                <div class="gauge-wrap">
                    <div class="gauge-circle" style="--gauge-pct:{overall};--gauge-color:{color}">
                        <div class="gauge-inner">
                            <span class="gauge-value">{overall:.0f}</span>
                            <span class="gauge-label">Overall Score</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
"""

    def _build_score_overview(self, scores: dict) -> str:
        cards_data = [
            ("On-Page", scores["onpage_score"]),
            ("Google Business", scores["gmb_score"]),
            ("Citations", scores["citation_score"]),
            ("Reviews", scores["review_score"]),
            ("Content", scores["content_score"]),
            ("Backlinks", scores["backlink_score"]),
        ]
        cards_html = ""
        for label, val in cards_data:
            color_cls = self._score_color(val)
            cards_html += f"""
            <div class="score-card">
                <div class="card-label">{label}</div>
                <div class="card-value" style="color:{self._score_hex(val)}">{val:.0f}</div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill {color_cls}" style="width:{min(val, 100):.0f}%"></div>
                </div>
            </div>"""
        return f"""
        <div class="section">
            <div class="section-title">Score Overview</div>
            <div class="score-grid">{cards_html}
            </div>
        </div>
"""

    def _build_top_issues(self, audit_data: dict) -> str:
        issues: list = audit_data.get("top_issues", [])
        if not issues:
            return ""
        items_html = ""
        for issue in issues:
            sev = issue.get("severity", "info")
            badge_color = self._severity_badge_color(sev)
            items_html += f"""
            <div class="issue-item">
                <span class="badge" style="background:{badge_color}">{self._esc(sev)}</span>
                <span class="issue-text">{self._esc(issue.get("message", ""))}</span>
                <span class="issue-cat">{self._esc(issue.get("category", ""))}</span>
            </div>"""
        return f"""
        <div class="section">
            <div class="section-title">Top Issues</div>
            {items_html}
        </div>
"""

    def _build_onpage(self, audit_data: dict) -> str:
        onpage = audit_data.get("onpage", {})
        checks: list = onpage.get("checks", [])
        if not checks:
            return ""
        rows = ""
        for c in checks:
            icon = self._status_icon(c.get("status", "warning"))
            rows += f"""
            <tr>
                <td>{icon}</td>
                <td>{self._esc(c.get("name", ""))}</td>
                <td>{self._esc(c.get("category", ""))}</td>
                <td>{self._esc(c.get("details", ""))}</td>
            </tr>"""
        return f"""
        <div class="section">
            <div class="section-title">On-Page Local SEO</div>
            <table class="data-table">
                <thead><tr><th style="width:48px">Status</th><th>Check</th><th>Category</th><th>Details</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
"""

    def _build_gbp(self, audit_data: dict) -> str:
        gbp = audit_data.get("gbp", {})
        checklist: list = gbp.get("checklist", [])
        found = gbp.get("listing_found", False)
        score = gbp.get("gmb_score", 0)

        status_line = f'<span style="color:{"#22c55e" if found else "#ef4444"};font-weight:700">{"\'Listing Found\'" if found else "\'Listing Not Found\'"}</span> &nbsp;|&nbsp; GBP Score: <strong>{score:.0f}</strong>'

        rows = ""
        for item in checklist:
            icon = self._status_icon(item.get("status", "fail"))
            pri = item.get("priority", "")
            pri_color = self._priority_color(pri) if pri else "#94a3b8"
            rows += f"""
            <tr>
                <td>{icon}</td>
                <td>{self._esc(item.get("label", ""))}</td>
                <td><span class="badge" style="background:{pri_color}">{self._esc(pri)}</span></td>
                <td>{self._esc(item.get("action", ""))}</td>
            </tr>"""

        table_html = ""
        if rows:
            table_html = f"""
            <table class="data-table">
                <thead><tr><th style="width:48px">Status</th><th>Item</th><th>Priority</th><th>Action</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>"""

        return f"""
        <div class="section">
            <div class="section-title">Google Business Profile</div>
            <p style="margin-bottom:14px">{status_line}</p>
            {table_html}
        </div>
"""

    def _build_citations(self, audit_data: dict) -> str:
        cit = audit_data.get("citations", {})
        summary = cit.get("summary", {})
        results: list = cit.get("results", [])

        total = summary.get("total_directories", 0)
        found = summary.get("found_count", 0)
        missing = summary.get("missing_count", 0)
        c_score = summary.get("citation_score", 0)

        stats_html = f"""
        <div class="stat-row">
            <div class="stat-box"><div class="stat-val">{total}</div><div class="stat-lbl">Total Checked</div></div>
            <div class="stat-box"><div class="stat-val" style="color:#22c55e">{found}</div><div class="stat-lbl">Found</div></div>
            <div class="stat-box"><div class="stat-val" style="color:#ef4444">{missing}</div><div class="stat-lbl">Missing</div></div>
            <div class="stat-box"><div class="stat-val" style="color:{self._score_hex(c_score)}">{c_score:.0f}</div><div class="stat-lbl">Score</div></div>
        </div>"""

        rows = ""
        for r in results:
            found_icon = self._bool_icon(r.get("found"))
            nap_icon = self._bool_icon(r.get("nap_consistent"))
            auth = r.get("authority_score", 0)
            rows += f"""
            <tr>
                <td>{self._esc(r.get("directory_name", ""))}</td>
                <td>{found_icon} {self._esc(r.get("status", ""))}</td>
                <td>{nap_icon}</td>
                <td>{auth}</td>
            </tr>"""

        table_html = ""
        if rows:
            table_html = f"""
            <table class="data-table">
                <thead><tr><th>Directory</th><th>Status</th><th>NAP Consistent</th><th>Authority</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>"""

        return f"""
        <div class="section">
            <div class="section-title">Citations</div>
            {stats_html}
            {table_html}
        </div>
"""

    def _build_reviews(self, audit_data: dict) -> str:
        rev = audit_data.get("reviews", {})
        total_reviews = rev.get("total_reviews", 0)
        avg_rating = rev.get("avg_rating", 0)
        score = rev.get("score", 0)
        comp = rev.get("competitor_comparison", {})

        stats_html = f"""
        <div class="stat-row">
            <div class="stat-box"><div class="stat-val">{total_reviews}</div><div class="stat-lbl">Total Reviews</div></div>
            <div class="stat-box"><div class="stat-val">{avg_rating:.1f} &#x2B50;</div><div class="stat-lbl">Avg Rating</div></div>
            <div class="stat-box"><div class="stat-val" style="color:{self._score_hex(score)}">{score:.0f}</div><div class="stat-lbl">Review Score</div></div>
        </div>"""

        comp_html = ""
        if comp:
            avg_comp_reviews = comp.get("avg_competitor_reviews", "N/A")
            avg_comp_rating = comp.get("avg_competitor_rating", "N/A")
            review_gap = comp.get("review_gap", "N/A")
            rating_gap = comp.get("rating_gap", "N/A")

            comp_html = f"""
            <table class="data-table" style="margin-top:16px">
                <thead><tr><th>Metric</th><th>You</th><th>Competitors Avg</th><th>Gap</th></tr></thead>
                <tbody>
                    <tr><td>Reviews</td><td>{total_reviews}</td><td>{avg_comp_reviews}</td><td>{review_gap}</td></tr>
                    <tr><td>Rating</td><td>{avg_rating:.1f}</td><td>{avg_comp_rating}</td><td>{rating_gap}</td></tr>
                </tbody>
            </table>"""

        return f"""
        <div class="section">
            <div class="section-title">Reviews</div>
            {stats_html}
            {comp_html}
        </div>
"""

    def _build_competitors(self, audit_data: dict) -> str:
        comp = audit_data.get("competitors", {})
        map_pack: list = comp.get("map_pack_results", [])
        our_pos = comp.get("our_position")
        if not map_pack:
            return ""

        our_pos_text = f"Your position: <strong>#{our_pos}</strong>" if our_pos else "Your business was <strong>not found</strong> in the map pack."

        rows = ""
        for mp in map_pack:
            pos = mp.get("position", "-")
            name = self._esc(mp.get("name", ""))
            rating = mp.get("rating", 0)
            rc = mp.get("review_count", 0)
            # Highlight our business
            highlight = ' style="background:#eff6ff"' if our_pos and pos == our_pos else ""
            rows += f"""
            <tr{highlight}>
                <td style="font-weight:700">#{pos}</td>
                <td>{name}</td>
                <td>{rating:.1f} &#x2B50;</td>
                <td>{rc}</td>
            </tr>"""

        return f"""
        <div class="section">
            <div class="section-title">Competitors &mdash; Map Pack</div>
            <p style="margin-bottom:14px">{our_pos_text}</p>
            <table class="data-table">
                <thead><tr><th style="width:64px">Position</th><th>Business</th><th>Rating</th><th>Reviews</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
"""

    def _build_recommendations(self, audit_data: dict) -> str:
        recs: list = audit_data.get("recommendations", [])
        if not recs:
            return ""

        groups = {
            "Quick Wins": {"emoji": "&#x1F680;", "items": []},
            "High Impact": {"emoji": "&#x2B50;", "items": []},
            "Long Term": {"emoji": "&#x1F4C5;", "items": []},
        }
        for rec in recs:
            g = rec.get("group", "Long Term")
            if g not in groups:
                g = "Long Term"
            groups[g]["items"].append(rec)

        sections = ""
        for group_name, gdata in groups.items():
            if not gdata["items"]:
                continue
            cards = ""
            for rec in gdata["items"]:
                pri = rec.get("priority", "P3")
                impact = rec.get("estimated_impact", "medium")
                effort = rec.get("effort", "medium")
                est_time = rec.get("estimated_time", "")
                cards += f"""
                <div class="rec-card">
                    <div class="rec-title">
                        <span class="badge" style="background:{self._priority_color(pri)};margin-right:6px">{self._esc(pri)}</span>
                        {self._esc(rec.get("title", ""))}
                    </div>
                    <div class="rec-desc">{self._esc(rec.get("description", ""))}</div>
                    <div class="rec-meta">
                        <span class="tag">Impact: {self._esc(impact)}</span>
                        <span class="tag">Effort: {self._esc(effort)}</span>
                        {f'<span class="tag">&#x23F1; {self._esc(est_time)}</span>' if est_time else ""}
                        {f'<span class="tag">{self._esc(rec.get("category", ""))}</span>' if rec.get("category") else ""}
                    </div>
                </div>"""
            sections += f"""
            <div class="rec-group-title">{gdata["emoji"]} {self._esc(group_name)}</div>
            {cards}"""

        return f"""
        <div class="section">
            <div class="section-title">Prioritized Recommendations</div>
            {sections}
        </div>
"""

    def _build_footer(self, audit_data: dict) -> str:
        gen_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""
        <div class="report-footer">
            <p>Report generated on {gen_date} for <strong>{self._esc(audit_data.get("business_name", ""))}</strong></p>
            <p style="margin-top:6px">This report is generated automatically and should be reviewed by a qualified SEO professional.
            Scores are indicative and based on automated checks. Actual search engine rankings depend on many additional factors.</p>
        </div>
"""

    # ------------------------------------------------------------------
    # Public: HTML report
    # ------------------------------------------------------------------

    def generate_html_report(self, audit_data: dict) -> str:
        """Generate a complete, self-contained HTML report from audit data.

        Args:
            audit_data: Dictionary containing all Local SEO audit results.

        Returns:
            Complete HTML string ready to be saved or served.
        """
        logger.info("Generating HTML report for: %s", audit_data.get("business_name", "unknown"))
        scores = self._safe_scores(audit_data)

        html_parts: List[str] = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f"<title>Local SEO Audit &mdash; {self._esc(audit_data.get('business_name', 'Report'))}</title>",
            self._build_css(),
            "</head>",
            "<body>",
            self._build_header(audit_data, scores),
            '<div class="container">',
            self._build_score_overview(scores),
            self._build_top_issues(audit_data),
            self._build_onpage(audit_data),
            self._build_gbp(audit_data),
            self._build_citations(audit_data),
            self._build_reviews(audit_data),
            self._build_competitors(audit_data),
            self._build_recommendations(audit_data),
            self._build_footer(audit_data),
            "</div>",
            "</body>",
            "</html>",
        ]

        report = "\n".join(html_parts)
        logger.info("HTML report generated: %d characters", len(report))
        return report

    # ------------------------------------------------------------------
    # Public: JSON report
    # ------------------------------------------------------------------

    def generate_json_report(self, audit_data: dict) -> dict:
        """Generate a structured JSON report from audit data.

        Args:
            audit_data: Dictionary containing all Local SEO audit results.

        Returns:
            Structured dictionary suitable for JSON serialization.
        """
        logger.info("Generating JSON report for: %s", audit_data.get("business_name", "unknown"))
        scores = self._safe_scores(audit_data)

        report: Dict[str, Any] = {
            "metadata": {
                "business_name": audit_data.get("business_name", ""),
                "domain": audit_data.get("domain", ""),
                "location": audit_data.get("location", ""),
                "audit_date": audit_data.get("audit_date", ""),
                "generated_at": datetime.now().isoformat(),
                "report_version": "1.0.0",
            },
            "scores": scores,
            "issues": [
                {
                    "severity": issue.get("severity", "info"),
                    "message": issue.get("message", ""),
                    "category": issue.get("category", ""),
                }
                for issue in audit_data.get("top_issues", [])
            ],
            "onpage_checks": [
                {
                    "name": c.get("name", ""),
                    "status": c.get("status", "warning"),
                    "details": c.get("details", ""),
                    "category": c.get("category", ""),
                    "weight": c.get("weight", 1),
                }
                for c in audit_data.get("onpage", {}).get("checks", [])
            ],
            "gbp_analysis": {
                "listing_found": audit_data.get("gbp", {}).get("listing_found", False),
                "gmb_score": audit_data.get("gbp", {}).get("gmb_score", 0),
                "checklist": [
                    {
                        "id": item.get("id", ""),
                        "label": item.get("label", ""),
                        "status": item.get("status", "fail"),
                        "priority": item.get("priority", ""),
                        "action": item.get("action", ""),
                    }
                    for item in audit_data.get("gbp", {}).get("checklist", [])
                ],
                "issues": audit_data.get("gbp", {}).get("issues", []),
                "recommendations": audit_data.get("gbp", {}).get("recommendations", []),
            },
            "citations": {
                "summary": audit_data.get("citations", {}).get("summary", {}),
                "results": [
                    {
                        "directory_name": r.get("directory_name", ""),
                        "found": r.get("found", False),
                        "nap_consistent": r.get("nap_consistent"),
                        "status": r.get("status", "unknown"),
                        "authority_score": r.get("authority_score", 0),
                    }
                    for r in audit_data.get("citations", {}).get("results", [])
                ],
            },
            "reviews": {
                "total_reviews": audit_data.get("reviews", {}).get("total_reviews", 0),
                "avg_rating": audit_data.get("reviews", {}).get("avg_rating", 0),
                "score": audit_data.get("reviews", {}).get("score", 0),
                "competitor_comparison": audit_data.get("reviews", {}).get("competitor_comparison", {}),
                "checks": audit_data.get("reviews", {}).get("checks", []),
            },
            "competitors": {
                "map_pack_results": [
                    {
                        "position": mp.get("position", 0),
                        "name": mp.get("name", ""),
                        "rating": mp.get("rating", 0),
                        "review_count": mp.get("review_count", 0),
                    }
                    for mp in audit_data.get("competitors", {}).get("map_pack_results", [])
                ],
                "our_position": audit_data.get("competitors", {}).get("our_position"),
                "gap_analysis": audit_data.get("competitors", {}).get("gap_analysis", {}),
            },
            "recommendations": [
                {
                    "title": rec.get("title", ""),
                    "description": rec.get("description", ""),
                    "category": rec.get("category", ""),
                    "priority": rec.get("priority", "P3"),
                    "estimated_impact": rec.get("estimated_impact", "medium"),
                    "effort": rec.get("effort", "medium"),
                    "estimated_time": rec.get("estimated_time", ""),
                    "group": rec.get("group", "Long Term"),
                }
                for rec in audit_data.get("recommendations", [])
            ],
        }

        logger.info("JSON report generated with %d sections", len(report))
        return report

    # ------------------------------------------------------------------
    # Public: Save report
    # ------------------------------------------------------------------

    def save_report(
        self,
        report: Union[str, dict],
        format: str = "html",
        filename: Optional[str] = None,
    ) -> str:
        """Save a report to disk.

        Args:
            report: HTML string or JSON-serializable dict.
            format: \"html\" or \"json\".
            filename: Optional filename. Auto-generated with timestamp if None.

        Returns:
            Absolute path to the saved report file.
        """
        fmt = format.lower()
        if fmt not in ("html", "json"):
            raise ValueError(f"Unsupported format: {format!r}. Use 'html' or 'json'.")

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"local_seo_report_{ts}.{fmt}"

        # Ensure correct extension
        if not filename.endswith(f".{fmt}"):
            filename = f"{filename}.{fmt}"

        filepath = os.path.join(self.output_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        if fmt == "html":
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(report if isinstance(report, str) else json.dumps(report, indent=2))
        else:
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(report if isinstance(report, dict) else {"raw": report}, fh, indent=2, default=str)

        abs_path = os.path.abspath(filepath)
        logger.info("Report saved to: %s", abs_path)
        return abs_path
