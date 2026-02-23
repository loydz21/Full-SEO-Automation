"""Topical Research dashboard page for SEO Automation.

Provides an interactive Streamlit interface for niche analysis,
topical map generation, content gap analysis, silo building,
competitor analysis, and trending topics discovery.
"""

import asyncio
import csv
import io
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

from src.modules.topical_research.researcher import TopicalResearcher
from src.modules.topical_research.entity_mapper import EntityMapper

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
def _get_researcher() -> TopicalResearcher:
    """Create and cache a TopicalResearcher instance."""
    return TopicalResearcher()


@st.cache_resource
def _get_entity_mapper() -> EntityMapper:
    """Create and cache an EntityMapper instance."""
    return EntityMapper()


# ------------------------------------------------------------------
# Export helpers
# ------------------------------------------------------------------

def _to_json_bytes(data: Any) -> bytes:
    """Serialize data to pretty-printed JSON bytes."""
    return json.dumps(data, indent=2, default=str).encode("utf-8")


def _to_csv_bytes(rows: list[dict]) -> bytes:
    """Convert a list of flat dicts to CSV bytes."""
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    for row in rows:
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, (list, dict)):
                clean_row[k] = json.dumps(v, default=str)
            else:
                clean_row[k] = v
        writer.writerow(clean_row)
    return output.getvalue().encode("utf-8")


def _flatten_topical_map(topical_map: dict) -> list[dict]:
    """Flatten a topical map hierarchy into rows for CSV export."""
    rows = []
    for pillar in topical_map.get("pillars", []):
        for cluster in pillar.get("clusters", []):
            for article in cluster.get("supporting_articles", []):
                rows.append({
                    "pillar": pillar.get("title", ""),
                    "cluster": cluster.get("title", ""),
                    "article": article.get("title", ""),
                    "search_intent": article.get("search_intent", ""),
                    "content_type": article.get("content_type", ""),
                    "difficulty": article.get("estimated_difficulty", ""),
                    "keywords": ", ".join(
                        article.get("suggested_keywords", [])
                    ),
                    "word_count_target": article.get(
                        "word_count_target", ""
                    ),
                })
    return rows


# ------------------------------------------------------------------
# Section renderers
# ------------------------------------------------------------------

