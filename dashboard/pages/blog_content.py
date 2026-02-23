"""Blog Content Engine dashboard page for SEO Automation.

Provides an interactive Streamlit interface for AI-powered content
generation, quality checking, editorial calendar management,
batch article production, and multi-format export.
"""

import asyncio
import csv
import io
import json
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure project root is on the path
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.modules.blog_content.writer import BlogContentWriter, CONTENT_TYPES, TONES
from src.modules.blog_content.quality_checker import ContentQualityChecker
from src.modules.blog_content.content_manager import ContentManager

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
def _get_writer() -> BlogContentWriter:
    return BlogContentWriter()


@st.cache_resource
def _get_checker() -> ContentQualityChecker:
    return ContentQualityChecker()


@st.cache_resource
def _get_manager() -> ContentManager:
    return ContentManager()


# ------------------------------------------------------------------
# Grade badge helper
# ------------------------------------------------------------------

def _grade_color(grade: str) -> str:
    """Return colour hex for a letter grade."""
    mapping = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}
    return mapping.get(grade, "#6b7280")


# ------------------------------------------------------------------
# Tab renderers
# ------------------------------------------------------------------

def _render_write_tab(writer: BlogContentWriter) -> None:
    """Tab: Write Content."""
    st.markdown("### AI Content Writer")
    st.markdown(
        "Enter a keyword or topic, configure options, and generate "
        "a full SEO-optimised article."
    )

    with st.form("write_content_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            keyword = st.text_input(
                "Target Keyword / Topic",
                placeholder="best seo tools 2025",
                key="wc_keyword",
            )
        with col2:
            content_type = st.selectbox(
                "Content Type",
                options=list(CONTENT_TYPES),
                index=list(CONTENT_TYPES).index("blog_post"),
                key="wc_type",
            )

        col3, col4, col5 = st.columns(3)
        with col3:
            tone = st.selectbox("Tone", options=list(TONES), index=0, key="wc_tone")
        with col4:
            word_count = st.number_input(
                "Target Word Count", min_value=500, max_value=5000,
                value=1500, step=100, key="wc_words",
            )
        with col5:
            include_faq = st.checkbox("Include FAQ Section", value=True, key="wc_faq")

        submitted = st.form_submit_button(
            "Generate Article", use_container_width=True, type="primary"
        )

    if submitted and keyword:
        with st.status("Generating article...", expanded=True) as status:
            st.write("Creating content brief...")
            try:
                brief = _run_async(
                    writer.generate_brief(keyword, content_type=content_type, target_word_count=word_count)
                )
                st.write("Brief created with " + str(len(brief.get("outline", []))) + " sections")

                st.write("Writing article section by section...")
                article = _run_async(
                    writer.write_article(brief, tone=tone, include_faq=include_faq)
                )
                st.session_state["last_article"] = article
                st.session_state["last_brief"] = brief
                status.update(label="Article generated!", state="complete")
            except Exception as exc:
                status.update(label="Generation failed", state="error")
                st.error("Error: " + str(exc))
                return

    # Display last generated article
    article = st.session_state.get("last_article")
    if article:
        st.markdown("---")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.metric("Words", article.get("word_count", 0))
        with col_b:
            st.metric("Sections", len(article.get("sections", [])))
        with col_c:
            st.metric("Reading Time", str(article.get("estimated_reading_time", 0)) + " min")
        with col_d:
            st.metric("FAQs", len(article.get("faq_section", [])))

        st.markdown("### Article Preview")
        with st.expander("Full Article (Markdown)", expanded=True):
            st.markdown(article.get("content", ""))

        with st.expander("Article Metadata"):
            st.json({
                "title": article.get("title"),
                "meta_description": article.get("meta_description"),
                "keyword": article.get("keyword"),
                "content_type": article.get("content_type"),
                "tone": article.get("tone"),
                "sections": article.get("sections", []),
            })
    elif submitted:
        st.warning("Please enter a keyword to generate content.")


