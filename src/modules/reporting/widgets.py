"""Reusable Streamlit widget components for the SEO reporting dashboard."""

import logging
from typing import Optional

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

logger = logging.getLogger(__name__)


class ReportWidgets:
    """Collection of reusable Streamlit UI widgets for SEO dashboards."""

    MODULE_ICONS = {
        "technical": "\U0001f527",
        "onpage": "\U0001f4c4",
        "local": "\U0001f4cd",
        "content": "\U0001f4dd",
        "backlinks": "\U0001f517",
        "rankings": "\U0001f4ca",
        "keywords": "\U0001f50d",
        "visibility": "\U0001f441",
    }

    SIZE_MAP = {"large": 200, "medium": 140, "small": 100}

    @staticmethod
    def _score_to_grade(score: int) -> str:
        """Convert numeric score (0-100) to letter grade."""
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 60:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    @staticmethod
    def _score_to_color(score: int) -> str:
        """Return hex color based on score threshold."""
        if score >= 80:
            return "#22c55e"
        if score >= 60:
            return "#eab308"
        if score >= 40:
            return "#f97316"
        return "#ef4444"

    @staticmethod
    def _trend_arrow(trend: str) -> str:
        """Return styled HTML trend arrow."""
        if not trend:
            return '<span style="color:#9ca3af">&#8594;</span>'
        t = trend.strip().lower()
        if t in ("up", "positive", "+", "improving"):
            return '<span style="color:#22c55e">&#8593;</span>'
        if t in ("down", "negative", "-", "declining"):
            return '<span style="color:#ef4444">&#8595;</span>'
        return '<span style="color:#9ca3af">&#8594;</span>'

    @staticmethod
    def score_gauge(score: int, label: str, size: str = "large") -> None:
        """Render a circular SVG score gauge with animated stroke and grade letter."""
        score = max(0, min(100, int(score or 0)))
        color = ReportWidgets._score_to_color(score)
        grade = ReportWidgets._score_to_grade(score)
        dim = ReportWidgets.SIZE_MAP.get(size, 200)
        half = dim // 2
        radius = half - 12
        circumference = 2 * 3.14159265 * radius
        offset = circumference * (1 - score / 100)
        stroke_w = 10 if dim >= 140 else 7
        font_grade = dim // 4
        font_score = dim // 8
        font_label = max(dim // 12, 10)

        svg = "".join([
            '<svg width="', str(dim), '" height="', str(dim), '"',
            ' viewBox="0 0 ', str(dim), " ", str(dim), '"',
            ' style="transform:rotate(-90deg)">',
            '<circle cx="', str(half), '" cy="', str(half), '"',
            ' r="', str(radius), '" fill="none" stroke="#e5e7eb"',
            ' stroke-width="', str(stroke_w), '"/>',
            '<circle cx="', str(half), '" cy="', str(half), '"',
            ' r="', str(radius), '" fill="none" stroke="', color, '"',
            ' stroke-width="', str(stroke_w), '"',
            ' stroke-dasharray="', str(round(circumference, 2)), '"',
            ' stroke-dashoffset="', str(round(offset, 2)), '"',
            ' stroke-linecap="round"',
            ' style="transition:stroke-dashoffset 1s ease"/>',
            '</svg>',
        ])

        overlay = "".join([
            '<div style="position:absolute;top:0;left:0;width:100%;height:100%;',
            'display:flex;flex-direction:column;align-items:center;justify-content:center">',
            '<span style="font-size:', str(font_grade), 'px;font-weight:700;',
            'color:', color, '">', grade, '</span>',
            '<span style="font-size:', str(font_score), 'px;color:#6b7280">',
            str(score), '</span>',
            '</div>',
        ])

        label_html = ""
        if label:
            label_html = "".join([
                '<span style="font-size:', str(font_label),
                'px;color:#374151;margin-top:4px;font-weight:500">',
                str(label), '</span>',
            ])

        wrapper = "".join([
            '<div style="display:flex;flex-direction:column;align-items:center;padding:8px">',
            '<div style="position:relative;width:',
            str(dim), 'px;height:', str(dim), 'px">',
            svg, overlay, '</div>', label_html, '</div>',
        ])
        st.markdown(wrapper, unsafe_allow_html=True)

    @staticmethod
    def metric_card(
        title: str,
        value: str,
        delta: Optional[str] = None,
        icon: str = "",
    ) -> None:
        """Render a styled metric card with optional trend delta."""
        delta_html = ""
        if delta is not None:
            d = str(delta).strip()
            is_positive = d.startswith("+") or (d and d[0].isdigit())
            arrow = "&#8593;" if is_positive else "&#8595;"
            clr = "#22c55e" if is_positive else "#ef4444"
            delta_html = "".join([
                '<div style="font-size:13px;margin-top:4px;color:',
                clr, '">', arrow, ' ', d, '</div>',
            ])

        icon_part = ""
        if icon:
            icon_part = '<span style="font-size:24px;margin-right:6px">' + icon + '</span>'

        card = "".join([
            '<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;',
            'padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:8px">',
            '<div style="display:flex;align-items:center;margin-bottom:8px">',
            icon_part,
            '<span style="font-size:14px;color:#6b7280;font-weight:500">',
            str(title), '</span></div>',
            '<div style="font-size:28px;font-weight:700;color:#111827">',
            str(value), '</div>',
            delta_html,
            '</div>',
        ])
        st.markdown(card, unsafe_allow_html=True)

    @staticmethod
    def module_score_grid(scores: dict) -> None:
        """Render a 4-column grid of module score cards with small gauges."""
        if not scores:
            st.info("No module scores available.")
            return

        keys = list(scores.keys())
        for row_start in range(0, len(keys), 4):
            row_keys = keys[row_start: row_start + 4]
            cols = st.columns(4)
            for idx, key in enumerate(row_keys):
                info = scores[key]
                sc = int(info.get("score", 0))
                trend = info.get("trend", "")
                lbl = info.get("label", key.replace("_", " ").title())
                icon = ReportWidgets.MODULE_ICONS.get(key, "\U0001f4cb")
                trend_html = ReportWidgets._trend_arrow(trend)
                with cols[idx]:
                    hdr = "".join([
                        '<div style="text-align:center;font-size:14px;',
                        'font-weight:600;color:#374151;margin-bottom:4px">',
                        icon, ' ', lbl, ' ', trend_html, '</div>',
                    ])
                    st.markdown(hdr, unsafe_allow_html=True)
                    ReportWidgets.score_gauge(sc, "", size="small")

    @staticmethod
    def trend_chart(
        data: list,
        x_key: str,
        y_key: str,
        title: str,
    ) -> None:
        """Render a Plotly area-line chart for time-series trends."""
        if not data:
            st.info("No trend data available for '" + title + "'.")
            return

        x_vals = [d.get(x_key, "") for d in data]
        y_vals = [d.get(y_key, 0) for d in data]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="lines+markers",
                line=dict(color="#3b82f6", width=2.5),
                marker=dict(size=6, color="#3b82f6"),
                fill="tozeroy",
                fillcolor="rgba(59,130,246,0.08)",
                hovertemplate="%{x}<br>" + y_key + ": %{y}<extra></extra>",
            )
        )
        fig.update_layout(
            title=dict(text=title, font=dict(size=16, color="#111827")),
            xaxis_title=x_key.replace("_", " ").title(),
            yaxis_title=y_key.replace("_", " ").title(),
            template="plotly_white",
            height=360,
            margin=dict(l=40, r=20, t=50, b=40),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    @staticmethod
    def issues_summary_bar(issues: dict) -> None:
        """Render a horizontal stacked bar of Critical / Warning / Info counts."""
        if not issues:
            st.success("\u2705 No issues detected!")
            return

        critical = int(issues.get("critical", 0))
        warning = int(issues.get("warning", 0))
        info_count = int(issues.get("info", 0))
        total = critical + warning + info_count

        if total == 0:
            st.success("\u2705 No issues detected!")
            return

        fig = go.Figure()
        categories = ["Issues"]
        for name, val, clr in [
            ("Critical", critical, "#ef4444"),
            ("Warning", warning, "#f59e0b"),
            ("Info", info_count, "#3b82f6"),
        ]:
            fig.add_trace(
                go.Bar(
                    y=categories,
                    x=[val],
                    name=name,
                    orientation="h",
                    marker_color=clr,
                    text=[str(val) if val > 0 else ""],
                    textposition="inside",
                    textfont=dict(color="#fff", size=13),
                )
            )
        fig.update_layout(
            barmode="stack",
            height=100,
            margin=dict(l=0, r=0, t=10, b=0),
            template="plotly_white",
            showlegend=True,
            legend=dict(orientation="h", y=-0.4),
            xaxis=dict(showticklabels=False, showgrid=False),
            yaxis=dict(showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True)

    @staticmethod
    def action_items_table(items: list) -> None:
        """Render a styled HTML table of prioritized action items."""
        if not items:
            st.info("No action items to display.")
            return

        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_items = sorted(
            items,
            key=lambda x: priority_order.get(
                str(x.get("priority", "low")).lower(), 3
            ),
        )

        badge_colors = {
            "high": ("#fef2f2", "#ef4444"),
            "medium": ("#fffbeb", "#f59e0b"),
            "low": ("#f0fdf4", "#22c55e"),
        }

        def _badge(text, level):
            bg, fg = badge_colors.get(level.lower(), ("#f3f4f6", "#6b7280"))
            return "".join([
                '<span style="background:', bg, ';color:', fg,
                ';padding:2px 10px;border-radius:12px;font-size:12px;',
                'font-weight:600">', text.capitalize(), '</span>',
            ])

        th_style = 'padding:10px;text-align:left;font-size:13px;color:#6b7280'
        td_style = 'padding:10px;border-bottom:1px solid #e5e7eb'

        header = "".join([
            '<thead><tr style="background:#f9fafb">',
            '<th style="', th_style, '">Priority</th>',
            '<th style="', th_style, '">Action</th>',
            '<th style="', th_style, '">Module</th>',
            '<th style="', th_style, '">Impact</th>',
            '<th style="', th_style, '">Effort</th>',
            '</tr></thead>',
        ])

        rows = []
        for item in sorted_items:
            pri = str(item.get("priority", "low")).lower()
            action = str(item.get("action", ""))
            module = str(item.get("module", ""))
            impact = str(item.get("impact", "medium")).lower()
            effort = str(item.get("effort", "medium")).lower()
            row = "".join([
                '<tr>',
                '<td style="', td_style, '">', _badge(pri, pri), '</td>',
                '<td style="', td_style, '">', action, '</td>',
                '<td style="', td_style, '">', module, '</td>',
                '<td style="', td_style, '">', _badge(impact, impact), '</td>',
                '<td style="', td_style, '">', _badge(effort, effort), '</td>',
                '</tr>',
            ])
            rows.append(row)

        body = '<tbody>' + '\n'.join(rows) + '</tbody>'
        html = "".join([
            '<table style="width:100%;border-collapse:collapse;',
            'font-size:14px;color:#374151">',
            header, body, '</table>',
        ])
        st.markdown(html, unsafe_allow_html=True)

    @staticmethod
    def comparison_table(data: dict, domains: list) -> None:
        """Render a side-by-side comparison table for competitor domains."""
        if not data or not domains:
            st.info("No comparison data available.")
            return

        th_style = 'padding:10px;text-align:center;font-size:13px;color:#6b7280'
        td_style = 'padding:10px;text-align:center;border-bottom:1px solid #e5e7eb'

        header_cells = []
        for d in domains:
            header_cells.append("".join([
                '<th style="', th_style, '">', str(d), '</th>',
            ]))
        header = "".join([
            '<thead><tr style="background:#f9fafb">',
            '<th style="', th_style, ';text-align:left">Metric</th>',
            "".join(header_cells), '</tr></thead>',
        ])

        rows = []
        row_idx = 0
        for metric, values in data.items():
            bg = "#ffffff" if row_idx % 2 == 0 else "#f9fafb"
            numeric_vals = {}
            for dom in domains:
                v = values.get(dom, "")
                try:
                    cleaned = str(v).replace("%", "").replace(",", "")
                    numeric_vals[dom] = float(cleaned)
                except (ValueError, TypeError):
                    pass
            best_dom = None
            if numeric_vals:
                best_dom = max(numeric_vals, key=numeric_vals.get)

            cells = []
            for dom in domains:
                v = str(values.get(dom, "-"))
                style = td_style
                if dom == best_dom:
                    style = style + ';color:#22c55e;font-weight:700'
                cells.append("".join([
                    '<td style="', style, '">', v, '</td>',
                ]))

            row = "".join([
                '<tr style="background:', bg, '">',
                '<td style="', td_style, ';text-align:left;font-weight:600">',
                str(metric), '</td>',
                "".join(cells), '</tr>',
            ])
            rows.append(row)
            row_idx += 1

        body = '<tbody>' + '\n'.join(rows) + '</tbody>'
        html = "".join([
            '<table style="width:100%;border-collapse:collapse;font-size:14px;',
            'color:#374151;border:1px solid #e5e7eb;border-radius:8px;',
            'overflow:hidden">',
            header, body, '</table>',
        ])
        st.markdown(html, unsafe_allow_html=True)

    @staticmethod
    def progress_timeline(phases: list) -> None:
        """Render a vertical timeline showing SEO improvement phases."""
        if not phases:
            st.info("No timeline data available.")
            return

        status_config = {
            "completed": ("#22c55e", "#f0fdf4", ""),
            "active": ("#3b82f6", "#eff6ff", "animation:a0pulse 2s infinite"),
            "pending": ("#9ca3af", "#f9fafb", ""),
        }

        items_html = []
        total = len(phases)
        for i, phase in enumerate(phases):
            status = str(phase.get("status", "pending")).lower()
            name = str(phase.get("name", ""))
            date = str(phase.get("date", ""))
            desc = str(phase.get("description", ""))
            dot_color, bg_color, anim = status_config.get(
                status, ("#9ca3af", "#f9fafb", "")
            )
            is_last = i == total - 1

            line_html = ""
            if not is_last:
                line_html = "".join([
                    '<div style="position:absolute;left:11px;top:24px;',
                    'width:2px;bottom:-8px;background:',
                    dot_color, ';opacity:0.3"></div>',
                ])

            dot_parts = [
                'width:24px;height:24px;border-radius:50%;background:',
                dot_color, ';border:3px solid ', bg_color,
            ]
            if anim:
                dot_parts.extend([';', anim])
            dot_style = "".join(dot_parts)

            item = "".join([
                '<div style="display:flex;gap:16px;position:relative;',
                'padding-bottom:24px">',
                line_html,
                '<div style="flex-shrink:0;z-index:1">',
                '<div style="', dot_style, '"></div></div>',
                '<div style="flex:1;background:', bg_color,
                ';border-radius:8px;padding:12px 16px;',
                'border:1px solid #e5e7eb">',
                '<div style="display:flex;justify-content:space-between;',
                'align-items:center">',
                '<span style="font-weight:600;color:#111827">',
                name, '</span>',
                '<span style="font-size:12px;color:#6b7280">',
                date, '</span></div>',
                '<div style="font-size:13px;color:#6b7280;margin-top:4px">',
                desc, '</div></div></div>',
            ])
            items_html.append(item)

        keyframes = "".join([
            '<style>@keyframes a0pulse{',
            '0%{opacity:1}50%{opacity:0.5}100%{opacity:1}',
            '}</style>',
        ])
        html = "".join([
            keyframes,
            '<div style="padding:8px 0">',
            "".join(items_html),
            '</div>',
        ])
        st.markdown(html, unsafe_allow_html=True)