def _render_niche_analysis(researcher: TopicalResearcher) -> None:
    """Render the Niche Analysis section."""
    st.markdown("### \U0001f50d Niche Analysis")
    st.markdown(
        "Analyze a niche for market size, competition, monetization "
        "potential, and trending subtopics."
    )

    with st.form("niche_analysis_form"):
        col1, col2 = st.columns(2)
        with col1:
            niche = st.text_input(
                "Niche / Industry",
                placeholder="e.g. home automation",
                key="na_niche",
            )
        with col2:
            location = st.text_input(
                "Location (optional)",
                placeholder="e.g. US, UK, or leave empty",
                key="na_location",
            )
        submitted = st.form_submit_button(
            "\U0001f50d Analyze Niche", use_container_width=True
        )

    if submitted and niche:
        with st.spinner("Analyzing niche... This may take a minute."):
            try:
                result = _run_async(
                    researcher.analyze_niche(niche, location)
                )
                st.session_state["niche_analysis"] = result
            except Exception as exc:
                st.error("Analysis failed: " + str(exc))
                logger.error("Niche analysis failed: %s", exc)
                return

    if "niche_analysis" in st.session_state:
        data = st.session_state["niche_analysis"]

        if data.get("error"):
            st.warning(data["error"])

        # Overall score
        overall = data.get("overall_opportunity_score", "N/A")
        st.metric("Overall Opportunity Score", str(overall) + " / 10")

        # Market / Competition / Monetization cards
        c1, c2, c3 = st.columns(3)
        market = data.get("market_analysis", {})
        comp = data.get("competition", {})
        money = data.get("monetization", {})

        with c1:
            st.markdown("**\U0001f4c8 Market Analysis**")
            st.write("Size Score:", market.get("market_size_score", "N/A"))
            st.write("Growth:", market.get("growth_trend", "N/A"))
            st.write("Demand:", market.get("search_demand", "N/A"))
            st.caption(str(market.get("estimated_market_size", "")))

        with c2:
            st.markdown("**\u2694\ufe0f Competition**")
            st.write("Level:", comp.get("level", "N/A"))
            st.write("Score:", comp.get("competition_score", "N/A"))
            st.write(
                "Saturation:", comp.get("content_saturation", "N/A")
            )
            players = comp.get("dominant_players", [])
            if players:
                st.write("Top Players:", ", ".join(players[:5]))

        with c3:
            st.markdown("**\U0001f4b0 Monetization**")
            st.write("Score:", money.get("potential_score", "N/A"))
            st.write("CPC Est:", money.get("avg_cpc_estimate", "N/A"))
            st.write(
                "Affiliate:", money.get("affiliate_potential", "N/A")
            )
            models = money.get("revenue_models", [])
            if models:
                st.write("Models:", ", ".join(models))

        # Trending subtopics
        subtopics = data.get("trending_subtopics", [])
        if subtopics:
            st.markdown("**Trending Subtopics**")
            for st_item in subtopics:
                direction = st_item.get("trend_direction", "")
                icon = {"up": "\u2b06\ufe0f", "stable": "\u27a1\ufe0f", "down": "\u2b07\ufe0f"}.get(
                    direction, "\u2022"
                )
                score = st_item.get("opportunity_score", "")
                st.write(
                    icon, "**" + str(st_item.get("topic", "")) + "**",
                    "— Opportunity:", str(score),
                    "|", str(st_item.get("reason", ""))
                )

        # Recommendations
        recs = data.get("recommendations", [])
        if recs:
            st.markdown("**Recommendations**")
            for rec in recs:
                priority = rec.get("priority", "medium")
                badge_color = {
                    "high": "red", "medium": "orange", "low": "blue"
                }.get(priority, "gray")
                st.markdown(
                    "- :" + badge_color + "[" + priority.upper() + "]"
                    + " " + str(rec.get("action", ""))
                    + " *(Impact: " + str(rec.get("impact", "")) + ")*"
                )

        # SERP Insights
        serp = data.get("serp_insights", {})
        if serp:
            with st.expander("SERP Insights"):
                st.write(
                    "Organic results:",
                    serp.get("organic_count", 0),
                )
                st.write(
                    "Featured Snippet:",
                    serp.get("has_featured_snippet", False),
                )
                paa = serp.get("paa_questions", [])
                if paa:
                    st.write("People Also Ask:")
                    for q in paa:
                        st.write("  -", q)

        # Export
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                "\u2b07\ufe0f Export JSON",
                data=_to_json_bytes(data),
                file_name="niche_analysis.json",
                mime="application/json",
            )
        with col_e2:
            flat_rows = []
            if subtopics:
                flat_rows = subtopics
            st.download_button(
                "\u2b07\ufe0f Export CSV",
                data=_to_csv_bytes(flat_rows) if flat_rows else b"No data",
                file_name="niche_subtopics.csv",
                mime="text/csv",
            )