def _render_quality_tab(checker: ContentQualityChecker) -> None:
    """Tab: Quality Check."""
    st.markdown("### Content Quality Checker")
    st.markdown(
        "Paste content or use a previously generated article to run "
        "a comprehensive quality analysis."
    )

    # Source selection
    source = st.radio(
        "Content Source",
        ["Paste Content", "Use Last Generated Article"],
        horizontal=True,
        key="qc_source",
    )

    content = ""
    if source == "Paste Content":
        content = st.text_area(
            "Content (Markdown)",
            height=300,
            placeholder="Paste your article content here...",
            key="qc_content",
        )
    else:
        article = st.session_state.get("last_article")
        if article:
            content = article.get("content", "")
            st.info("Using generated article: " + article.get("title", "Untitled"))
        else:
            st.warning("No generated article found. Generate one in the Write tab first.")

    target_kw = st.text_input("Target Keyword (optional)", key="qc_keyword")

    if st.button("Run Quality Check", type="primary", use_container_width=True, key="qc_run"):
        if not content.strip():
            st.warning("Please provide content to check.")
            return

        with st.spinner("Analysing content quality..."):
            report = checker.check_quality(content, target_keyword=target_kw)
            st.session_state["last_quality_report"] = report

    report = st.session_state.get("last_quality_report")
    if report:
        st.markdown("---")

        # Grade badge
        grade = report.get("grade", "F")
        overall = report.get("overall_score", 0)
        color = _grade_color(grade)
        st.markdown(
            '<div style="text-align:center; padding:10px;">'
            '<span style="font-size:3em; font-weight:bold; color:' + color + ';">'
            + grade + '</span>'
            '<br><span style="font-size:1.2em; color:#6b7280;">'
            + str(overall) + '/100</span></div>',
            unsafe_allow_html=True,
        )

        # Score progress bars
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Readability**")
            st.progress(min(100, int(report.get("readability_score", 0))) / 100)
            st.caption(str(report.get("readability_score", 0)) + "/100")

            st.markdown("**Uniqueness**")
            st.progress(min(100, int(report.get("uniqueness_estimate", 0))) / 100)
            st.caption(str(report.get("uniqueness_estimate", 0)) + "/100")

        with col2:
            st.markdown("**SEO Score**")
            st.progress(min(100, int(report.get("seo_score", 0))) / 100)
            st.caption(str(report.get("seo_score", 0)) + "/100")

            st.markdown("**Heading Structure**")
            heading_ok = report.get("heading_structure_ok", False)
            st.progress(1.0 if heading_ok else 0.4)
            st.caption("Valid" if heading_ok else "Needs Improvement")

        # Stats row
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("Word Count", report.get("word_count", 0))
        with mc2:
            st.metric("Reading Time", str(report.get("reading_time", 0)) + " min")
        with mc3:
            st.metric("Keyword Density", str(report.get("keyword_density", 0)) + "%")
        with mc4:
            st.metric("Has FAQ", "Yes" if report.get("has_faq") else "No")

        # Issues and suggestions
        issues = report.get("issues", [])
        suggestions = report.get("suggestions", [])

        if issues:
            st.markdown("#### Issues Found")
            for issue in issues:
                st.warning(issue)

        if suggestions:
            st.markdown("#### Suggestions")
            for suggestion in suggestions:
                st.info(suggestion)

        # AI suggestions button
        if st.button("Get AI Improvement Suggestions", key="qc_ai_suggest"):
            with st.spinner("Getting AI suggestions..."):
                try:
                    ai_suggestions = _run_async(
                        checker.suggest_improvements(report)
                    )
                    st.session_state["ai_suggestions"] = ai_suggestions
                except Exception as exc:
                    st.error("Failed to get AI suggestions: " + str(exc))

        ai_sugg = st.session_state.get("ai_suggestions", [])
        if ai_sugg:
            st.markdown("#### AI Improvement Suggestions")
            for s in ai_sugg:
                priority = s.get("priority", "medium")
                icon = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F7E2"}.get(priority, "\U0001F7E1")
                area = s.get("area", "general")
                st.markdown(
                    icon + " **[" + area.upper() + "]** " + s.get("current_issue", "")
                )
                st.markdown("   \u2192 " + s.get("recommendation", ""))
                st.caption(
                    "Priority: " + priority
                    + " | Impact: " + s.get("estimated_impact", "medium")
                )
                st.markdown("---")


