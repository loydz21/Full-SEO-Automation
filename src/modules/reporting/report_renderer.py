"""
report_renderer.py - SEO Report Rendering Engine

Renders structured SEO report data into multiple output formats:
HTML (themed), PDF, JSON, CSV bundle, and email summaries.

Part of the Full SEO Automation project.
"""

import json
import csv
import os
import zipfile
import logging
import io
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ReportRenderer:
    """Renders SEO report data dicts into various output formats."""

    THEMES = {
        "professional": {
            "bg": "#f8fafc",
            "text": "#1e293b",
            "primary": "#2563eb",
            "secondary": "#3b82f6",
            "accent": "#dbeafe",
            "card_bg": "#ffffff",
            "border": "#e2e8f0",
            "muted": "#64748b",
            "success": "#16a34a",
            "warning": "#eab308",
            "danger": "#dc2626",
            "header_bg": "#1e40af",
            "header_text": "#ffffff",
        },
        "modern": {
            "bg": "#0f172a",
            "text": "#e2e8f0",
            "primary": "#1e293b",
            "secondary": "#334155",
            "accent": "#1e3a5f",
            "card_bg": "#1e293b",
            "border": "#334155",
            "muted": "#94a3b8",
            "success": "#22c55e",
            "warning": "#facc15",
            "danger": "#ef4444",
            "header_bg": "#020617",
            "header_text": "#f1f5f9",
        },
        "minimal": {
            "bg": "#ffffff",
            "text": "#334155",
            "primary": "#64748b",
            "secondary": "#94a3b8",
            "accent": "#f1f5f9",
            "card_bg": "#ffffff",
            "border": "#e2e8f0",
            "muted": "#94a3b8",
            "success": "#16a34a",
            "warning": "#ca8a04",
            "danger": "#dc2626",
            "header_bg": "#f8fafc",
            "header_text": "#1e293b",
        },
    }

    MODULE_SECTIONS = [
        ("technical_audit", "Technical Audit"),
        ("onpage_seo", "On-Page SEO"),
        ("local_seo", "Local SEO"),
        ("keyword_rankings", "Keyword Rankings"),
        ("content_performance", "Content Performance"),
        ("link_building", "Link Building"),
        ("serp_features", "SERP Features"),
    ]

    SCORE_KEYS = [
        ("technical_score", "Technical"),
        ("onpage_score", "On-Page"),
        ("local_score", "Local"),
        ("content_score", "Content"),
        ("backlink_score", "Backlinks"),
        ("visibility_score", "Visibility"),
    ]

    def __init__(self, branding: dict = None):
        """Initialize with optional branding configuration."""
        self._branding = {
            "logo_path": None,
            "company_name": "SEO Automation",
            "primary_color": "#2563eb",
            "secondary_color": "#3b82f6",
        }
        if branding:
            self._branding.update(branding)
        logger.info("ReportRenderer initialized with branding: %s", self._branding.get("company_name"))

    # ------------------------------------------------------------------
    # Public rendering methods
    # ------------------------------------------------------------------

    def render_html(self, report_data: dict, template: str = "professional") -> str:
        """Generate a self-contained HTML report with embedded CSS."""
        logger.info("Rendering HTML report with template: %s", template)
        theme = self._get_theme_colors(template)

        domain = report_data.get("domain", "Unknown Domain")
        date_range = report_data.get("date_range", "")
        generated_at = str(report_data.get("generated_at", datetime.utcnow().isoformat()))
        report_id = report_data.get("report_id", "N/A")
        exec_summary = report_data.get("executive_summary", {})
        scores = report_data.get("scores", {})
        recommendations = report_data.get("recommendations", [])
        overall_score = scores.get("overall_score", exec_summary.get("overall_health_score", 0))
        grade = exec_summary.get("grade", self._score_to_grade(overall_score))
        company_name = self._branding.get("company_name", "SEO Automation")

        parts = []
        parts.append(self._build_html_head(theme, domain))
        parts.append(self._build_header_html(theme, domain, date_range, company_name))
        parts.append(self._build_executive_summary_html(theme, exec_summary, overall_score, grade))
        parts.append(self._build_score_grid_html(theme, scores))

        for section_key, section_title in self.MODULE_SECTIONS:
            section_data = report_data.get(section_key, {})
            if section_data:
                parts.append(self._build_section_html(theme, section_title, section_data))

        if recommendations:
            parts.append(self._build_recommendations_html(theme, recommendations))

        parts.append(self._build_footer_html(theme, generated_at, report_id, company_name))
        parts.append("</div></body></html>")

        html = "\n".join(parts)
        logger.info("HTML report rendered successfully (%d chars)", len(html))
        return html

    def render_pdf(self, report_data: dict) -> bytes:
        """Generate PDF from HTML. Falls back to HTML bytes if weasyprint unavailable."""
        logger.info("Rendering PDF report")
        html_content = self.render_html(report_data, template="professional")
        try:
            from weasyprint import HTML as WeasyprintHTML  # type: ignore
            pdf_bytes = WeasyprintHTML(string=html_content).write_pdf()
            logger.info("PDF generated via weasyprint (%d bytes)", len(pdf_bytes))
            return pdf_bytes
        except ImportError:
            logger.warning("weasyprint not available; returning HTML bytes as PDF fallback")
            return html_content.encode("utf-8")
        except Exception as exc:
            logger.error("PDF generation failed: %s", exc)
            return html_content.encode("utf-8")

    def render_json(self, report_data: dict) -> str:
        """Export report data as pretty-printed JSON."""
        logger.info("Rendering JSON report")
        output = json.dumps(report_data, indent=2, default=str, ensure_ascii=False)
        logger.info("JSON report rendered (%d chars)", len(output))
        return output

    def render_csv_bundle(self, report_data: dict, output_dir: str) -> str:
        """Export report sections as CSV files bundled in a ZIP archive."""
        logger.info("Rendering CSV bundle to %s", output_dir)
        os.makedirs(output_dir, exist_ok=True)

        csv_files = []
        section_map = {
            "executive_summary": report_data.get("executive_summary", {}),
            "technical_audit": report_data.get("technical_audit", {}),
            "onpage_seo": report_data.get("onpage_seo", {}),
            "local_seo": report_data.get("local_seo", {}),
            "keyword_rankings": report_data.get("keyword_rankings", {}),
            "content_performance": report_data.get("content_performance", {}),
            "link_building": report_data.get("link_building", {}),
            "recommendations": report_data.get("recommendations", []),
        }

        for name, data in section_map.items():
            csv_path = os.path.join(output_dir, name + ".csv")
            try:
                self._write_section_csv(csv_path, name, data)
                csv_files.append(csv_path)
                logger.debug("Wrote CSV: %s", csv_path)
            except Exception as exc:
                logger.error("Failed to write CSV %s: %s", name, exc)

        domain = report_data.get("domain", "report")
        safe_domain = domain.replace(".", "_").replace("/", "_")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        zip_name = "seo_report_" + safe_domain + "_" + ts + ".zip"
        zip_path = os.path.join(output_dir, zip_name)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in csv_files:
                zf.write(fpath, os.path.basename(fpath))

        # Clean up individual CSV files
        for fpath in csv_files:
            try:
                os.remove(fpath)
            except OSError:
                pass

        logger.info("CSV bundle created: %s", zip_path)
        return zip_path

    def render_email_summary(self, report_data: dict) -> dict:
        """Generate a simplified email-friendly HTML summary."""
        logger.info("Rendering email summary")
        exec_summary = report_data.get("executive_summary", {})
        scores = report_data.get("scores", {})
        domain = report_data.get("domain", "Unknown")
        overall_score = scores.get("overall_score", exec_summary.get("overall_health_score", 0))
        grade = exec_summary.get("grade", self._score_to_grade(overall_score))
        score_color = self._score_to_color(overall_score)
        top_wins = exec_summary.get("top_wins", [])
        top_issues = exec_summary.get("top_issues", [])
        priority_actions = exec_summary.get("priority_actions", [])
        recommendations = report_data.get("recommendations", [])
        date_range = report_data.get("date_range", "")

        subject = "SEO Report: " + str(domain) + " - Score: " + str(overall_score) + "/100 (" + str(grade) + ")"

        body_parts = []
        body_parts.append('<!DOCTYPE html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;max-width:600px;margin:0 auto;padding:20px;">')

        # Header
        body_parts.append('<div style="text-align:center;padding:20px 0;border-bottom:2px solid #e2e8f0;">')
        body_parts.append('<h1 style="margin:0;font-size:22px;color:#1e293b;">SEO Performance Report</h1>')
        body_parts.append('<p style="margin:5px 0 0;color:#64748b;font-size:14px;">' + str(domain))
        if date_range:
            body_parts.append(' | ' + str(date_range))
        body_parts.append('</p></div>')

        # Score badge
        body_parts.append('<div style="text-align:center;padding:25px 0;">')
        body_parts.append('<div style="display:inline-block;width:80px;height:80px;border-radius:50%;')
        body_parts.append('background-color:' + score_color + ';color:#ffffff;font-size:28px;font-weight:bold;')
        body_parts.append('line-height:80px;text-align:center;">' + str(overall_score) + '</div>')
        body_parts.append('<p style="margin:8px 0 0;font-size:18px;font-weight:bold;color:' + score_color + ';">Grade: ' + str(grade) + '</p>')
        body_parts.append('</div>')

        # Module scores
        body_parts.append('<table style="width:100%;border-collapse:collapse;margin:15px 0;">')
        body_parts.append('<tr style="background-color:#f1f5f9;"><th style="padding:8px;text-align:left;font-size:13px;">Module</th>')
        body_parts.append('<th style="padding:8px;text-align:center;font-size:13px;">Score</th>')
        body_parts.append('<th style="padding:8px;text-align:center;font-size:13px;">Grade</th></tr>')
        for key, label in self.SCORE_KEYS:
            sc = scores.get(key, 0)
            sc_color = self._score_to_color(sc)
            sc_grade = self._score_to_grade(sc)
            body_parts.append('<tr style="border-bottom:1px solid #e2e8f0;">')
            body_parts.append('<td style="padding:8px;font-size:13px;">' + label + '</td>')
            body_parts.append('<td style="padding:8px;text-align:center;font-size:13px;color:' + sc_color + ';font-weight:bold;">' + str(sc) + '</td>')
            body_parts.append('<td style="padding:8px;text-align:center;font-size:13px;font-weight:bold;">' + sc_grade + '</td>')
            body_parts.append('</tr>')
        body_parts.append('</table>')

        # Top wins
        if top_wins:
            body_parts.append('<div style="margin:20px 0;">')
            body_parts.append('<h3 style="color:#16a34a;font-size:15px;margin-bottom:8px;">Top Wins</h3>')
            for win in top_wins[:5]:
                body_parts.append('<p style="margin:4px 0;font-size:13px;padding-left:15px;">&#10003; ' + str(win) + '</p>')
            body_parts.append('</div>')

        # Top issues
        if top_issues:
            body_parts.append('<div style="margin:20px 0;">')
            body_parts.append('<h3 style="color:#dc2626;font-size:15px;margin-bottom:8px;">Top Issues</h3>')
            for issue in top_issues[:5]:
                body_parts.append('<p style="margin:4px 0;font-size:13px;padding-left:15px;">&#10007; ' + str(issue) + '</p>')
            body_parts.append('</div>')

        # Priority actions
        actions_list = priority_actions if priority_actions else []
        if not actions_list and recommendations:
            actions_list = [r.get("action", "") for r in recommendations[:5] if r.get("action")]
        if actions_list:
            body_parts.append('<div style="margin:20px 0;padding:15px;background-color:#fffbeb;border:1px solid #fde68a;border-radius:6px;">')
            body_parts.append('<h3 style="color:#92400e;font-size:15px;margin:0 0 10px;">Priority Actions</h3>')
            for idx, action in enumerate(actions_list[:5], 1):
                body_parts.append('<p style="margin:4px 0;font-size:13px;">' + str(idx) + '. ' + str(action) + '</p>')
            body_parts.append('</div>')

        # Footer
        generated_at = str(report_data.get("generated_at", datetime.utcnow().isoformat()))
        body_parts.append('<div style="margin-top:25px;padding-top:15px;border-top:1px solid #e2e8f0;text-align:center;color:#94a3b8;font-size:11px;">')
        body_parts.append('<p>Generated by ' + str(self._branding.get("company_name", "SEO Automation")) + ' on ' + generated_at + '</p>')
        body_parts.append('</div>')
        body_parts.append('</body></html>')

        html_body = "\n".join(body_parts)
        logger.info("Email summary rendered (%d chars)", len(html_body))
        return {"subject": subject, "html_body": html_body}

    def customize_branding(
        self,
        logo_path: str = None,
        company_name: str = None,
        primary_color: str = None,
        secondary_color: str = None,
    ) -> dict:
        """Set white-label branding configuration."""
        if logo_path is not None:
            self._branding["logo_path"] = logo_path
        if company_name is not None:
            self._branding["company_name"] = company_name
        if primary_color is not None:
            self._branding["primary_color"] = primary_color
        if secondary_color is not None:
            self._branding["secondary_color"] = secondary_color
        logger.info("Branding updated: %s", self._branding)
        return dict(self._branding)

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    def _get_theme_colors(self, template: str) -> dict:
        """Return color dict for the requested theme."""
        if template in self.THEMES:
            return dict(self.THEMES[template])
        logger.warning("Unknown template '%s', falling back to 'professional'", template)
        return dict(self.THEMES["professional"])

    def _score_to_grade(self, score: float) -> str:
        """Convert a 0-100 numeric score to a letter grade A-F."""
        try:
            s = float(score)
        except (TypeError, ValueError):
            return "F"
        if s >= 90:
            return "A"
        if s >= 80:
            return "B"
        if s >= 70:
            return "C"
        if s >= 60:
            return "D"
        return "F"

    def _score_to_color(self, score: float) -> str:
        """Return hex color based on score bracket."""
        try:
            s = float(score)
        except (TypeError, ValueError):
            return "#dc2626"
        if s >= 80:
            return "#16a34a"  # green
        if s >= 60:
            return "#eab308"  # yellow
        if s >= 40:
            return "#f97316"  # orange
        return "#dc2626"  # red

    def _build_score_gauge_svg(self, score: int, size: int = 120) -> str:
        """Build an SVG circular gauge for the given score."""
        try:
            s = int(score)
        except (TypeError, ValueError):
            s = 0
        s = max(0, min(100, s))
        color = self._score_to_color(s)
        grade = self._score_to_grade(s)

        radius = (size // 2) - 10
        circumference = 2 * 3.14159 * radius
        offset = circumference - (s / 100.0) * circumference
        cx = size // 2
        cy = size // 2
        stroke_w = 8

        svg_parts = []
        svg_parts.append('<svg width="' + str(size) + '" height="' + str(size) + '" viewBox="0 0 ' + str(size) + ' ' + str(size) + '">')
        # Background circle
        svg_parts.append('<circle cx="' + str(cx) + '" cy="' + str(cy) + '" r="' + str(radius) + '" ')
        svg_parts.append('fill="none" stroke="#e2e8f0" stroke-width="' + str(stroke_w) + '" />')
        # Score arc
        svg_parts.append('<circle cx="' + str(cx) + '" cy="' + str(cy) + '" r="' + str(radius) + '" ')
        svg_parts.append('fill="none" stroke="' + color + '" stroke-width="' + str(stroke_w) + '" ')
        svg_parts.append('stroke-linecap="round" ')
        svg_parts.append('stroke-dasharray="' + str(round(circumference, 2)) + '" ')
        svg_parts.append('stroke-dashoffset="' + str(round(offset, 2)) + '" ')
        svg_parts.append('transform="rotate(-90 ' + str(cx) + ' ' + str(cy) + ')" ')
        svg_parts.append('style="transition: stroke-dashoffset 1.5s ease-in-out;" />')
        # Score text
        svg_parts.append('<text x="' + str(cx) + '" y="' + str(cy - 5) + '" text-anchor="middle" ')
        svg_parts.append('font-size="' + str(size // 4) + '" font-weight="bold" fill="' + color + '">' + str(s) + '</text>')
        # Grade text
        svg_parts.append('<text x="' + str(cx) + '" y="' + str(cy + 18) + '" text-anchor="middle" ')
        svg_parts.append('font-size="' + str(size // 7) + '" fill="#64748b">Grade ' + grade + '</text>')
        svg_parts.append('</svg>')

        return "".join(svg_parts)

    def _flatten_dict(self, d: dict, prefix: str = "") -> dict:
        """Flatten a nested dictionary for CSV writing."""
        items = {}
        if not isinstance(d, dict):
            return {prefix: str(d)} if prefix else {}
        for k, v in d.items():
            new_key = prefix + "." + str(k) if prefix else str(k)
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key))
            elif isinstance(v, (list, tuple)):
                if v and isinstance(v[0], dict):
                    for idx, item in enumerate(v):
                        list_key = new_key + "[" + str(idx) + "]"
                        items.update(self._flatten_dict(item, list_key))
                else:
                    items[new_key] = "; ".join(str(item) for item in v)
            else:
                items[new_key] = str(v) if v is not None else ""
        return items

    def _safe_get(self, data: dict, *keys, default=None) -> Any:
        """Safely access nested dictionary keys."""
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default
            if current is None:
                return default
        return current

    # ------------------------------------------------------------------
    # HTML building helpers
    # ------------------------------------------------------------------

    def _build_html_head(self, theme: dict, domain: str) -> str:
        """Build the DOCTYPE, head, and opening body tags with full CSS."""
        bg = theme["bg"]
        text_color = theme["text"]
        primary = theme["primary"]
        card_bg = theme["card_bg"]
        border = theme["border"]
        muted = theme["muted"]

        css = []
        css.append("* { margin:0; padding:0; box-sizing:border-box; }")
        css.append("body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; ")
        css.append("background-color: " + bg + "; color: " + text_color + "; line-height: 1.6; }")
        css.append(".report-container { max-width: 1200px; margin: 0 auto; padding: 30px; }")
        css.append(".header { padding: 30px; border-radius: 12px; margin-bottom: 30px; }")
        css.append(".section { background: " + card_bg + "; border: 1px solid " + border + "; ")
        css.append("border-radius: 10px; padding: 25px; margin-bottom: 25px; ")
        css.append("box-shadow: 0 1px 3px rgba(0,0,0,0.05); }")
        css.append(".section-title { font-size: 20px; font-weight: 700; margin-bottom: 18px; ")
        css.append("padding-bottom: 12px; border-bottom: 2px solid " + primary + "; }")
        css.append(".score-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 25px; }")
        css.append(".score-card { background: " + card_bg + "; border: 1px solid " + border + "; ")
        css.append("border-radius: 10px; padding: 20px; text-align: center; ")
        css.append("box-shadow: 0 1px 3px rgba(0,0,0,0.05); transition: transform 0.2s; }")
        css.append(".score-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }")
        css.append(".score-value { font-size: 32px; font-weight: 800; }")
        css.append(".score-label { font-size: 13px; color: " + muted + "; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }")
        css.append(".score-grade { font-size: 14px; font-weight: 600; margin-top: 6px; }")
        css.append("table { width: 100%; border-collapse: collapse; margin: 12px 0; }")
        css.append("th { background: " + bg + "; padding: 10px 14px; text-align: left; font-size: 12px; ")
        css.append("text-transform: uppercase; letter-spacing: 0.5px; color: " + muted + "; font-weight: 600; }")
        css.append("td { padding: 10px 14px; border-bottom: 1px solid " + border + "; font-size: 14px; }")
        css.append("tr:hover td { background-color: " + bg + "; }")
        css.append(".badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }")
        css.append(".badge-high { background: #fef2f2; color: #dc2626; }")
        css.append(".badge-medium { background: #fffbeb; color: #d97706; }")
        css.append(".badge-low { background: #f0fdf4; color: #16a34a; }")
        css.append(".exec-summary { display: flex; gap: 30px; align-items: flex-start; flex-wrap: wrap; }")
        css.append(".exec-gauge { flex-shrink: 0; text-align: center; }")
        css.append(".exec-details { flex: 1; min-width: 280px; }")
        css.append(".list-item { padding: 6px 0; font-size: 14px; }")
        css.append(".list-item-win { color: #16a34a; }")
        css.append(".list-item-issue { color: #dc2626; }")
        css.append(".list-item-action { color: " + primary + "; }")
        css.append(".metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 15px 0; }")
        css.append(".metric-item { padding: 12px 16px; background: " + bg + "; border-radius: 8px; }")
        css.append(".metric-label { font-size: 12px; color: " + muted + "; text-transform: uppercase; }")
        css.append(".metric-value { font-size: 20px; font-weight: 700; margin-top: 2px; }")
        css.append(".sub-title { font-size: 15px; font-weight: 600; margin: 18px 0 10px; color: " + muted + "; }")
        css.append(".issue-tag { display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; ")
        css.append("background: #fef2f2; color: #dc2626; border-radius: 4px; font-size: 12px; }")
        css.append(".improvement-tag { display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; ")
        css.append("background: #f0fdf4; color: #16a34a; border-radius: 4px; font-size: 12px; }")
        css.append(".footer { text-align: center; padding: 20px; color: " + muted + "; font-size: 12px; margin-top: 10px; }")
        # Print CSS
        css.append("@media print { body { background: #fff; } ")
        css.append(".section { break-inside: avoid; box-shadow: none; border: 1px solid #ddd; } ")
        css.append(".score-card { break-inside: avoid; box-shadow: none; } ")
        css.append(".header { -webkit-print-color-adjust: exact; print-color-adjust: exact; } ")
        css.append(".report-container { max-width: 100%; padding: 10px; } }")

        css_block = "\n".join(css)

        head_parts = []
        head_parts.append('<!DOCTYPE html>')
        head_parts.append('<html lang="en">')
        head_parts.append('<head>')
        head_parts.append('<meta charset="UTF-8">')
        head_parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        head_parts.append('<title>SEO Report - ' + str(domain) + '</title>')
        head_parts.append('<style>')
        head_parts.append(css_block)
        head_parts.append('</style>')
        head_parts.append('</head>')
        head_parts.append('<body>')
        head_parts.append('<div class="report-container">')

        return "\n".join(head_parts)

    def _build_header_html(self, theme: dict, domain: str, date_range: str, company_name: str) -> str:
        """Build the report header with branding."""
        header_bg = theme["header_bg"]
        header_text = theme["header_text"]
        logo_path = self._branding.get("logo_path")

        parts = []
        parts.append('<div class="header" style="background-color: ' + header_bg + '; color: ' + header_text + ';">')
        parts.append('<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">')
        parts.append('<div>')
        if logo_path:
            parts.append('<img src="' + str(logo_path) + '" alt="Logo" style="max-height:40px; margin-bottom:8px;">')
        parts.append('<h1 style="font-size:26px; margin:0; color:' + header_text + ';">' + str(company_name) + '</h1>')
        parts.append('<p style="font-size:13px; opacity:0.85; margin-top:4px;">SEO Performance Report</p>')
        parts.append('</div>')
        parts.append('<div style="text-align:right;">')
        parts.append('<h2 style="font-size:22px; margin:0; color:' + header_text + ';">' + str(domain) + '</h2>')
        if date_range:
            parts.append('<p style="font-size:13px; opacity:0.85; margin-top:4px;">' + str(date_range) + '</p>')
        parts.append('</div>')
        parts.append('</div>')
        parts.append('</div>')

        return "\n".join(parts)

    def _build_executive_summary_html(self, theme: dict, exec_summary: dict, overall_score: int, grade: str) -> str:
        """Build the executive summary section with gauge and lists."""
        primary = theme["primary"]
        top_wins = exec_summary.get("top_wins", [])
        top_issues = exec_summary.get("top_issues", [])
        priority_actions = exec_summary.get("priority_actions", [])

        gauge_svg = self._build_score_gauge_svg(overall_score, size=150)

        parts = []
        parts.append('<div class="section">')
        parts.append('<h2 class="section-title" style="color: ' + primary + ';">Executive Summary</h2>')
        parts.append('<div class="exec-summary">')

        # Gauge
        parts.append('<div class="exec-gauge">')
        parts.append(gauge_svg)
        parts.append('<p style="margin-top:10px; font-size:14px; font-weight:600;">Overall Health Score</p>')
        parts.append('</div>')

        # Details
        parts.append('<div class="exec-details">')

        # Top wins
        if top_wins:
            parts.append('<div style="margin-bottom:16px;">')
            parts.append('<h3 style="font-size:15px; color:#16a34a; margin-bottom:8px;">Top Wins</h3>')
            for win in top_wins[:5]:
                parts.append('<div class="list-item list-item-win">&#10003; ' + str(win) + '</div>')
            parts.append('</div>')

        # Top issues
        if top_issues:
            parts.append('<div style="margin-bottom:16px;">')
            parts.append('<h3 style="font-size:15px; color:#dc2626; margin-bottom:8px;">Top Issues</h3>')
            for issue in top_issues[:5]:
                parts.append('<div class="list-item list-item-issue">&#10007; ' + str(issue) + '</div>')
            parts.append('</div>')

        # Priority actions
        if priority_actions:
            parts.append('<div style="margin-bottom:16px;">')
            parts.append('<h3 style="font-size:15px; color:' + primary + '; margin-bottom:8px;">Priority Actions</h3>')
            for idx, action in enumerate(priority_actions[:5], 1):
                parts.append('<div class="list-item list-item-action">' + str(idx) + '. ' + str(action) + '</div>')
            parts.append('</div>')

        parts.append('</div>')  # exec-details
        parts.append('</div>')  # exec-summary
        parts.append('</div>')  # section

        return "\n".join(parts)

    def _build_score_grid_html(self, theme: dict, scores: dict) -> str:
        """Build the module score cards grid."""
        overall = scores.get("overall_score", 0)
        overall_color = self._score_to_color(overall)
        overall_grade = self._score_to_grade(overall)

        parts = []
        parts.append('<div class="score-grid">')

        # Overall card (slightly larger emphasis)
        parts.append('<div class="score-card" style="border-top:4px solid ' + overall_color + ';">')
        parts.append('<div class="score-value" style="color:' + overall_color + ';">' + str(overall) + '</div>')
        parts.append('<div class="score-label">Overall</div>')
        parts.append('<div class="score-grade" style="color:' + overall_color + ';">Grade ' + overall_grade + '</div>')
        parts.append('</div>')

        # Module score cards
        for key, label in self.SCORE_KEYS:
            sc = scores.get(key, 0)
            sc_color = self._score_to_color(sc)
            sc_grade = self._score_to_grade(sc)
            parts.append(self._build_module_card_html(label, sc, sc_color, sc_grade))

        parts.append('</div>')  # score-grid
        return "\n".join(parts)

    def _build_module_card_html(self, label: str, score: int, color: str, grade: str) -> str:
        """Build a single module score card."""
        parts = []
        parts.append('<div class="score-card" style="border-top:4px solid ' + color + ';">')
        parts.append('<div class="score-value" style="color:' + color + ';">' + str(score) + '</div>')
        parts.append('<div class="score-label">' + str(label) + '</div>')
        parts.append('<div class="score-grade" style="color:' + color + ';">Grade ' + grade + '</div>')
        parts.append('</div>')
        return "\n".join(parts)

    def _build_section_html(self, theme: dict, title: str, section_data: dict) -> str:
        """Build a detailed module section with metrics, issues, and improvements."""
        primary = theme["primary"]
        muted = theme["muted"]

        section_score = section_data.get("score", 0)
        score_color = self._score_to_color(section_score)
        score_grade = self._score_to_grade(section_score)
        key_metrics = section_data.get("key_metrics", {})
        issues = section_data.get("issues", [])
        improvements = section_data.get("improvements", [])

        parts = []
        parts.append('<div class="section">')
        # Title with score badge
        parts.append('<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; padding-bottom:12px; border-bottom:2px solid ' + primary + ';">')
        parts.append('<h2 style="font-size:20px; font-weight:700; margin:0;">' + str(title) + '</h2>')
        parts.append('<div style="display:flex; align-items:center; gap:10px;">')
        parts.append('<span style="font-size:28px; font-weight:800; color:' + score_color + ';">' + str(section_score) + '</span>')
        parts.append('<span style="font-size:14px; font-weight:600; color:' + score_color + ';">(' + score_grade + ')</span>')
        parts.append('</div>')
        parts.append('</div>')

        # Key metrics grid
        if key_metrics and isinstance(key_metrics, dict):
            parts.append('<div class="metric-grid">')
            for mk, mv in key_metrics.items():
                display_label = str(mk).replace("_", " ").title()
                display_value = str(mv)
                parts.append('<div class="metric-item">')
                parts.append('<div class="metric-label">' + display_label + '</div>')
                parts.append('<div class="metric-value">' + display_value + '</div>')
                parts.append('</div>')
            parts.append('</div>')

        # Issues
        if issues:
            parts.append('<p class="sub-title" style="color:#dc2626;">Issues (' + str(len(issues)) + ')</p>')
            if isinstance(issues[0], dict):
                # Table format for structured issues
                parts.append('<table>')
                headers = list(issues[0].keys())
                parts.append('<tr>')
                for h in headers:
                    parts.append('<th>' + str(h).replace("_", " ").title() + '</th>')
                parts.append('</tr>')
                for iss in issues:
                    parts.append('<tr>')
                    for h in headers:
                        val = iss.get(h, "")
                        parts.append('<td>' + str(val) + '</td>')
                    parts.append('</tr>')
                parts.append('</table>')
            else:
                # Simple list format
                for iss in issues:
                    parts.append('<span class="issue-tag">' + str(iss) + '</span>')
                parts.append('<br style="clear:both;">')

        # Improvements
        if improvements:
            parts.append('<p class="sub-title" style="color:#16a34a;">Improvements (' + str(len(improvements)) + ')</p>')
            if isinstance(improvements[0], dict):
                parts.append('<table>')
                headers = list(improvements[0].keys())
                parts.append('<tr>')
                for h in headers:
                    parts.append('<th>' + str(h).replace("_", " ").title() + '</th>')
                parts.append('</tr>')
                for imp in improvements:
                    parts.append('<tr>')
                    for h in headers:
                        val = imp.get(h, "")
                        parts.append('<td>' + str(val) + '</td>')
                    parts.append('</tr>')
                parts.append('</table>')
            else:
                for imp in improvements:
                    parts.append('<span class="improvement-tag">' + str(imp) + '</span>')
                parts.append('<br style="clear:both;">')

        parts.append('</div>')  # section
        return "\n".join(parts)

    def _build_recommendations_html(self, theme: dict, recommendations: list) -> str:
        """Build the recommendations/action items table."""
        primary = theme["primary"]

        parts = []
        parts.append('<div class="section">')
        parts.append('<h2 class="section-title" style="color: ' + primary + ';">Recommendations & Action Items</h2>')
        parts.append('<table>')
        parts.append('<tr>')
        parts.append('<th style="width:8%;">#</th>')
        parts.append('<th style="width:10%;">Priority</th>')
        parts.append('<th style="width:35%;">Action</th>')
        parts.append('<th style="width:15%;">Module</th>')
        parts.append('<th style="width:17%;">Est. Impact</th>')
        parts.append('<th style="width:15%;">Effort</th>')
        parts.append('</tr>')

        for idx, rec in enumerate(recommendations, 1):
            priority = str(rec.get("priority", "medium")).lower()
            action = str(rec.get("action", ""))
            module = str(rec.get("module", ""))
            impact = str(rec.get("estimated_impact", ""))
            effort = str(rec.get("effort", ""))

            if priority == "high":
                badge_class = "badge badge-high"
            elif priority == "medium":
                badge_class = "badge badge-medium"
            else:
                badge_class = "badge badge-low"

            parts.append('<tr>')
            parts.append('<td>' + str(idx) + '</td>')
            parts.append('<td><span class="' + badge_class + '">' + priority.upper() + '</span></td>')
            parts.append('<td>' + action + '</td>')
            parts.append('<td>' + module + '</td>')
            parts.append('<td>' + impact + '</td>')
            parts.append('<td>' + effort + '</td>')
            parts.append('</tr>')

        parts.append('</table>')
        parts.append('</div>')

        return "\n".join(parts)

    def _build_footer_html(self, theme: dict, generated_at: str, report_id: str, company_name: str) -> str:
        """Build the report footer."""
        parts = []
        parts.append('<div class="footer">')
        parts.append('<p>Report generated by <strong>' + str(company_name) + '</strong></p>')
        parts.append('<p>Generated at: ' + str(generated_at) + ' | Report ID: ' + str(report_id) + '</p>')
        parts.append('<p style="margin-top:6px; font-size:11px; opacity:0.7;">This report is auto-generated. Data accuracy depends on source availability.</p>')
        parts.append('</div>')
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # CSV helpers
    # ------------------------------------------------------------------

    def _write_section_csv(self, csv_path: str, section_name: str, data: Any) -> None:
        """Write a single section's data to a CSV file."""
        if isinstance(data, list):
            # List of dicts (e.g., recommendations)
            self._write_list_csv(csv_path, data)
        elif isinstance(data, dict):
            self._write_dict_csv(csv_path, section_name, data)
        else:
            # Scalar fallback
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["section", "value"])
                writer.writerow([section_name, str(data)])

    def _write_list_csv(self, csv_path: str, data: list) -> None:
        """Write a list of dicts to CSV."""
        if not data:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["(empty)"])
            return

        # Flatten each row
        flat_rows = []
        all_keys = []
        for item in data:
            if isinstance(item, dict):
                flat = self._flatten_dict(item)
            else:
                flat = {"value": str(item)}
            flat_rows.append(flat)
            for k in flat.keys():
                if k not in all_keys:
                    all_keys.append(k)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for row in flat_rows:
                writer.writerow(row)

    def _write_dict_csv(self, csv_path: str, section_name: str, data: dict) -> None:
        """Write a dict section to CSV, handling nested structures."""
        flat = self._flatten_dict(data)

        if not flat:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["section", "note"])
                writer.writerow([section_name, "No data"])
            return

        # Check if there are list-type sub-sections that should be rows
        # For sections like technical_audit with issues/improvements lists
        list_keys = []
        scalar_data = {}
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                list_keys.append(k)
            elif isinstance(v, list):
                scalar_data[k] = "; ".join(str(i) for i in v)
            elif isinstance(v, dict):
                for sk, sv in self._flatten_dict(v, k).items():
                    scalar_data[sk] = sv
            else:
                scalar_data[k] = str(v) if v is not None else ""

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Write scalar/summary row first
            if scalar_data:
                headers = list(scalar_data.keys())
                writer.writerow(headers)
                writer.writerow([scalar_data.get(h, "") for h in headers])
                writer.writerow([])  # separator

            # Write list sub-sections
            for lk in list_keys:
                items = data[lk]
                if not items:
                    continue
                writer.writerow(["--- " + lk + " ---"])
                flat_items = []
                item_keys = []
                for item in items:
                    flat_item = self._flatten_dict(item) if isinstance(item, dict) else {"value": str(item)}
                    flat_items.append(flat_item)
                    for ik in flat_item.keys():
                        if ik not in item_keys:
                            item_keys.append(ik)
                writer.writerow(item_keys)
                for fi in flat_items:
                    writer.writerow([fi.get(ik, "") for ik in item_keys])
                writer.writerow([])  # separator