def _render_topical_map(researcher: TopicalResearcher) -> None:
    """Render the Topical Map Generator section."""
    st.markdown("### \U0001f5fa\ufe0f Topical Map Generator")
    st.markdown(
        "Generate a comprehensive topical map with pillars, clusters, "
        "and supporting articles."
    )

    with st.form("topical_map_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            niche = st.text_input(
                "Niche",
                placeholder="e.g. home automation",
                key="tm_niche",
            )
        with col2:
            num_pillars = st.number_input(
                "Pillars", min_value=2, max_value=10, value=5,
                key="tm_pillars",
            )
        submitted = st.form_submit_button(
            "\U0001f5fa\ufe0f Generate Topical Map",
            use_container_width=True,
        )

    if submitted and niche:
        with st.spinner("Generating topical map..."):
            try:
                result = _run_async(
                    researcher.generate_topical_map(niche, num_pillars)
                )
                st.session_state["topical_map"] = result
            except Exception as exc:
                st.error("Generation failed: " + str(exc))
                return

    if "topical_map" in st.session_state:
        tmap = st.session_state["topical_map"]

        if tmap.get("error"):
            st.warning(tmap["error"])
            return

        # Summary metrics
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Pillars", len(tmap.get("pillars", [])))
        with mc2:
            st.metric("Total Articles", tmap.get("total_articles", 0))
        with mc3:
            st.metric(
                "Est. Months",
                tmap.get("estimated_completion_months", "N/A"),
            )

        # Hierarchical display
        for pillar in tmap.get("pillars", []):
            pillar_title = pillar.get("title", "Untitled")
            diff = pillar.get("estimated_difficulty", "?")
            intent = pillar.get("search_intent", "")
            ctype = pillar.get("content_type", "")

            with st.expander(
                "\U0001f3db\ufe0f " + pillar_title
                + " (Difficulty: " + str(diff) + ")"
            ):
                st.markdown(
                    "**Intent:** " + intent
                    + " | **Type:** " + ctype
                )
                kws = pillar.get("suggested_keywords", [])
                if kws:
                    st.markdown(
                        "**Keywords:** " + ", ".join(kws)
                    )

                for cluster in pillar.get("clusters", []):
                    c_title = cluster.get("title", "Untitled")
                    c_diff = cluster.get("estimated_difficulty", "?")
                    st.markdown(
                        "\n---\n\U0001f4c1 **" + c_title
                        + "** (Difficulty: " + str(c_diff) + ")"
                    )
                    c_kws = cluster.get("suggested_keywords", [])
                    if c_kws:
                        st.caption("Keywords: " + ", ".join(c_kws))

                    for article in cluster.get(
                        "supporting_articles", []
                    ):
                        a_title = article.get("title", "Untitled")
                        a_diff = article.get(
                            "estimated_difficulty", "?"
                        )
                        a_intent = article.get("search_intent", "")
                        a_type = article.get("content_type", "")
                        a_wc = article.get("word_count_target", "")
                        st.markdown(
                            "- \U0001f4dd **" + a_title + "**"
                            + " | Diff: " + str(a_diff)
                            + " | Intent: " + a_intent
                            + " | Type: " + a_type
                            + " | Words: " + str(a_wc)
                        )

        # Export
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                "\u2b07\ufe0f Export JSON",
                data=_to_json_bytes(tmap),
                file_name="topical_map.json",
                mime="application/json",
                key="tm_export_json",
            )
        with col_e2:
            flat = _flatten_topical_map(tmap)
            st.download_button(
                "\u2b07\ufe0f Export CSV",
                data=_to_csv_bytes(flat) if flat else b"No data",
                file_name="topical_map.csv",
                mime="text/csv",
                key="tm_export_csv",
            )


def _render_content_gaps(
    researcher: TopicalResearcher,
) -> None:
    """Render the Content Gap Analysis section."""
    st.markdown("### \U0001f4ca Content Gap Analysis")
    st.markdown(
        "Discover topics your competitors rank for but your domain doesn't."
    )

    with st.form("content_gap_form"):
        col1, col2 = st.columns(2)
        with col1:
            domain = st.text_input(
                "Your Domain",
                placeholder="e.g. example.com",
                key="cg_domain",
            )
        with col2:
            niche = st.text_input(
                "Niche",
                placeholder="e.g. home automation",
                key="cg_niche",
            )
        submitted = st.form_submit_button(
            "\U0001f4ca Find Content Gaps",
            use_container_width=True,
        )

    if submitted and domain and niche:
        with st.spinner("Analyzing content gaps... This may take a few minutes."):
            try:
                result = _run_async(
                    researcher.find_content_gaps(domain, niche)
                )
                st.session_state["content_gaps"] = result
            except Exception as exc:
                st.error("Gap analysis failed: " + str(exc))
                return

    if "content_gaps" in st.session_state:
        gaps = st.session_state["content_gaps"]

        if not gaps:
            st.info("No content gaps found — great coverage!")
            return

        st.metric("Content Gaps Found", len(gaps))

        # Display as table
        table_rows = []
        for g in gaps:
            table_rows.append({
                "Query": g.get("query", ""),
                "Opportunity": g.get("opportunity_score", 0),
                "Difficulty": g.get("difficulty", 0),
                "Priority": g.get("priority", "medium"),
                "Content Type": g.get(
                    "suggested_content_type", "guide"
                ),
                "Top Competitor": g.get(
                    "top_competitor_title", "N/A"
                ),
            })

        st.dataframe(
            table_rows,
            use_container_width=True,
            column_config={
                "Opportunity": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%d"
                ),
                "Difficulty": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%d"
                ),
            },
        )

        # Export
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                "\u2b07\ufe0f Export JSON",
                data=_to_json_bytes(gaps),
                file_name="content_gaps.json",
                mime="application/json",
                key="cg_export_json",
            )
        with col_e2:
            st.download_button(
                "\u2b07\ufe0f Export CSV",
                data=_to_csv_bytes(table_rows),
                file_name="content_gaps.csv",
                mime="text/csv",
                key="cg_export_csv",
            )