def _render_calendar_tab(manager: ContentManager) -> None:
    """Tab: Editorial Calendar."""
    st.markdown("### Editorial Calendar")
    st.markdown(
        "Generate a publishing schedule from a list of topics or keywords."
    )

    with st.form("calendar_form"):
        topics_text = st.text_area(
            "Topics / Keywords (one per line)",
            placeholder="best seo tools 2025\nkeyword research guide\ncontent optimization tips",
            height=150,
            key="cal_topics",
        )
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", key="cal_start")
        with col2:
            frequency = st.selectbox(
                "Publishing Frequency",
                ["daily", "weekly", "biweekly", "monthly"],
                index=1,
                key="cal_freq",
            )
        submitted = st.form_submit_button(
            "Generate Calendar", use_container_width=True, type="primary"
        )

    if submitted and topics_text.strip():
        lines = [l.strip() for l in topics_text.strip().split("\n") if l.strip()]
        topic_dicts = [{"keyword": kw, "content_type": "blog_post"} for kw in lines]
        calendar = manager.create_editorial_calendar(
            topic_dicts,
            start_date=start_date.strftime("%Y-%m-%d"),
            frequency=frequency,
        )
        st.session_state["editorial_calendar"] = calendar

    calendar = st.session_state.get("editorial_calendar", [])
    if calendar:
        st.markdown("---")
        st.markdown("**" + str(len(calendar)) + " entries generated**")

        # Display as table
        import pandas as pd
        df = pd.DataFrame(calendar)
        st.dataframe(df, use_container_width=True)

        # CSV download
        csv_str = manager.calendar_to_csv_string(calendar)
        st.download_button(
            label="Download CSV",
            data=csv_str,
            file_name="editorial_calendar.csv",
            mime="text/csv",
            key="cal_csv_dl",
        )


def _render_batch_tab(writer: BlogContentWriter) -> None:
    """Tab: Batch Generate."""
    st.markdown("### Batch Article Generator")
    st.markdown(
        "Upload a CSV or enter multiple topics to generate articles in batch."
    )

    input_method = st.radio(
        "Input Method", ["Enter Topics", "Upload CSV"], horizontal=True, key="batch_method"
    )

    topics: list[dict[str, Any]] = []

    if input_method == "Enter Topics":
        topics_text = st.text_area(
            "Topics (one per line: keyword | content_type | word_count)",
            placeholder="best seo tools | blog_post | 1500\nkeyword research | how_to | 2000",
            height=150,
            key="batch_topics",
        )
        if topics_text.strip():
            for line in topics_text.strip().split("\n"):
                parts = [p.strip() for p in line.split("|")]
                if parts:
                    t = {"keyword": parts[0]}
                    if len(parts) > 1:
                        t["content_type"] = parts[1]
                    if len(parts) > 2:
                        try:
                            t["word_count"] = int(parts[2])
                        except ValueError:
                            t["word_count"] = 1500
                    topics.append(t)
    else:
        uploaded = st.file_uploader(
            "Upload CSV (columns: keyword, content_type, word_count)",
            type=["csv"],
            key="batch_csv",
        )
        if uploaded:
            try:
                content = uploaded.read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    t = {"keyword": row.get("keyword", "").strip()}
                    if row.get("content_type"):
                        t["content_type"] = row["content_type"].strip()
                    if row.get("word_count"):
                        try:
                            t["word_count"] = int(row["word_count"])
                        except ValueError:
                            pass
                    if t["keyword"]:
                        topics.append(t)
                st.success("Loaded " + str(len(topics)) + " topics from CSV")
            except Exception as exc:
                st.error("Failed to parse CSV: " + str(exc))

    if topics:
        st.markdown("**Topics to generate:**")
        for i, t in enumerate(topics):
            ct = t.get("content_type", "blog_post")
            wc = t.get("word_count", 1500)
            st.caption(
                str(i + 1) + ". " + t["keyword"]
                + " (" + ct + ", " + str(wc) + " words)"
            )

    if st.button(
        "Generate All Articles",
        type="primary",
        use_container_width=True,
        disabled=len(topics) == 0,
        key="batch_generate",
    ):
        progress = st.progress(0)
        status_text = st.empty()
        results: list[dict[str, Any]] = []

        for i, topic in enumerate(topics):
            kw = topic.get("keyword", "")
            status_text.text("Generating " + str(i + 1) + "/" + str(len(topics)) + ": " + kw)
            try:
                brief = _run_async(
                    writer.generate_brief(
                        kw,
                        content_type=topic.get("content_type", "blog_post"),
                        target_word_count=topic.get("word_count", 1500),
                    )
                )
                article = _run_async(writer.write_article(brief))
                article["index"] = i
                results.append(article)
            except Exception as exc:
                results.append({"error": str(exc), "keyword": kw, "index": i})
            progress.progress((i + 1) / len(topics))

        st.session_state["batch_results"] = results
        status_text.text("Batch generation complete!")
        succeeded = sum(1 for r in results if "error" not in r)
        st.success(str(succeeded) + "/" + str(len(topics)) + " articles generated successfully")

    batch_results = st.session_state.get("batch_results", [])
    if batch_results:
        st.markdown("---")
        for article in batch_results:
            if "error" in article:
                st.error(
                    "Failed: " + article.get("keyword", "Unknown")
                    + " — " + article["error"]
                )
            else:
                with st.expander(
                    article.get("title", "Untitled")
                    + " (" + str(article.get("word_count", 0)) + " words)"
                ):
                    st.markdown(article.get("content", "")[:2000] + "...")


