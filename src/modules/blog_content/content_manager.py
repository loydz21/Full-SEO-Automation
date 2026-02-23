"""Content Manager — export, scheduling, and statistics for blog content.

Provides markdown/HTML/WordPress-XML export, editorial calendar
generation, and aggregate content statistics.
"""

import collections
import csv
import io
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from xml.dom import minidom

import markdown as md_lib  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Create a URL-safe slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dir(filepath: str) -> None:
    """Ensure parent directory exists."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# ContentManager
# ---------------------------------------------------------------------------

class ContentManager:
    """Manage export, scheduling, and statistics for generated content.

    Usage::

        mgr = ContentManager()
        mgr.export_markdown(article, "/tmp/article.md")
        mgr.export_html(article, "/tmp/article.html")
        calendar = mgr.create_editorial_calendar(topics, "2025-03-01")
    """

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def export_markdown(
        self,
        article: dict[str, Any],
        filepath: str,
    ) -> str:
        """Export article to a Markdown file with YAML frontmatter.

        Returns the absolute path of the written file.
        """
        _ensure_dir(filepath)

        title = article.get("title", "Untitled")
        keyword = article.get("keyword", "")
        meta = article.get("meta_description", "")
        content = article.get("content", "")
        word_count = article.get("word_count", len(content.split()))
        reading_time = article.get("estimated_reading_time", max(1, round(word_count / 238)))
        content_type = article.get("content_type", "blog_post")
        now_str = _now_iso()

        frontmatter_lines = [
            "---",
            "title: \"" + title.replace('"', '\\"') + "\"",
            "date: " + now_str,
            "keyword: \"" + keyword + "\"",
            "meta_description: \"" + meta.replace('"', '\\"') + "\"",
            "content_type: " + content_type,
            "word_count: " + str(word_count),
            "reading_time: " + str(reading_time) + " min",
            "---",
        ]

        full = "\n".join(frontmatter_lines) + "\n\n" + content

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(full)

        logger.info("Exported markdown to %s (%d words)", filepath, word_count)
        return os.path.abspath(filepath)

    # ------------------------------------------------------------------
    # HTML export
    # ------------------------------------------------------------------

    def export_html(
        self,
        article: dict[str, Any],
        filepath: str,
    ) -> str:
        """Export article to an HTML file with basic styling.

        Returns the absolute path of the written file.
        """
        _ensure_dir(filepath)

        title = article.get("title", "Untitled")
        meta = article.get("meta_description", "")
        content_md = article.get("content", "")

        try:
            content_html = md_lib.markdown(
                content_md,
                extensions=["extra", "codehilite", "toc", "meta"],
            )
        except Exception as exc:
            logger.warning("Markdown conversion failed, using raw: %s", exc)
            content_html = "<pre>" + content_md + "</pre>"

        escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped_meta = meta.replace('"', '&quot;').replace("&", "&amp;")

        html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            '  <meta name="description" content="' + escaped_meta + '">\n'
            "  <title>" + escaped_title + "</title>\n"
            "  <style>\n"
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\n"
            "           max-width: 800px; margin: 40px auto; padding: 0 20px;\n"
            "           line-height: 1.7; color: #1a202c; }\n"
            "    h1 { font-size: 2em; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }\n"
            "    h2 { font-size: 1.5em; color: #1e40af; margin-top: 2em; }\n"
            "    h3 { font-size: 1.2em; color: #374151; margin-top: 1.5em; }\n"
            "    p { margin: 1em 0; }\n"
            "    ul, ol { padding-left: 2em; }\n"
            "    blockquote { border-left: 4px solid #3b82f6; padding-left: 1em;\n"
            "                 margin-left: 0; color: #4b5563; }\n"
            "    code { background: #f3f4f6; padding: 2px 6px; border-radius: 3px; }\n"
            "    pre { background: #1e293b; color: #e2e8f0; padding: 16px;\n"
            "          border-radius: 8px; overflow-x: auto; }\n"
            "    a { color: #3b82f6; text-decoration: none; }\n"
            "    a:hover { text-decoration: underline; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            + content_html + "\n"
            "</body>\n"
            "</html>"
        )

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(html)

        logger.info("Exported HTML to %s", filepath)
        return os.path.abspath(filepath)

    # ------------------------------------------------------------------
    # WordPress XML export (WXR format)
    # ------------------------------------------------------------------

    def export_wordpress_xml(
        self,
        articles: list[dict[str, Any]],
        filepath: str,
    ) -> str:
        """Export articles as WordPress-importable WXR XML.

        Returns the absolute path of the written file.
        """
        _ensure_dir(filepath)

        rss = ET.Element("rss")
        rss.set("version", "2.0")
        rss.set("xmlns:wp", "http://wordpress.org/export/1.2/")
        rss.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
        rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
        rss.set("xmlns:excerpt", "http://wordpress.org/export/1.2/excerpt/")

        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "SEO Blog Export"
        ET.SubElement(channel, "link").text = "https://example.com"
        ET.SubElement(channel, "description").text = "Exported blog posts"
        ET.SubElement(channel, "{http://wordpress.org/export/1.2/}wxr_version").text = "1.2"

        for i, article in enumerate(articles):
            title = article.get("title", "Untitled")
            content_text = article.get("content", "")
            meta = article.get("meta_description", "")
            slug = _slug(title)
            now_str = _now_iso()

            try:
                html_body = md_lib.markdown(
                    content_text, extensions=["extra"]
                )
            except Exception:
                html_body = content_text

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = "https://example.com/" + slug
            ET.SubElement(item, "pubDate").text = now_str
            ET.SubElement(item, "{http://purl.org/dc/elements/1.1/}creator").text = "admin"
            ET.SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded").text = html_body
            ET.SubElement(item, "{http://wordpress.org/export/1.2/excerpt/}encoded").text = meta
            ET.SubElement(item, "{http://wordpress.org/export/1.2/}post_id").text = str(i + 1)
            ET.SubElement(item, "{http://wordpress.org/export/1.2/}post_date").text = now_str
            ET.SubElement(item, "{http://wordpress.org/export/1.2/}post_name").text = slug
            ET.SubElement(item, "{http://wordpress.org/export/1.2/}status").text = "draft"
            ET.SubElement(item, "{http://wordpress.org/export/1.2/}post_type").text = "post"

        # Pretty-print
        rough = ET.tostring(rss, encoding="unicode")
        parsed = minidom.parseString(rough)
        pretty = parsed.toprettyxml(indent="  ", encoding="utf-8")

        with open(filepath, "wb") as fh:
            fh.write(pretty)

        logger.info("Exported %d articles to WordPress XML: %s", len(articles), filepath)
        return os.path.abspath(filepath)

    # ------------------------------------------------------------------
    # Editorial calendar
    # ------------------------------------------------------------------

    def create_editorial_calendar(
        self,
        topics: list[dict[str, Any]],
        start_date: str,
        frequency: str = "weekly",
    ) -> list[dict[str, Any]]:
        """Generate a publishing schedule from a list of topics.

        Args:
            topics: list of dicts with keyword, content_type (optional).
            start_date: ISO date string (YYYY-MM-DD).
            frequency: "daily", "weekly", "biweekly", "monthly".

        Returns:
            list of calendar entries with publish_date, topic, keyword,
            content_type, status, assignee.
        """
        freq_days = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
        }
        delta = timedelta(days=freq_days.get(frequency, 7))

        try:
            current = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            logger.warning("Invalid start_date %r, using today", start_date)
            current = datetime.now(timezone.utc)

        calendar: list[dict[str, Any]] = []
        for topic in topics:
            kw = topic.get("keyword", topic.get("topic", "Untitled"))
            ct = topic.get("content_type", "blog_post")
            entry = {
                "publish_date": current.strftime("%Y-%m-%d"),
                "topic": kw,
                "keyword": kw,
                "content_type": ct,
                "status": "planned",
                "assignee": "AI Writer",
            }
            calendar.append(entry)
            current += delta

        logger.info(
            "Editorial calendar created: %d entries from %s (%s)",
            len(calendar), start_date, frequency,
        )
        return calendar

    # ------------------------------------------------------------------
    # Content statistics
    # ------------------------------------------------------------------

    def get_content_stats(
        self,
        articles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute summary statistics across a set of articles."""
        if not articles:
            return {
                "total_articles": 0,
                "avg_word_count": 0,
                "total_word_count": 0,
                "topics_covered": [],
                "content_types_distribution": {},
                "avg_reading_time": 0,
                "min_word_count": 0,
                "max_word_count": 0,
            }

        word_counts = [a.get("word_count", 0) for a in articles]
        topics = [a.get("keyword", a.get("title", "Unknown")) for a in articles]
        content_types = [a.get("content_type", "blog_post") for a in articles]
        reading_times = [a.get("estimated_reading_time", 0) for a in articles]

        ct_dist = dict(collections.Counter(content_types))

        return {
            "total_articles": len(articles),
            "avg_word_count": round(sum(word_counts) / len(word_counts)),
            "total_word_count": sum(word_counts),
            "topics_covered": topics,
            "content_types_distribution": ct_dist,
            "avg_reading_time": round(sum(reading_times) / max(len(reading_times), 1)),
            "min_word_count": min(word_counts) if word_counts else 0,
            "max_word_count": max(word_counts) if word_counts else 0,
        }

    # ------------------------------------------------------------------
    # CSV export helper for calendar
    # ------------------------------------------------------------------

    def export_calendar_csv(
        self,
        calendar: list[dict[str, Any]],
        filepath: str,
    ) -> str:
        """Export editorial calendar to CSV file."""
        _ensure_dir(filepath)
        if not calendar:
            logger.warning("Empty calendar — nothing to export")
            return filepath

        fieldnames = ["publish_date", "topic", "keyword", "content_type", "status", "assignee"]
        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for entry in calendar:
                writer.writerow(entry)

        logger.info("Exported calendar CSV to %s (%d entries)", filepath, len(calendar))
        return os.path.abspath(filepath)

    def calendar_to_csv_string(self, calendar: list[dict[str, Any]]) -> str:
        """Convert editorial calendar to CSV string for download."""
        if not calendar:
            return ""
        buf = io.StringIO()
        fieldnames = ["publish_date", "topic", "keyword", "content_type", "status", "assignee"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in calendar:
            writer.writerow(entry)
        return buf.getvalue()
