"""Reports & Analytics — Streamlit dashboard page."""

import asyncio
import concurrent.futures
import json
import logging
import os
import tempfile
from datetime import datetime, date, timedelta, timezone
from typing import Any

import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import distinct

from src.database import get_session
from src.models.report import Report, Alert
from src.models.audit import SiteAudit
from src.models.ranking import RankingRecord, VisibilityScore
from src.models.backlink import Backlink
from src.models.content import BlogPost
from src.models.local_seo import LocalBusinessProfile
from src.models.keyword import Keyword
from src.modules.reporting.report_engine import ReportEngine
from src.modules.reporting.report_renderer import ReportRenderer
from src.modules.reporting.widgets import ReportWidgets

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine in Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Lazy initializers
# ---------------------------------------------------------------------------


def _get_engine() -> ReportEngine:
    """Lazy-initialize ReportEngine in session state."""
    if "reports_engine" not in st.session_state:
        st.session_state.reports_engine = ReportEngine()
    return st.session_state.reports_engine


def _get_renderer() -> ReportRenderer:
    """Lazy-initialize ReportRenderer with saved branding."""
    if "reports_renderer" not in st.session_state:
        branding = st.session_state.get("reports_branding", None)
        st.session_state.reports_renderer = ReportRenderer(branding=branding)
    return st.session_state.reports_renderer


# ---------------------------------------------------------------------------
# Domain discovery
# ---------------------------------------------------------------------------


def _get_available_domains() -> list:
    """Query distinct domains from multiple tables."""
    domains: set = set()
    try:
        with get_session() as session:
            for val in session.query(distinct(SiteAudit.domain)).all():
                if val[0]:
                    domains.add(val[0])
            for val in session.query(distinct(RankingRecord.domain)).all():
                if val[0]:
                    domains.add(val[0])
            for val in session.query(distinct(Backlink.source_domain)).all():
                if val[0]:
                    domains.add(val[0])
            for val in session.query(distinct(VisibilityScore.domain)).all():
                if val[0]:
                    domains.add(val[0])
    except Exception as exc:
        logger.warning("Failed to query domains: %s", exc)
    return sorted(domains)


# ---------------------------------------------------------------------------
# Safe dict access helper
# ---------------------------------------------------------------------------


def _safe(data: Any, key: str, default: Any = None) -> Any:
    """Safely get a value from a dict or return default."""
    if isinstance(data, dict):
        return data.get(key, default)
    return default


# ===================================================================
# MAIN ENTRY POINT
# ===================================================================


def render_reports_page():
    """Render the Reports & Analytics dashboard page."""
    st.title("\U0001f4ca Reports & Analytics")
    st.markdown("Generate comprehensive SEO reports, track trends, and export data.")

    tabs = st.tabs([
        "\U0001f4ca Overview Dashboard",
        "\U0001f4c8 Trends",
        "\U0001f4cb Full Report",
        "\U0001f3c6 Competitors",
        "\U0001f4c5 Scheduled Reports",
        "\U0001f3a8 Branding",
        "\U0001f4e5 Export Center",
    ])

    with tabs[0]:
        _render_overview_tab()
    with tabs[1]:
        _render_trends_tab()
    with tabs[2]:
        _render_full_report_tab()
    with tabs[3]:
        _render_competitors_tab()
    with tabs[4]:
        _render_scheduled_tab()
    with tabs[5]:
        _render_branding_tab()
    with tabs[6]:
        _render_export_tab()


# ===================================================================
# TAB 1: Overview Dashboard
# ===================================================================