def _render_content_silo(
    researcher: TopicalResearcher,
) -> None:
    """Render the Content Silo Builder section."""
    st.markdown("### \U0001f3d7\ufe0f Content Silo Builder")
    st.markdown(
        "Build a content silo structure with hub pages, spoke articles, "
        "and an internal linking plan."
    )

    if "topical_map" not in st.session_state:
        st.info(
            "\u2b06\ufe0f Generate a Topical Map first, then build a silo from it."
        )
        return

    tmap = st.session_state["topical_map"]
    niche = tmap.get("niche", "unknown")
    st.write(
        "Building silo from topical map for niche: **" + niche + "**"
    )

    if st.button(
        "\U0001f3d7\ufe0f Build Content Silo",
        use_container_width=True,
    ):
        with st.spinner("Building silo structure..."):
            try:
                result = _run_async(
                    researcher.build_content_silo(tmap)
                )
                st.session_state["content_silo"] = result
            except Exception as exc:
                st.error("Silo building failed: " + str(exc))
                return

    if "content_silo" in st.session_state:
        silo = st.session_state["content_silo"]

        if silo.get("error"):
            st.warning(silo["error"])
            return

        # Summary
        sc1, sc2 = st.columns(2)
        with sc1:
            st.metric("Total Silos", silo.get("total_silos", 0))
        with sc2:
            st.metric("Total Pages", silo.get("total_pages", 0))

        # Silo structure display
        for silo_item in silo.get("silos", []):
            hub = silo_item.get("hub_page", {})
            hub_title = hub.get("title", "Untitled")

            with st.expander(
                "\U0001f3e0 Hub: " + hub_title
                + " (" + str(silo_item.get("total_spokes", 0))
                + " spokes)"
            ):
                st.markdown(
                    "**Slug:** `" + hub.get("slug", "") + "`"
                )
                links_to = hub.get("internal_links_to", [])
                if links_to:
                    st.markdown(
                        "**Links to:** "
                        + ", ".join(links_to[:10])
                    )

                for cluster_page in silo_item.get(
                    "spoke_articles", []
                ):
                    cp_title = cluster_page.get("title", "")
                    st.markdown(
                        "\n**\U0001f4c1 Sub-hub: " + cp_title + "**"
                    )
                    st.caption(
                        "Slug: " + cluster_page.get("slug", "")
                    )

                    for spoke in cluster_page.get(
                        "supporting_articles", []
                    ):
                        s_title = spoke.get("title", "")
                        s_slug = spoke.get("slug", "")
                        s_diff = spoke.get(
                            "estimated_difficulty", "?"
                        )
                        st.markdown(
                            "- \U0001f4dd " + s_title
                            + " (`" + s_slug + "`)"
                            + " | Diff: " + str(s_diff)
                        )

        # Cross-silo linking matrix
        linking_matrix = silo.get("linking_matrix", {})
        if linking_matrix:
            with st.expander(
                "\U0001f517 Cross-Silo Linking Matrix"
            ):
                for page_title, targets in linking_matrix.items():
                    target_str = ", ".join(targets) if isinstance(
                        targets, list
                    ) else str(targets)
                    st.write(
                        "**" + page_title + "**",
                        "\u2192",
                        target_str,
                    )

        # Export
        st.download_button(
            "\u2b07\ufe0f Export Silo JSON",
            data=_to_json_bytes(silo),
            file_name="content_silo.json",
            mime="application/json",
            key="silo_export_json",
        )


