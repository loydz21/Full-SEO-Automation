"""Universal PDF Export Helper for Dashboard Pages.

Provides standardized PDF report generation for all SEO modules.
Converts raw data into narrative paragraph-form reports with charts.
"""

import os
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_export_dir():
    """Get the export directory path."""
    from pathlib import Path
    export_dir = Path(__file__).resolve().parent.parent.parent / "data" / "exports"
    os.makedirs(str(export_dir), exist_ok=True)
    return export_dir


def _safe_get(data, key, default=None):
    """Safely get nested dict values."""
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def generate_technical_audit_pdf(audit_data, filepath=None):
    """Generate a narrative PDF report for Technical SEO Audit results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(audit_data, "domain", "Unknown")
    score = _safe_get(audit_data, "overall_score", 0)
    grade = _safe_get(audit_data, "grade", "?")
    cat_scores = _safe_get(audit_data, "category_scores", {})
    issues = _safe_get(audit_data, "issues", [])
    passed = _safe_get(audit_data, "passed_checks", [])
    recs = _safe_get(audit_data, "recommendations", [])
    summary = _safe_get(audit_data, "crawl_summary", {})
    cwv = _safe_get(audit_data, "core_web_vitals", {})
    security = _safe_get(audit_data, "security", {})
    ts = _safe_get(audit_data, "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "")
        filepath = str(get_export_dir() / "audit_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    errors = [i for i in issues if _safe_get(i, "severity") == "error"]
    warnings = [i for i in issues if _safe_get(i, "severity") == "warning"]
    infos = [i for i in issues if _safe_get(i, "severity") == "info"]

    builder = PDFReportBuilder(
        title="Technical SEO Audit Report",
        subtitle="Comprehensive Website Analysis",
    )

    # Cover Page
    builder.add_cover_page(
        domain=domain,
        date=ts,
        summary_text=(
            "This report presents a comprehensive technical SEO audit of {domain}. "
            "The analysis covers site performance, crawlability, security, mobile "
            "friendliness, and content quality. The website received an overall "
            "grade of {grade} with a score of {score} out of 100."
        ).format(domain=domain, grade=grade, score=score)
    )

    # Executive Summary
    exec_paragraphs = [
        (
            "Our technical audit of {domain} has been completed successfully. "
            "The website achieved an overall score of {score}/100, earning a grade "
            "of {grade}. During the analysis, we crawled {pages} pages and "
            "identified {errors} critical errors, {warnings} warnings, and "
            "{infos} informational items that require attention."
        ).format(
            domain=domain, score=score, grade=grade,
            pages=_safe_get(summary, "total_pages", 0),
            errors=len(errors), warnings=len(warnings), infos=len(infos)
        ),
    ]
    if len(errors) > 0:
        exec_paragraphs.append(
            "Immediate action is recommended for the {n} critical errors found. "
            "These issues can significantly impact search engine rankings and "
            "user experience if left unresolved.".format(n=len(errors))
        )
    if score >= 80:
        exec_paragraphs.append(
            "Overall, the website demonstrates strong technical SEO health. "
            "Focus on addressing the remaining issues to achieve an even higher score."
        )
    elif score >= 60:
        exec_paragraphs.append(
            "The website has a moderate technical SEO foundation but there is "
            "significant room for improvement. Prioritizing the critical issues "
            "listed below will have the greatest impact on search performance."
        )
    else:
        exec_paragraphs.append(
            "The website has serious technical SEO deficiencies that are likely "
            "impacting search visibility. We strongly recommend addressing the "
            "critical issues as soon as possible to improve rankings."
        )
    builder.add_executive_summary(exec_paragraphs)

    # Score Overview
    builder.add_score_card(score, grade, "Overall Technical Score")

    if cat_scores:
        builder.add_category_scores(cat_scores)
        # Category scores bar chart
        labels = [k.replace("_", " ").title() for k in cat_scores.keys()]
        values = list(cat_scores.values())
        builder.add_bar_chart(labels, values, "Category Score Breakdown",
                             ylabel="Score (0-100)")

    # Issues Analysis
    builder.add_heading("Issues Analysis", level=2)
    builder.add_paragraph(
        "A total of {total} issues were identified during the audit. "
        "Of these, {errors} are critical errors requiring immediate attention, "
        "{warnings} are warnings that should be addressed soon, and {infos} are "
        "informational items for future optimization.".format(
            total=len(issues), errors=len(errors),
            warnings=len(warnings), infos=len(infos)
        )
    )

    if issues:
        # Issues severity pie chart
        sev_labels = []
        sev_values = []
        sev_colors = []
        if len(errors) > 0:
            sev_labels.append("Critical ({n})".format(n=len(errors)))
            sev_values.append(len(errors))
            sev_colors.append("#ef4444")
        if len(warnings) > 0:
            sev_labels.append("Warning ({n})".format(n=len(warnings)))
            sev_values.append(len(warnings))
            sev_colors.append("#f97316")
        if len(infos) > 0:
            sev_labels.append("Info ({n})".format(n=len(infos)))
            sev_values.append(len(infos))
            sev_colors.append("#3b82f6")
        if sev_values:
            builder.add_pie_chart(sev_labels, sev_values,
                                "Issues by Severity", colors=sev_colors)

        # Issues table
        issue_rows = []
        for iss in issues[:30]:  # Limit to 30 for readability
            issue_rows.append([
                _safe_get(iss, "severity", "info").upper(),
                _safe_get(iss, "category", ""),
                _safe_get(iss, "description", ""),
                _safe_get(iss, "how_to_fix", ""),
            ])
        builder.add_table(
            ["Severity", "Category", "Description", "Fix"],
            issue_rows,
            caption="Detected Issues"
        )

    # Core Web Vitals
    if cwv:
        builder.add_page_break()
        builder.add_heading("Core Web Vitals & Performance", level=2)
        builder.add_paragraph(
            "Core Web Vitals are a set of metrics that Google uses to measure "
            "real-world user experience. These metrics directly impact search "
            "rankings and should be optimized for both mobile and desktop."
        )
        cwv_labels = []
        cwv_values = []
        for key, label in [("lcp", "LCP (s)"), ("fcp", "FCP (s)"),
                           ("cls", "CLS"), ("ttfb", "TTFB (ms)")]:
            val = _safe_get(cwv, key)
            if val is not None:
                cwv_labels.append(label)
                cwv_values.append(float(val))
        if cwv_labels:
            builder.add_bar_chart(cwv_labels, cwv_values, "Core Web Vitals Metrics")

    # Passed Checks
    if passed:
        builder.add_heading("Passed Checks", level=2)
        builder.add_paragraph(
            "The following {n} checks passed successfully, indicating healthy "
            "areas of your website's technical SEO.".format(n=len(passed))
        )
        passed_findings = []
        for p in passed[:20]:
            if isinstance(p, str):
                passed_findings.append({"title": p, "description": "Passed", "severity": "success"})
            else:
                passed_findings.append({"title": str(p), "description": "Passed", "severity": "success"})
        builder.add_key_findings(passed_findings)

    # Recommendations
    if recs:
        builder.add_page_break()
        builder.add_heading("Recommendations & Action Plan", level=2)
        builder.add_paragraph(
            "Based on our analysis, we have compiled {n} actionable recommendations "
            "to improve your website's technical SEO performance. These are "
            "prioritized by potential impact on search rankings.".format(n=len(recs))
        )
        builder.add_recommendations(recs)

    # Crawl Summary
    if summary:
        builder.add_heading("Crawl Summary", level=2)
        metrics = {}
        for key in ["total_pages", "total_links", "total_images",
                    "avg_word_count", "status_2xx", "status_3xx",
                    "status_4xx", "status_5xx"]:
            val = _safe_get(summary, key)
            if val is not None:
                label = key.replace("_", " ").title()
                metrics[label] = val
        if metrics:
            builder.add_metrics_summary(metrics)

    return builder.build_pdf(filepath)


def generate_keyword_research_pdf(kw_data, filepath=None):
    """Generate a narrative PDF for Keyword Research results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(kw_data, "domain", "")
    keywords = _safe_get(kw_data, "keywords", [])
    clusters = _safe_get(kw_data, "clusters", [])
    quick_wins = _safe_get(kw_data, "quick_wins", [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "") if domain else "keywords"
        filepath = str(get_export_dir() / "keywords_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Keyword Research Report",
        subtitle="Strategic Keyword Analysis",
    )

    builder.add_cover_page(
        domain=domain or "Keyword Research",
        date=ts,
        summary_text=(
            "This report presents comprehensive keyword research findings "
            "including {n} keywords analyzed, {c} keyword clusters identified, "
            "and {q} quick win opportunities for rapid ranking improvement."
        ).format(n=len(keywords), c=len(clusters), q=len(quick_wins))
    )

    # Executive Summary
    builder.add_executive_summary([
        (
            "Our keyword research uncovered {n} keyword opportunities. "
            "These keywords have been analyzed for search volume, competition, "
            "and ranking difficulty to help prioritize your content strategy."
        ).format(n=len(keywords)),
        (
            "We identified {c} thematic keyword clusters that can be targeted "
            "with dedicated content pieces, and {q} quick win keywords where "
            "you can achieve rapid ranking improvements."
        ).format(c=len(clusters), q=len(quick_wins))
    ])

    # Keyword Overview
    if keywords:
        builder.add_heading("Keyword Overview", level=2)
        # Show top keywords by volume
        sorted_kw = sorted(keywords, key=lambda x: _safe_get(x, "volume", 0), reverse=True)
        top_kw = sorted_kw[:20]

        if top_kw:
            kw_labels = [_safe_get(k, "keyword", "")[:25] for k in top_kw[:10]]
            kw_volumes = [_safe_get(k, "volume", 0) for k in top_kw[:10]]
            if any(v > 0 for v in kw_volumes):
                builder.add_horizontal_bar_chart(
                    kw_labels, kw_volumes, "Top Keywords by Search Volume"
                )

            rows = []
            for k in top_kw:
                rows.append([
                    _safe_get(k, "keyword", ""),
                    str(_safe_get(k, "volume", 0)),
                    str(_safe_get(k, "difficulty", "N/A")),
                    _safe_get(k, "intent", "N/A"),
                ])
            builder.add_table(
                ["Keyword", "Volume", "Difficulty", "Intent"],
                rows, caption="Top {n} Keywords".format(n=len(rows))
            )

    # Quick Wins
    if quick_wins:
        builder.add_page_break()
        builder.add_heading("Quick Win Opportunities", level=2)
        builder.add_paragraph(
            "The following {n} keywords represent quick win opportunities "
            "where your website can achieve faster ranking improvements "
            "with targeted optimization efforts.".format(n=len(quick_wins))
        )
        qw_rows = []
        for q in quick_wins[:15]:
            qw_rows.append([
                _safe_get(q, "keyword", ""),
                str(_safe_get(q, "current_position", "N/A")),
                str(_safe_get(q, "volume", 0)),
                _safe_get(q, "recommendation", ""),
            ])
        builder.add_table(
            ["Keyword", "Current Pos", "Volume", "Recommendation"],
            qw_rows, caption="Quick Win Keywords"
        )

    return builder.build_pdf(filepath)


def generate_onpage_seo_pdf(onpage_data, filepath=None):
    """Generate a narrative PDF for On-Page SEO analysis."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    url = _safe_get(onpage_data, "url", "")
    overall = _safe_get(onpage_data, "overall_score", 0)
    meta = _safe_get(onpage_data, "meta_analysis", {})
    content = _safe_get(onpage_data, "content_analysis", {})
    eeat = _safe_get(onpage_data, "eeat_signals", {})
    images = _safe_get(onpage_data, "image_analysis", {})
    links = _safe_get(onpage_data, "internal_links", {})
    schema = _safe_get(onpage_data, "schema_analysis", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")[:40]
        filepath = str(get_export_dir() / "onpage_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="On-Page SEO Analysis Report",
        subtitle="Detailed Page Optimization Review",
    )

    builder.add_cover_page(
        domain=url,
        date=ts,
        summary_text=(
            "This report provides a detailed on-page SEO analysis for {url}. "
            "The page achieved an overall optimization score of {score}/100. "
            "Analysis covers meta tags, content quality, E-E-A-T signals, "
            "internal linking, image optimization, and schema markup."
        ).format(url=url, score=overall)
    )

    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    builder.add_score_card(overall, grade, "On-Page SEO Score")

    # Category scores if available
    cat_scores = {}
    if meta:
        cat_scores["Meta Tags"] = _safe_get(meta, "score", 0)
    if content:
        cat_scores["Content Quality"] = _safe_get(content, "score", 0)
    if eeat:
        cat_scores["E-E-A-T"] = _safe_get(eeat, "score", 0)
    if images:
        cat_scores["Images"] = _safe_get(images, "score", 0)
    if links:
        cat_scores["Internal Links"] = _safe_get(links, "score", 0)
    if cat_scores:
        builder.add_category_scores(cat_scores)
        builder.add_radar_chart(
            list(cat_scores.keys()), list(cat_scores.values()),
            "On-Page SEO Radar"
        )

    builder.add_executive_summary([
        (
            "The on-page SEO analysis for {url} reveals a score of {score}/100. "
            "This assessment evaluates all critical on-page ranking factors "
            "including title tags, meta descriptions, heading structure, content "
            "quality, and technical elements."
        ).format(url=url, score=overall)
    ])

    return builder.build_pdf(filepath)


def generate_link_building_pdf(lb_data, filepath=None):
    """Generate a narrative PDF for Link Building results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(lb_data, "domain", "")
    prospects = _safe_get(lb_data, "prospects", [])
    backlinks = _safe_get(lb_data, "backlinks", [])
    outreach = _safe_get(lb_data, "outreach_stats", {})
    toxic = _safe_get(lb_data, "toxic_links", [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "") if domain else "links"
        filepath = str(get_export_dir() / "links_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Link Building Report",
        subtitle="Backlink Analysis & Outreach Strategy",
    )

    builder.add_cover_page(
        domain=domain or "Link Building",
        date=ts,
        summary_text=(
            "This report summarizes link building activities and backlink "
            "health for {domain}. Analysis includes {p} prospects identified, "
            "{b} backlinks monitored, and {t} potentially toxic links detected."
        ).format(domain=domain, p=len(prospects), b=len(backlinks), t=len(toxic))
    )

    builder.add_executive_summary([
        (
            "Our link building analysis identified {p} high-quality link "
            "prospects for outreach campaigns. The current backlink profile "
            "contains {b} monitored links with {t} flagged as potentially toxic."
        ).format(p=len(prospects), b=len(backlinks), t=len(toxic))
    ])

    metrics = {
        "Total Prospects": len(prospects),
        "Active Backlinks": len(backlinks),
        "Toxic Links": len(toxic),
    }
    if outreach:
        metrics["Emails Sent"] = _safe_get(outreach, "sent", 0)
        metrics["Response Rate"] = "{v}%".format(v=_safe_get(outreach, "response_rate", 0))
    builder.add_metrics_summary(metrics)

    return builder.build_pdf(filepath)


def generate_rank_tracking_pdf(rt_data, filepath=None):
    """Generate a narrative PDF for Rank Tracking results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(rt_data, "domain", "")
    rankings = _safe_get(rt_data, "rankings", [])
    visibility = _safe_get(rt_data, "visibility_score", 0)
    opportunities = _safe_get(rt_data, "opportunities", [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "") if domain else "rankings"
        filepath = str(get_export_dir() / "rankings_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Rank Tracking Report",
        subtitle="Keyword Rankings & Visibility Analysis",
    )

    builder.add_cover_page(
        domain=domain or "Rank Tracking",
        date=ts,
        summary_text=(
            "This report tracks keyword rankings for {domain}. "
            "Currently monitoring {n} keywords with a visibility "
            "score of {v}/100."
        ).format(domain=domain, n=len(rankings), v=visibility)
    )

    grade = "A" if visibility >= 80 else "B" if visibility >= 60 else "C" if visibility >= 40 else "D" if visibility >= 20 else "F"
    builder.add_score_card(visibility, grade, "Visibility Score")

    builder.add_executive_summary([
        (
            "We are currently tracking {n} keywords for {domain}. "
            "The overall search visibility score is {v}/100. "
            "{opp} keywords have been identified as ranking opportunities "
            "in striking distance (positions 4-20)."
        ).format(domain=domain, n=len(rankings), v=visibility, opp=len(opportunities))
    ])

    if rankings:
        # Position distribution
        top3 = len([r for r in rankings if _safe_get(r, "position", 100) <= 3])
        top10 = len([r for r in rankings if _safe_get(r, "position", 100) <= 10])
        top20 = len([r for r in rankings if _safe_get(r, "position", 100) <= 20])
        beyond = len(rankings) - top20

        pos_labels = ["Top 3", "Top 4-10", "Top 11-20", "Below 20"]
        pos_values = [top3, top10 - top3, top20 - top10, max(0, beyond)]
        pos_colors = ["#22c55e", "#84cc16", "#eab308", "#ef4444"]
        builder.add_pie_chart(pos_labels, pos_values,
                            "Ranking Position Distribution", colors=pos_colors)

        rows = []
        sorted_ranks = sorted(rankings, key=lambda x: _safe_get(x, "position", 999))
        for r in sorted_ranks[:20]:
            rows.append([
                _safe_get(r, "keyword", ""),
                str(_safe_get(r, "position", "N/A")),
                str(_safe_get(r, "volume", 0)),
                str(_safe_get(r, "change", 0)),
            ])
        builder.add_table(
            ["Keyword", "Position", "Volume", "Change"],
            rows, caption="Current Rankings"
        )

    return builder.build_pdf(filepath)


def generate_local_seo_pdf(local_data, filepath=None):
    """Generate a narrative PDF for Local SEO analysis."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(local_data, "domain", "")
    overall = _safe_get(local_data, "overall_score", 0)
    gmb = _safe_get(local_data, "gmb_analysis", {})
    citations = _safe_get(local_data, "citations", {})
    reviews = _safe_get(local_data, "reviews", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "") if domain else "local"
        filepath = str(get_export_dir() / "local_seo_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Local SEO Analysis Report",
        subtitle="Google Business Profile & Local Rankings",
    )

    builder.add_cover_page(
        domain=domain or "Local SEO",
        date=ts,
        summary_text=(
            "This report presents a comprehensive local SEO analysis for {domain}. "
            "The analysis covers Google Business Profile optimization, local citation "
            "consistency, review management, and local search ranking factors."
        ).format(domain=domain)
    )

    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    builder.add_score_card(overall, grade, "Local SEO Score")

    builder.add_executive_summary([
        (
            "The local SEO audit for {domain} resulted in a score of {score}/100. "
            "This assessment evaluates all factors contributing to local search "
            "visibility including Google Business Profile optimization, NAP "
            "consistency, review signals, and local content relevance."
        ).format(domain=domain, score=overall)
    ])

    return builder.build_pdf(filepath)


def generate_content_pdf(content_data, filepath=None):
    """Generate a narrative PDF for Blog Content analysis."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    articles = _safe_get(content_data, "articles", [])
    quality = _safe_get(content_data, "quality_stats", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        filepath = str(get_export_dir() / "content_{t}.pdf".format(
            t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Content Performance Report",
        subtitle="Blog Content Analysis & Quality Audit",
    )

    builder.add_cover_page(
        domain="Content Analysis",
        date=ts,
        summary_text=(
            "This report analyzes {n} content pieces for SEO quality, "
            "readability, and optimization. It includes detailed scoring "
            "and actionable recommendations for content improvement."
        ).format(n=len(articles))
    )

    builder.add_executive_summary([
        (
            "Our content analysis reviewed {n} articles for SEO optimization, "
            "readability, heading structure, and keyword targeting. "
            "The findings below highlight opportunities to improve content "
            "quality and search engine performance."
        ).format(n=len(articles))
    ])

    return builder.build_pdf(filepath)


def generate_topical_research_pdf(topic_data, filepath=None):
    """Generate a narrative PDF for Topical Research results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    niche = _safe_get(topic_data, "niche", "")
    topics = _safe_get(topic_data, "topics", [])
    content_gaps = _safe_get(topic_data, "content_gaps", [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = niche.replace(" ", "_")[:30] if niche else "topics"
        filepath = str(get_export_dir() / "topical_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Topical Research Report",
        subtitle="Niche Analysis & Content Strategy",
    )

    builder.add_cover_page(
        domain=niche or "Topical Research",
        date=ts,
        summary_text=(
            "This report presents topical research findings for the '{niche}' niche. "
            "Analysis includes {t} topic clusters identified and {g} content "
            "gap opportunities for strategic content creation."
        ).format(niche=niche, t=len(topics), g=len(content_gaps))
    )

    builder.add_executive_summary([
        (
            "Our topical research into the '{niche}' niche identified {t} "
            "key topic clusters and {g} content gaps that represent "
            "opportunities for establishing topical authority."
        ).format(niche=niche, t=len(topics), g=len(content_gaps))
    ])

    return builder.build_pdf(filepath)


def generate_seo_news_pdf(news_data, filepath=None):
    """Generate a narrative PDF for SEO News & Strategy results."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    articles = _safe_get(news_data, "articles", [])
    strategies = _safe_get(news_data, "strategies", [])
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        filepath = str(get_export_dir() / "seo_news_{t}.pdf".format(
            t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="SEO News & Strategy Report",
        subtitle="Latest Trends & Actionable Strategies",
    )

    builder.add_cover_page(
        domain="SEO Industry News",
        date=ts,
        summary_text=(
            "This report summarizes {a} recent SEO news articles and {s} "
            "actionable strategies identified through AI analysis of "
            "the latest industry trends and algorithm updates."
        ).format(a=len(articles), s=len(strategies))
    )

    builder.add_executive_summary([
        (
            "We analyzed {a} recent SEO articles from leading industry "
            "sources and identified {s} high-impact strategies that can "
            "be implemented to improve search performance."
        ).format(a=len(articles), s=len(strategies))
    ])

    if strategies:
        findings = []
        for s in strategies[:10]:
            findings.append({
                "title": _safe_get(s, "title", ""),
                "description": _safe_get(s, "description", ""),
                "severity": "info",
            })
        builder.add_key_findings(findings)

    return builder.build_pdf(filepath)


def generate_full_report_pdf(report_data, filepath=None):
    """Generate a comprehensive full SEO report PDF combining all modules."""
    from src.utils.pdf_report_builder import PDFReportBuilder

    domain = _safe_get(report_data, "domain", "")
    overall = _safe_get(report_data, "overall_score", 0)
    module_scores = _safe_get(report_data, "module_scores", {})
    exec_summary = _safe_get(report_data, "executive_summary", "")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not filepath:
        slug = domain.replace(".", "_").replace("/", "") if domain else "full"
        filepath = str(get_export_dir() / "full_report_{d}_{t}.pdf".format(
            d=slug, t=datetime.now().strftime("%Y%m%d_%H%M%S")))

    builder = PDFReportBuilder(
        title="Comprehensive SEO Report",
        subtitle="Full Website Analysis & Strategy",
    )

    builder.add_cover_page(
        domain=domain or "SEO Report",
        date=ts,
        summary_text=(
            "This comprehensive report provides a complete SEO analysis "
            "of {domain} covering technical health, on-page optimization, "
            "content quality, backlink profile, keyword rankings, and "
            "local SEO performance."
        ).format(domain=domain)
    )

    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    builder.add_score_card(overall, grade, "Overall SEO Score")

    if module_scores:
        builder.add_category_scores(module_scores)
        labels = list(module_scores.keys())
        values = list(module_scores.values())
        builder.add_radar_chart(labels, values, "Module Score Overview")

    if exec_summary:
        if isinstance(exec_summary, str):
            builder.add_executive_summary([exec_summary])
        elif isinstance(exec_summary, list):
            builder.add_executive_summary(exec_summary)

    return builder.build_pdf(filepath)