def _render_overview_tab():
    """Overview dashboard with domain selector and health scores."""
    st.subheader("Overview Dashboard")

    domains = _get_available_domains()
    if not domains:
        st.info(
            "No domains found yet. Run a site audit, track rankings, or add "
            "backlinks to get started. Your domains will appear here automatically."
        )
        return

    selected = st.selectbox(
        "Select Domain",
        options=["-- Select a domain --"] + domains,
        key="reports_domain_select",
    )

    if selected == "-- Select a domain --":
        st.info(
            "Select a domain above to view its SEO health dashboard. "
            "Scores are aggregated from all modules."
        )
        return

    domain = selected
    st.session_state["reports_selected_domain"] = domain

    engine = _get_engine()

    with st.spinner("Aggregating scores..."):
        try:
            scores = engine.aggregate_scores(domain)
        except Exception as exc:
            logger.error("aggregate_scores failed: %s", exc)
            st.error("Failed to aggregate scores. Please try again.")
            return

    if not scores:
        st.info("No scoring data available for this domain yet.")
        return

    # Overall health score - centered
    overall = int(_safe(scores, "overall_score", 0))
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        ReportWidgets.score_gauge(overall, "Overall SEO Health", size="large")

    st.divider()

    # Module score grid
    module_scores = {}
    score_keys = [
        ("technical_score", "Technical SEO", "technical"),
        ("onpage_score", "On-Page SEO", "onpage"),
        ("local_score", "Local SEO", "local"),
        ("content_score", "Content", "content"),
        ("backlink_score", "Backlinks", "backlink"),
        ("visibility_score", "Visibility", "visibility"),
    ]
    trends_data = _safe(scores, "trends", {})
    current_trends = _safe(trends_data, "current", {})
    previous_trends = _safe(trends_data, "previous", {})

    for key, label, module_id in score_keys:
        score_val = int(_safe(scores, key, 0))
        current_val = _safe(current_trends, module_id, score_val)
        previous_val = _safe(previous_trends, module_id, 0)
        if previous_val and current_val:
            diff = current_val - previous_val
            trend_str = "up" if diff > 0 else ("down" if diff < 0 else "stable")
        else:
            trend_str = "stable"
        module_scores[module_id] = {
            "score": score_val,
            "trend": trend_str,
            "label": label,
        }

    st.markdown("### Module Scores")
    ReportWidgets.module_score_grid(module_scores)

    st.divider()

    # Recent alerts and action items
    col_alerts, col_actions = st.columns(2)

    with col_alerts:
        st.markdown("### Recent Alerts")
        try:
            with get_session() as session:
                alerts = (
                    session.query(Alert)
                    .order_by(Alert.created_at.desc())
                    .limit(5)
                    .all()
                )
            if alerts:
                for alert in alerts:
                    severity_icon = {
                        "critical": "\U0001f534",
                        "warning": "\U0001f7e1",
                        "info": "\U0001f535",
                    }.get(alert.severity, "\u2139\ufe0f")
                    status_tag = "\u2705" if alert.resolved else "\u23f3"
                    st.markdown(
                        severity_icon + " **" + alert.alert_type + "** \u2014 "
                        + alert.message[:120] + " " + status_tag
                    )
            else:
                st.info("No alerts recorded yet.")
        except Exception as exc:
            logger.warning("Failed to load alerts: %s", exc)
            st.info("Alert data is not available.")

    with col_actions:
        st.markdown("### Quick Action Items")
        try:
            action_items = []
            for key, label, module_id in score_keys:
                summary = engine.get_module_summary(module_id, domain)
                if summary and _safe(summary, "issues_count", 0) > 0:
                    score_val = _safe(summary, "score", 0)
                    priority = "high" if score_val < 50 else ("medium" if score_val < 75 else "low")
                    action_items.append({
                        "module": label,
                        "action": "Review " + str(_safe(summary, "issues_count", 0)) + " issues",
                        "priority": priority,
                        "score": score_val,
                    })
            action_items.sort(key=lambda x: x.get("score", 100))
            top_actions = action_items[:5]
            if top_actions:
                ReportWidgets.action_items_table(top_actions)
            else:
                st.success("No urgent action items. Your SEO is in good shape!")
        except Exception as exc:
            logger.warning("Failed to build action items: %s", exc)
            st.info("Action items not available.")

    st.divider()

    # 30-day trend mini-charts
    st.markdown("### 30-Day Trends")
    try:
        with get_session() as session:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            vis_records = (
                session.query(VisibilityScore)
                .filter(
                    VisibilityScore.domain == domain,
                    VisibilityScore.date >= thirty_days_ago,
                )
                .order_by(VisibilityScore.date.asc())
                .all()
            )
        if vis_records:
            trend_data = []
            for rec in vis_records:
                date_str = rec.date.strftime("%Y-%m-%d") if rec.date else "N/A"
                trend_data.append({
                    "date": date_str,
                    "score": rec.score,
                    "keywords": rec.keyword_count,
                    "avg_position": rec.avg_position,
                })

            tcol1, tcol2 = st.columns(2)
            with tcol1:
                ReportWidgets.trend_chart(trend_data, "date", "score", "Visibility Score")
            with tcol2:
                ReportWidgets.trend_chart(trend_data, "date", "avg_position", "Avg Position")
        else:
            st.info("No visibility data in the last 30 days. Track rankings to see trends.")
    except Exception as exc:
        logger.warning("Failed to load trend data: %s", exc)
        st.info("Trend data is not available.")