def _render_export_tab(manager: ContentManager) -> None:
    """Tab: Export."""
    st.markdown("### Export Content")
    # --- PDF Report Download ---
    st.markdown("**📄 Professional PDF Report**")
    st.markdown("Generate a narrative PDF report of your content analysis with quality scores.")
    if st.button("Generate PDF Report", type="primary", key="bc_pdf_btn"):
        try:
            from dashboard.export_helper import generate_content_pdf
            content_data = {
                "articles": st.session_state.get("bc_articles", []),
                "quality_stats": st.session_state.get("bc_quality_stats", {}),
            }
            pdf_path = generate_content_pdf(content_data)
            with open(pdf_path, "rb") as fh:
                st.download_button("⬇️ Download PDF", fh.read(),
                    file_name=pdf_path.split("/")[-1], mime="application/pdf", key="bc_pdf_dl")
            st.success("PDF report generated!")
        except Exception as exc:
            st.error("PDF generation failed: " + str(exc))
    st.divider()
    st.markdown("Download generated content in various formats.")

    # Determine available articles
    articles: list[dict[str, Any]] = []
    last_article = st.session_state.get("last_article")
    batch_results = st.session_state.get("batch_results", [])
    batch_articles = [a for a in batch_results if "error" not in a]

    source = st.radio(
        "Export Source",
        ["Last Generated Article", "All Batch Articles"],
        horizontal=True,
        key="exp_source",
    )

    if source == "Last Generated Article":
        if last_article:
            articles = [last_article]
            st.info("Exporting: " + last_article.get("title", "Untitled"))
        else:
            st.warning("No article available. Generate one first.")
            return
    else:
        if batch_articles:
            articles = batch_articles
            st.info("Exporting " + str(len(articles)) + " articles")
        else:
            st.warning("No batch articles available. Run batch generation first.")
            return

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    # Markdown download
    with col1:
        st.markdown("#### Markdown")
        if len(articles) == 1:
            md_content = articles[0].get("content", "")
            title = articles[0].get("title", "article")
            st.download_button(
                label="Download .md",
                data=md_content,
                file_name=title.replace(" ", "-").lower()[:50] + ".md",
                mime="text/markdown",
                key="dl_md",
                use_container_width=True,
            )
        else:
            combined_md = ""
            for a in articles:
                combined_md += a.get("content", "") + "\n\n---\n\n"
            st.download_button(
                label="Download All .md",
                data=combined_md,
                file_name="articles_export.md",
                mime="text/markdown",
                key="dl_md_all",
                use_container_width=True,
            )

    # HTML download
    with col2:
        st.markdown("#### HTML")
        try:
            import markdown as md_lib
            if len(articles) == 1:
                html_body = md_lib.markdown(articles[0].get("content", ""), extensions=["extra"])
                title = articles[0].get("title", "article")
                full_html = (
                    "<!DOCTYPE html><html><head>"
                    "<meta charset='UTF-8'>"
                    "<title>" + title + "</title>"
                    "<style>body{font-family:sans-serif;max-width:800px;margin:40px auto;"
                    "padding:0 20px;line-height:1.7;}</style>"
                    "</head><body>" + html_body + "</body></html>"
                )
                st.download_button(
                    label="Download .html",
                    data=full_html,
                    file_name=title.replace(" ", "-").lower()[:50] + ".html",
                    mime="text/html",
                    key="dl_html",
                    use_container_width=True,
                )
            else:
                combined_parts = []
                for a in articles:
                    combined_parts.append(
                        "<article>" + md_lib.markdown(a.get("content", ""), extensions=["extra"]) + "</article><hr>"
                    )
                full_html = (
                    "<!DOCTYPE html><html><head>"
                    "<meta charset='UTF-8'><title>Articles Export</title>"
                    "<style>body{font-family:sans-serif;max-width:800px;margin:40px auto;"
                    "padding:0 20px;line-height:1.7;}</style>"
                    "</head><body>" + "".join(combined_parts) + "</body></html>"
                )
                st.download_button(
                    label="Download All .html",
                    data=full_html,
                    file_name="articles_export.html",
                    mime="text/html",
                    key="dl_html_all",
                    use_container_width=True,
                )
        except ImportError:
            st.warning("Install `markdown` package for HTML export.")

    # WordPress XML download
    with col3:
        st.markdown("#### WordPress XML")
        if st.button("Generate WXR", key="gen_wxr", use_container_width=True):
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
                manager.export_wordpress_xml(articles, tmp.name)
                with open(tmp.name, "rb") as fh:
                    xml_data = fh.read()
                st.download_button(
                    label="Download .xml",
                    data=xml_data,
                    file_name="wordpress_export.xml",
                    mime="application/xml",
                    key="dl_xml",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error("WordPress XML export failed: " + str(exc))

    # Content stats
    if articles:
        st.markdown("---")
        st.markdown("### Content Statistics")
        stats = manager.get_content_stats(articles)
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.metric("Total Articles", stats.get("total_articles", 0))
        with sc2:
            st.metric("Avg Word Count", stats.get("avg_word_count", 0))
        with sc3:
            st.metric("Total Words", stats.get("total_word_count", 0))
        with sc4:
            st.metric("Avg Reading Time", str(stats.get("avg_reading_time", 0)) + " min")

        ct_dist = stats.get("content_types_distribution", {})
        if ct_dist:
            st.markdown("**Content Types:**")
            for ct_name, ct_count in ct_dist.items():
                st.caption(ct_name + ": " + str(ct_count))


# ------------------------------------------------------------------
# Main page renderer
# ------------------------------------------------------------------

def render_blog_content_page() -> None:
    """Render the Blog Content Engine page."""
    st.title("\U0001F4DD Blog Content Engine")
    st.markdown(
        "Generate SEO-optimised articles, check content quality, "
        "plan your editorial calendar, and export in multiple formats."
    )

    writer = _get_writer()
    checker = _get_checker()
    manager = _get_manager()

    tabs = st.tabs([
        "\U0001F4DD Write Content",
        "\u2705 Quality Check",
        "\U0001F4CB Editorial Calendar",
        "\U0001F4E6 Batch Generate",
        "\U0001F4E5 Export",
    ])

    with tabs[0]:
        _render_write_tab(writer)
    with tabs[1]:
        _render_quality_tab(checker)
    with tabs[2]:
        _render_calendar_tab(manager)
    with tabs[3]:
        _render_batch_tab(writer)
    with tabs[4]:
        _render_export_tab(manager)


# Allow direct execution for testing
if __name__ == "__main__":
    render_blog_content_page()
