"""Keyword Research dashboard page for SEO Automation.

Provides an interactive Streamlit interface for keyword expansion,
intent classification, clustering, scoring, SERP analysis,
trend analysis, and data export.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project root is on the path
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.modules.keyword_research.researcher import KeywordResearcher
from src.modules.keyword_research.kw_analyzer import KeywordAnalyzer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Async helper
# ------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ------------------------------------------------------------------
# Cached resource factories
# ------------------------------------------------------------------

@st.cache_resource
def _get_researcher() -> KeywordResearcher:
    """Create and cache a KeywordResearcher instance."""
    return KeywordResearcher()


@st.cache_resource
def _get_analyzer() -> KeywordAnalyzer:
    """Create and cache a KeywordAnalyzer instance."""
    return KeywordAnalyzer()


# ------------------------------------------------------------------
# Section renderers
# ------------------------------------------------------------------

def _render_input_form(researcher: KeywordResearcher) -> None:
    """Render the input form and run the full research pipeline."""
    st.markdown("### Research Input")
    st.markdown(
        "Enter seed keywords (one per line) and an optional niche name "
        "to start comprehensive keyword research."
    )

    with st.form("kw_research_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            seeds_text = st.text_area(
                "Seed Keywords (one per line)",
                placeholder="seo tools\nkeyword research\ncontent optimization",
                height=120,
                key="kw_seeds",
            )
        with col2:
            niche = st.text_input(
                "Niche / Industry",
                placeholder="e.g. digital marketing",
                key="kw_niche",
            )
            clustering_method = st.selectbox(
                "Clustering Method",
                ["semantic", "tfidf"],
                index=0,
                key="kw_cluster_method",
            )
        submitted = st.form_submit_button(
            "\U0001f50d Run Full Research",
            use_container_width=True,
        )

    if submitted and seeds_text.strip():
        seed_keywords = [
            line.strip()
            for line in seeds_text.strip().splitlines()
            if line.strip()
        ]
        if not seed_keywords:
            st.warning("Please enter at least one seed keyword.")
            return

        with st.spinner(
            "Running full keyword research pipeline... "
            "This may take a few minutes."
        ):
            try:
                result = _run_async(
                    researcher.full_research_pipeline(seed_keywords, niche)
                )
                st.session_state["kw_research_data"] = result
                st.session_state["kw_cluster_method"] = clustering_method
                st.success(
                    "Research complete! Found "
                    + str(result.get("summary", {}).get("total_keywords", 0))
                    + " keywords in "
                    + str(result.get("summary", {}).get("total_clusters", 0))
                    + " clusters."
                )
            except Exception as exc:
                st.error("Research pipeline failed: " + str(exc))
                logger.error("Pipeline failed: %s", exc, exc_info=True)

    # Show summary metrics if data available
    if "kw_research_data" in st.session_state:
        data = st.session_state["kw_research_data"]
        summary = data.get("summary", {})

        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric(
                "Total Keywords",
                summary.get("total_keywords", 0),
            )
        with m2:
            st.metric(
                "Est. Total Volume",
                "{:,}".format(summary.get("total_estimated_volume", 0)),
            )
        with m3:
            st.metric(
                "Avg Difficulty",
                summary.get("average_difficulty", 0),
            )
        with m4:
            st.metric(
                "Avg Opp. Score",
                summary.get("average_opportunity_score", 0),
            )


def _render_all_keywords_tab() -> None:
    """Render the All Keywords tab with sortable/filterable table."""
    if "kw_research_data" not in st.session_state:
        st.info("Run a research pipeline first to see keywords.")
        return

    data = st.session_state["kw_research_data"]
    all_kws = data.get("scored_keywords", []) or data.get("expanded_keywords", [])
    if not all_kws:
        st.info("No keywords found.")
        return

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        intent_options = list(set(
            kw.get("intent", "unknown") for kw in all_kws
        ))
        intent_filter = st.multiselect(
            "Filter by Intent",
            options=sorted(intent_options),
            default=[],
            key="kw_intent_filter",
        )
    with col_f2:
        source_options = list(set(
            kw.get("source", "unknown") for kw in all_kws
        ))
        source_filter = st.multiselect(
            "Filter by Source",
            options=sorted(source_options),
            default=[],
            key="kw_source_filter",
        )
    with col_f3:
        min_score = st.slider(
            "Min Opportunity Score",
            min_value=0, max_value=100, value=0,
            key="kw_min_score",
        )

    # Apply filters
    filtered = all_kws
    if intent_filter:
        filtered = [kw for kw in filtered if kw.get("intent") in intent_filter]
    if source_filter:
        filtered = [kw for kw in filtered if kw.get("source") in source_filter]
    if min_score > 0:
        filtered = [
            kw for kw in filtered
            if int(kw.get("opportunity_score", 0)) >= min_score
        ]

    st.markdown(
        "**Showing " + str(len(filtered)) + " of "
        + str(len(all_kws)) + " keywords**"
    )

    # Build table data
    table_rows = []
    for kw in filtered:
        table_rows.append({
            "Keyword": kw.get("keyword", ""),
            "Volume": int(kw.get("estimated_volume", 0)),
            "Difficulty": int(kw.get("difficulty_estimate", 0)),
            "Intent": kw.get("intent", "unknown"),
            "Score": int(kw.get("opportunity_score", 0)),
            "Source": kw.get("source", "unknown"),
        })

    if table_rows:
        st.dataframe(
            table_rows,
            use_container_width=True,
            column_config={
                "Volume": st.column_config.NumberColumn(format="%d"),
                "Difficulty": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%d",
                ),
                "Score": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%d",
                ),
            },
        )


def _render_clusters_tab() -> None:
    """Render the Clusters tab with expandable cluster groups."""
    if "kw_research_data" not in st.session_state:
        st.info("Run a research pipeline first to see clusters.")
        return

    data = st.session_state["kw_research_data"]
    clusters = data.get("clusters", [])
    if not clusters:
        st.info("No clusters found.")
        return

    st.metric("Total Clusters", len(clusters))

    # Sort clusters by estimated volume
    sorted_clusters = sorted(
        clusters,
        key=lambda c: c.get("estimated_total_volume", 0),
        reverse=True,
    )

    for idx, cl in enumerate(sorted_clusters):
        cl_name = cl.get("cluster_name", "Unnamed")
        cl_intent = cl.get("cluster_intent", "informational")
        cl_vol = cl.get("estimated_total_volume", 0)
        cl_kws = cl.get("keywords", [])
        primary = cl.get("primary_keyword", "")

        intent_icon = {
            "informational": "\U0001f4d6",
            "transactional": "\U0001f4b3",
            "commercial": "\U0001f50d",
            "navigational": "\U0001f517",
        }.get(cl_intent, "\u2022")

        header = (
            intent_icon + " " + cl_name
            + " (" + str(len(cl_kws)) + " kws, vol: "
            + "{:,}".format(cl_vol) + ")"
        )

        with st.expander(header):
            st.markdown("**Primary Keyword:** " + primary)
            st.markdown("**Intent:** " + cl_intent)
            st.markdown(
                "**Est. Total Volume:** {:,}".format(cl_vol)
            )
            st.markdown("**Keywords:**")
            for kw_text in cl_kws:
                st.write("  - " + str(kw_text))


def _render_quick_wins_tab(analyzer: KeywordAnalyzer) -> None:
    """Render the Quick Wins tab."""
    if "kw_research_data" not in st.session_state:
        st.info("Run a research pipeline first to find quick wins.")
        return

    data = st.session_state["kw_research_data"]
    all_kws = data.get("scored_keywords", []) or data.get("expanded_keywords", [])

    if "kw_quick_wins" not in st.session_state:
        with st.spinner("Identifying quick wins..."):
            try:
                quick_wins = _run_async(analyzer.find_quick_wins(all_kws))
                st.session_state["kw_quick_wins"] = quick_wins
            except Exception as exc:
                st.error("Quick win analysis failed: " + str(exc))
                return

    quick_wins = st.session_state.get("kw_quick_wins", [])
    if not quick_wins:
        st.info(
            "No quick wins found. Try adjusting your seed keywords "
            "or targeting a less competitive niche."
        )
        return

    st.metric("Quick Wins Found", len(quick_wins))

    # Display as table
    table_rows = []
    for qw in quick_wins:
        table_rows.append({
            "Keyword": qw.get("keyword", ""),
            "Volume": int(qw.get("estimated_volume", 0)),
            "Difficulty": int(qw.get("difficulty_estimate", 0)),
            "Opp. Score": int(qw.get("opportunity_score", 0)),
            "QW Score": int(qw.get("quick_win_score", 0)),
            "Intent": qw.get("intent", ""),
            "Reason": qw.get("quick_win_reason", ""),
        })

    st.dataframe(
        table_rows,
        use_container_width=True,
        column_config={
            "Volume": st.column_config.NumberColumn(format="%d"),
            "Difficulty": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%d",
            ),
            "Opp. Score": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%d",
            ),
            "QW Score": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%d",
            ),
        },
    )


def _render_serp_analysis_tab(researcher: KeywordResearcher) -> None:
    """Render the SERP Analysis tab."""
    st.markdown("Select a keyword to perform detailed SERP analysis.")

    # Build keyword list from research data or allow manual entry
    kw_options = []
    if "kw_research_data" in st.session_state:
        data = st.session_state["kw_research_data"]
        all_kws = data.get("scored_keywords", []) or data.get("expanded_keywords", [])
        kw_options = [kw.get("keyword", "") for kw in all_kws if kw.get("keyword")]

    col1, col2 = st.columns([3, 1])
    with col1:
        if kw_options:
            selected_kw = st.selectbox(
                "Select keyword from research",
                options=kw_options[:100],
                key="serp_select_kw",
            )
        else:
            selected_kw = ""
    with col2:
        manual_kw = st.text_input(
            "Or enter manually",
            placeholder="keyword to analyze",
            key="serp_manual_kw",
        )

    target_kw = manual_kw.strip() if manual_kw.strip() else selected_kw

    if st.button(
        "\U0001f50e Analyze SERP",
        use_container_width=True,
        disabled=not target_kw,
    ):
        with st.spinner("Analyzing SERP for: " + target_kw + "..."):
            try:
                serp_result = _run_async(researcher.analyze_serp(target_kw))
                st.session_state["kw_serp_result"] = serp_result
            except Exception as exc:
                st.error("SERP analysis failed: " + str(exc))
                return

    if "kw_serp_result" in st.session_state:
        serp = st.session_state["kw_serp_result"]

        st.markdown("#### SERP Analysis: " + serp.get("keyword", ""))

        # Summary
        if serp.get("analysis_summary"):
            st.info(serp["analysis_summary"])

        # Metrics row
        sm1, sm2, sm3, sm4 = st.columns(4)
        with sm1:
            st.metric(
                "Organic Results",
                serp.get("serp_features", {}).get("organic_count", 0),
            )
        with sm2:
            st.metric(
                "Avg Word Count",
                "{:,}".format(serp.get("avg_word_count_estimate", 0)),
            )
        with sm3:
            st.metric(
                "Dominant Format",
                serp.get("dominant_format", "N/A"),
            )
        with sm4:
            st.metric(
                "Authority Level",
                serp.get("authority_level", "N/A"),
            )

        # SERP Features
        features = serp.get("serp_features", {})
        st.markdown("**SERP Features:**")
        feat_cols = st.columns(3)
        with feat_cols[0]:
            icon_snippet = "\u2705" if features.get("has_featured_snippet") else "\u274c"
            st.write(icon_snippet + " Featured Snippet")
        with feat_cols[1]:
            icon_paa = "\u2705" if features.get("has_paa") else "\u274c"
            st.write(icon_paa + " People Also Ask")
        with feat_cols[2]:
            icon_rel = "\u2705" if features.get("has_related_searches") else "\u274c"
            st.write(icon_rel + " Related Searches")

        # Top Results
        top_results = serp.get("top_results", [])
        if top_results:
            st.markdown("**Top Ranking Pages:**")
            for r in top_results:
                pos = r.get("position", "?")
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("snippet", "")
                st.markdown(
                    "**#" + str(pos) + "** " + title
                )
                if url:
                    st.caption(url)
                if snippet:
                    st.caption(snippet[:200])
                st.markdown("---")

        # Content Types
        content_types = serp.get("content_types", [])
        if content_types:
            st.markdown("**Content Types Ranking:**")
            st.write(", ".join(content_types))

        # PAA Questions
        paa = serp.get("paa_questions", [])
        if paa:
            with st.expander("People Also Ask (" + str(len(paa)) + " questions)"):
                for q in paa:
                    st.write("- " + q)

        # Related Searches
        related = serp.get("related_searches", [])
        if related:
            with st.expander("Related Searches (" + str(len(related)) + ")"):
                for r in related:
                    st.write("- " + r)


def _render_trends_tab(analyzer: KeywordAnalyzer) -> None:
    """Render the Trends / Seasonal Analysis tab."""
    if "kw_research_data" not in st.session_state:
        st.info("Run a research pipeline first, then analyze trends.")
        return

    data = st.session_state["kw_research_data"]
    all_kws = data.get("scored_keywords", []) or data.get("expanded_keywords", [])
    kw_texts = [kw.get("keyword", "") for kw in all_kws if kw.get("keyword")][:50]

    if not kw_texts:
        st.info("No keywords available for trend analysis.")
        return

    # Let user select keywords for trend analysis
    selected_for_trends = st.multiselect(
        "Select keywords for seasonal analysis (max 20)",
        options=kw_texts,
        default=kw_texts[:5],
        max_selections=20,
        key="kw_trend_selection",
    )

    if st.button(
        "\U0001f4c8 Analyze Seasonality",
        use_container_width=True,
        disabled=not selected_for_trends,
    ):
        with st.spinner("Analyzing seasonal trends..."):
            try:
                seasonal_data = _run_async(
                    analyzer.seasonal_analysis(selected_for_trends)
                )
                st.session_state["kw_seasonal"] = seasonal_data
            except Exception as exc:
                st.error("Seasonal analysis failed: " + str(exc))
                return

    if "kw_seasonal" in st.session_state:
        seasonal = st.session_state["kw_seasonal"]

        if not seasonal:
            st.info("No seasonal data available.")
            return

        # Display as table with trend indicators
        table_rows = []
        for s in seasonal:
            direction = s.get("trend_direction", "stable")
            direction_icon = {
                "rising": "\u2b06\ufe0f Rising",
                "declining": "\u2b07\ufe0f Declining",
                "stable": "\u27a1\ufe0f Stable",
                "unknown": "\u2753 Unknown",
            }.get(direction, direction)

            peak_str = ", ".join(s.get("peak_months", [])[:3])

            table_rows.append({
                "Keyword": s.get("keyword", ""),
                "Seasonal Score": int(s.get("seasonal_score", 0)),
                "Trend": direction_icon,
                "Peak Months": peak_str,
                "Best Publish": s.get("best_publish_time", "anytime"),
            })

        st.dataframe(
            table_rows,
            use_container_width=True,
            column_config={
                "Seasonal Score": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%d",
                ),
            },
        )

        # Detailed per-keyword expandable
        for s in seasonal:
            kw_name = s.get("keyword", "")
            monthly_data = s.get("monthly_data", [])
            if not monthly_data:
                continue

            with st.expander("\U0001f4c5 " + kw_name + " -- Monthly Breakdown"):
                chart_data = {}
                for m in monthly_data:
                    chart_data[m.get("month", "")] = m.get("interest", 0)
                if chart_data:
                    st.bar_chart(chart_data)


def _render_export_tab(analyzer: KeywordAnalyzer) -> None:
    """Render the Export tab with download buttons."""
    if "kw_research_data" not in st.session_state:
        st.info("Run a research pipeline first to export data.")
        return

    data = st.session_state["kw_research_data"]
    all_kws = data.get("scored_keywords", []) or data.get("expanded_keywords", [])

    st.markdown("### Download Research Data")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Keywords CSV**")
        st.caption(
            str(len(all_kws)) + " keywords with volume, difficulty, "
            "intent, and opportunity scores."
        )
        csv_bytes = KeywordAnalyzer.keywords_to_csv_bytes(all_kws)
        st.download_button(
            "\u2b07\ufe0f Download Keywords CSV",
            data=csv_bytes,
            file_name="keyword_research.csv",
            mime="text/csv",
            key="export_kw_csv",
            use_container_width=True,
        )

    with col2:
        st.markdown("**Full Research JSON**")
        st.caption(
            "Complete research data including clusters, scores, "
            "and pipeline summary."
        )
        json_bytes = KeywordAnalyzer.research_to_json_bytes(data)
        st.download_button(
            "\u2b07\ufe0f Download Full JSON",
            data=json_bytes,
            file_name="keyword_research.json",
            mime="application/json",
            key="export_kw_json",
            use_container_width=True,
        )

    st.markdown("---")

    # Quick wins export
    if "kw_quick_wins" in st.session_state:
        quick_wins = st.session_state["kw_quick_wins"]
        if quick_wins:
            st.markdown("**Quick Wins CSV**")
            st.caption(str(len(quick_wins)) + " quick-win keywords.")
            qw_csv = KeywordAnalyzer.keywords_to_csv_bytes(quick_wins)
            st.download_button(
                "\u2b07\ufe0f Download Quick Wins CSV",
                data=qw_csv,
                file_name="quick_wins.csv",
                mime="text/csv",
                key="export_qw_csv",
                use_container_width=True,
            )

    # Report export
    if st.button(
        "\U0001f4cb Generate & Download Report",
        use_container_width=True,
    ):
        with st.spinner("Generating keyword research report..."):
            try:
                report = _run_async(
                    analyzer.generate_keyword_report(data)
                )
                st.session_state["kw_report"] = report
                report_bytes = KeywordAnalyzer.research_to_json_bytes(report)
                st.download_button(
                    "\u2b07\ufe0f Download Report JSON",
                    data=report_bytes,
                    file_name="keyword_report.json",
                    mime="application/json",
                    key="export_report_json",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error("Report generation failed: " + str(exc))

    # Show report preview if available
    if "kw_report" in st.session_state:
        report = st.session_state["kw_report"]
        with st.expander("\U0001f4cb Report Preview"):
            exec_summary = report.get("executive_summary", "")
            if exec_summary:
                st.markdown("**Executive Summary**")
                st.write(exec_summary)

            recs = report.get("recommendations", [])
            if recs:
                st.markdown("**Recommendations**")
                for rec in recs:
                    priority = rec.get("priority", "medium")
                    action = rec.get("action", "")
                    impact = rec.get("impact", "")
                    badge_color = {
                        "high": "red", "medium": "orange", "low": "blue"
                    }.get(priority, "gray")
                    st.markdown(
                        "- :"
                        + badge_color + "[" + priority.upper() + "]"
                        + " " + action
                        + " *(Impact: " + impact + ")*"
                    )

            actions = report.get("priority_actions", [])
            if actions:
                st.markdown("**Priority Actions**")
                for i, action in enumerate(actions, 1):
                    st.write(str(i) + ". " + action)

            strategy = report.get("content_strategy", "")
            if strategy:
                st.markdown("**Content Strategy**")
                st.write(strategy)


# ------------------------------------------------------------------
# Main page render function
# ------------------------------------------------------------------

def render_keywords_page() -> None:
    """Render the complete Keyword Research dashboard page."""
    st.title("\U0001f50d Keyword Research")
    st.markdown(
        "AI-powered keyword expansion, intent classification, "
        "semantic clustering, opportunity scoring, and SERP analysis."
    )

    researcher = _get_researcher()
    analyzer = _get_analyzer()

    # Input form (always visible)
    _render_input_form(researcher)

    # Only show tabs when research data is available
    if "kw_research_data" not in st.session_state:
        st.info(
            "\u261d Enter seed keywords above and click "
            "\"Run Full Research\" to get started."
        )
        return

    # Tab-based navigation for results
    tabs = st.tabs([
        "\U0001f4cb All Keywords",
        "\U0001f3af Clusters",
        "\U0001f3c6 Quick Wins",
        "\U0001f4ca SERP Analysis",
        "\U0001f4c8 Trends",
        "\U0001f4e5 Export",
    ])

    with tabs[0]:
        _render_all_keywords_tab()

    with tabs[1]:
        _render_clusters_tab()

    with tabs[2]:
        _render_quick_wins_tab(analyzer)

    with tabs[3]:
        _render_serp_analysis_tab(researcher)

    with tabs[4]:
        _render_trends_tab(analyzer)

    with tabs[5]:
        _render_export_tab(analyzer)


# Allow direct execution for testing
if __name__ == "__main__":
    render_keywords_page()