# ===================================================================
# TAB 2: Trends
# ===================================================================


def _render_trends_tab():
    """Trends analysis with date range selection and period comparison."""
    st.subheader("Trends Analysis")

    domain = st.session_state.get("reports_selected_domain", "")
    if not domain:
        st.info("Please select a domain in the Overview tab first.")
        return

    st.markdown("**Domain:** " + domain)

    # Date range selector
    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=90),
            key="reports_trend_start",
        )
    with col_end:
        end_date = st.date_input(
            "End Date",
            value=date.today(),
            key="reports_trend_end",
        )

    if start_date >= end_date:
        st.warning("Start date must be before end date.")
        return

    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    # Load visibility data for the date range
    try:
        with get_session() as session:
            vis_records = (
                session.query(VisibilityScore)
                .filter(
                    VisibilityScore.domain == domain,
                    VisibilityScore.date >= start_dt,
                    VisibilityScore.date <= end_dt,
                )
                .order_by(VisibilityScore.date.asc())
                .all()
            )
    except Exception as exc:
        logger.error("Failed to query visibility data: %s", exc)
        st.error("Failed to load trend data.")
        return

    if not vis_records:
        st.info("No visibility data found for this date range. Track rankings to generate trend data.")
        return

    trend_data = []
    for rec in vis_records:
        date_str = rec.date.strftime("%Y-%m-%d") if rec.date else "N/A"
        trend_data.append({
            "date": date_str,
            "score": rec.score,
            "keywords": rec.keyword_count,
            "avg_position": rec.avg_position,
            "top3": rec.top3_count,
            "top10": rec.top10_count,
            "top20": rec.top20_count,
        })

    # Charts
    st.markdown("### Visibility Score Over Time")
    ReportWidgets.trend_chart(trend_data, "date", "score", "Visibility Score")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("### Keyword Count")
        ReportWidgets.trend_chart(trend_data, "date", "keywords", "Tracked Keywords")
    with chart_col2:
        st.markdown("### Average Position")
        ReportWidgets.trend_chart(trend_data, "date", "avg_position", "Avg Position")

    st.markdown("### Top Positions Breakdown")
    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        ReportWidgets.trend_chart(trend_data, "date", "top3", "Top 3 Keywords")
    with top_col2:
        ReportWidgets.trend_chart(trend_data, "date", "top10", "Top 10 Keywords")
    with top_col3:
        ReportWidgets.trend_chart(trend_data, "date", "top20", "Top 20 Keywords")

    # Period comparison
    st.divider()
    st.markdown("### Period Comparison")
    st.markdown("Compare SEO metrics between two time periods.")

    comp_col1, comp_col2 = st.columns(2)
    with comp_col1:
        st.markdown("**Period 1**")
        p1_start = st.date_input("P1 Start", value=date.today() - timedelta(days=60), key="reports_p1_start")
        p1_end = st.date_input("P1 End", value=date.today() - timedelta(days=31), key="reports_p1_end")
    with comp_col2:
        st.markdown("**Period 2**")
        p2_start = st.date_input("P2 Start", value=date.today() - timedelta(days=30), key="reports_p2_start")
        p2_end = st.date_input("P2 End", value=date.today(), key="reports_p2_end")

    engine = _get_engine()
    if st.button("Compare Periods", key="reports_compare_btn"):
        period1 = (
            datetime.combine(p1_start, datetime.min.time()).replace(tzinfo=timezone.utc),
            datetime.combine(p1_end, datetime.max.time()).replace(tzinfo=timezone.utc),
        )
        period2 = (
            datetime.combine(p2_start, datetime.min.time()).replace(tzinfo=timezone.utc),
            datetime.combine(p2_end, datetime.max.time()).replace(tzinfo=timezone.utc),
        )
        with st.spinner("Comparing periods..."):
            try:
                comparison = engine.compare_periods(domain, period1, period2)
                st.session_state["reports_period_comparison"] = comparison
            except Exception as exc:
                logger.error("Period comparison failed: %s", exc)
                st.error("Failed to compare periods: " + str(exc))
                return

    comparison = st.session_state.get("reports_period_comparison")
    if comparison:
        st.markdown("#### Comparison Results")
        if isinstance(comparison, dict):
            p1_data = _safe(comparison, "period1", {})
            p2_data = _safe(comparison, "period2", {})
            changes = _safe(comparison, "changes", {})

            metric_cols = st.columns(4)
            metric_names = ["overall_score", "visibility", "avg_position", "keyword_count"]
            metric_labels = ["Overall Score", "Visibility", "Avg Position", "Keywords"]
            for i, (mname, mlabel) in enumerate(zip(metric_names, metric_labels)):
                with metric_cols[i % 4]:
                    p2_val = _safe(p2_data, mname, 0)
                    change_val = _safe(changes, mname, 0)
                    delta_str = ""
                    if change_val:
                        sign = "+" if change_val > 0 else ""
                        delta_str = sign + str(round(change_val, 1))
                    ReportWidgets.metric_card(
                        mlabel,
                        str(round(p2_val, 1)) if p2_val else "N/A",
                        delta=delta_str if delta_str else None,
                    )
        else:
            st.json(comparison)


