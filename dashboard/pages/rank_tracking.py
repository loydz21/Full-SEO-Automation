"""Rank Tracking — Streamlit dashboard page."""

import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_tracker():
    """Lazy-initialize RankTracker in session state."""
    if "rank_tracker" not in st.session_state:
        from src.modules.rank_tracker.tracker import RankTracker
        st.session_state.rank_tracker = RankTracker()
    return st.session_state.rank_tracker


def _get_analyzer():
    """Lazy-initialize SERPAnalyzer in session state."""
    if "serp_analyzer" not in st.session_state:
        from src.modules.rank_tracker.serp_analyzer import SERPAnalyzer
        st.session_state.serp_analyzer = SERPAnalyzer()
    return st.session_state.serp_analyzer


def render_rank_tracking_page():
    """Main entry point for the Rank Tracking dashboard page."""
    st.title("📈 Rank Tracking")
    st.markdown("Track keyword rankings, analyze SERP features, and monitor competitors.")

    tabs = st.tabs([
        "📊 Overview",
        "📈 Track Rankings",
        "📉 History",
        "🎯 Opportunities",
        "🏆 Competitors",
        "🔍 SERP Features",
        "📥 Export",
    ])

    with tabs[0]:
        _render_overview_tab()
    with tabs[1]:
        _render_track_tab()
    with tabs[2]:
        _render_history_tab()
    with tabs[3]:
        _render_opportunities_tab()
    with tabs[4]:
        _render_competitors_tab()
    with tabs[5]:
        _render_serp_features_tab()
    with tabs[6]:
        _render_export_tab()


# ------------------------------------------------------------------
# Tab: Overview
# ------------------------------------------------------------------

def _render_overview_tab():
    """Domain overview with visibility score and position distribution."""
    st.subheader("📊 Domain Overview")

    domain = st.text_input(
        "Enter your domain",
        key="overview_domain",
        placeholder="example.com",
    )

    if not domain:
        st.info("Enter a domain above to see your ranking overview.")
        return

    if st.button("Calculate Visibility", key="btn_visibility"):
        tracker = _get_tracker()
        with st.spinner("Calculating visibility score..."):
            vis = tracker.calculate_visibility_score(domain)
            st.session_state["visibility_data"] = vis

    vis = st.session_state.get("visibility_data")
    if not vis:
        return

    # Score cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Visibility Score", str(vis.get("score", 0)) + "/100")
    with col2:
        st.metric("Keywords Tracked", vis.get("keyword_count", 0))
    with col3:
        st.metric("Avg Position", vis.get("avg_position", "-"))
    with col4:
        st.metric("Top 10 Keywords", vis.get("top10_count", 0))

    # Position distribution chart
    st.markdown("#### Position Distribution")
    top3 = vis.get("top3_count", 0)
    top10 = vis.get("top10_count", 0) - top3
    top20 = vis.get("top20_count", 0) - vis.get("top10_count", 0)
    beyond = vis.get("keyword_count", 0) - vis.get("top20_count", 0)

    dist_df = pd.DataFrame({
        "Range": ["Top 3", "4-10", "11-20", "20+"],
        "Keywords": [top3, top10, top20, beyond],
    })
    st.bar_chart(dist_df.set_index("Range"))

    # Recent changes
    st.markdown("#### Recent Ranking Changes")
    tracker = _get_tracker()
    changes = tracker.detect_ranking_changes(domain, threshold=3)
    if changes:
        changes_df = pd.DataFrame(changes)
        st.dataframe(changes_df, use_container_width=True)
    else:
        st.info("No significant ranking changes detected.")


# ------------------------------------------------------------------
# Tab: Track Rankings
# ------------------------------------------------------------------