def _render_competitors(
    researcher: TopicalResearcher,
) -> None:
    """Render the Competitor Analysis section."""
    st.markdown("### \U0001f3af Competitor Analysis")
    st.markdown(
        "Discover and analyze top competitors in your niche."
    )

    with st.form("competitor_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            niche = st.text_input(
                "Niche",
                placeholder="e.g. home automation",
                key="comp_niche",
            )
        with col2:
            num_comp = st.number_input(
                "Max Competitors",
                min_value=3,
                max_value=10,
                value=5,
                key="comp_num",
            )
        submitted = st.form_submit_button(
            "\U0001f3af Analyze Competitors",
            use_container_width=True,
        )

    if submitted and niche:
        with st.spinner("Analyzing competitors... This may take a few minutes."):
            try:
                result = _run_async(
                    researcher.analyze_competitors(niche, num_comp)
                )
                st.session_state["competitors"] = result
            except Exception as exc:
                st.error("Competitor analysis failed: " + str(exc))
                return

    if "competitors" in st.session_state:
        competitors = st.session_state["competitors"]

        if not competitors:
            st.info("No competitors found.")
            return

        st.metric("Competitors Found", len(competitors))

        # Comparison table
        comp_table = []
        for comp in competitors:
            comp_table.append({
                "Domain": comp.get("domain", ""),
                "Appearances": comp.get("total_appearances", 0),
                "Avg Position": round(
                    comp.get("avg_position", 0), 1
                ),
                "Threat Level": comp.get("threat_level", "N/A"),
                "Topics Covered": len(
                    comp.get("topics_covered", [])
                ),
            })

        st.dataframe(comp_table, use_container_width=True)

        # Detailed competitor cards
        for comp in competitors:
            domain = comp.get("domain", "Unknown")
            threat = comp.get("threat_level", "medium")
            threat_icon = {
                "high": "\U0001f534",
                "medium": "\U0001f7e1",
                "low": "\U0001f7e2",
            }.get(threat, "\u26aa")

            with st.expander(
                threat_icon + " " + domain
                + " (" + threat + " threat)"
            ):
                strategy = comp.get("content_strategy", "")
                if strategy:
                    st.write("**Strategy:**", strategy)

                strengths = comp.get("strengths", [])
                if strengths:
                    st.markdown("**Strengths:**")
                    for s in strengths:
                        st.write("  \u2705", s)

                weaknesses = comp.get("weaknesses", [])
                if weaknesses:
                    st.markdown("**Weaknesses:**")
                    for w in weaknesses:
                        st.write("  \u26a0\ufe0f", w)

                steal = comp.get("topics_to_steal", [])
                if steal:
                    st.markdown("**Topics to Compete On:**")
                    for t in steal:
                        st.write("  \U0001f3af", t)

                top_pages = comp.get("top_pages", [])
                if top_pages:
                    st.markdown("**Top Ranking Pages:**")
                    for p in top_pages[:5]:
                        pos = p.get("position", "?")
                        title = p.get("title", "")
                        st.write(
                            "  #" + str(pos) + ":",
                            title,
                        )

        # Export
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                "\u2b07\ufe0f Export JSON",
                data=_to_json_bytes(competitors),
                file_name="competitors.json",
                mime="application/json",
                key="comp_export_json",
            )
        with col_e2:
            st.download_button(
                "\u2b07\ufe0f Export CSV",
                data=_to_csv_bytes(comp_table),
                file_name="competitors.csv",
                mime="text/csv",
                key="comp_export_csv",
            )