# ===================================================================
# TAB 3: Full Report
# ===================================================================


def _render_full_report_tab():
    """Generate comprehensive SEO report."""
    st.subheader("Full Report")

    domain = st.session_state.get("reports_selected_domain", "")
    if not domain:
        st.info("Please select a domain in the Overview tab first.")
        return

    st.markdown("**Domain:** " + domain)

    date_range_col1, date_range_col2 = st.columns(2)
    with date_range_col1:
        report_start = st.date_input(
            "Report Start",
            value=date.today() - timedelta(days=30),
            key="reports_full_start",
        )
    with date_range_col2:
        report_end = st.date_input(
            "Report End",
            value=date.today(),
            key="reports_full_end",
        )

    if st.button("Generate Comprehensive Report", key="reports_generate_btn", type="primary"):
        engine = _get_engine()
        dr = (
            datetime.combine(report_start, datetime.min.time()).replace(tzinfo=timezone.utc),
            datetime.combine(report_end, datetime.max.time()).replace(tzinfo=timezone.utc),
        )
        with st.spinner("Generating comprehensive report... This may take a moment."):
            try:
                report_data = _run_async(engine.generate_full_report(domain, date_range=dr))
                st.session_state["reports_full_data"] = report_data
                st.success("Report generated successfully!")
            except Exception as exc:
                logger.error("Report generation failed: %s", exc)
                st.error("Failed to generate report: " + str(exc))
                return

    report_data = st.session_state.get("reports_full_data")
    if not report_data:
        st.info(
            "Click the button above to generate a comprehensive SEO report. "
            "The report aggregates data from all modules."
        )
        return

    # Inline HTML preview
    st.markdown("### Report Preview")
    renderer = _get_renderer()
    try:
        html_content = renderer.render_html(report_data, template="professional")
        with st.expander("View Full Report", expanded=True):
            st.components.v1.html(html_content, height=800, scrolling=True)
    except Exception as exc:
        logger.warning("HTML render failed: %s", exc)
        st.warning("Could not render HTML preview.")

    # Download buttons
    st.markdown("### Download Report")
    dl_col1, dl_col2, dl_col3 = st.columns(3)

    with dl_col1:
        try:
            html_bytes = renderer.render_html(report_data).encode("utf-8")
            st.download_button(
                label="Download HTML",
                data=html_bytes,
                file_name="seo_report_" + domain.replace(".", "_") + ".html",
                mime="text/html",
                key="reports_dl_html",
            )
        except Exception as exc:
            logger.warning("HTML download prep failed: %s", exc)
            st.warning("HTML export not available.")

    with dl_col2:
        try:
            pdf_bytes = renderer.render_pdf(report_data)
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name="seo_report_" + domain.replace(".", "_") + ".pdf",
                mime="application/pdf",
                key="reports_dl_pdf",
            )
        except Exception as exc:
            logger.warning("PDF export failed: %s", exc)
            st.warning("PDF export not available. Install weasyprint for PDF support.")

    with dl_col3:
        try:
            json_str = renderer.render_json(report_data)
            st.download_button(
                label="Download JSON",
                data=json_str.encode("utf-8"),
                file_name="seo_report_" + domain.replace(".", "_") + ".json",
                mime="application/json",
                key="reports_dl_json",
            )
        except Exception as exc:
            logger.warning("JSON export failed: %s", exc)
            st.warning("JSON export not available.")


