"""SEO News & Strategy Dashboard Page."""

import streamlit as st
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def get_event_loop():
    """Get or create an event loop for async operations."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def render_seo_news_page():
    """Render the SEO News & Strategy page."""
    st.title("📰 SEO News & Strategy Tracker")
    st.markdown("*Scrape SEO news, extract strategies, verify them, and auto-upgrade your system.*")
    st.divider()

    # Initialize session state
    if "scraped_articles" not in st.session_state:
        st.session_state.scraped_articles = []
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = None
    if "scrape_status" not in st.session_state:
        st.session_state.scrape_status = "idle"

    # --- PDF Report Download ---
    with st.expander("📄 Download PDF Report", expanded=False):
        st.markdown("Generate a professional narrative PDF report of SEO news and strategies.")
        if st.button("Generate PDF Report", type="primary", key="sn_pdf_btn"):
            try:
                from dashboard.export_helper import generate_seo_news_pdf
                news_data = {
                    "articles": st.session_state.get("scraped_articles", []),
                    "strategies": st.session_state.get("sn_strategies", []),
                }
                pdf_path = generate_seo_news_pdf(news_data)
                with open(pdf_path, "rb") as fh:
                    st.download_button("⬇️ Download PDF", fh.read(),
                        file_name=pdf_path.split("/")[-1], mime="application/pdf", key="sn_pdf_dl")
                st.success("PDF report generated!")
            except Exception as exc:
                st.error("PDF generation failed: " + str(exc))

    # ---- Tabs ----
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Scrape News", "📊 Strategies", "✅ Verified", "🚀 Upgrades", "📜 History"
    ])

    # =========================
    # TAB 1: Scrape News
    # =========================
    with tab1:
        st.subheader("🔍 Scrape SEO News Sources")

        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("### 📡 Configured Sources")
            from src.modules.seo_news.scraper import DEFAULT_SOURCES

            source_data = []
            for src in DEFAULT_SOURCES:
                source_data.append({
                    "Name": src["name"],
                    "Category": src.get("category", "general").title(),
                    "Type": src.get("source_type", "rss").upper(),
                    "Reliability": f"{'⭐' * int(src.get('reliability_score', 0.5) * 5)}",
                })

            st.dataframe(source_data, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("### ⚙️ Scrape Settings")
            max_age = st.slider("Max article age (days)", 1, 90, 30)
            fetch_content = st.checkbox("Fetch full article content", value=True)
            st.markdown("---")

            if st.button("🚀 Start Scraping", type="primary", use_container_width=True):
                st.session_state.scrape_status = "running"
                with st.spinner("Scraping SEO news sources..."):
                    try:
                        from src.modules.seo_news.scraper import SEONewsScraper
                        scraper = SEONewsScraper(max_age_days=max_age)
                        loop = get_event_loop()

                        if fetch_content:
                            articles = loop.run_until_complete(scraper.scrape_and_extract())
                        else:
                            articles = loop.run_until_complete(scraper.scrape_all_sources())

                        loop.run_until_complete(scraper.close())
                        st.session_state.scraped_articles = articles
                        st.session_state.scrape_status = "done"
                        st.success(f"✅ Scraped {len(articles)} articles!")
                    except Exception as e:
                        st.session_state.scrape_status = "error"
                        st.error(f"❌ Scraping failed: {e}")

        # Show scraped articles
        articles = st.session_state.scraped_articles
        if articles:
            st.markdown("---")
            st.subheader(f"📰 Scraped Articles ({len(articles)})")

            # Filters
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                categories = sorted(set(a.get("category", "general") for a in articles))
                cat_filter = st.selectbox("Category", ["All"] + categories)
            with col_f2:
                sources = sorted(set(a.get("source_name", "") for a in articles))
                src_filter = st.selectbox("Source", ["All"] + sources)
            with col_f3:
                actionable_only = st.checkbox("Actionable only", value=False)

            # Filter articles
            filtered = articles
            if cat_filter != "All":
                filtered = [a for a in filtered if a.get("category") == cat_filter]
            if src_filter != "All":
                filtered = [a for a in filtered if a.get("source_name") == src_filter]
            if actionable_only:
                filtered = [a for a in filtered if a.get("is_actionable", False)]

            # Sort by relevance
            filtered.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)

            for article in filtered[:50]:  # Show max 50
                score = article.get("relevance_score", 0)
                icon = "🟢" if score >= 0.6 else "🟡" if score >= 0.3 else "⚪"
                actionable_badge = " 🎯" if article.get("is_actionable") else ""

                with st.expander(f"{icon} {article.get('title', 'Untitled')}{actionable_badge}"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Source", article.get("source_name", "Unknown"))
                    c2.metric("Relevance", f"{score:.0%}")
                    pub = article.get("published_at", "")
                    c3.metric("Published", str(pub)[:10] if pub else "N/A")

                    if article.get("summary"):
                        st.markdown(f"**Summary:** {article['summary']}")

                    if article.get("url"):
                        st.markdown(f"[🔗 Read Full Article]({article['url']})")

                    if article.get("tags"):
                        st.markdown(f"**Tags:** {'  '.join(article['tags'][:10])}")

    # =========================
    # TAB 2: Extracted Strategies
    # =========================
    with tab2:
        st.subheader("📊 AI Strategy Extraction")

        if not st.session_state.scraped_articles:
            st.info("👆 First scrape news articles in the Scrape News tab.")
        else:
            actionable = [a for a in st.session_state.scraped_articles if a.get("is_actionable")]
            st.markdown(f"**{len(actionable)}** actionable articles ready for AI analysis.")

            if st.button("🤖 Extract Strategies with AI", type="primary"):
                with st.spinner("Analyzing articles with AI... (this may take a few minutes)"):
                    try:
                        from src.modules.seo_news.strategy_analyzer import SEOStrategyAnalyzer
                        analyzer = SEOStrategyAnalyzer(llm_client=None)  # TODO: inject real client
                        loop = get_event_loop()
                        results = loop.run_until_complete(
                            analyzer.full_pipeline(st.session_state.scraped_articles)
                        )
                        st.session_state.analysis_results = results
                        st.success(
                            f"✅ Extracted {results['total_strategies_extracted']} strategies, "
                            f"{results['verified_strategies']} verified!"
                        )
                    except Exception as e:
                        st.error(f"❌ Analysis failed: {e}")

            # Show results
            results = st.session_state.analysis_results
            if results:
                # Summary metrics
                m1, m2, m3, m4 = st.columns(4)
                summary = results.get("summary", {})
                m1.metric("Total Strategies", summary.get("total_found", 0))
                m2.metric("Verified", summary.get("verified_count", 0))
                m3.metric("High Impact", summary.get("high_impact_count", 0))
                m4.metric("Quick Wins", summary.get("quick_wins_count", 0))

                st.markdown("---")

                # Strategy list
                for strategy in results.get("strategies", []):
                    impact = strategy.get("estimated_impact", "medium")
                    impact_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(impact, "⚪")
                    status = strategy.get("verification_status", "pending")
                    status_icon = {"verified": "✅", "rejected": "❌", "pending": "⏳"}.get(status, "❓")

                    with st.expander(
                        f"{status_icon} {impact_icon} {strategy.get('title', 'Untitled')} "
                        f"[{strategy.get('category', '')}]"
                    ):
                        st.markdown(f"**Description:** {strategy.get('description', '')}")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Impact", impact.title())
                        c2.metric("Effort", strategy.get("estimated_effort", "medium").title())
                        c3.metric("Confidence", f"{strategy.get('confidence_score', 0):.0%}")

                        steps = strategy.get("implementation_steps", [])
                        if steps and isinstance(steps, list):
                            st.markdown("**Implementation Steps:**")
                            for i, step in enumerate(steps, 1):
                                step_text = step if isinstance(step, str) else step.get("step", str(step))
                                st.markdown(f"{i}. {step_text}")

    # =========================
    # TAB 3: Verified Strategies
    # =========================
    with tab3:
        st.subheader("✅ Verified Strategies")

        results = st.session_state.analysis_results
        if not results or not results.get("verified"):
            st.info("No verified strategies yet. Run the AI analysis first.")
        else:
            verified = results["verified"]
            st.success(f"**{len(verified)}** strategies verified and ready to apply!")

            for strategy in verified:
                with st.expander(f"✅ {strategy.get('title', '')}"):
                    st.markdown(f"**{strategy.get('description', '')}**")

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Category", strategy.get("category", "").replace("_", " ").title())
                    c2.metric("Impact", strategy.get("estimated_impact", "medium").title())
                    c3.metric("Effort", strategy.get("estimated_effort", "medium").title())
                    c4.metric("Confidence", f"{strategy.get('confidence_score', 0):.0%}")

                    ver = strategy.get("verification_result", {})
                    if ver:
                        st.markdown(f"**Evidence:** {ver.get('evidence', 'N/A')}")
                        st.markdown(f"**Risk Level:** {ver.get('risk_level', 'unknown')}")
                        st.markdown(f"**Google Compliant:** {'✅ Yes' if ver.get('google_compliant') else '❌ No'}")
                        action = ver.get("recommended_action", "monitor")
                        action_colors = {
                            "apply": "green", "test_first": "orange",
                            "monitor": "blue", "avoid": "red",
                        }
                        st.markdown(f"**Recommended Action:** :{action_colors.get(action, 'gray')}[{action.replace('_', ' ').title()}]")

    # =========================
    # TAB 4: Auto Upgrades
    # =========================
    with tab4:
        st.subheader("🚀 Auto-Upgrade System")

        results = st.session_state.analysis_results
        if not results or not results.get("upgrade_plans"):
            st.info("No upgrade plans available. Verify strategies first.")
        else:
            plans = results["upgrade_plans"]
            st.markdown(f"**{len(plans)}** upgrade plans ready.")

            for plan_entry in plans:
                strategy = plan_entry.get("strategy", {})
                plan = plan_entry.get("plan", {})

                auto_badge = "🤖 Auto" if plan.get("auto_applicable") else "🔧 Manual"
                with st.expander(f"{auto_badge} {strategy.get('title', '')}"):
                    st.markdown(f"**Affected Modules:** {'  '.join(plan.get('affected_modules', []))}")
                    st.markdown(f"**Est. Dev Time:** {plan.get('estimated_dev_time', 'Unknown')}")

                    changes = plan.get("changes_required", [])
                    if changes:
                        st.markdown("**Changes Required:**")
                        for change in changes:
                            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                                change.get("priority", "medium"), "⚪"
                            )
                            st.markdown(
                                f"- {priority_icon} **{change.get('module', '')}** "
                                f"({change.get('change_type', '')}) — "
                                f"{change.get('description', '')}")

                    # Apply button
                    if st.button(
                        f"🚀 Apply Upgrade",
                        key=f"apply_{strategy.get('title', '')[:20]}",
                    ):
                        with st.spinner("Applying upgrade..."):
                            try:
                                from src.modules.seo_news.auto_upgrader import SEOAutoUpgrader
                                upgrader = SEOAutoUpgrader()
                                result = upgrader.apply_strategy(strategy, plan)
                                if result["status"] == "applied":
                                    st.success(f"✅ Applied! {len(result['changes_made'])} changes made.")
                                elif result["status"] == "partial":
                                    st.warning(f"⚠️ Partial: {len(result['changes_made'])} done, {len(result['errors'])} errors.")
                                else:
                                    st.error(f"❌ Failed: {'  '.join(result['errors'])}")
                            except Exception as e:
                                st.error(f"❌ Upgrade error: {e}")

    # =========================
    # TAB 5: Upgrade History
    # =========================
    with tab5:
        st.subheader("📜 Upgrade History")

        try:
            from src.modules.seo_news.auto_upgrader import SEOAutoUpgrader
            upgrader = SEOAutoUpgrader()
            history = upgrader.get_upgrade_history()

            if not history:
                st.info("No upgrades applied yet.")
            else:
                for entry in reversed(history):
                    status = entry.get("status", "unknown")
                    status_icon = {
                        "applied": "✅", "partial": "⚠️",
                        "failed": "❌", "rolled_back": "↩️",
                    }.get(status, "❓")

                    with st.expander(
                        f"{status_icon} {entry.get('strategy_title', 'Unknown')} — "
                        f"{entry.get('applied_at', '')[:10]}"
                    ):
                        st.json(entry)

            # Pending enhancements
            st.markdown("---")
            st.subheader("📋 Pending Enhancements")
            enhancements = upgrader.get_pending_enhancements()
            if enhancements:
                for enh in enhancements:
                    st.markdown(
                        f"- **{enh.get('module', '')}**: "
                        f"{enh.get('description', '')} "
                        f"(Priority: {enh.get('priority', 'medium')})"
                    )
            else:
                st.info("No pending enhancements.")

            # Rollback button
            st.markdown("---")
            if st.button("↩️ Rollback Last Upgrade", type="secondary"):
                result = upgrader.rollback_last_upgrade()
                if result["status"] == "rolled_back":
                    st.success(f"✅ Rolled back! Restored from: {result['restored_from']}")
                else:
                    st.warning(result.get("message", "Rollback issue."))

        except Exception as e:
            st.error(f"Error loading history: {e}")


# Main entry point for Streamlit page
render_seo_news_page()