def _render_trending(
    researcher: TopicalResearcher,
) -> None:
    """Render the Trending Topics section."""
    st.markdown("### \U0001f525 Trending Topics")
    st.markdown(
        "Discover trending and emerging topics in your niche "
        "using Google Trends data."
    )

    with st.form("trending_form"):
        niche = st.text_input(
            "Niche",
            placeholder="e.g. home automation",
            key="trend_niche",
        )
        submitted = st.form_submit_button(
            "\U0001f525 Find Trending Topics",
            use_container_width=True,
        )

    if submitted and niche:
        with st.spinner("Fetching trending topics..."):
            try:
                result = _run_async(
                    researcher.get_trending_topics(niche)
                )
                st.session_state["trending"] = result
            except Exception as exc:
                st.error("Trending analysis failed: " + str(exc))
                return

    if "trending" in st.session_state:
        topics = st.session_state["trending"]

        if not topics:
            st.info("No trending topics found.")
            return

        st.metric("Trending Topics Found", len(topics))

        for topic in topics:
            topic_name = topic.get("topic", "")
            score = topic.get("trend_score", 0)
            growth = topic.get("growth_direction", "stable")
            seasonality = topic.get("seasonality", "unknown")
            notes = topic.get("opportunity_notes", "")
            angle = topic.get("content_angle", "")

            growth_icon = {
                "breakout": "\U0001f680",
                "rising": "\u2b06\ufe0f",
                "stable": "\u27a1\ufe0f",
                "declining": "\u2b07\ufe0f",
            }.get(growth, "\u2022")

            with st.container():
                tc1, tc2, tc3 = st.columns([3, 1, 1])
                with tc1:
                    st.markdown(
                        growth_icon + " **" + topic_name + "**"
                    )
                    if notes:
                        st.caption(notes)
                    if angle:
                        st.caption(
                            "\U0001f4a1 Angle: " + angle
                        )
                with tc2:
                    st.metric("Score", score)
                with tc3:
                    st.write("Seasonality:", seasonality)
                st.markdown("---")

        # Export
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                "\u2b07\ufe0f Export JSON",
                data=_to_json_bytes(topics),
                file_name="trending_topics.json",
                mime="application/json",
                key="trend_export_json",
            )
        with col_e2:
            flat = []
            for t in topics:
                flat.append({
                    "Topic": t.get("topic", ""),
                    "Score": t.get("trend_score", 0),
                    "Growth": t.get("growth_direction", ""),
                    "Seasonality": t.get("seasonality", ""),
                    "Notes": t.get("opportunity_notes", ""),
                    "Angle": t.get("content_angle", ""),
                })
            st.download_button(
                "\u2b07\ufe0f Export CSV",
                data=_to_csv_bytes(flat),
                file_name="trending_topics.csv",
                mime="text/csv",
                key="trend_export_csv",
            )


# ------------------------------------------------------------------
# Main page render function
# ------------------------------------------------------------------

def render_topical_research_page() -> None:
    """Render the complete Topical Research dashboard page."""
    st.title("\U0001f30d Topical Research")
    st.markdown(
        "Comprehensive niche analysis, topical mapping, "
        "content gap discovery, and competitor intelligence."
    )

    researcher = _get_researcher()

    # Tab-based navigation for sub-sections
    tabs = st.tabs([
        "\U0001f50d Niche Analysis",
        "\U0001f5fa\ufe0f Topical Map",
        "\U0001f4ca Content Gaps",
        "\U0001f3d7\ufe0f Content Silo",
        "\U0001f3af Competitors",
        "\U0001f525 Trending",
    ])

    with tabs[0]:
        _render_niche_analysis(researcher)

    with tabs[1]:
        _render_topical_map(researcher)

    with tabs[2]:
        _render_content_gaps(researcher)

    with tabs[3]:
        _render_content_silo(researcher)

    with tabs[4]:
        _render_competitors(researcher)

    with tabs[5]:
        _render_trending(researcher)


# Allow direct execution for testing
if __name__ == "__main__":
    render_topical_research_page()