# ===================================================================
# TAB 4: Competitors
# ===================================================================


def _render_competitors_tab():
    """Competitor comparison analysis."""
    st.subheader("Competitor Comparison")

    domain = st.session_state.get("reports_selected_domain", "")
    if not domain:
        st.info("Please select a domain in the Overview tab first.")
        return

    st.markdown("**Your Domain:** " + domain)

    competitors_input = st.text_input(
        "Enter competitor domains (comma-separated)",
        placeholder="competitor1.com, competitor2.com, competitor3.com",
        key="reports_competitors_input",
    )

    if st.button("Compare", key="reports_compare_competitors_btn", type="primary"):
        if not competitors_input.strip():
            st.warning("Please enter at least one competitor domain.")
            return

        competitors = [c.strip() for c in competitors_input.split(",") if c.strip()]
        if not competitors:
            st.warning("Please enter valid competitor domains.")
            return

        engine = _get_engine()
        with st.spinner("Analyzing competitors... This may take a moment."):
            try:
                comp_data = _run_async(engine.generate_competitor_comparison(domain, competitors))
                st.session_state["reports_competitor_data"] = comp_data
                st.session_state["reports_competitor_list"] = [domain] + competitors
            except Exception as exc:
                logger.error("Competitor comparison failed: %s", exc)
                st.error("Failed to compare competitors: " + str(exc))
                return

    comp_data = st.session_state.get("reports_competitor_data")
    comp_list = st.session_state.get("reports_competitor_list", [])

    if not comp_data:
        st.info(
            "Enter competitor domains above and click Compare to see a "
            "side-by-side analysis of SEO metrics."
        )
        return

    # Comparison table
    st.markdown("### Side-by-Side Comparison")
    try:
        ReportWidgets.comparison_table(comp_data, comp_list)
    except Exception as exc:
        logger.warning("Comparison table render failed: %s", exc)

    # Radar chart using Plotly
    st.markdown("### Visual Comparison")
    try:
        categories = ["Technical", "On-Page", "Content", "Backlinks", "Visibility", "Local"]
        fig = go.Figure()

        domains_data = _safe(comp_data, "domains", comp_data)
        if isinstance(domains_data, dict):
            for d_name in comp_list:
                d_scores = _safe(domains_data, d_name, {})
                if isinstance(d_scores, dict):
                    values = [
                        _safe(d_scores, "technical_score", 0),
                        _safe(d_scores, "onpage_score", 0),
                        _safe(d_scores, "content_score", 0),
                        _safe(d_scores, "backlink_score", 0),
                        _safe(d_scores, "visibility_score", 0),
                        _safe(d_scores, "local_score", 0),
                    ]
                    values_closed = values + [values[0]]
                    cats_closed = categories + [categories[0]]
                    fig.add_trace(go.Scatterpolar(
                        r=values_closed,
                        theta=cats_closed,
                        fill="toself",
                        name=d_name,
                        opacity=0.6,
                    ))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True,
            height=500,
            title="SEO Score Comparison",
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        logger.warning("Radar chart failed: %s", exc)
        st.info("Visual comparison chart not available.")