def _render_track_tab():
    """Add and track keyword rankings."""
    st.subheader("📈 Track Keywords")

    col1, col2 = st.columns([2, 1])
    with col1:
        domain = st.text_input(
            "Domain to track",
            key="track_domain",
            placeholder="example.com",
        )
    with col2:
        location = st.selectbox(
            "Location",
            ["us", "gb", "ca", "au", "de", "fr", "es", "it", "br", "in"],
            key="track_location",
        )

    keywords_text = st.text_area(
        "Keywords (one per line)",
        key="track_keywords",
        height=150,
        placeholder="best seo tools\nkeyword research\nlink building strategies",
    )

    if not domain or not keywords_text.strip():
        st.info("Enter a domain and keywords to start tracking.")
        return

    keywords = [kw.strip() for kw in keywords_text.strip().split("\n") if kw.strip()]
    st.caption("Keywords to track: " + str(len(keywords)))

    if st.button("🚀 Start Tracking", key="btn_track", type="primary"):
        tracker = _get_tracker()
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.empty()

        all_results = []

        for idx, kw in enumerate(keywords):
            pct = int((idx + 1) / len(keywords) * 100)
            status_text.text("Tracking: " + kw + " (" + str(idx + 1) + "/" + str(len(keywords)) + ")")
            progress_bar.progress(pct)

            result = _run_async(tracker.track_keyword(domain, kw, location=location))
            all_results.append(result)

        progress_bar.progress(100)
        status_text.text("Tracking complete!")
        st.session_state["tracking_results"] = all_results

    results = st.session_state.get("tracking_results", [])
    if results:
        st.markdown("#### Results")
        rows = []
        for r in results:
            pos = r.get("position", 0)
            pos_display = str(pos) if pos > 0 else "Not Found"
            change_val = ""
            rows.append({
                "Keyword": r.get("keyword", ""),
                "Position": pos_display,
                "URL Ranked": r.get("url_ranked", "-") or "-",
                "Featured Snippet": "Yes" if r.get("serp_features", {}).get("featured_snippet") else "No",
                "Competitors in Top 10": len(r.get("competitors_in_top10", [])),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)


# ------------------------------------------------------------------
# Tab: History
# ------------------------------------------------------------------

def _render_history_tab():
    """Position history chart with keyword selector."""
    st.subheader("📉 Ranking History")

    col1, col2, col3 = st.columns(3)
    with col1:
        domain = st.text_input(
            "Domain", key="history_domain", placeholder="example.com"
        )
    with col2:
        keyword = st.text_input(
            "Keyword", key="history_keyword", placeholder="seo tools"
        )
    with col3:
        days = st.slider("Days", min_value=7, max_value=90, value=30, key="history_days")

    if not domain or not keyword:
        st.info("Enter a domain and keyword to view ranking history.")
        return

    if st.button("Load History", key="btn_history"):
        tracker = _get_tracker()
        history = tracker.get_ranking_history(domain, keyword, days=days)
        st.session_state["ranking_history"] = history
        st.session_state["history_kw"] = keyword

    history = st.session_state.get("ranking_history", [])
    if not history:
        st.info("No history data available. Track keywords first.")
        return

    kw_label = st.session_state.get("history_kw", keyword)
    st.markdown("#### Position Over Time: " + kw_label)

    hist_df = pd.DataFrame(history)
    if "date" in hist_df.columns and "position" in hist_df.columns:
        hist_df["date"] = pd.to_datetime(hist_df["date"])
        chart_df = hist_df.set_index("date")[["position"]]
        # Invert axis: lower position = better (1 is top)
        st.line_chart(chart_df)
        st.caption("Note: Lower position is better (1 = top of Google).")

        # Show change deltas
        if "change" in hist_df.columns:
            st.markdown("#### Position Changes")
            st.dataframe(
                hist_df[["date", "position", "change"]],
                use_container_width=True,
            )


# ------------------------------------------------------------------
# Tab: Opportunities
# ------------------------------------------------------------------

def _render_opportunities_tab():
    """Striking-distance keywords with AI suggestions."""
    st.subheader("🎯 Ranking Opportunities")
    st.markdown("Keywords ranking **4-20** — within striking distance of page 1 or top 3.")

    domain = st.text_input(
        "Domain", key="opp_domain", placeholder="example.com"
    )
    limit = st.slider("Max results", 5, 50, 20, key="opp_limit")

    if not domain:
        st.info("Enter a domain to discover ranking opportunities.")
        return

    if st.button("Find Opportunities", key="btn_opportunities", type="primary"):
        tracker = _get_tracker()
        with st.spinner("Analyzing striking-distance keywords with AI..."):
            opps = _run_async(tracker.get_top_opportunities(domain, limit=limit))
            st.session_state["opportunities"] = opps

    opps = st.session_state.get("opportunities", [])
    if not opps:
        st.info("No opportunities found. Track more keywords first.")
        return

    st.markdown("#### Striking Distance Keywords (" + str(len(opps)) + ")")
    for opp in opps:
        pos = opp.get("position", 0)
        kw = opp.get("keyword", "")
        suggestion = opp.get("suggestion", "")
        url = opp.get("url_ranked", "-") or "-"

        with st.expander("Pos " + str(pos) + " — " + kw):
            st.markdown("**Current Position:** " + str(pos))
            st.markdown("**URL:** " + url)
            st.markdown("**AI Suggestion:** " + suggestion)


# ------------------------------------------------------------------
# Tab: Competitors
# ------------------------------------------------------------------

def _render_competitors_tab():
    """Competitor comparison matrix."""
    st.subheader("🏆 Competitor Analysis")

    domain = st.text_input(
        "Your domain", key="comp_domain", placeholder="example.com"
    )
    competitors_text = st.text_area(
        "Competitor domains (one per line)",
        key="comp_competitors",
        height=100,
        placeholder="competitor1.com\ncompetitor2.com",
    )

    if not domain or not competitors_text.strip():
        st.info("Enter your domain and competitor domains to compare.")
        return

    competitors = [
        c.strip() for c in competitors_text.strip().split("\n") if c.strip()
    ]

    if st.button("Compare Rankings", key="btn_compare", type="primary"):
        tracker = _get_tracker()
        with st.spinner("Comparing rankings across domains..."):
            comparison = _run_async(
                tracker.compare_with_competitors(domain, competitors)
            )
            st.session_state["comparison"] = comparison

    comparison = st.session_state.get("comparison")
    if not comparison:
        return

    # Visibility comparison bar chart
    st.markdown("#### Visibility Comparison")
    vis_data = comparison.get("visibility", {})
    if vis_data:
        vis_rows = []
        for d, v in vis_data.items():
            vis_rows.append({
                "Domain": d,
                "Top 10 Keywords": v.get("top10_count", 0),
                "Avg Position": v.get("avg_position", 0),
                "Ranked Keywords": v.get("ranked_count", 0),
            })
        vis_df = pd.DataFrame(vis_rows)
        st.dataframe(vis_df, use_container_width=True)
        st.bar_chart(vis_df.set_index("Domain")[["Top 10 Keywords"]])

    # Ranking matrix
    st.markdown("#### Ranking Matrix")
    matrix = comparison.get("matrix", {})
    domains = comparison.get("domains", [])
    winners = comparison.get("winners", {})

    if matrix:
        matrix_rows = []
        for kw, positions in matrix.items():
            row = {"Keyword": kw}
            for d in domains:
                pos = positions.get(d, 0)
                row[d] = str(pos) if pos > 0 else "-"
            row["Winner"] = winners.get(kw, "-")
            matrix_rows.append(row)
        matrix_df = pd.DataFrame(matrix_rows)
        st.dataframe(matrix_df, use_container_width=True)


# ------------------------------------------------------------------
# Tab: SERP Features
# ------------------------------------------------------------------

def _render_serp_features_tab():
    """SERP feature detection and analysis."""
    st.subheader("🔍 SERP Feature Analysis")

    col1, col2 = st.columns([2, 1])
    with col1:
        keyword = st.text_input(
            "Keyword to analyze",
            key="serp_keyword",
            placeholder="best seo tools 2025",
        )
    with col2:
        location = st.selectbox(
            "Location",
            ["us", "gb", "ca", "au", "de", "fr"],
            key="serp_location",
        )

    if keyword and st.button("Analyze SERP Features", key="btn_serp_features"):
        analyzer = _get_analyzer()
        with st.spinner("Analyzing SERP features..."):
            features = _run_async(
                analyzer.analyze_serp_features(keyword, location=location)
            )
            st.session_state["serp_features_result"] = features

    features = st.session_state.get("serp_features_result")
    if features:
        st.markdown("#### Features Detected: " + str(features.get("feature_count", 0)))

        feat_data = features.get("features", {})
        for ftype, finfo in feat_data.items():
            present = finfo.get("present", False)
            icon = "✅" if present else "❌"
            label = ftype.replace("_", " ").title()
            st.markdown(icon + " **" + label + "**")
            if present and finfo.get("content"):
                st.caption(str(finfo["content"])[:200])
            if present and finfo.get("questions"):
                for q in finfo["questions"][:3]:
                    st.caption("  • " + q)

    # Featured snippet opportunities section
    st.markdown("---")
    st.markdown("#### Featured Snippet Opportunities")
    fs_domain = st.text_input(
        "Your domain", key="fs_domain", placeholder="example.com"
    )
    fs_keywords = st.text_area(
        "Keywords to check (one per line)",
        key="fs_keywords",
        height=80,
    )

    if fs_domain and fs_keywords and st.button("Find Snippet Opportunities", key="btn_fs_opps"):
        kw_list = [k.strip() for k in fs_keywords.strip().split("\n") if k.strip()]
        analyzer = _get_analyzer()
        with st.spinner("Analyzing featured snippet opportunities..."):
            fs_opps = _run_async(
                analyzer.get_featured_snippet_opportunities(fs_domain, kw_list)
            )
            st.session_state["fs_opportunities"] = fs_opps

    fs_opps = st.session_state.get("fs_opportunities", [])
    if fs_opps:
        st.markdown("Found **" + str(len(fs_opps)) + "** snippet opportunities")
        for opp in fs_opps:
            with st.expander("Pos " + str(opp.get("current_position", "?")) + " — " + opp.get("keyword", "")):
                st.markdown("**URL:** " + str(opp.get("url_ranked", "-")))
                st.markdown("**Competitor Owns:** " + str(opp.get("competitor_owns", "-")))
                st.markdown("**Suggestion:** " + opp.get("suggestion", ""))


# ------------------------------------------------------------------
# Tab: Export
# ------------------------------------------------------------------

def _render_export_tab():
    """Export ranking data as CSV or JSON."""
    st.subheader("📥 Export Ranking Data")

    domain = st.text_input(
        "Domain to export", key="export_domain", placeholder="example.com"
    )

    if not domain:
        st.info("Enter a domain to export its ranking data.")
        return

    export_format = st.radio(
        "Export format", ["CSV", "JSON"], horizontal=True, key="export_format"
    )

    if st.button("Generate Export", key="btn_export"):
        from src.database import get_session
        from src.models.ranking import RankingRecord
        from urllib.parse import urlparse

        domain_clean = domain.lower().removeprefix("www.")

        with get_session() as session:
            records = (
                session.query(RankingRecord)
                .filter(RankingRecord.domain == domain_clean)
                .order_by(RankingRecord.checked_at.desc())
                .limit(1000)
                .all()
            )

        if not records:
            st.warning("No ranking data found for this domain.")
            return

        rows = []
        for r in records:
            rows.append({
                "keyword": r.keyword,
                "position": r.position,
                "url_ranked": r.url_ranked or "",
                "device": r.device,
                "location": r.location,
                "search_engine": r.search_engine,
                "checked_at": r.checked_at.isoformat() if r.checked_at else "",
            })

        if export_format == "CSV":
            df = pd.DataFrame(rows)
            csv_data = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name="rankings_" + domain_clean.replace(".", "_") + ".csv",
                mime="text/csv",
            )
            st.dataframe(df.head(20), use_container_width=True)
        else:
            json_data = json.dumps(rows, indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=json_data,
                file_name="rankings_" + domain_clean.replace(".", "_") + ".json",
                mime="application/json",
            )
            st.json(rows[:10])

        st.success("Export ready! " + str(len(rows)) + " records.")
