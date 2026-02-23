"""Local SEO Analyzer - Streamlit Dashboard Page.

Comprehensive local SEO analysis for SERP #1 and Map Pack Top 3.
Provides business profile input, analysis execution, results visualization,
report downloads, and audit history.
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.database import get_session
from src.models.local_seo import LocalBusinessProfile, LocalSEOAudit
from src.modules.local_seo.analyzer import LocalSEOAnalyzer
from src.modules.local_seo.report_generator import LocalSEOReportGenerator


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    """Return CSS color string based on score threshold."""
    if score >= 70:
        return "green"
    if score >= 40:
        return "orange"
    return "red"


def _severity_badge(severity: str) -> str:
    """Return an HTML badge for issue severity."""
    colors = {
        "critical": "#ef4444",
        "high": "#f97316",
        "medium": "#eab308",
        "low": "#3b82f6",
        "info": "#6b7280",
    }
    bg = colors.get(severity.lower(), "#6b7280")
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:600;">'
        f'{severity.upper()}</span>'
    )


def _priority_badge(priority: str) -> str:
    """Return an HTML badge for recommendation priority."""
    colors = {"P1": "#ef4444", "P2": "#f97316", "P3": "#3b82f6"}
    bg = colors.get(priority, "#6b7280")
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:600;">'
        f'{priority}</span>'
    )


def _impact_badge(impact: str) -> str:
    """Return an HTML badge for impact level."""
    colors = {"high": "#16a34a", "medium": "#eab308", "low": "#6b7280"}
    bg = colors.get(impact.lower(), "#6b7280")
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;">'
        f'Impact: {impact.title()}</span>'
    )


def _effort_badge(effort: str) -> str:
    """Return an HTML badge for effort level."""
    colors = {"low": "#16a34a", "medium": "#eab308", "high": "#ef4444"}
    bg = colors.get(effort.lower(), "#6b7280")
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;">'
        f'Effort: {effort.title()}</span>'
    )


def _status_icon(status: Any) -> str:
    """Return emoji icon for boolean or string status values."""
    if isinstance(status, bool):
        return "\u2705" if status else "\u274c"
    s = str(status).lower()
    if s in ("pass", "passed", "found", "true", "yes", "ok", "good"):
        return "\u2705"
    if s in ("warning", "partial", "needs_improvement"):
        return "\u26a0\ufe0f"
    return "\u274c"


def _safe_get(data: Dict, *keys, default=None):
    """Safely traverse nested dictionary keys."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------