# ===================================================================
# TAB 5: Scheduled Reports
# ===================================================================


def _render_scheduled_tab():
    """Set up and manage recurring report schedules."""
    st.subheader("Scheduled Reports")

    domain = st.session_state.get("reports_selected_domain", "")
    if not domain:
        st.info("Please select a domain in the Overview tab first.")
        return

    st.markdown("**Domain:** " + domain)

    # Create new schedule form
    with st.expander("Create New Report Schedule", expanded=False):
        with st.form("reports_schedule_form"):
            freq = st.selectbox(
                "Frequency",
                options=["daily", "weekly", "monthly"],
                key="reports_sched_freq",
            )
            fmt = st.selectbox(
                "Report Format",
                options=["html", "pdf", "json"],
                key="reports_sched_fmt",
            )
            email = st.text_input(
                "Email (optional)",
                placeholder="reports@example.com",
                key="reports_sched_email",
            )
            submitted = st.form_submit_button("Create Schedule")

            if submitted:
                engine = _get_engine()
                try:
                    email_val = email.strip() if email.strip() else None
                    result = engine.schedule_report(domain, freq, email_to=email_val)
                    st.success(
                        "Report schedule created! Frequency: " + freq
                        + (" | Email: " + email_val if email_val else "")
                    )
                    logger.info("Scheduled report created for %s: %s", domain, result)
                except Exception as exc:
                    logger.error("Schedule creation failed: %s", exc)
                    st.error("Failed to create schedule: " + str(exc))

    # List existing schedules
    st.markdown("### Existing Report Schedules")
    try:
        with get_session() as session:
            schedules = (
                session.query(Report)
                .filter(Report.report_type == "scheduled_config")
                .order_by(Report.created_at.desc())
                .all()
            )

        if not schedules:
            st.info("No scheduled reports configured. Create one above to get started.")
        else:
            for sched in schedules:
                config = sched.data_json or {}
                sched_domain = _safe(config, "domain", "Unknown")
                sched_freq = _safe(config, "frequency", "N/A")
                sched_email = _safe(config, "email_to", "None")
                sched_enabled = _safe(config, "enabled", True)
                created_str = sched.created_at.strftime("%Y-%m-%d %H:%M") if sched.created_at else "N/A"

                col_info, col_toggle = st.columns([3, 1])
                with col_info:
                    st.markdown(
                        "**" + sched.title + "** | "
                        + sched_domain + " | " + sched_freq
                        + " | Email: " + str(sched_email)
                        + " | Created: " + created_str
                    )
                with col_toggle:
                    enabled = st.checkbox(
                        "Enabled",
                        value=bool(sched_enabled),
                        key="reports_sched_toggle_" + str(sched.id),
                    )
                    if enabled != sched_enabled:
                        try:
                            with get_session() as sess:
                                db_report = sess.get(Report, sched.id)
                                if db_report and db_report.data_json:
                                    updated_config = dict(db_report.data_json)
                                    updated_config["enabled"] = enabled
                                    db_report.data_json = updated_config
                                    sess.commit()
                                    st.rerun()
                        except Exception as exc:
                            logger.warning("Toggle schedule failed: %s", exc)
    except Exception as exc:
        logger.warning("Failed to list schedules: %s", exc)
        st.info("Could not load scheduled reports.")


