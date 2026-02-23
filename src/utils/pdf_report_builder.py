# -*- coding: utf-8 -*-
"""Universal PDF Report Builder for SEO Automation Suite.

Builder-pattern class that constructs professional, narrative-style
HTML reports with embedded matplotlib charts and converts them to PDF
via xhtml2pdf (pure Python) with WeasyPrint fallback.
"""
from __future__ import annotations

import os
import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_COLORS = {
    'navy': '#0f172a',
    'blue': '#2563eb',
    'blue_light': '#3b82f6',
    'blue_bg': '#eff6ff',
    'green': '#16a34a',
    'green_bg': '#f0fdf4',
    'yellow': '#ca8a04',
    'yellow_bg': '#fefce8',
    'red': '#dc2626',
    'red_bg': '#fef2f2',
    'gray': '#64748b',
    'gray_light': '#f1f5f9',
    'white': '#ffffff',
    'text': '#1e293b',
    'text_light': '#475569',
    'border': '#e2e8f0',
}

_CHART_PALETTE = [
    '#2563eb', '#16a34a', '#ca8a04', '#dc2626', '#7c3aed',
    '#0891b2', '#db2777', '#ea580c', '#4f46e5', '#059669',
]


def _score_color(score):
    """Return color hex based on score threshold."""
    if score >= 80:
        return _COLORS['green']
    elif score >= 60:
        return _COLORS['yellow']
    return _COLORS['red']


def _score_bg(score):
    """Return background color based on score threshold."""
    if score >= 80:
        return _COLORS['green_bg']
    elif score >= 60:
        return _COLORS['yellow_bg']
    return _COLORS['red_bg']


def _severity_color(severity):
    """Return color for severity level."""
    sev = str(severity).lower()
    if sev in ('critical', 'high', 'p1', 'error'):
        return _COLORS['red']
    elif sev in ('medium', 'warning', 'p2'):
        return _COLORS['yellow']
    elif sev in ('low', 'info', 'p3'):
        return _COLORS['blue']
    return _COLORS['gray']


