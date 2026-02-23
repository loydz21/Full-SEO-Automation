"""Technical SEO Audit — Streamlit dashboard page.

Provides a multi-tab interface for running audits, viewing results,
crawl data, performance metrics, security checks, recommendations,
and exporting reports.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _severity_badge(severity: str) -> str:
    colors = {"error": "#ef4444", "warning": "#f97316", "info": "#3b82f6"}
    c = colors.get(severity, "#6b7280")
    return (
        "<span style=\"background:{c};color:white;padding:2px 8px;"
        "border-radius:4px;font-size:0.8rem;font-weight:bold;\">"
        "{sev}</span>"
    ).format(c=c, sev=severity.upper())


def _score_color(score: float) -> str:
    if score >= 80:
        return "#22c55e"
    if score >= 60:
        return "#eab308"
    return "#ef4444"


def _cwv_color(metric: str, value) -> str:
    """Return colour based on Core Web Vitals thresholds."""
    if value is None:
        return "#6b7280"
    thresholds = {
        "lcp": (2500, 4000),
        "fcp": (1800, 3000),
        "cls": (0.1, 0.25),
        "ttfb": (800, 1800),
        "inp": (200, 500),
        "speed_index": (3400, 5800),
    }
    good, poor = thresholds.get(metric, (0, 0))
    if good == 0:
        return "#6b7280"
    if value <= good:
        return "#22c55e"
    if value <= poor:
        return "#eab308"
    return "#ef4444"


def _grade_badge(grade: str) -> str:
    colors = {
        "A": "#22c55e", "B": "#84cc16", "C": "#eab308",
        "D": "#f97316", "F": "#ef4444",
    }
    c = colors.get(grade, "#6b7280")
    return (
        "<div style=\"display:inline-block;background:{c};color:white;"
        "font-size:3rem;font-weight:bold;width:80px;height:80px;"
        "border-radius:50%;text-align:center;line-height:80px;\">"
        "{grade}</div>"
    ).format(c=c, grade=grade)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_technical_audit_page():
    """Render the Technical SEO Audit dashboard page."""
    st.title("Technical SEO Audit")

    # Session state defaults
    if "ta_audit_result" not in st.session_state:
        st.session_state.ta_audit_result = None
    if "ta_running" not in st.session_state:
        st.session_state.ta_running = False

    tabs = st.tabs([
        "Run Audit",
        "Results",
        "Crawl Data",
        "Performance",
        "Security",
        "Recommendations",
        "Export",
    ])

    with tabs[0]:
        _tab_run_audit()
    with tabs[1]:
        _tab_results()
    with tabs[2]:
        _tab_crawl_data()
    with tabs[3]:
        _tab_performance()
    with tabs[4]:
        _tab_security()
    with tabs[5]:
        _tab_recommendations()
    with tabs[6]:
        _tab_export()


# ---------------------------------------------------------------------------
# Tab: Run Audit
# ---------------------------------------------------------------------------

def _tab_run_audit():
    st.header("Run Audit")
    st.markdown("Enter a domain or URL to start a comprehensive technical SEO audit.")

    col1, col2 = st.columns([3, 1])
    with col1:
        domain = st.text_input(
            "Domain / URL",
            placeholder="example.com or https://example.com",
            key="ta_domain_input",
        )
    with col2:
        max_pages = st.number_input("Max pages", min_value=5, max_value=500, value=50, step=10, key="ta_max_pages")

    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        check_speed = st.checkbox("Check PageSpeed (requires API key)", value=True, key="ta_check_speed")
    with opt_col2:
        check_security = st.checkbox("Check Security", value=True, key="ta_check_security")

    if st.button("Start Audit", type="primary", use_container_width=True, key="ta_run_btn"):
        if not domain:
            st.warning("Please enter a domain or URL.")
            return

        st.session_state.ta_running = True
        progress_bar = st.progress(0, text="Initialising audit...")
        status_area = st.empty()

        try:
            # Build clients
            llm_client = _get_llm_client()
            psi_client = _get_psi_client()

            from src.modules.technical_audit.auditor import TechnicalAuditor
            auditor = TechnicalAuditor(llm_client=llm_client, pagespeed_client=psi_client)

            progress_bar.progress(10, text="Starting crawl...")

            result = _run_async(
                auditor.run_full_audit(
                    domain=domain,
                    max_pages=max_pages,
                    check_speed=check_speed,
                    check_security=check_security,
                )
            )

            progress_bar.progress(100, text="Audit complete!")
            st.session_state.ta_audit_result = result
            st.session_state.ta_running = False

            grade = result.get("grade", "?")
            score = result.get("overall_score", 0)
            status_area.success(
                "Audit complete! Score: {score} | Grade: {grade}".format(
                    score=score, grade=grade,
                )
            )

        except Exception as exc:
            progress_bar.progress(100, text="Error")
            st.session_state.ta_running = False
            st.error("Audit failed: {err}".format(err=str(exc)))

    # Show quick summary if result exists
    result = st.session_state.ta_audit_result
    if result:
        st.markdown("---")
        st.subheader("Latest Audit Summary")
        _render_score_cards(result)


# ---------------------------------------------------------------------------
# Tab: Results
# ---------------------------------------------------------------------------

def _tab_results():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Audit Results")
    _render_score_cards(result)

    st.markdown("---")

    # Category score breakdown
    st.subheader("Category Scores")
    cat_scores = result.get("category_scores", {})
    for cat, score in cat_scores.items():
        label = cat.replace("_", " ").title()
        col1, col2 = st.columns([4, 1])
        with col1:
            st.progress(min(score / 100.0, 1.0), text=label)
        with col2:
            st.markdown(
                "<span style=\"font-size:1.2rem;font-weight:bold;color:{c};\">{s}</span>".format(
                    c=_score_color(score), s=score,
                ),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # Issues table
    st.subheader("Issues ({n})".format(n=len(result.get("issues", []))))
    issues = result.get("issues", [])
    if issues:
        severity_filter = st.multiselect(
            "Filter by severity",
            ["error", "warning", "info"],
            default=["error", "warning", "info"],
            key="ta_sev_filter",
        )
        filtered = [i for i in issues if i.get("severity") in severity_filter]

        for iss in filtered:
            sev = iss.get("severity", "info")
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(sev, "")
            with st.expander(
                "{icon} [{sev}] {desc}".format(
                    icon=icon,
                    sev=sev.upper(),
                    desc=iss.get("description", "")[:100],
                )
            ):
                st.markdown("**Category:** " + iss.get("category", "—"))
                st.markdown("**How to fix:** " + iss.get("how_to_fix", "—"))
                affected = iss.get("affected_url", "")
                if affected:
                    st.markdown("**Affected:** " + affected)
    else:
        st.success("No issues found!")

    # Passed checks
    st.markdown("---")
    st.subheader("Passed Checks")
    passed = result.get("passed_checks", [])
    if passed:
        for p in passed:
            st.markdown("✅ " + p)
    else:
        st.info("No passed checks recorded.")


# ---------------------------------------------------------------------------
# Tab: Crawl Data
# ---------------------------------------------------------------------------

def _tab_crawl_data():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Crawl Data")

    summary = result.get("crawl_summary", {})
    if summary:
        cols = st.columns(5)
        metrics = [
            ("Total Pages", summary.get("total_pages", 0)),
            ("2xx OK", summary.get("status_2xx", 0)),
            ("3xx Redirects", summary.get("status_3xx", 0)),
            ("4xx Errors", summary.get("status_4xx", 0)),
            ("5xx Errors", summary.get("status_5xx", 0)),
        ]
        for col, (label, val) in zip(cols, metrics):
            col.metric(label, val)

        cols2 = st.columns(4)
        metrics2 = [
            ("Avg Words", summary.get("avg_word_count", 0)),
            ("Internal Links", summary.get("total_internal_links", 0)),
            ("External Links", summary.get("total_external_links", 0)),
            ("Images", summary.get("total_images", 0)),
        ]
        for col, (label, val) in zip(cols2, metrics2):
            col.metric(label, val)

    st.markdown("---")

    # Pages table
    st.subheader("Pages Crawled")
    pages = result.get("pages", [])
    if pages:
        import pandas as pd
        rows = []
        for p in pages:
            rows.append({
                "URL": p.get("url", "")[:80],
                "Status": p.get("status_code", 0),
                "Title": (p.get("title", "") or "")[:60],
                "Words": p.get("word_count", 0),
                "Links (int)": len(p.get("internal_links", [])),
                "Links (ext)": len(p.get("external_links", [])),
                "Load (s)": p.get("load_time", 0),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Broken links
    st.markdown("---")
    st.subheader("Broken Links ({n})".format(n=len(result.get("broken_links", []))))
    broken = result.get("broken_links", [])
    if broken:
        import pandas as pd
        bl_rows = []
        for bl in broken:
            bl_rows.append({
                "Source Page": bl.get("source_page", "")[:60],
                "Broken URL": bl.get("broken_url", "")[:60],
                "Status": bl.get("status_code", 0),
                "Link Text": bl.get("link_text", "")[:40],
            })
        df_bl = pd.DataFrame(bl_rows)
        st.dataframe(df_bl, use_container_width=True, hide_index=True)
    else:
        st.success("No broken links found!")

    # Redirect chains
    st.markdown("---")
    st.subheader("Redirect Chains ({n})".format(n=len(result.get("redirect_chains", []))))
    redirects = result.get("redirect_chains", [])
    if redirects:
        for rc in redirects:
            chain_len = rc.get("chain_length", 0)
            is_loop = rc.get("is_loop", False)
            label = "Original: {url} ({n} hops{loop})".format(
                url=rc.get("original_url", "")[:60],
                n=chain_len,
                loop=" - LOOP!" if is_loop else "",
            )
            with st.expander(label):
                for step in rc.get("chain", []):
                    st.markdown(
                        "  {status} -> {to}".format(
                            status=step.get("status", "?"),
                            to=step.get("redirects_to", "?")[:80],
                        )
                    )
                st.markdown("**Final URL:** " + rc.get("final_url", "?"))
    else:
        st.success("No redirect chains found!")


# ---------------------------------------------------------------------------
# Tab: Performance
# ---------------------------------------------------------------------------

def _tab_performance():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Performance & Core Web Vitals")

    speed = result.get("speed_data", {})
    if speed.get("error"):
        st.warning("PageSpeed check encountered an error: " + speed.get("error", ""))
        return
    if not speed or (not speed.get("mobile") and not speed.get("desktop")):
        st.info("No performance data available. Enable PageSpeed check when running audit.")
        return

    # Mobile vs Desktop comparison
    mobile = speed.get("mobile", {})
    desktop = speed.get("desktop", {})

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Mobile")
        m_score = mobile.get("performance_score", 0)
        st.markdown(
            "<div style=\"text-align:center;padding:20px;\">" +
            "<div style=\"font-size:3rem;font-weight:bold;color:{c};\">{s}</div>".format(
                c=_score_color(m_score), s=m_score,
            ) +
            "<div>Performance Score</div></div>",
            unsafe_allow_html=True,
        )

    with col2:
        st.subheader("Desktop")
        d_score = desktop.get("performance_score", 0)
        st.markdown(
            "<div style=\"text-align:center;padding:20px;\">" +
            "<div style=\"font-size:3rem;font-weight:bold;color:{c};\">{s}</div>".format(
                c=_score_color(d_score), s=d_score,
            ) +
            "<div>Performance Score</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("Core Web Vitals")

    cwv_metrics = [
        ("LCP", "lcp", "ms", "Largest Contentful Paint"),
        ("FCP", "fcp", "ms", "First Contentful Paint"),
        ("CLS", "cls", "", "Cumulative Layout Shift"),
        ("TTFB", "ttfb", "ms", "Time to First Byte"),
        ("INP", "inp", "ms", "Interaction to Next Paint"),
        ("SI", "speed_index", "ms", "Speed Index"),
    ]

    cols = st.columns(3)
    for idx, (label, key, unit, full_name) in enumerate(cwv_metrics):
        col = cols[idx % 3]
        m_val = mobile.get(key)
        d_val = desktop.get(key)
        with col:
            st.markdown("**{name}** ({label})".format(name=full_name, label=label))
            mc = _cwv_color(key, m_val)
            dc = _cwv_color(key, d_val)
            m_display = "{v}{u}".format(v=round(m_val, 2) if m_val is not None else "—", u=unit if m_val is not None else "")
            d_display = "{v}{u}".format(v=round(d_val, 2) if d_val is not None else "—", u=unit if d_val is not None else "")
            st.markdown(
                "Mobile: <span style=\"color:{mc};font-weight:bold;\">{mv}</span> | "
                "Desktop: <span style=\"color:{dc};font-weight:bold;\">{dv}</span>".format(
                    mc=mc, mv=m_display, dc=dc, dv=d_display,
                ),
                unsafe_allow_html=True,
            )
            st.markdown("")

    # Opportunities
    opportunities = speed.get("opportunities", [])
    if opportunities:
        st.markdown("---")
        st.subheader("Optimization Opportunities")
        for opp in opportunities[:10]:
            savings = opp.get("savings_ms", 0)
            st.markdown(
                "- **{title}** — potential savings: {s}ms".format(
                    title=opp.get("title", ""),
                    s=round(savings),
                )
            )


# ---------------------------------------------------------------------------
# Tab: Security
# ---------------------------------------------------------------------------

def _tab_security():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Security Analysis")

    sec = result.get("security_data", {})
    if sec.get("error"):
        st.warning("Security check encountered an error: " + sec.get("error", ""))
        return
    if not sec:
        st.info("No security data available.")
        return

    # SSL Status
    st.subheader("SSL Certificate")
    col1, col2, col3 = st.columns(3)
    with col1:
        if sec.get("ssl_valid"):
            st.success("SSL Valid")
        else:
            st.error("SSL Invalid or Missing")
    with col2:
        expiry = sec.get("ssl_expiry", "Unknown")
        st.metric("Expires", str(expiry)[:20] if expiry else "Unknown")
    with col3:
        issuer = sec.get("ssl_issuer", "Unknown")
        st.metric("Issuer", str(issuer) if issuer else "Unknown")

    # HTTPS
    st.markdown("---")
    st.subheader("HTTPS Enforcement")
    if sec.get("https_enforced"):
        st.success("HTTP redirects to HTTPS")
    else:
        st.warning("HTTP does not redirect to HTTPS")

    # Security Headers
    st.markdown("---")
    st.subheader("Security Headers")
    headers = sec.get("security_headers", {})
    if headers:
        for hdr_name, hdr_info in headers.items():
            present = hdr_info.get("present", False)
            value = hdr_info.get("value", "")
            if present:
                st.markdown(
                    "- {icon} **{name}**: `{val}`".format(
                        icon="✅",
                        name=hdr_name,
                        val=value[:80] if value else "present",
                    )
                )
            else:
                st.markdown(
                    "- {icon} **{name}**: Missing".format(
                        icon="❌",
                        name=hdr_name,
                    )
                )
    else:
        st.info("No security header data.")

    # Mixed content
    st.markdown("---")
    st.subheader("Mixed Content")
    mixed = sec.get("mixed_content", [])
    if mixed:
        st.warning("{n} mixed content issues found".format(n=len(mixed)))
        for mc in mixed[:20]:
            st.markdown(
                "- `{tag}` loading: {url}".format(
                    tag=mc.get("tag", "?"),
                    url=mc.get("url", "")[:80],
                )
            )
    else:
        st.success("No mixed content detected!")

    # Issues
    sec_issues = [i for i in result.get("issues", []) if i.get("category") == "security"]
    if sec_issues:
        st.markdown("---")
        st.subheader("Security Issues")
        for iss in sec_issues:
            sev = iss.get("severity", "info")
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(sev, "")
            st.markdown(
                "{icon} **{desc}** — {fix}".format(
                    icon=icon,
                    desc=iss.get("description", ""),
                    fix=iss.get("how_to_fix", ""),
                )
            )


# ---------------------------------------------------------------------------
# Tab: Recommendations
# ---------------------------------------------------------------------------

def _tab_recommendations():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Recommendations")

    recs = result.get("recommendations", [])
    if not recs:
        st.info("No recommendations available.")
        return

    # Priority filter
    pri_options = sorted(set(r.get("priority", "P3") for r in recs))
    sel_pri = st.multiselect("Filter by priority", pri_options, default=pri_options, key="ta_rec_pri")
    filtered_recs = [r for r in recs if r.get("priority", "P3") in sel_pri]

    for rec in filtered_recs:
        pri = rec.get("priority", "P3")
        pri_color = {"P1": "#ef4444", "P2": "#f97316", "P3": "#3b82f6"}.get(pri, "#6b7280")
        title = rec.get("title", "Recommendation")
        with st.expander(
            "[{pri}] {title}".format(pri=pri, title=title)
        ):
            st.markdown(rec.get("description", ""))
            st.markdown("**Category:** " + str(rec.get("category", "—")))
            st.markdown("**Estimated Impact:** " + str(rec.get("estimated_impact", "—")))

            steps = rec.get("implementation_steps", [])
            if steps:
                st.markdown("**Implementation Steps:**")
                for i, step in enumerate(steps, 1):
                    st.markdown("{n}. {step}".format(n=i, step=step))

            urls = rec.get("affected_urls", [])
            if urls:
                st.markdown("**Affected URLs:**")
                for u in urls[:5]:
                    st.markdown("- " + str(u))


# ---------------------------------------------------------------------------
# Tab: Export
# ---------------------------------------------------------------------------

def _tab_export():
    result = st.session_state.ta_audit_result
    if not result:
        st.info("No audit results yet. Run an audit first.")
        return

    st.header("Export Audit Report")

    st.markdown(
        "Generate a professional PDF report with narrative analysis, "
        "charts, score visualizations, and actionable recommendations."
    )

    fmt = st.selectbox("Format", ["PDF", "HTML", "JSON"], key="ta_export_fmt")

    domain_slug = result.get("domain", "site").replace(".", "_").replace("/", "")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext_map = {"PDF": "pdf", "HTML": "html", "JSON": "json"}
    ext = ext_map.get(fmt, "pdf")
    default_name = "audit_{d}_{t}.{e}".format(d=domain_slug, t=ts, e=ext)

    filename = st.text_input("Filename", value=default_name, key="ta_export_name")

    if st.button("Export Report", type="primary", key="ta_export_btn"):
        try:
            filepath = str(EXPORT_DIR / filename)
            os.makedirs(str(EXPORT_DIR), exist_ok=True)

            if fmt == "PDF":
                from dashboard.export_helper import generate_technical_audit_pdf
                filepath = generate_technical_audit_pdf(result, filepath)
                st.success("PDF report generated: " + filepath)
                with open(filepath, "rb") as fh:
                    pdf_data = fh.read()
                st.download_button(
                    label="Download PDF Report",
                    data=pdf_data,
                    file_name=filename,
                    mime="application/pdf",
                    key="ta_download_btn",
                )
            elif fmt == "HTML":
                from src.modules.technical_audit.auditor import TechnicalAuditor
                auditor = TechnicalAuditor()
                auditor.export_audit_report(audit_data=result, filepath=filepath, fmt="html")
                st.success("HTML report exported: " + filepath)
                with open(filepath, "r", encoding="utf-8") as fh:
                    html_content = fh.read()
                st.download_button(
                    label="Download HTML Report",
                    data=html_content,
                    file_name=filename,
                    mime="text/html",
                    key="ta_download_btn",
                )
            else:
                from src.modules.technical_audit.auditor import TechnicalAuditor
                auditor = TechnicalAuditor()
                auditor.export_audit_report(audit_data=result, filepath=filepath, fmt="json")
                st.success("JSON report exported: " + filepath)
                with open(filepath, "r", encoding="utf-8") as fh:
                    json_content = fh.read()
                st.download_button(
                    label="Download JSON Report",
                    data=json_content,
                    file_name=filename,
                    mime="application/json",
                    key="ta_download_btn",
                )
        except Exception as exc:
            st.error("Export failed: " + str(exc))
            import traceback
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Score cards helper
# ---------------------------------------------------------------------------

def _render_score_cards(result: dict):
    """Render the top-level score summary cards."""
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        grade = result.get("grade", "?")
        st.markdown(_grade_badge(grade), unsafe_allow_html=True)
        st.caption("Grade")
    with col2:
        score = result.get("overall_score", 0)
        st.metric("Overall Score", score)
    with col3:
        summary = result.get("crawl_summary", {})
        st.metric("Pages Crawled", summary.get("total_pages", 0))
    with col4:
        issues = result.get("issues", [])
        errors = len([i for i in issues if i.get("severity") == "error"])
        warnings = len([i for i in issues if i.get("severity") == "warning"])
        st.metric("Issues", "{e} errors / {w} warnings".format(e=errors, w=warnings))


# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------

def _get_llm_client():
    """Try to build an LLMClient from env."""
    try:
        from src.integrations.llm_client import LLMClient
        client = LLMClient()
        return client
    except Exception:
        return None


def _get_psi_client():
    """Try to build a PageSpeedInsights client from env."""
    try:
        from src.integrations.google_pagespeed import PageSpeedInsights
        client = PageSpeedInsights()
        return client
    except Exception:
        return None