# ===================================================================
# TAB 6: Branding
# ===================================================================


def _render_branding_tab():
    """Configure white-label branding for reports."""
    st.subheader("Report Branding")
    st.markdown("Customize the look and feel of your exported reports.")

    branding = st.session_state.get("reports_branding", {})

    col_logo, col_settings = st.columns([1, 2])

    with col_logo:
        st.markdown("### Logo")
        uploaded_logo = st.file_uploader(
            "Upload Logo (PNG, JPG, SVG)",
            type=["png", "jpg", "jpeg", "svg"],
            key="reports_logo_upload",
        )
        logo_path = _safe(branding, "logo_path", None)

        if uploaded_logo:
            logo_dir = os.path.join("/a0/usr/projects/fullseoautomation/data", "branding")
            os.makedirs(logo_dir, exist_ok=True)
            logo_path = os.path.join(logo_dir, uploaded_logo.name)
            with open(logo_path, "wb") as f:
                f.write(uploaded_logo.getbuffer())
            st.image(logo_path, width=200)
            st.success("Logo uploaded!")
        elif logo_path and os.path.exists(logo_path):
            st.image(logo_path, width=200)
        else:
            st.info("No logo uploaded. A default header will be used.")

    with col_settings:
        st.markdown("### Company Details")
        company_name = st.text_input(
            "Company Name",
            value=_safe(branding, "company_name", ""),
            key="reports_company_name",
        )

        st.markdown("### Colors")
        color_col1, color_col2 = st.columns(2)
        with color_col1:
            primary_color = st.color_picker(
                "Primary Color",
                value=_safe(branding, "primary_color", "#1a73e8"),
                key="reports_primary_color",
            )
        with color_col2:
            secondary_color = st.color_picker(
                "Secondary Color",
                value=_safe(branding, "secondary_color", "#34a853"),
                key="reports_secondary_color",
            )

    st.divider()

    save_col, preview_col = st.columns(2)

    with save_col:
        if st.button("Save Branding", key="reports_save_branding", type="primary"):
            new_branding = {
                "logo_path": logo_path,
                "company_name": company_name,
                "primary_color": primary_color,
                "secondary_color": secondary_color,
            }
            st.session_state["reports_branding"] = new_branding
            # Re-initialize renderer with new branding
            renderer = _get_renderer()
            try:
                renderer.customize_branding(
                    logo_path=logo_path,
                    company_name=company_name,
                    primary_color=primary_color,
                    secondary_color=secondary_color,
                )
                st.session_state["reports_renderer"] = renderer
                st.success("Branding saved and applied!")
            except Exception as exc:
                logger.warning("Branding customization failed: %s", exc)
                st.warning("Branding saved locally but renderer update failed.")

    with preview_col:
        if st.button("Preview Branded Report", key="reports_preview_branding"):
            report_data = st.session_state.get("reports_full_data")
            if not report_data:
                st.info("Generate a full report first (Full Report tab) to preview branding.")
            else:
                renderer = _get_renderer()
                try:
                    html_preview = renderer.render_html(report_data, template="professional")
                    st.components.v1.html(html_preview, height=600, scrolling=True)
                except Exception as exc:
                    logger.warning("Branding preview failed: %s", exc)
                    st.warning("Could not generate branded preview.")


# ===================================================================
# TAB 7: Export Center
# ===================================================================