def _escape_html(text):
    """Escape HTML special characters."""
    if text is None:
        return 'N/A'
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def _build_css(footer_text):
    """Build the complete CSS stylesheet."""
    c = _COLORS
    css_parts = []
    css_parts.append('@page {{')
    css_parts.append('  size: A4;')
    css_parts.append('  margin: 1.8cm 1.5cm 2cm 1.5cm;')
    css_parts.append('  @bottom-center {{')
    css_parts.append('    content: "{ft}";'.format(ft=footer_text))
    css_parts.append('    font-size: 9px;')
    css_parts.append('    color: {0};'.format(c['gray']))
    css_parts.append('  }}')
    css_parts.append('  @bottom-right {{')
    css_parts.append('    content: "Page " counter(page) " of " counter(pages);')
    css_parts.append('    font-size: 9px;')
    css_parts.append('    color: {0};'.format(c['gray']))
    css_parts.append('  }}')
    css_parts.append('}}')
    css_parts.append('* {{ margin: 0; padding: 0; box-sizing: border-box; }}')
    css_parts.append('body {{')
    css_parts.append('  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,')
    css_parts.append('               "Helvetica Neue", Arial, sans-serif;')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('  line-height: 1.65;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('  background: {0};'.format(c['white']))
    css_parts.append('}}')
    css_parts.append('.cover-page {{')
    css_parts.append('  page-break-after: always;')
    css_parts.append('  display: flex;')
    css_parts.append('  flex-direction: column;')
    css_parts.append('  justify-content: center;')
    css_parts.append('  min-height: 90vh;')
    css_parts.append('  text-align: center;')
    css_parts.append('  padding: 60px 40px;')
    css_parts.append('}}')
    css_parts.append('.cover-header {{')
    css_parts.append('  background: {0};'.format(c['navy']))
    css_parts.append('  color: {0};'.format(c['white']))
    css_parts.append('  padding: 60px 40px;')
    css_parts.append('  border-radius: 8px;')
    css_parts.append('  margin-bottom: 40px;')
    css_parts.append('}}')
    css_parts.append('.cover-title {{')
    css_parts.append('  font-size: 32pt;')
    css_parts.append('  font-weight: 700;')
    css_parts.append('  margin-bottom: 12px;')
    css_parts.append('  letter-spacing: -0.5px;')
    css_parts.append('}}')
    css_parts.append('.cover-subtitle {{')
    css_parts.append('  font-size: 14pt;')
    css_parts.append('  font-weight: 400;')
    css_parts.append('  opacity: 0.85;')
    css_parts.append('  margin-bottom: 8px;')
    css_parts.append('}}')
    css_parts.append('.cover-domain {{')
    css_parts.append('  font-size: 16pt;')
    css_parts.append('  color: {0};'.format(c['blue_light']))
    css_parts.append('  margin-top: 16px;')
    css_parts.append('}}')
    css_parts.append('.cover-meta {{')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('  margin-top: 30px;')
    css_parts.append('}}')
    css_parts.append('.cover-summary {{')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('  margin-top: 24px;')
    css_parts.append('  max-width: 600px;')
    css_parts.append('  margin-left: auto;')
    css_parts.append('  margin-right: auto;')
    css_parts.append('  line-height: 1.7;')
    css_parts.append('}}')
    css_parts.append('.toc {{')
    css_parts.append('  page-break-after: always;')
    css_parts.append('  padding: 40px 0;')
    css_parts.append('}}')
    css_parts.append('.toc h2 {{')
    css_parts.append('  font-size: 20pt;')
    css_parts.append('  color: {0};'.format(c['navy']))
    css_parts.append('  border-bottom: 3px solid {0};'.format(c['blue']))
    css_parts.append('  padding-bottom: 10px;')
    css_parts.append('  margin-bottom: 24px;')
    css_parts.append('}}')
    css_parts.append('.toc-item {{')
    css_parts.append('  padding: 8px 0;')
    css_parts.append('  border-bottom: 1px dotted {0};'.format(c['border']))
    css_parts.append('  font-size: 11pt;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('}}')
    css_parts.append('.toc-number {{')
    css_parts.append('  display: inline-block;')
    css_parts.append('  width: 30px;')
    css_parts.append('  color: {0};'.format(c['blue']))
    css_parts.append('  font-weight: 600;')
    css_parts.append('}}')
    css_parts.append('h1 {{')
    css_parts.append('  font-size: 22pt;')
    css_parts.append('  color: {0};'.format(c['navy']))
    css_parts.append('  border-bottom: 3px solid {0};'.format(c['blue']))
    css_parts.append('  padding-bottom: 10px;')
    css_parts.append('  margin: 32px 0 16px 0;')
    css_parts.append('  page-break-after: avoid;')
    css_parts.append('}}')
    css_parts.append('h2 {{')
    css_parts.append('  font-size: 16pt;')
    css_parts.append('  color: {0};'.format(c['navy']))
    css_parts.append('  margin: 28px 0 12px 0;')
    css_parts.append('  page-break-after: avoid;')
    css_parts.append('}}')
    css_parts.append('h3 {{')
    css_parts.append('  font-size: 13pt;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('  margin: 20px 0 10px 0;')
    css_parts.append('  page-break-after: avoid;')
    css_parts.append('}}')
    css_parts.append('p {{')
    css_parts.append('  margin: 8px 0 12px 0;')
    css_parts.append('  text-align: justify;')
    css_parts.append('}}')
    css_parts.append('.exec-summary {{')
    css_parts.append('  background: {0};'.format(c['blue_bg']))
    css_parts.append('  border-left: 4px solid {0};'.format(c['blue']))
    css_parts.append('  padding: 20px 24px;')
    css_parts.append('  margin: 20px 0;')
    css_parts.append('  border-radius: 0 6px 6px 0;')
    css_parts.append('}}')
    css_parts.append('.exec-summary p {{')
    css_parts.append('  margin: 6px 0;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('}}')
    css_parts.append('.metrics-grid {{')
    css_parts.append('  display: flex;')
    css_parts.append('  flex-wrap: wrap;')
    css_parts.append('  gap: 12px;')
    css_parts.append('  margin: 16px 0 24px 0;')
    css_parts.append('}}')
    css_parts.append('.metric-card {{')
    css_parts.append('  flex: 1 1 140px;')
    css_parts.append('  background: {0};'.format(c['gray_light']))
    css_parts.append('  border-radius: 8px;')
    css_parts.append('  padding: 16px;')
    css_parts.append('  text-align: center;')
    css_parts.append('  border: 1px solid {0};'.format(c['border']))
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.metric-value {{')
    css_parts.append('  font-size: 22pt;')
    css_parts.append('  font-weight: 700;')
    css_parts.append('  color: {0};'.format(c['blue']))
    css_parts.append('}}')
    css_parts.append('.metric-label {{')
    css_parts.append('  font-size: 9pt;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('  margin-top: 4px;')
    css_parts.append('  text-transform: uppercase;')
    css_parts.append('  letter-spacing: 0.5px;')
    css_parts.append('}}')
    css_parts.append('.score-card {{')
    css_parts.append('  text-align: center;')
    css_parts.append('  padding: 24px;')
    css_parts.append('  margin: 16px 0;')
    css_parts.append('  border-radius: 10px;')
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.score-value {{')
    css_parts.append('  font-size: 48pt;')
    css_parts.append('  font-weight: 800;')
    css_parts.append('  line-height: 1.1;')
    css_parts.append('}}')
    css_parts.append('.score-grade {{')
    css_parts.append('  font-size: 20pt;')
    css_parts.append('  font-weight: 700;')
    css_parts.append('  margin-top: 4px;')
    css_parts.append('}}')
    css_parts.append('.score-label {{')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  text-transform: uppercase;')
    css_parts.append('  letter-spacing: 1px;')
    css_parts.append('  margin-top: 8px;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('}}')
    css_parts.append('.category-scores {{')
    css_parts.append('  margin: 16px 0 24px 0;')
    css_parts.append('}}')
    css_parts.append('.cat-score-row {{')
    css_parts.append('  display: flex;')
    css_parts.append('  align-items: center;')
    css_parts.append('  margin: 8px 0;')
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.cat-score-label {{')
    css_parts.append('  width: 160px;')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('}}')
    css_parts.append('.cat-score-bar-bg {{')
    css_parts.append('  flex: 1;')
    css_parts.append('  height: 22px;')
    css_parts.append('  background: {0};'.format(c['gray_light']))
    css_parts.append('  border-radius: 11px;')
    css_parts.append('  overflow: hidden;')
    css_parts.append('  margin: 0 12px;')
    css_parts.append('}}')
    css_parts.append('.cat-score-bar {{')
    css_parts.append('  height: 100%;')
    css_parts.append('  border-radius: 11px;')
    css_parts.append('}}')
    css_parts.append('.cat-score-val {{')
    css_parts.append('  width: 50px;')
    css_parts.append('  text-align: right;')
    css_parts.append('  font-weight: 700;')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('}}')
    css_parts.append('.findings-list {{')
    css_parts.append('  margin: 16px 0;')
    css_parts.append('}}')
    css_parts.append('.finding-item {{')
    css_parts.append('  border: 1px solid {0};'.format(c['border']))
    css_parts.append('  border-radius: 8px;')
    css_parts.append('  padding: 16px;')
    css_parts.append('  margin: 10px 0;')
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.finding-header {{')
    css_parts.append('  display: flex;')
    css_parts.append('  align-items: center;')
    css_parts.append('  gap: 10px;')
    css_parts.append('  margin-bottom: 8px;')
    css_parts.append('}}')
    css_parts.append('.finding-severity {{')
    css_parts.append('  display: inline-block;')
    css_parts.append('  padding: 2px 10px;')
    css_parts.append('  border-radius: 12px;')
    css_parts.append('  font-size: 9pt;')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  color: {0};'.format(c['white']))
    css_parts.append('  text-transform: uppercase;')
    css_parts.append('}}')
    css_parts.append('.finding-title {{')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('}}')
    css_parts.append('.finding-desc {{')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('}}')
    css_parts.append('.rec-list {{')
    css_parts.append('  margin: 16px 0;')
    css_parts.append('}}')
    css_parts.append('.rec-item {{')
    css_parts.append('  border-left: 4px solid {0};'.format(c['blue']))
    css_parts.append('  padding: 14px 18px;')
    css_parts.append('  margin: 12px 0;')
    css_parts.append('  background: {0};'.format(c['gray_light']))
    css_parts.append('  border-radius: 0 8px 8px 0;')
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.rec-priority {{')
    css_parts.append('  display: inline-block;')
    css_parts.append('  padding: 2px 8px;')
    css_parts.append('  border-radius: 4px;')
    css_parts.append('  font-size: 9pt;')
    css_parts.append('  font-weight: 700;')
    css_parts.append('  color: {0};'.format(c['white']))
    css_parts.append('  margin-bottom: 6px;')
    css_parts.append('}}')
    css_parts.append('.rec-title {{')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  font-size: 11pt;')
    css_parts.append('  margin-bottom: 4px;')
    css_parts.append('}}')
    css_parts.append('.rec-desc {{')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('  margin-bottom: 6px;')
    css_parts.append('}}')
    css_parts.append('.rec-steps {{')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  padding-left: 18px;')
    css_parts.append('}}')
    css_parts.append('.rec-steps li {{')
    css_parts.append('  margin: 3px 0;')
    css_parts.append('  color: {0};'.format(c['text']))
    css_parts.append('}}')
    css_parts.append('table {{')
    css_parts.append('  width: 100%;')
    css_parts.append('  border-collapse: collapse;')
    css_parts.append('  margin: 14px 0 20px 0;')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  page-break-inside: auto;')
    css_parts.append('}}')
    css_parts.append('table caption {{')
    css_parts.append('  font-size: 10pt;')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  color: {0};'.format(c['text_light']))
    css_parts.append('  margin-bottom: 6px;')
    css_parts.append('  text-align: left;')
    css_parts.append('}}')
    css_parts.append('th {{')
    css_parts.append('  background: {0};'.format(c['navy']))
    css_parts.append('  color: {0};'.format(c['white']))
    css_parts.append('  padding: 10px 12px;')
    css_parts.append('  text-align: left;')
    css_parts.append('  font-weight: 600;')
    css_parts.append('  font-size: 9pt;')
    css_parts.append('  text-transform: uppercase;')
    css_parts.append('  letter-spacing: 0.4px;')
    css_parts.append('}}')
    css_parts.append('td {{')
    css_parts.append('  padding: 8px 12px;')
    css_parts.append('  border-bottom: 1px solid {0};'.format(c['border']))
    css_parts.append('}}')
    css_parts.append('tr:nth-child(even) {{')
    css_parts.append('  background: {0};'.format(c['gray_light']))
    css_parts.append('}}')
    css_parts.append('.chart-container {{')
    css_parts.append('  text-align: center;')
    css_parts.append('  margin: 18px 0;')
    css_parts.append('  page-break-inside: avoid;')
    css_parts.append('}}')
    css_parts.append('.chart-container img {{')
    css_parts.append('  max-width: 100%;')
    css_parts.append('  height: auto;')
    css_parts.append('}}')
    css_parts.append('.page-break {{')
    css_parts.append('  page-break-after: always;')
    css_parts.append('}}')
    return '\n'.join(css_parts)


# ---------------------------------------------------------------------------
# PDFReportBuilder
# ---------------------------------------------------------------------------
class PDFReportBuilder:
    """Builder-pattern class for constructing professional PDF reports."""

    def __init__(
        self,
        title,
        subtitle='',
        company_name='',
        logo_path=None,
        theme='professional',
    ):
        self._title = title
        self._subtitle = subtitle
        self._company_name = company_name
        self._logo_path = logo_path
        self._theme = theme
        self._sections = []
        self._toc_entries = []
        self._section_counter = 0
        self._date_str = datetime.datetime.now().strftime('%Y-%m-%d')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _fig_to_base64(fig):
        """Convert matplotlib figure to base64 PNG string."""
        import base64
        from io import BytesIO
        import matplotlib.pyplot as plt

        buf = BytesIO()
        fig.savefig(
            buf, format='png', dpi=150,
            bbox_inches='tight', facecolor='white',
        )
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        plt.close(fig)
        return img_b64

    def _add_toc_entry(self, title):
        """Register a section for table of contents."""
        self._section_counter += 1
        self._toc_entries.append(title)

    def _chart_img_tag(self, b64):
        """Build an img tag from base64 data."""
        return (
            '<div class="chart-container">'
            '<img src="data:image/png;base64,{b64}" alt="chart">'
            '</div>'
        ).format(b64=b64)

    def _get_colors(self, n, colors=None):
        """Return n colors from palette or user-supplied list."""
        if colors and len(colors) >= n:
            return colors[:n]
        result = []
        for i in range(n):
            result.append(_CHART_PALETTE[i % len(_CHART_PALETTE)])
        return result

    # ------------------------------------------------------------------
    # Content methods (builder pattern - each returns self)
    # ------------------------------------------------------------------
    def add_cover_page(self, domain, date, summary_text):
        """Add a styled cover / title page."""
        self._date_str = date or self._date_str
        logo_html = ''
        if self._logo_path and os.path.isfile(self._logo_path):
            logo_html = (
                '<img src="{path}" style="max-height:60px;'
                'margin-bottom:16px;" alt="logo">'
            ).format(path=self._logo_path)
        html = (
            '<div class="cover-page">'
            '{logo}'
            '<div class="cover-header">'
            '<div class="cover-title">{title}</div>'
            '<div class="cover-subtitle">{subtitle}</div>'
            '<div class="cover-domain">{domain}</div>'
            '</div>'
            '<div class="cover-meta">{company} &mdash; {date}</div>'
            '<div class="cover-summary">{summary}</div>'
            '</div>'
        ).format(
            logo=logo_html,
            title=_escape_html(self._title),
            subtitle=_escape_html(self._subtitle),
            domain=_escape_html(domain),
            company=_escape_html(self._company_name) if self._company_name else '',
            date=_escape_html(date),
            summary=_escape_html(summary_text),
        )
        self._sections.append({'type': 'raw', 'html': html})
        return self

    def add_executive_summary(self, paragraphs):
        """Add an executive summary section."""
        self._add_toc_entry('Executive Summary')
        parts = ['<h1>Executive Summary</h1>', '<div class="exec-summary">']
        for para in (paragraphs or []):
            parts.append('<p>{0}</p>'.format(_escape_html(para)))
        parts.append('</div>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_section(self, title, paragraphs):
        """Add a titled section with paragraphs."""
        self._add_toc_entry(title)
        parts = ['<h1>{0}</h1>'.format(_escape_html(title))]
        for para in (paragraphs or []):
            parts.append('<p>{0}</p>'.format(_escape_html(para)))
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_paragraph(self, text):
        """Add a standalone paragraph."""
        html = '<p>{0}</p>'.format(_escape_html(text))
        self._sections.append({'type': 'raw', 'html': html})
        return self

    def add_heading(self, text, level=2):
        """Add a heading (h2-h4)."""
        lvl = max(2, min(level, 4))
        html = '<h{0}>{1}</h{0}>'.format(lvl, _escape_html(text))
        self._sections.append({'type': 'raw', 'html': html})
        return self

    def add_key_findings(self, findings):
        """Add key findings with severity badges."""
        self._add_toc_entry('Key Findings')
        parts = ['<h1>Key Findings</h1>', '<div class="findings-list">']
        for f in (findings or []):
            title = f.get('title', 'Finding')
            desc = f.get('description', '')
            severity = f.get('severity', 'info')
            sev_color = _severity_color(severity)
            parts.append(
                '<div class="finding-item">'
                '<div class="finding-header">'
                '<span class="finding-severity" style="background:{sc};">'
                '{sev}</span>'
                '<span class="finding-title">{t}</span>'
                '</div>'
                '<div class="finding-desc">{d}</div>'
                '</div>'.format(
                    sc=sev_color,
                    sev=_escape_html(str(severity).upper()),
                    t=_escape_html(title),
                    d=_escape_html(desc),
                )
            )
        parts.append('</div>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_metrics_summary(self, metrics):
        """Render metrics as styled flex cards."""
        parts = ['<div class="metrics-grid">']
        for label, value in (metrics or {}).items():
            display_val = value if value is not None else 'N/A'
            parts.append(
                '<div class="metric-card">'
                '<div class="metric-value">{v}</div>'
                '<div class="metric-label">{l}</div>'
                '</div>'.format(
                    v=_escape_html(str(display_val)),
                    l=_escape_html(str(label)),
                )
            )
        parts.append('</div>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_recommendations(self, items):
        """Add prioritised recommendation cards."""
        self._add_toc_entry('Recommendations')
        parts = ['<h1>Recommendations</h1>', '<div class="rec-list">']
        for item in (items or []):
            priority = item.get('priority', '')
            title = item.get('title', '')
            desc = item.get('description', '')
            steps = item.get('steps', [])
            p_color = _severity_color(priority)
            steps_html = ''
            if steps:
                li_items = ''.join(
                    '<li>{0}</li>'.format(_escape_html(s)) for s in steps
                )
                steps_html = '<ol class="rec-steps">{0}</ol>'.format(li_items)
            parts.append(
                '<div class="rec-item">'
                '<span class="rec-priority" style="background:{pc};">'
                '{p}</span>'
                '<div class="rec-title">{t}</div>'
                '<div class="rec-desc">{d}</div>'
                '{steps}'
                '</div>'.format(
                    pc=p_color,
                    p=_escape_html(str(priority).upper()),
                    t=_escape_html(title),
                    d=_escape_html(desc),
                    steps=steps_html,
                )
            )
        parts.append('</div>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_table(self, headers, rows, caption=''):
        """Add a styled data table."""
        parts = ['<table>']
        if caption:
            parts.append('<caption>{0}</caption>'.format(_escape_html(caption)))
        hdr_cells = ''.join(
            '<th>{0}</th>'.format(_escape_html(str(h))) for h in headers
        )
        parts.append('<thead><tr>{0}</tr></thead>'.format(hdr_cells))
        parts.append('<tbody>')
        for row in (rows or []):
            cells = ''.join(
                '<td>{0}</td>'.format(
                    _escape_html(str(v) if v is not None else 'N/A')
                )
                for v in row
            )
            parts.append('<tr>{0}</tr>'.format(cells))
        parts.append('</tbody></table>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    def add_page_break(self):
        """Insert a manual page break."""
        self._sections.append(
            {'type': 'raw', 'html': '<div class="page-break"></div>'}
        )
        return self

    # ------------------------------------------------------------------
    # Score visualisation
    # ------------------------------------------------------------------
    def add_score_card(self, score, grade, label='Overall Score'):
        """Add a large centred score card with color coding."""
        score_val = score if score is not None else 0
        color = _score_color(score_val)
        bg = _score_bg(score_val)
        html = (
            '<div class="score-card" style="background:{bg};">'
            '<div class="score-value" style="color:{c};">{s}</div>'
            '<div class="score-grade" style="color:{c};">{g}</div>'
            '<div class="score-label">{l}</div>'
            '</div>'
        ).format(
            bg=bg, c=color,
            s=_escape_html(str(score_val)),
            g=_escape_html(str(grade)),
            l=_escape_html(str(label)),
        )
        self._sections.append({'type': 'raw', 'html': html})
        return self

    def add_category_scores(self, scores):
        """Add horizontal progress bars for category scores."""
        parts = ['<div class="category-scores">']
        for name, val in (scores or {}).items():
            safe_val = float(val) if val is not None else 0
            clamped = max(0.0, min(100.0, safe_val))
            color = _score_color(clamped)
            parts.append(
                '<div class="cat-score-row">'
                '<span class="cat-score-label">{name}</span>'
                '<div class="cat-score-bar-bg">'
                '<div class="cat-score-bar" '
                'style="width:{w}%;background:{c};"></div>'
                '</div>'
                '<span class="cat-score-val" style="color:{c};">{v}</span>'
                '</div>'.format(
                    name=_escape_html(str(name)),
                    w=int(clamped),
                    c=color,
                    v=int(clamped),
                )
            )
        parts.append('</div>')
        self._sections.append({'type': 'raw', 'html': '\n'.join(parts)})
        return self

    # ------------------------------------------------------------------
    # Chart methods (lazy-import matplotlib)
    # ------------------------------------------------------------------
    def _import_plt(self):
        """Lazy-import matplotlib with Agg backend."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        try:
            plt.style.use('seaborn-v0_8-whitegrid')
        except OSError:
            try:
                plt.style.use('seaborn-whitegrid')
            except OSError:
                pass
        return plt

    def add_bar_chart(self, labels, values, title,
                      xlabel='', ylabel='', colors=None):
        """Add a vertical bar chart."""
        plt = self._import_plt()
        if not labels or not values:
            return self
        n = len(labels)
        bar_colors = self._get_colors(n, colors)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(
            range(n), values, color=bar_colors,
            width=0.6, edgecolor='white', linewidth=0.5,
        )
        ax.set_xticks(range(n))
        ax.set_xticklabels(
            [str(lb) for lb in labels], rotation=30, ha='right', fontsize=9,
        )
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.3)
        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    def add_horizontal_bar_chart(self, labels, values, title, colors=None):
        """Add a horizontal bar chart."""
        plt = self._import_plt()
        if not labels or not values:
            return self
        n = len(labels)
        bar_colors = self._get_colors(n, colors)
        fig, ax = plt.subplots(figsize=(8, max(3, n * 0.5 + 1)))
        y_pos = range(n)
        ax.barh(
            y_pos, values, color=bar_colors,
            height=0.6, edgecolor='white', linewidth=0.5,
        )
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels([str(lb) for lb in labels], fontsize=9)
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
        ax.invert_yaxis()
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='x', alpha=0.3)
        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    def add_pie_chart(self, labels, values, title, colors=None):
        """Add a pie chart."""
        plt = self._import_plt()
        if not labels or not values:
            return self
        n = len(labels)
        pie_colors = self._get_colors(n, colors)
        fig, ax = plt.subplots(figsize=(6, 5))
        wedges, texts, autotexts = ax.pie(
            values,
            labels=[str(lb) for lb in labels],
            colors=pie_colors,
            autopct='%1.1f%%',
            startangle=90,
            pctdistance=0.75,
            textprops={'fontsize': 9},
        )
        for at in autotexts:
            at.set_fontsize(8)
            at.set_color('white')
            at.set_fontweight('bold')
        ax.set_title(title, fontsize=13, fontweight='bold', pad=14)
        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    def add_line_chart(self, x_data, y_data_dict, title,
                       xlabel='', ylabel=''):
        """Add a multi-series line chart."""
        plt = self._import_plt()
        if not x_data or not y_data_dict:
            return self
        fig, ax = plt.subplots(figsize=(8, 4.5))
        line_colors = self._get_colors(len(y_data_dict))
        for idx, (series_name, y_vals) in enumerate(y_data_dict.items()):
            ax.plot(
                x_data[:len(y_vals)], y_vals,
                color=line_colors[idx],
                linewidth=2,
                marker='o',
                markersize=4,
                label=str(series_name),
            )
        ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=10)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(alpha=0.3)
        if len(y_data_dict) > 1:
            ax.legend(fontsize=9, framealpha=0.9)
        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    def add_gauge_chart(self, value, max_val=100, title='', thresholds=None):
        """Add a semi-circle gauge chart."""
        plt = self._import_plt()
        import numpy as np

        safe_val = float(value) if value is not None else 0
        safe_max = float(max_val) if max_val else 100
        ratio = min(safe_val / safe_max, 1.0) if safe_max > 0 else 0

        fig, ax = plt.subplots(figsize=(5, 3.5))

        # Draw gauge arcs manually using matplotlib patches
        from matplotlib.patches import Arc
        # Background arc
        arc_bg = Arc(
            (0.5, 0.0), 0.8, 0.8, angle=0,
            theta1=0, theta2=180,
            color=_COLORS['border'], linewidth=18,
        )
        ax.add_patch(arc_bg)

        # Value arc
        gauge_color = _score_color(safe_val)
        theta_end = 180 * ratio
        arc_val = Arc(
            (0.5, 0.0), 0.8, 0.8, angle=0,
            theta1=180 - theta_end, theta2=180,
            color=gauge_color, linewidth=18,
        )
        ax.add_patch(arc_val)

        # Centre text
        ax.text(
            0.5, 0.15, str(int(safe_val)),
            ha='center', va='center',
            fontsize=28, fontweight='bold',
            color=gauge_color,
        )
        if title:
            ax.text(
                0.5, -0.15, title,
                ha='center', va='center',
                fontsize=10, color=_COLORS['text_light'],
            )

        ax.set_xlim(-0.1, 1.1)
        ax.set_ylim(-0.3, 0.6)
        ax.set_aspect('equal')
        ax.axis('off')
        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    def add_radar_chart(self, categories, values, title):
        """Add a radar / spider chart."""
        plt = self._import_plt()
        import numpy as np

        if not categories or not values:
            return self

        n = len(categories)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        plot_vals = list(values) + [values[0]]
        angles_closed = angles + [angles[0]]

        fig, ax = plt.subplots(
            figsize=(5.5, 5.5), subplot_kw={'projection': 'polar'},
        )
        ax.plot(angles_closed, plot_vals, color=_COLORS['blue'], linewidth=2)
        ax.fill(angles_closed, plot_vals, color=_COLORS['blue'], alpha=0.15)

        ax.set_xticks(angles)
        ax.set_xticklabels([str(c) for c in categories], fontsize=9)
        ax.set_title(title, fontsize=13, fontweight='bold', pad=20, y=1.08)
        ax.spines['polar'].set_color(_COLORS['border'])
        ax.grid(color=_COLORS['border'], alpha=0.5)

        fig.tight_layout()
        b64 = self._fig_to_base64(fig)
        self._sections.append({'type': 'raw', 'html': self._chart_img_tag(b64)})
        return self

    # ------------------------------------------------------------------
    # Build methods
    # ------------------------------------------------------------------
    def _build_toc_html(self):
        """Generate table of contents HTML."""
        if not self._toc_entries:
            return ''
        parts = [
            '<div class="toc">',
            '<h2>Table of Contents</h2>',
        ]
        for idx, entry in enumerate(self._toc_entries, 1):
            parts.append(
                '<div class="toc-item">'
                '<span class="toc-number">{n}.</span> {t}'
                '</div>'.format(
                    n=idx,
                    t=_escape_html(entry),
                )
            )
        parts.append('</div>')
        return '\n'.join(parts)

    def build_html(self):
        """Build the complete HTML document."""
        footer_text = '{0} | {1}'.format(
            self._company_name or 'SEO Report',
            self._date_str,
        )
        css = _build_css(footer_text)

        body_parts = []
        for section in self._sections:
            body_parts.append(section.get('html', ''))

        # Insert TOC after cover page (first section)
        toc_html = self._build_toc_html()
        if toc_html and len(body_parts) > 0:
            body_parts.insert(1, toc_html)

        html = (
            '<!DOCTYPE html>\n'
            '<html lang="en">\n'
            '<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" '
            'content="width=device-width, initial-scale=1">\n'
            '<title>{title}</title>\n'
            '<style>{css}</style>\n'
            '</head>\n'
            '<body>\n'
            '{body}\n'
            '</body>\n'
            '</html>'
        ).format(
            title=_escape_html(self._title),
            css=css,
            body='\n'.join(body_parts),
        )
        return html

    def build_pdf(self, filepath):
        """Build PDF and save to filepath. Returns the file path."""
        html_content = self.build_html()
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        # Try xhtml2pdf first (pure Python, works on all platforms)
        try:
            from xhtml2pdf import pisa
            with open(filepath, 'wb') as pdf_file:
                result = pisa.CreatePDF(html_content, dest=pdf_file)
                if result.err:
                    raise RuntimeError('xhtml2pdf conversion had errors')
            return filepath
        except ImportError:
            pass

        # Fallback to WeasyPrint (requires GTK on Windows)
        try:
            from weasyprint import HTML as WeasyprintHTML
            WeasyprintHTML(string=html_content).write_pdf(filepath)
            return filepath
        except (ImportError, OSError) as e:
            # Last resort: save as HTML
            html_path = filepath.replace('.pdf', '.html')
            with open(html_path, 'w', encoding='utf-8') as fh:
                fh.write(html_content)
            raise RuntimeError(
                'PDF generation requires xhtml2pdf or weasyprint. '
                'Install with: pip install xhtml2pdf. '
                'HTML report saved to: {0}'.format(html_path)
            ) from e

    def build_both(self, filepath_base):
        """Build both HTML and PDF. Returns (html_path, pdf_path)."""
        html_path = '{0}.html'.format(filepath_base)
        pdf_path = '{0}.pdf'.format(filepath_base)

        html_content = self.build_html()
        dirpath = os.path.dirname(html_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        with open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(html_content)

        # Try xhtml2pdf first (pure Python, works on all platforms)
        try:
            from xhtml2pdf import pisa
            with open(pdf_path, 'wb') as pdf_file:
                result = pisa.CreatePDF(html_content, dest=pdf_file)
                if result.err:
                    raise RuntimeError('xhtml2pdf conversion had errors')
        except ImportError:
            # Fallback to WeasyPrint
            try:
                from weasyprint import HTML as WeasyprintHTML
                WeasyprintHTML(string=html_content).write_pdf(pdf_path)
            except (ImportError, OSError):
                pdf_path = html_path  # Return HTML path if PDF fails

        return (html_path, pdf_path)
