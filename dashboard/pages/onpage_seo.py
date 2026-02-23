"""On-Page SEO — Streamlit dashboard page.

Provides a multi-tab interface for page analysis, meta tag optimization,
schema markup generation, internal link analysis, image auditing,
content optimization, E-E-A-T checks, and report export.
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


def _score_color(score: float) -> str:
    if score >= 80:
        return "#22c55e"
    if score >= 60:
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


def _severity_badge(stype: str) -> str:
    colors = {"error": "#ef4444", "warning": "#f97316", "info": "#3b82f6"}
    c = colors.get(stype, "#6b7280")
    return (
        "<span style=\"background:{c};color:white;padding:2px 8px;"
        "border-radius:4px;font-size:0.8rem;font-weight:bold;\">"
        "{sev}</span>"
    ).format(c=c, sev=stype.upper())


def _get_optimizer():
    """Instantiate OnPageOptimizer with available integrations."""
    try:
        from src.integrations.llm_client import LLMClient
        llm = LLMClient()
    except Exception:
        llm = None
    try:
        from src.integrations.serp_scraper import SERPScraper
        serp = SERPScraper()
    except Exception:
        serp = None
    from src.modules.onpage_seo.optimizer import OnPageOptimizer
    return OnPageOptimizer(llm_client=llm, serp_scraper=serp)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_onpage_seo_page():
    """Render the On-Page SEO dashboard page."""
    st.title("On-Page SEO Optimizer")

    # Session state defaults
    if "op_analysis" not in st.session_state:
        st.session_state.op_analysis = None
    if "op_meta" not in st.session_state:
        st.session_state.op_meta = None
    if "op_schema" not in st.session_state:
        st.session_state.op_schema = None
    if "op_links" not in st.session_state:
        st.session_state.op_links = None
    if "op_images" not in st.session_state:
        st.session_state.op_images = None
    if "op_content" not in st.session_state:
        st.session_state.op_content = None
    if "op_eeat" not in st.session_state:
        st.session_state.op_eeat = None
    if "op_running" not in st.session_state:
        st.session_state.op_running = False

    tabs = st.tabs([
        "\U0001f4c4 Page Analysis",
        "\U0001f3f7\ufe0f Meta Tags",
        "\U0001f4cb Schema Markup",
        "\U0001f517 Internal Links",
        "\U0001f5bc\ufe0f Images",
        "\u270d\ufe0f Content",
        "\U0001f3c5 E-E-A-T",
        "\U0001f4e5 Export",
    ])

    with tabs[0]:
        _tab_page_analysis()
    with tabs[1]:
        _tab_meta_tags()
    with tabs[2]:
        _tab_schema_markup()
    with tabs[3]:
        _tab_internal_links()
    with tabs[4]:
        _tab_images()
    with tabs[5]:
        _tab_content()
    with tabs[6]:
        _tab_eeat()
    with tabs[7]:
        _tab_export()


# ---------------------------------------------------------------------------
# Tab: Page Analysis
# ---------------------------------------------------------------------------

def _tab_page_analysis():
    st.header("Full Page Analysis")
    st.markdown("Enter a URL and optional target keyword for comprehensive on-page SEO analysis.")

    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input(
            "Page URL",
            placeholder="https://example.com/page",
            key="op_url_input",
        )
    with col2:
        keyword = st.text_input(
            "Target Keyword (optional)",
            placeholder="e.g. best seo tools",
            key="op_kw_input",
        )

    if st.button("Analyze Page", type="primary", key="op_run_btn", disabled=st.session_state.op_running):
        if not url:
            st.warning("Please enter a URL.")
            return
        st.session_state.op_running = True
        with st.spinner("Running on-page analysis..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.analyze_page(url, keyword))
                st.session_state.op_analysis = result
            except Exception as exc:
                st.error("Analysis failed: " + str(exc))
            finally:
                st.session_state.op_running = False

    analysis = st.session_state.op_analysis
    if not analysis:
        st.info("Run an analysis to see results here.")
        return

    if "error" in analysis:
        st.error(analysis["error"])
        return

    # Overall score
    col_score, col_grade, col_url = st.columns([1, 1, 2])
    with col_score:
        score = analysis.get("overall_score", 0)
        color = _score_color(score)
        st.markdown(
            "<div style='text-align:center;'>"
            "<div style='font-size:2.5rem;font-weight:bold;color:{c};'>{s}</div>"
            "<div style='font-size:0.9rem;color:#64748b;'>Overall Score</div>"
            "</div>".format(c=color, s=score),
            unsafe_allow_html=True,
        )
    with col_grade:
        st.markdown(
            "<div style='text-align:center;padding-top:5px;'>" +
            _grade_badge(analysis.get("grade", "F")) + "</div>",
            unsafe_allow_html=True,
        )
    with col_url:
        st.markdown("**URL:** " + analysis.get("url", ""))
        st.markdown("**Keyword:** " + analysis.get("target_keyword", "N/A"))
        elapsed = analysis.get("elapsed_seconds", 0)
        st.caption("Analysis completed in " + str(elapsed) + "s")

    st.markdown("---")

    # Category breakdown
    st.subheader("Category Scores")
    categories = analysis.get("categories", {})
    cols = st.columns(len(categories) if categories else 1)
    for idx, (cat, cat_score) in enumerate(categories.items()):
        with cols[idx]:
            label = cat.replace("_", " ").title()
            color = _score_color(cat_score)
            st.markdown(
                "<div style='text-align:center;padding:10px;background:#f8fafc;"
                "border-radius:8px;border:1px solid #e2e8f0;'>"
                "<div style='font-size:1.5rem;font-weight:bold;color:{c};'>{s}</div>"
                "<div style='font-size:0.8rem;color:#64748b;'>{lbl}</div>"
                "</div>".format(c=color, s=int(cat_score), lbl=label),
                unsafe_allow_html=True,
            )

    # Issues summary
    st.markdown("---")
    st.subheader("Issues Found")
    for section_key in ("meta_tags", "technical", "content", "images",
                        "internal_links", "schema", "eeat"):
        section = analysis.get(section_key, {})
        issues = section.get("issues", [])
        if issues:
            label = section_key.replace("_", " ").title()
            with st.expander(label + " (" + str(len(issues)) + " issues)", expanded=False):
                for issue in issues:
                    badge = _severity_badge(issue.get("type", "info"))
                    st.markdown(badge + " " + issue.get("msg", ""), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab: Meta Tags
# ---------------------------------------------------------------------------

def _tab_meta_tags():
    st.header("Meta Tag Optimization")

    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input("Page URL", key="op_meta_url", placeholder="https://example.com/page")
    with col2:
        kw = st.text_input("Target Keyword", key="op_meta_kw", placeholder="e.g. seo tools")

    if st.button("Optimize Meta Tags", type="primary", key="op_meta_btn"):
        if not url or not kw:
            st.warning("Please provide both URL and keyword.")
            return
        with st.spinner("Analyzing and optimizing meta tags..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.optimize_meta_tags(url, kw))
                st.session_state.op_meta = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    meta = st.session_state.op_meta
    if not meta:
        st.info("Enter a URL and keyword to get AI-optimized meta tag suggestions.")
        return

    if "error" in meta:
        st.error(meta["error"])
        return

    current = meta.get("current", {})
    st.subheader("Current Meta Tags")
    col_t, col_d = st.columns(2)
    with col_t:
        st.markdown("**Title** (" + str(current.get("title_length", 0)) + " chars)")
        st.code(current.get("title", "N/A"))
    with col_d:
        st.markdown("**Description** (" + str(current.get("description_length", 0)) + " chars)")
        st.code(current.get("description", "N/A"))

    suggestions = meta.get("suggestions", {})
    if isinstance(suggestions, dict):
        st.subheader("AI-Optimized Suggestions")
        titles = suggestions.get("titles", [])
        if titles:
            st.markdown("**Title Tag Options:**")
            for i, t in enumerate(titles, 1):
                text = t.get("text", "") if isinstance(t, dict) else str(t)
                length = t.get("length", len(text)) if isinstance(t, dict) else len(text)
                st.markdown(str(i) + ". " + text + " *(" + str(length) + " chars)*")

        descs = suggestions.get("descriptions", [])
        if descs:
            st.markdown("**Meta Description Options:**")
            for i, d in enumerate(descs, 1):
                text = d.get("text", "") if isinstance(d, dict) else str(d)
                length = d.get("length", len(text)) if isinstance(d, dict) else len(text)
                st.markdown(str(i) + ". " + text + " *(" + str(length) + " chars)*")


# ---------------------------------------------------------------------------
# Tab: Schema Markup
# ---------------------------------------------------------------------------

def _tab_schema_markup():
    st.header("Schema Markup Generator")

    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input("Page URL", key="op_schema_url", placeholder="https://example.com/page")
    with col2:
        schema_type = st.selectbox(
            "Schema Type",
            ["auto", "Article", "LocalBusiness", "FAQPage", "HowTo",
             "Product", "Organization", "BreadcrumbList"],
            key="op_schema_type",
        )

    if st.button("Generate Schema", type="primary", key="op_schema_btn"):
        if not url:
            st.warning("Please enter a URL.")
            return
        with st.spinner("Analyzing page and generating schema..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.generate_schema_markup(url, schema_type))
                st.session_state.op_schema = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    schema = st.session_state.op_schema
    if not schema:
        st.info("Enter a URL to auto-detect page type and generate JSON-LD schema markup.")
        return

    if "error" in schema:
        st.error(schema["error"])
        return

    st.subheader("Detected Type: " + schema.get("detected_type", "Unknown"))

    # JSON-LD output
    json_ld = schema.get("json_ld", "")
    st.markdown("**Generated JSON-LD:**")
    st.code(json_ld, language="json")

    # Copy button
    st.download_button(
        label="Download JSON-LD",
        data=json_ld,
        file_name="schema_markup.json",
        mime="application/json",
    )

    # Validation
    validation = schema.get("validation", {})
    if validation.get("is_valid"):
        st.success("Schema is valid!")
    else:
        st.warning("Schema has validation issues.")

    errors = validation.get("errors", [])
    if errors:
        st.markdown("**Errors:**")
        for e in errors:
            st.markdown("- " + e)

    warnings = validation.get("warnings", [])
    if warnings:
        st.markdown("**Warnings:**")
        for w in warnings:
            st.markdown("- " + w)


# ---------------------------------------------------------------------------
# Tab: Internal Links
# ---------------------------------------------------------------------------

def _tab_internal_links():
    st.header("Internal Link Analysis")

    url = st.text_input("Page URL", key="op_links_url", placeholder="https://example.com/page")

    if st.button("Analyze Internal Links", type="primary", key="op_links_btn"):
        if not url:
            st.warning("Please enter a URL.")
            return
        with st.spinner("Analyzing internal links..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.analyze_internal_links(url))
                st.session_state.op_links = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    links = st.session_state.op_links
    if not links:
        st.info("Enter a URL to analyze its internal linking structure.")
        return

    if "error" in links:
        st.error(links["error"])
        return

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Internal Links", links.get("internal_count", 0))
    with col2:
        st.metric("External Links", links.get("external_count", 0))
    with col3:
        st.metric("Generic Anchors", links.get("generic_anchor_count", 0))

    # Issues
    issues = links.get("issues", [])
    if issues:
        st.subheader("Issues")
        for issue in issues:
            badge = _severity_badge(issue.get("type", "info"))
            st.markdown(badge + " " + issue.get("msg", ""), unsafe_allow_html=True)

    # Internal links table
    internal = links.get("internal_links", [])
    if internal:
        st.subheader("Internal Links")
        table_data = []
        for link in internal:
            table_data.append({
                "URL": link.get("href", "")[:80],
                "Anchor Text": link.get("anchor_text", "")[:60],
                "Nofollow": "Yes" if link.get("nofollow") else "No",
            })
        st.dataframe(table_data, use_container_width=True)

    # Anchor text distribution
    distribution = links.get("anchor_distribution", {})
    if distribution:
        st.subheader("Anchor Text Distribution")
        for text, count in list(distribution.items())[:15]:
            st.markdown("- **" + text + "**: " + str(count))

    # AI suggestions
    suggested = links.get("suggested_links", [])
    if suggested:
        st.subheader("Suggested Internal Links")
        for s in suggested:
            target = s.get("target_url", "")
            anchor = s.get("anchor_text", "")
            reason = s.get("reason", "")
            st.markdown("- Link to **" + target + "** with anchor: *" + anchor + "* — " + reason)


# ---------------------------------------------------------------------------
# Tab: Images
# ---------------------------------------------------------------------------

def _tab_images():
    st.header("Image Optimization Audit")

    url = st.text_input("Page URL", key="op_img_url", placeholder="https://example.com/page")

    if st.button("Audit Images", type="primary", key="op_img_btn"):
        if not url:
            st.warning("Please enter a URL.")
            return
        with st.spinner("Auditing images..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.optimize_images(url))
                st.session_state.op_images = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    images = st.session_state.op_images
    if not images:
        st.info("Enter a URL to audit all images on the page.")
        return

    if "error" in images:
        st.error(images["error"])
        return

    # Summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Images", images.get("total_images", 0))
    with col2:
        st.metric("Missing Alt", images.get("missing_alt", 0))
    with col3:
        st.metric("No Dimensions", images.get("missing_dimensions", 0))
    with col4:
        st.metric("Non-Modern Format", images.get("non_modern_format", 0))

    # Issues
    issues = images.get("issues", [])
    if issues:
        st.subheader("Issues")
        for issue in issues:
            badge = _severity_badge(issue.get("type", "info"))
            st.markdown(badge + " " + issue.get("msg", ""), unsafe_allow_html=True)

    # Image table
    img_list = images.get("images", [])
    if img_list:
        st.subheader("Image Details")
        table_data = []
        for img in img_list:
            alt_val = img.get("alt")
            alt_display = alt_val if alt_val else "MISSING"
            img_issues = ", ".join(img.get("issues", []))
            table_data.append({
                "Source": img.get("src", "")[:60],
                "Alt Text": alt_display[:50],
                "Dimensions": "Yes" if img.get("has_dimensions") else "No",
                "Lazy Load": "Yes" if img.get("has_lazy_loading") else "No",
                "Issues": img_issues[:60],
            })
        st.dataframe(table_data, use_container_width=True)

    # AI alt text suggestions
    ai_alts = images.get("ai_alt_suggestions", [])
    if ai_alts:
        st.subheader("AI-Generated Alt Text Suggestions")
        for suggestion in ai_alts:
            src = suggestion.get("src", "")
            alt = suggestion.get("alt", "")
            st.markdown("- **" + src[:50] + "**: " + alt)


# ---------------------------------------------------------------------------
# Tab: Content
# ---------------------------------------------------------------------------

def _tab_content():
    st.header("Content Optimization")

    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input("Page URL", key="op_content_url", placeholder="https://example.com/page")
    with col2:
        kw = st.text_input("Target Keyword", key="op_content_kw", placeholder="e.g. best seo tools")

    if st.button("Analyze Content", type="primary", key="op_content_btn"):
        if not url or not kw:
            st.warning("Please provide both URL and keyword.")
            return
        with st.spinner("Analyzing content optimization..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.analyze_content_optimization(url, kw))
                st.session_state.op_content = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    content = st.session_state.op_content
    if not content:
        st.info("Enter a URL and keyword to analyze content optimization.")
        return

    if "error" in content:
        st.error(content["error"])
        return

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Word Count", content.get("word_count", 0))
    with col2:
        st.metric("Keyword Density", str(content.get("keyword_density", 0)) + "%")
    with col3:
        st.metric("Readability", content.get("readability_score", 0))
    with col4:
        sc = content.get("score", 0)
        st.metric("Content Score", sc)

    # Keyword checks
    st.subheader("Keyword Usage")
    checks = [
        ("Keyword in first 100 words", content.get("keyword_in_first_100", False)),
        ("Keyword in headings", content.get("keyword_in_headings", False)),
    ]
    for label, passed in checks:
        icon = "\u2705" if passed else "\u274c"
        st.markdown(icon + " " + label)

    # LSI Keywords
    lsi_present = content.get("lsi_present", [])
    lsi_missing = content.get("lsi_missing", [])
    if lsi_present or lsi_missing:
        st.subheader("LSI / Semantic Keywords")
        col_p, col_m = st.columns(2)
        with col_p:
            st.markdown("**Present:**")
            for kw in lsi_present:
                st.markdown("\u2705 " + kw)
        with col_m:
            st.markdown("**Missing:**")
            for kw in lsi_missing:
                st.markdown("\u274c " + kw)

    # Suggestions
    suggestions = content.get("content_suggestions", [])
    if suggestions:
        st.subheader("AI Content Suggestions")
        for i, s in enumerate(suggestions, 1):
            st.markdown(str(i) + ". " + s)

    # Issues
    issues = content.get("issues", [])
    if issues:
        st.subheader("Issues")
        for issue in issues:
            badge = _severity_badge(issue.get("type", "info"))
            st.markdown(badge + " " + issue.get("msg", ""), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab: E-E-A-T
# ---------------------------------------------------------------------------

def _tab_eeat():
    st.header("E-E-A-T Signals")
    st.markdown("Check Experience, Expertise, Authoritativeness, and Trustworthiness signals.")

    url = st.text_input("Page URL", key="op_eeat_url", placeholder="https://example.com/page")

    if st.button("Check E-E-A-T", type="primary", key="op_eeat_btn"):
        if not url:
            st.warning("Please enter a URL.")
            return
        with st.spinner("Checking E-E-A-T signals..."):
            try:
                optimizer = _get_optimizer()
                result = _run_async(optimizer.check_eeat_signals(url))
                st.session_state.op_eeat = result
            except Exception as exc:
                st.error("Failed: " + str(exc))

    eeat = st.session_state.op_eeat
    if not eeat:
        st.info("Enter a URL to check E-E-A-T signals.")
        return

    if "error" in eeat:
        st.error(eeat["error"])
        return

    # Score
    score = eeat.get("score", 0)
    passed = eeat.get("passed", 0)
    total = eeat.get("total", 0)
    st.markdown(
        "**E-E-A-T Score:** "
        "<span style='font-size:1.5rem;font-weight:bold;color:{c};'>{s}/100</span>"
        " &nbsp; ({p}/{t} signals detected)".format(
            c=_score_color(score), s=score, p=passed, t=total
        ),
        unsafe_allow_html=True,
    )

    # Signals checklist
    st.subheader("Signal Checklist")
    signals = eeat.get("signals", {})
    signal_labels = {
        "author_byline": "Author byline / attribution",
        "author_credentials": "Author credentials (expertise indicators)",
        "date_published": "Publication date",
        "date_updated": "Last updated date",
        "citations_references": "Citations / references",
        "about_page_link": "Link to About page",
        "trust_signals": "Trust signals (testimonials, certifications)",
        "contact_info": "Contact information",
        "privacy_terms": "Privacy policy / Terms of service",
    }

    for key, label in signal_labels.items():
        found = signals.get(key, False)
        icon = "\u2705" if found else "\u274c"
        st.markdown(icon + " " + label)

    # Issues
    issues = eeat.get("issues", [])
    if issues:
        st.subheader("Recommendations")
        for issue in issues:
            badge = _severity_badge(issue.get("type", "info"))
            st.markdown(badge + " " + issue.get("msg", ""), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tab: Export
# ---------------------------------------------------------------------------

def _tab_export():
    st.header("Export Analysis")
    # --- PDF Report Download ---
    st.markdown("### 📥 Download PDF Report")
    st.markdown("Generate a professional narrative PDF report with radar charts and analysis.")
    if st.button("Generate PDF Report", type="primary", key="op_pdf_btn"):
        try:
            from dashboard.export_helper import generate_onpage_seo_pdf
            onpage_data = st.session_state.get("op_analysis_result", {})
            pdf_path = generate_onpage_seo_pdf(onpage_data)
            with open(pdf_path, "rb") as fh:
                st.download_button("⬇️ Download PDF", fh.read(),
                    file_name=pdf_path.split("/")[-1], mime="application/pdf", key="op_pdf_dl")
            st.success("PDF report generated!")
        except Exception as exc:
            st.error("PDF generation failed: " + str(exc))
    st.divider()

    analysis = st.session_state.op_analysis
    if not analysis:
        st.info("Run a full page analysis first (Page Analysis tab) to export results.")
        return

    if "error" in analysis:
        st.warning("Cannot export — the last analysis had errors.")
        return

    st.markdown(
        "**URL:** " + analysis.get("url", "") + "  \n"
        "**Score:** " + str(analysis.get("overall_score", 0)) + " ("
        + analysis.get("grade", "F") + ")"
    )

    # JSON export
    json_str = json.dumps(analysis, indent=2, default=str)
    st.download_button(
        label="Download Full Analysis (JSON)",
        data=json_str,
        file_name="onpage_seo_analysis.json",
        mime="application/json",
        type="primary",
    )

    # Save to exports dir
    if st.button("Save to Exports Folder", key="op_save_export"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = "onpage_" + ts + ".json"
        filepath = EXPORT_DIR / filename
        with open(filepath, "w") as f:
            json.dump(analysis, f, indent=2, default=str)
        st.success("Saved to: " + str(filepath))

    # Preview
    with st.expander("Preview JSON", expanded=False):
        st.json(analysis)