def _render_export_tab():
    """Export reports in various formats and view history."""
    st.subheader("Export Center")

    report_data = st.session_state.get("reports_full_data")

    # Export current report
    st.markdown("### Export Current Report")
    if not report_data:
        st.info(
            "No report has been generated yet. Go to the Full Report tab "
            "to generate a comprehensive report, then return here to export."
        )
    else:
        domain = _safe(report_data, "domain", "unknown")
        generated_at = _safe(report_data, "generated_at", "")
        st.markdown(
            "**Report for:** " + str(domain)
            + " | **Generated:** " + str(generated_at)
        )

        renderer = _get_renderer()
        export_cols = st.columns(3)

        with export_cols[0]:
            st.markdown("#### HTML Report")
            try:
                html_data = renderer.render_html(report_data).encode("utf-8")
                st.download_button(
                    label="Download HTML",
                    data=html_data,
                    file_name="seo_report_" + str(domain).replace(".", "_") + ".html",
                    mime="text/html",
                    key="reports_export_html",
                )
            except Exception as exc:
                logger.warning("HTML export failed: %s", exc)
                st.warning("HTML export not available.")

        with export_cols[1]:
            st.markdown("#### JSON Data")
            try:
                json_data = renderer.render_json(report_data).encode("utf-8")
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name="seo_report_" + str(domain).replace(".", "_") + ".json",
                    mime="application/json",
                    key="reports_export_json",
                )
            except Exception as exc:
                logger.warning("JSON export failed: %s", exc)
                st.warning("JSON export not available.")

        with export_cols[2]:
            st.markdown("#### CSV Bundle")
            try:
                output_dir = tempfile.mkdtemp(prefix="seo_csv_")
                zip_path = renderer.render_csv_bundle(report_data, output_dir)
                if zip_path and os.path.exists(zip_path):
                    with open(zip_path, "rb") as zf:
                        zip_bytes = zf.read()
                    st.download_button(
                        label="Download CSV Bundle",
                        data=zip_bytes,
                        file_name="seo_data_" + str(domain).replace(".", "_") + ".zip",
                        mime="application/zip",
                        key="reports_export_csv",
                    )
                else:
                    st.warning("CSV bundle generation returned no file.")
            except Exception as exc:
                logger.warning("CSV export failed: %s", exc)
                st.warning("CSV export not available.")

    st.divider()

    # Report history
    st.markdown("### Report History")
    try:
        with get_session() as session:
            past_reports = (
                session.query(Report)
                .filter(Report.report_type != "scheduled_config")
                .order_by(Report.created_at.desc())
                .limit(20)
                .all()
            )

        if not past_reports:
            st.info("No past reports found. Generated reports will appear here.")
        else:
            for report in past_reports:
                created_str = (
                    report.created_at.strftime("%Y-%m-%d %H:%M")
                    if report.created_at else "N/A"
                )
                hist_col1, hist_col2, hist_col3 = st.columns([3, 1, 1])
                with hist_col1:
                    st.markdown(
                        "**" + report.title + "** | "
                        + report.report_type + " | " + created_str
                    )
                with hist_col2:
                    if report.data_json:
                        report_json_str = json.dumps(report.data_json, default=str)
                        st.download_button(
                            label="JSON",
                            data=report_json_str.encode("utf-8"),
                            file_name="report_" + str(report.id) + ".json",
                            mime="application/json",
                            key="reports_hist_json_" + str(report.id),
                        )
                    else:
                        st.caption("No data")
                with hist_col3:
                    if report.file_path and os.path.exists(report.file_path):
                        with open(report.file_path, "rb") as rf:
                            file_bytes = rf.read()
                        ext = os.path.splitext(report.file_path)[1]
                        mime_map = {
                            ".html": "text/html",
                            ".pdf": "application/pdf",
                            ".json": "application/json",
                            ".zip": "application/zip",
                        }
                        st.download_button(
                            label="File",
                            data=file_bytes,
                            file_name="report_" + str(report.id) + ext,
                            mime=mime_map.get(ext, "application/octet-stream"),
                            key="reports_hist_file_" + str(report.id),
                        )
                    else:
                        st.caption("No file")
    except Exception as exc:
        logger.warning("Failed to load report history: %s", exc)
        st.info("Report history is not available.")
