"""Full SEO Automation — Dashboard

Main Streamlit application with sidebar navigation.
Run with: streamlit run dashboard/app.py
"""

import logging
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="SEO Automation Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        text-align: left;
        padding: 12px 16px;
        border-radius: 10px;
        border: none;
        background: transparent;
        color: #e2e8f0 !important;
        font-size: 0.95rem;
        transition: all 0.2s;
        margin-bottom: 4px;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(59, 130, 246, 0.2) !important;
    }
    /* Active page button */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: rgba(59, 130, 246, 0.3) !important;
        border-left: 3px solid #3b82f6 !important;
    }
    /* Main content */
    .main .block-container { padding-top: 2rem; }
    /* Cards */
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
</style>
""", unsafe_allow_html=True)


def main():
    # Initialize session state for navigation
    if "current_page" not in st.session_state:
        st.session_state.current_page = "overview"

    # Sidebar
    with st.sidebar:
        st.markdown("### 🚀 SEO Automation")
        st.markdown("---")

        # Navigation buttons
        pages = {
            "overview": ("🏠", "Overview"),
            "topics": ("🌐", "Topical Research"),
            "keywords": ("🔍", "Keywords"),
            "content": ("📝", "Blog Content"),
            "technical": ("🔧", "Technical Audit"),
            "onpage": ("📄", "On-Page SEO"),
            "local_seo": ("📍", "Local SEO"),
            "link_building": ("🔗", "Link Building"),
            "rankings": ("📊", "Rank Tracking"),
            "seo_news": ("📰", "SEO News & Strategy"),
            "reports": ("📈", "Reports"),
        }

        for page_id, (icon, label) in pages.items():
            is_active = st.session_state.current_page == page_id
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{page_id}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state.current_page = page_id
                st.rerun()

        st.markdown("---")

        # Settings button (prominent)
        if st.button(
            "⚙️  Settings & API Keys",
            key="nav_settings",
            type="primary" if st.session_state.current_page == "settings" else "secondary",
            use_container_width=True,
        ):
            st.session_state.current_page = "settings"
            st.rerun()

        st.markdown("---")
        st.markdown(
            "<div style='text-align:center; font-size:0.75rem; opacity:0.5;'>v2.1 · $100/mo Budget</div>",
            unsafe_allow_html=True,
        )

    # Main content area — route to pages
    page = st.session_state.current_page

    if page == "settings":
        from pages.settings import render_settings_page
        render_settings_page()
    elif page == "local_seo":
        from pages.local_seo import render_local_seo_page
        render_local_seo_page()
    elif page == "seo_news":
        from pages.seo_news import render_seo_news_page
        render_seo_news_page()
    elif page == "topics":
        from pages.topical_research import render_topical_research_page
        render_topical_research_page()
    elif page == "keywords":
        from pages.keywords import render_keywords_page
        render_keywords_page()
    elif page == "content":
        from pages.blog_content import render_blog_content_page
        render_blog_content_page()
    elif page == "technical":
        from pages.technical_audit import render_technical_audit_page
        render_technical_audit_page()
    elif page == "onpage":
        from pages.onpage_seo import render_onpage_seo_page
        render_onpage_seo_page()
    elif page == "link_building":
        from pages.link_building import render_link_building_page
        render_link_building_page()
    elif page == "rankings":
        from pages.rank_tracking import render_rank_tracking_page
        render_rank_tracking_page()
    elif page == "reports":
        from pages.reports import render_reports_page
        render_reports_page()
    elif page == "overview":
        render_overview()
    else:
        render_placeholder(page, pages.get(page, ("", page))[1])


def render_overview():
    """Render the overview/home page with reporting widgets."""
    st.title("🏠 SEO Automation Dashboard")
    st.markdown("Welcome to your **Full SEO Automation** control center.")

    # Try to load real data from reporting engine
    try:
        from src.modules.reporting.report_engine import ReportEngine
        from src.modules.reporting.widgets import ReportWidgets
        from src.database import get_session
        from src.models.audit import SiteAudit
        from src.models.ranking import RankingRecord, VisibilityScore
        from src.models.backlink import Backlink
        from src.models.content import BlogPost
        from src.models.keyword import Keyword

        # Find tracked domains
        domains = set()
        with get_session() as session:
            for row in session.query(SiteAudit.domain).distinct().all():
                domains.add(row[0])
            for row in session.query(RankingRecord.domain).distinct().all():
                domains.add(row[0])
            keyword_count = session.query(Keyword).count()
            content_count = session.query(BlogPost).count()
            backlink_count = session.query(Backlink).count()

        domains = sorted(domains)

        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🔍 Keywords Tracked", str(keyword_count),
                      help="Total keywords in database")
        with col2:
            st.metric("📝 Content Pieces", str(content_count),
                      help="Blog posts created")
        with col3:
            # Get latest tech score
            tech_score = "--"
            if domains:
                with get_session() as session:
                    from sqlalchemy import desc
                    latest = session.query(SiteAudit).order_by(
                        desc(SiteAudit.created_at)
                    ).first()
                    if latest and latest.overall_score is not None:
                        tech_score = str(int(latest.overall_score))
            st.metric("🔧 Tech Score", tech_score,
                      help="Latest technical audit score")
        with col4:
            st.metric("🔗 Backlinks", str(backlink_count),
                      help="Total backlinks tracked")

        st.markdown("---")

        if domains:
            # Domain selector for overview
            selected_domain = st.selectbox(
                "Select domain for overview", domains,
                key="overview_domain_select"
            )

            if selected_domain:
                engine = ReportEngine()
                try:
                    scores = engine.aggregate_scores(selected_domain)
                    overall = scores.get("overall_score", 0)

                    # Overall score gauge
                    gauge_col1, gauge_col2, gauge_col3 = st.columns([1, 2, 1])
                    with gauge_col2:
                        ReportWidgets.score_gauge(
                            int(overall), "Overall SEO Health", size="large"
                        )

                    st.markdown("---")
                    st.markdown("### Module Scores")

                    # Build module scores dict for grid
                    module_scores = {}
                    score_keys = [
                        ("technical_score", "Technical"),
                        ("onpage_score", "On-Page"),
                        ("local_score", "Local SEO"),
                        ("content_score", "Content"),
                        ("backlink_score", "Backlinks"),
                        ("visibility_score", "Visibility"),
                    ]
                    for key, label in score_keys:
                        val = scores.get(key, 0)
                        # Determine trend from trends data
                        trends = scores.get("trends", {})
                        current = trends.get("current", {})
                        previous = trends.get("previous", {})
                        cur_val = current.get(key, 0)
                        prev_val = previous.get(key, 0)
                        if cur_val > prev_val:
                            trend = "up"
                        elif cur_val < prev_val:
                            trend = "down"
                        else:
                            trend = "stable"
                        module_scores[key] = {
                            "score": int(val) if val else 0,
                            "trend": trend,
                            "label": label,
                        }

                    ReportWidgets.module_score_grid(module_scores)

                except Exception as exc:
                    logger.error("Failed to load scores: %s", exc)
                    st.warning("Could not load module scores. Run some audits first.")

            st.markdown("---")

        else:
            st.info(
                "👋 **Getting Started:** Go to **⚙️ Settings & API Keys** in the sidebar "
                "to configure your API keys, then run a Technical Audit or Rank Tracking "
                "to start seeing data here."
            )

    except ImportError as exc:
        logger.warning("Reporting module not fully available: %s", exc)
        # Fallback to basic overview
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🔍 Keywords Tracked", "0", help="Total keywords in database")
        with col2:
            st.metric("📝 Content Pieces", "0", help="Blog posts created")
        with col3:
            st.metric("🔧 Tech Score", "--", help="Latest technical audit score")
        with col4:
            st.metric("🔗 Backlinks", "0", help="Total backlinks tracked")

        st.markdown("---")
        st.info(
            "👋 **Getting Started:** Go to **⚙️ Settings & API Keys** in the sidebar "
            "to configure your API keys before running any modules."
        )

    except Exception as exc:
        logger.error("Overview error: %s", exc)
        st.error("An error occurred loading the dashboard overview.")

    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🔧 Run Technical Audit", use_container_width=True):
            st.session_state.current_page = "technical"
            st.rerun()
    with c2:
        if st.button("📝 Generate Content", use_container_width=True):
            st.session_state.current_page = "content"
            st.rerun()
    with c3:
        if st.button("📈 View Reports", use_container_width=True):
            st.session_state.current_page = "reports"
            st.rerun()


def render_placeholder(page_id: str, page_name: str):
    """Placeholder for pages not yet built."""
    st.title(f"{page_name}")
    st.info(f"🚧 The **{page_name}** module is coming in a future phase. Stay tuned!")


if __name__ == "__main__":
    main()