def _render_overview_tab(results: Dict) -> None:
    """Render the Overview tab with scores and top issues."""
    scores = results.get("scores", {})
    overall = scores.get("overall_score", 0)

    # Overall score hero
    color = _score_color(overall)
    st.markdown(
        f'<div style="text-align:center;padding:20px;">'
        f'<h1 style="color:{color};font-size:3.5em;margin:0;">{overall:.0f}/100</h1>'
        f'<p style="color:#64748b;font-size:1.1em;">Overall Local SEO Score</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # Score cards in 3x2 grid
    score_items = [
        ("On-Page", scores.get("on_page_score", 0)),
        ("Google Business", scores.get("gbp_score", 0)),
        ("Citations", scores.get("citation_score", 0)),
        ("Reviews", scores.get("review_score", 0)),
        ("Content", scores.get("content_score", 0)),
        ("Backlinks", scores.get("backlink_score", 0)),
    ]

    for row_start in range(0, 6, 3):
        cols = st.columns(3)
        for idx, col in enumerate(cols):
            item_idx = row_start + idx
            if item_idx < len(score_items):
                label, score = score_items[item_idx]
                with col:
                    st.metric(label=label, value=f"{score:.0f}")
                    st.progress(min(score / 100.0, 1.0))

    # Top issues
    issues = results.get("issues", [])
    if issues:
        st.divider()
        st.subheader("\U0001f6a8 Top Issues")
        critical_high = [
            i for i in issues
            if i.get("severity", "").lower() in ("critical", "high")
        ]
        display_issues = critical_high[:10] if critical_high else issues[:10]
        for issue in display_issues:
            severity = issue.get("severity", "info")
            title = issue.get("title", issue.get("message", "Unknown issue"))
            desc = issue.get("description", "")
            line = f"{_severity_badge(severity)} **{title}**"
            if desc:
                line += f" \u2014 {desc}"
            st.markdown(line, unsafe_allow_html=True)


def _render_onpage_tab(results: Dict) -> None:
    """Render the On-Page Local SEO tab."""
    on_page = results.get("on_page_results", {})
    score = _safe_get(results, "scores", "on_page_score", default=0)

    st.metric("On-Page Local SEO Score", f"{score:.0f}/100")
    st.progress(min(score / 100.0, 1.0))
    st.divider()

    checks = on_page.get("checks", on_page.get("signals", []))

    # Build checks list from dict keys if not already a list
    if not checks and isinstance(on_page, dict):
        checks = []
        for key, val in on_page.items():
            if key in ("score", "checks", "signals"):
                continue
            if isinstance(val, dict):
                checks.append({
                    "check": val.get("label", key.replace("_", " ").title()),
                    "status": val.get("status", val.get("found", False)),
                    "details": val.get("details", val.get("message", "")),
                    "category": val.get("category", "General"),
                })
            else:
                checks.append({
                    "check": key.replace("_", " ").title(),
                    "status": val,
                    "details": "",
                    "category": "General",
                })

    if checks:
        categories = sorted({c.get("category", "General") for c in checks})
        categories.insert(0, "All")
        selected_cat = st.selectbox("Filter by Category", categories, key="onpage_cat")

        filtered = (
            checks if selected_cat == "All"
            else [c for c in checks if c.get("category", "General") == selected_cat]
        )

        rows = []
        for c in filtered:
            rows.append({
                "Check": c.get("check", c.get("label", "")),
                "Status": _status_icon(c.get("status", False)),
                "Details": str(c.get("details", "")),
                "Category": c.get("category", "General"),
            })
        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No on-page check data available.")


def _render_gbp_tab(results: Dict) -> None:
    """Render the Google Business Profile tab."""
    gbp = results.get("gbp_results", {})
    score = _safe_get(results, "scores", "gbp_score", default=0)

    st.metric("GBP Score", f"{score:.0f}/100")
    st.progress(min(score / 100.0, 1.0))
    st.divider()

    listing = gbp.get("listing", gbp)
    found = listing.get("found", listing.get("claimed", None))

    if found is not None:
        if found:
            st.success("\u2705 Google Business Profile listing found")
        else:
            st.error("\u274c Google Business Profile listing NOT found")
            st.markdown(
                "**Action:** Claim or create your Google Business Profile at "
                "[business.google.com](https://business.google.com)"
            )
            return

    # Listing summary metrics
    c1, c2, c3 = st.columns(3)
    with c1:
        rating = listing.get("rating", listing.get("average_rating", "N/A"))
        st.metric("Rating", f"\u2b50 {rating}")
    with c2:
        reviews = listing.get("review_count", listing.get("reviews", "N/A"))
        st.metric("Reviews", reviews)
    with c3:
        cats = listing.get("categories", listing.get("category", []))
        if isinstance(cats, list):
            st.metric("Categories", len(cats))
        else:
            st.metric("Category", str(cats)[:30])

    st.divider()
    st.subheader("Optimization Checklist")

    checklist = gbp.get("checklist", gbp.get("optimization", []))
    if isinstance(checklist, list):
        for item in checklist:
            label = item.get("label", item.get("name", "Check"))
            status = item.get("status", item.get("complete", False))
            action = item.get("action", item.get("recommendation", ""))
            with st.expander(f"{_status_icon(status)} {label}"):
                if action:
                    st.markdown(f"**Action needed:** {action}")
                else:
                    st.markdown("\u2705 Looks good!")
    elif isinstance(checklist, dict):
        for key, val in checklist.items():
            label = key.replace("_", " ").title()
            if isinstance(val, dict):
                status = val.get("status", val.get("complete", False))
                action = val.get("action", val.get("recommendation", ""))
            else:
                status = val
                action = ""
            with st.expander(f"{_status_icon(status)} {label}"):
                if action:
                    st.markdown(f"**Action needed:** {action}")
                else:
                    msg = "No additional action required." if status else "Needs attention."
                    st.markdown(msg)
    else:
        st.info("No GBP optimization checklist data available.")


def _render_citations_tab(results: Dict) -> None:
    """Render the Citations tab."""
    citations = results.get("citation_results", {})
    score = _safe_get(results, "scores", "citation_score", default=0)

    directories = citations.get("directories", citations.get("citations", []))
    total = len(directories) if isinstance(directories, list) else 0
    found_count = (
        sum(1 for d in directories if d.get("found", False))
        if isinstance(directories, list)
        else 0
    )
    nap_pct = citations.get("nap_consistency", 0)
    if isinstance(nap_pct, (int, float)) and nap_pct <= 1:
        nap_pct *= 100

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Directories Found", f"{found_count}/{total}")
    with c2:
        st.metric("NAP Consistency", f"{nap_pct:.0f}%")
    with c3:
        st.metric("Citation Score", f"{score:.0f}/100")

    st.divider()

    if isinstance(directories, list) and directories:
        rows = []
        for d in directories:
            name = d.get("name", d.get("directory", "Unknown"))
            is_found = d.get("found", False)
            nap_ok = d.get("nap_consistent", d.get("consistent", False))
            authority = d.get("authority", d.get("da", "N/A"))

            if is_found and nap_ok:
                status_str = "\u2705 Found & Consistent"
            elif is_found:
                status_str = "\u26a0\ufe0f Found, Inconsistent"
            else:
                status_str = "\u274c Not Found"

            rows.append({
                "Directory": name,
                "Status": status_str,
                "NAP Consistent": "\u2705" if nap_ok else "\u274c",
                "Authority": str(authority),
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No citation data available.")


def _render_reviews_tab(results: Dict) -> None:
    """Render the Reviews tab."""
    reviews = results.get("review_results", {})
    score = _safe_get(results, "scores", "review_score", default=0)

    st.metric("Review Score", f"{score:.0f}/100")
    st.progress(min(score / 100.0, 1.0))
    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        total = reviews.get("total_reviews", reviews.get("count", "N/A"))
        st.metric("Total Reviews", total)
    with c2:
        avg = reviews.get("average_rating", reviews.get("rating", "N/A"))
        st.metric("Average Rating", f"\u2b50 {avg}")
    with c3:
        comp_avg = reviews.get(
            "competitor_average", reviews.get("competitor_avg_rating", "N/A")
        )
        st.metric("Competitor Avg", f"\u2b50 {comp_avg}")

    # Review gap analysis
    gap = reviews.get("gap_analysis", reviews.get("review_gap", {}))
    if gap:
        st.divider()
        st.subheader("\U0001f4ca Review Gap Analysis")
        if isinstance(gap, dict):
            gap_data = []
            for comp, data in gap.items():
                if isinstance(data, dict):
                    gap_data.append({
                        "Competitor": comp,
                        "Reviews": data.get("reviews", data.get("count", "N/A")),
                        "Rating": data.get("rating", "N/A"),
                        "Gap": data.get("gap", "N/A"),
                    })
            if gap_data:
                st.dataframe(
                    pd.DataFrame(gap_data),
                    use_container_width=True,
                    hide_index=True,
                )
        elif isinstance(gap, str):
            st.markdown(gap)

    # Recommendations
    recs = reviews.get("recommendations", [])
    if recs:
        st.divider()
        st.subheader("\U0001f4a1 Review Improvement Recommendations")
        if isinstance(recs, list):
            for r in recs:
                if isinstance(r, dict):
                    title = r.get("title", r.get("action", ""))
                    desc = r.get("description", "")
                    st.markdown(f"- **{title}**: {desc}")
                else:
                    st.markdown(f"- {r}")
        elif isinstance(recs, str):
            st.markdown(recs)


def _render_competitors_tab(results: Dict) -> None:
    """Render the Competitors tab."""
    competitors = results.get("competitor_results", {})
    business_info = results.get("business_info", {})
    our_name = business_info.get("business_name", "").lower()

    map_pack = competitors.get("map_pack", competitors.get("map_pack_results", []))

    if isinstance(map_pack, list) and map_pack:
        st.subheader("\U0001f5fa Map Pack Results")
        rows = []
        our_position: Optional[int] = None
        for idx, entry in enumerate(map_pack):
            name = entry.get("name", entry.get("title", f"Result {idx + 1}"))
            pos = entry.get("position", idx + 1)
            rating = entry.get("rating", "N/A")
            rev_count = entry.get("reviews", entry.get("review_count", "N/A"))
            is_ours = name.lower() == our_name or entry.get("is_target", False)
            if is_ours:
                our_position = pos
            rows.append({
                "Position": pos,
                "Business": f"\U0001f3af {name}" if is_ours else name,
                "Rating": f"\u2b50 {rating}",
                "Reviews": rev_count,
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

        if our_position is not None:
            st.success(
                f"\U0001f3af Your business is at position **#{our_position}** "
                "in the Map Pack"
            )
        else:
            st.warning("\u26a0\ufe0f Your business was not found in the Map Pack")
    else:
        st.info("No map pack competitor data available.")

    # Gap analysis metrics
    gap_metrics = competitors.get("gap_analysis", {})
    if gap_metrics and isinstance(gap_metrics, dict):
        st.divider()
        st.subheader("\U0001f4ca Gap Analysis")
        num_cols = min(len(gap_metrics), 4)
        if num_cols > 0:
            cols = st.columns(num_cols)
            for idx, (metric, value) in enumerate(gap_metrics.items()):
                with cols[idx % num_cols]:
                    label = metric.replace("_", " ").title()
                    st.metric(label, str(value))


def _render_recommendations_tab(results: Dict) -> None:
    """Render the Recommendations tab with filters and grouping."""
    recs = results.get("recommendations", [])
    if not recs:
        st.info("No recommendations available.")
        return

    if not isinstance(recs, list):
        st.markdown(str(recs))
        return

    # Only process dict-type recommendations
    dict_recs = [r for r in recs if isinstance(r, dict)]
    if not dict_recs:
        for r in recs:
            st.markdown(f"- {r}")
        return

    # Gather filter options
    all_categories = sorted({r.get("category", "General") for r in dict_recs})
    all_impacts = sorted({r.get("impact", "medium").lower() for r in dict_recs})
    all_efforts = sorted({r.get("effort", "medium").lower() for r in dict_recs})

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_cat = st.selectbox(
            "Category", ["All"] + all_categories, key="rec_cat"
        )
    with c2:
        sel_impact = st.selectbox(
            "Impact", ["All"] + [i.title() for i in all_impacts], key="rec_impact"
        )
    with c3:
        sel_effort = st.selectbox(
            "Effort", ["All"] + [e.title() for e in all_efforts], key="rec_effort"
        )

    filtered: List[Dict] = []
    for r in dict_recs:
        if sel_cat != "All" and r.get("category", "General") != sel_cat:
            continue
        if sel_impact != "All" and r.get("impact", "medium").lower() != sel_impact.lower():
            continue
        if sel_effort != "All" and r.get("effort", "medium").lower() != sel_effort.lower():
            continue
        filtered.append(r)

    # Group: Quick Wins, High Impact, Long Term
    quick_wins = [
        r for r in filtered
        if r.get("effort", "").lower() == "low"
        and r.get("impact", "").lower() == "high"
    ]
    high_impact = [
        r for r in filtered
        if r.get("impact", "").lower() == "high" and r not in quick_wins
    ]
    long_term = [
        r for r in filtered if r not in quick_wins and r not in high_impact
    ]

    sections = [
        ("\u26a1 Quick Wins", quick_wins),
        ("\U0001f680 High Impact", high_impact),
        ("\U0001f4c5 Long Term", long_term),
    ]

    for section_title, items in sections:
        if not items:
            continue
        st.subheader(section_title)
        for r in items:
            title = r.get("title", r.get("action", "Recommendation"))
            priority = r.get("priority", "P3")
            impact = r.get("impact", "medium")
            effort = r.get("effort", "medium")
            desc = r.get("description", r.get("details", ""))
            est_time = r.get("estimated_time", r.get("time_estimate", ""))

            with st.expander(f"**{title}**"):
                st.markdown(
                    f"{_priority_badge(priority)} "
                    f"{_impact_badge(impact)} "
                    f"{_effort_badge(effort)}",
                    unsafe_allow_html=True,
                )
                if desc:
                    st.markdown(desc)
                if est_time:
                    st.markdown(f"\u23f1 **Estimated time:** {est_time}")


# ---------------------------------------------------------------------------
# Report downloads
# ---------------------------------------------------------------------------

def _render_report_downloads(results: Dict) -> None:
    """Render HTML and JSON report download buttons."""
    st.divider()
    st.subheader("\U0001f4e5 Download Reports")

    try:
        generator = LocalSEOReportGenerator()
    except Exception:
        generator = None

    domain = _safe_get(results, "business_info", "domain", default="local_seo")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    c1, c2 = st.columns(2)

    with c1:
        if generator:
            try:
                html_report = generator.generate_html_report(results)
                st.download_button(
                    label="\U0001f4c4 Download HTML Report",
                    data=html_report,
                    file_name=f"local_seo_report_{domain}_{ts}.html",
                    mime="text/html",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Failed to generate HTML report: {e}")
        else:
            st.warning("Report generator unavailable.")

    with c2:
        if generator:
            try:
                json_report = generator.generate_json_report(results)
                st.download_button(
                    label="\U0001f4ca Download JSON Report",
                    data=json_report,
                    file_name=f"local_seo_report_{domain}_{ts}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Failed to generate JSON report: {e}")
        else:
            st.warning("Report generator unavailable.")


# ---------------------------------------------------------------------------
# Audit history
# ---------------------------------------------------------------------------

def _render_audit_history() -> None:
    """Render past audits from database with option to reload."""
    with st.expander("\U0001f4dc Past Audits"):
        try:
            with get_session() as session:
                audits = (
                    session.query(LocalSEOAudit)
                    .order_by(LocalSEOAudit.created_at.desc())
                    .limit(20)
                    .all()
                )

                if not audits:
                    st.info("No past audits found.")
                    return

                rows = []
                audit_map: Dict[str, int] = {}
                for audit in audits:
                    profile = None
                    if audit.business_profile_id:
                        profile = session.query(LocalBusinessProfile).get(
                            audit.business_profile_id
                        )
                    domain_val = profile.domain if profile else "N/A"
                    name = profile.business_name if profile else "N/A"
                    created = (
                        audit.created_at.strftime("%Y-%m-%d %H:%M")
                        if audit.created_at
                        else "N/A"
                    )
                    overall = (
                        f"{audit.overall_score:.0f}"
                        if audit.overall_score is not None
                        else "N/A"
                    )
                    rows.append({
                        "Date": created,
                        "Business": name,
                        "Domain": domain_val,
                        "Overall Score": overall,
                    })
                    audit_map[created] = audit.id

                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )

                selected = st.selectbox(
                    "Load a past audit",
                    ["Select..."] + list(audit_map.keys()),
                    key="past_audit_select",
                )
                if selected != "Select...":
                    audit_id = audit_map[selected]
                    audit_obj = session.query(LocalSEOAudit).get(audit_id)
                    if audit_obj and audit_obj.results_json:
                        try:
                            past_results = json.loads(audit_obj.results_json)
                            st.session_state.local_seo_results = past_results
                            st.success(f"Loaded audit from {selected}")
                            st.rerun()
                        except json.JSONDecodeError:
                            st.error("Failed to parse stored audit results.")
                    else:
                        st.warning("No detailed results stored for this audit.")

        except Exception as e:
            st.error(f"Failed to load audit history: {e}")


# ---------------------------------------------------------------------------
# Main page entry point
# ---------------------------------------------------------------------------

def render_local_seo_page() -> None:
    """Render the complete Local SEO Analyzer page.

    Main entry point called from ``dashboard/app.py``.  Provides business
    profile input, analysis execution, tabbed results visualization,
    report downloads, and audit history.
    """
    st.title("\U0001f4cd Local SEO Analyzer")
    st.markdown(
        "Comprehensive local SEO analysis for **SERP #1** and **Map Pack Top 3**"
    )

    # ------------------------------------------------------------------ #
    # Business Profile Input Form                                         #
    # ------------------------------------------------------------------ #
    with st.form("local_seo_form", clear_on_submit=False):
        st.subheader("\U0001f3e2 Business Profile")

        left, right = st.columns(2)
        with left:
            business_name = st.text_input("Business Name *", key="lseo_name")
            location = st.text_input(
                "Location *", placeholder="Denver, CO", key="lseo_location"
            )
            phone = st.text_input("Phone", key="lseo_phone")
        with right:
            domain = st.text_input(
                "Domain *", placeholder="example.com", key="lseo_domain"
            )
            gbp_url = st.text_input(
                "Google Business Profile URL",
                placeholder="Google Business Profile URL",
                key="lseo_gbp",
            )
            address = st.text_input("Address", key="lseo_address")

        target_keywords = st.text_area(
            "Target Keywords",
            placeholder="One keyword per line",
            key="lseo_keywords",
        )

        submitted = st.form_submit_button(
            "\U0001f50d Analyze Local SEO", use_container_width=True
        )

    # ------------------------------------------------------------------ #
    # Analysis Execution                                                  #
    # ------------------------------------------------------------------ #
    if submitted:
        if not business_name or not domain or not location:
            st.error(
                "\u274c Please fill in all required fields: "
                "Business Name, Domain, and Location."
            )
        else:
            keywords: List[str] = []
            if target_keywords and target_keywords.strip():
                keywords = [
                    kw.strip()
                    for kw in target_keywords.strip().splitlines()
                    if kw.strip()
                ]

            try:
                with st.spinner(
                    "\U0001f50d Analyzing local SEO... This may take a few minutes."
                ):
                    progress = st.progress(0, text="Initializing analyzer...")

                    analyzer = LocalSEOAnalyzer()
                    progress.progress(10, text="Running analysis...")

                    loop = asyncio.new_event_loop()
                    try:
                        analysis_results = loop.run_until_complete(
                            analyzer.analyze_business(
                                domain=domain,
                                business_name=business_name,
                                location=location,
                                target_keywords=keywords,
                            )
                        )
                    finally:
                        loop.close()

                    progress.progress(90, text="Processing results...")

                    # Ensure business_info is populated
                    if "business_info" not in analysis_results:
                        analysis_results["business_info"] = {}
                    analysis_results["business_info"].update({
                        "business_name": business_name,
                        "domain": domain,
                        "location": location,
                        "gbp_url": gbp_url,
                        "phone": phone,
                        "address": address,
                    })

                    st.session_state.local_seo_results = analysis_results
                    progress.progress(100, text="Analysis complete!")
                    st.success("\u2705 Local SEO analysis complete!")

            except Exception as e:
                st.error(f"\u274c Analysis failed: {e}")
                with st.expander("Error Details"):
                    st.code(traceback.format_exc())

    # ------------------------------------------------------------------ #
    # Results Display                                                     #
    # ------------------------------------------------------------------ #
    results = st.session_state.get("local_seo_results")
    if results:
        st.divider()

    # --- PDF Report Download ---
    with st.expander("📄 Download PDF Report", expanded=False):
        st.markdown("Generate a professional narrative PDF report of your local SEO analysis.")
        if st.button("Generate PDF Report", type="primary", key="ls_pdf_btn"):
            try:
                from dashboard.export_helper import generate_local_seo_pdf
                local_data = {
                    "domain": st.session_state.get("ls_domain", ""),
                    "overall_score": st.session_state.get("ls_overall_score", 0),
                    "gmb_analysis": st.session_state.get("ls_gmb_data", {}),
                    "citations": st.session_state.get("ls_citations", {}),
                    "reviews": st.session_state.get("ls_reviews", {}),
                }
                pdf_path = generate_local_seo_pdf(local_data)
                with open(pdf_path, "rb") as fh:
                    st.download_button("⬇️ Download PDF", fh.read(),
                        file_name=pdf_path.split("/")[-1], mime="application/pdf", key="ls_pdf_dl")
                st.success("PDF report generated!")
            except Exception as exc:
                st.error("PDF generation failed: " + str(exc))

        tabs = st.tabs([
            "\U0001f4ca Overview",
            "\U0001f310 On-Page Local SEO",
            "\U0001f4cd Google Business Profile",
            "\U0001f4cb Citations",
            "\u2b50 Reviews",
            "\U0001f3c6 Competitors",
            "\U0001f3af Recommendations",
        ])

        with tabs[0]:
            _render_overview_tab(results)
        with tabs[1]:
            _render_onpage_tab(results)
        with tabs[2]:
            _render_gbp_tab(results)
        with tabs[3]:
            _render_citations_tab(results)
        with tabs[4]:
            _render_reviews_tab(results)
        with tabs[5]:
            _render_competitors_tab(results)
        with tabs[6]:
            _render_recommendations_tab(results)

        # Report downloads
        _render_report_downloads(results)

    # ------------------------------------------------------------------ #
    # Audit History                                                       #
    # ------------------------------------------------------------------ #
    _render_audit_history()
