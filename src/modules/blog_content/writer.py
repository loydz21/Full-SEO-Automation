"""Blog Content Writer — AI-powered article generation engine.

Provides end-to-end content creation: briefing, outlining, section writing,
FAQ generation, title suggestions, and batch article production.
"""

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTENT_TYPES = (
    "how_to", "listicle", "comparison", "guide", "review",
    "case_study", "news", "opinion", "blog_post",
)

TONES = (
    "professional", "casual", "academic", "conversational",
    "authoritative", "friendly", "persuasive",
)

_SYSTEM_PROMPT = (
    "You are an expert SEO content writer. "
    "You produce well-structured, engaging, and keyword-optimised content. "
    "Always respond ONLY with valid JSON unless told otherwise."
)

_SYSTEM_PROMPT_TEXT = (
    "You are an expert SEO content writer. "
    "You produce well-structured, engaging, and keyword-optimised content. "
    "Write in Markdown format."
)


# ---------------------------------------------------------------------------
# BlogContentWriter
# ---------------------------------------------------------------------------

class BlogContentWriter:
    """AI-powered blog content generation engine.

    Usage::

        writer = BlogContentWriter()
        brief = await writer.generate_brief("best seo tools 2025")
        article = await writer.write_article(brief)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        serp_scraper: Optional[SERPScraper] = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._serp = serp_scraper or SERPScraper()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_brief(
        self,
        keyword: str,
        content_type: str = "blog_post",
        target_word_count: int = 1500,
    ) -> dict[str, Any]:
        """Create a detailed content brief for *keyword*.

        Returns a dict with title_options, meta_description, outline,
        competitor_insights, internal_linking_suggestions, cta_suggestions,
        and more.
        """
        content_type = content_type if content_type in CONTENT_TYPES else "blog_post"
        logger.info(
            "Generating brief for %r (type=%s, words=%d)",
            keyword, content_type, target_word_count,
        )

        # Gather SERP intelligence in parallel
        serp_data, paa_questions, autocomplete = await asyncio.gather(
            self._safe_serp_search(keyword),
            self._safe_paa(keyword),
            self._safe_autocomplete(keyword),
        )

        competitor_titles = [
            r.get("title", "") for r in serp_data.get("organic_results", [])[:5]
        ]
        competitor_snippets = [
            r.get("snippet", "") for r in serp_data.get("organic_results", [])[:5]
        ]

        comp_lines = "\n".join(
            "- " + t for t in competitor_titles if t
        )
        paa_lines = "\n".join(
            "- " + q for q in paa_questions[:5]
        )
        auto_lines = "\n".join(
            "- " + s for s in autocomplete[:5]
        )

        prompt = (
            "Create a detailed content brief for the keyword: "
            '"' + keyword + '"\n'
            "Content type: " + content_type + "\n"
            "Target word count: " + str(target_word_count) + "\n\n"
            "Competitor titles from SERP:\n" + comp_lines + "\n\n"
            "People Also Ask questions:\n" + paa_lines + "\n\n"
            "Autocomplete suggestions:\n" + auto_lines + "\n\n"
            "Return JSON with these exact keys:\n"
            '{"title_options": ["title1", "title2", "title3"],'
            ' "meta_description": "...",'
            ' "target_keyword": "...",'
            ' "secondary_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],'
            ' "outline": [{"heading": "H2 heading", "subheadings": ["H3 a", "H3 b"], "key_points": ["point1", "point2"]}],'
            ' "competitor_insights": ["insight1", "insight2", "insight3"],'
            ' "recommended_word_count": 1500,'
            ' "internal_linking_suggestions": ["page1", "page2"],'
            ' "cta_suggestions": ["cta1", "cta2"]}'
        )

        try:
            brief = await self._llm.generate_json(
                prompt, system_prompt=_SYSTEM_PROMPT
            )
        except Exception as exc:
            logger.error("LLM brief generation failed: %s", exc)
            brief = self._fallback_brief(keyword, content_type, target_word_count)

        # Enrich with raw SERP data
        brief["keyword"] = keyword
        brief["content_type"] = content_type
        brief["target_word_count"] = target_word_count
        brief["serp_data"] = {
            "organic_results": serp_data.get("organic_results", [])[:5],
            "paa_questions": paa_questions[:5],
            "related_searches": serp_data.get("related_searches", []),
        }
        logger.info(
            "Brief generated for %r with %d outline sections",
            keyword, len(brief.get("outline", [])),
        )
        return brief

    async def write_article(
        self,
        brief: dict[str, Any],
        tone: str = "professional",
        include_faq: bool = True,
    ) -> dict[str, Any]:
        """Write a full article section-by-section from a content brief.

        Returns a dict with title, meta_description, content (markdown),
        word_count, sections, faq_section, estimated_reading_time.
        """
        tone = tone if tone in TONES else "professional"
        keyword = brief.get("keyword", brief.get("target_keyword", "topic"))
        title_opts = brief.get("title_options", ["Untitled"])
        title = title_opts[0] if title_opts else "Untitled"
        meta_desc = brief.get("meta_description", "")
        outline = brief.get("outline", [])
        secondary_kws = brief.get("secondary_keywords", [])

        logger.info(
            "Writing article for %r — %d sections, tone=%s",
            keyword, len(outline), tone,
        )

        # Build introduction
        intro = await self._write_introduction(keyword, title, secondary_kws, tone)

        # Write each section
        sections: list[dict[str, Any]] = []
        total_word_target = brief.get("target_word_count", 1500)
        per_section = self._section_word_target(total_word_target, len(outline))

        for sec in outline:
            heading = sec.get("heading", "Section")
            key_points = sec.get("key_points", [])
            subheadings = sec.get("subheadings", [])
            context = (
                "Article title: " + title + "\n"
                "Target keyword: " + keyword + "\n"
                "Secondary keywords: " + ", ".join(secondary_kws[:3]) + "\n"
                "Tone: " + tone
            )
            section_md = await self.write_section(
                heading=heading,
                key_points=key_points,
                context=context,
                word_count=per_section,
            )
            # Add subheading content
            sub_parts: list[str] = []
            for sub_h in subheadings:
                sub_text = await self.write_section(
                    heading=sub_h,
                    key_points=[],
                    context="Parent section: " + heading + "\nTone: " + tone,
                    word_count=150,
                )
                sub_parts.append(sub_text)

            full_section = section_md
            if sub_parts:
                full_section += "\n\n" + "\n\n".join(sub_parts)

            sections.append({"heading": heading, "content": full_section})

        # FAQ section
        faq_section = ""
        faq_list: list[dict[str, Any]] = []
        if include_faq:
            faq_list = await self.generate_faq(keyword, count=5)
            if faq_list:
                faq_md_parts = ["## Frequently Asked Questions\n"]
                for faq in faq_list:
                    q = faq.get("question", "")
                    a = faq.get("answer", "")
                    faq_md_parts.append("### " + q + "\n\n" + a + "\n")
                faq_section = "\n".join(faq_md_parts)

        # Build conclusion
        conclusion = await self._write_conclusion(keyword, title, tone)

        # Assemble full article
        parts = ["# " + title + "\n", intro, ""]
        for sec in sections:
            parts.append(sec["content"])
            parts.append("")
        if faq_section:
            parts.append(faq_section)
        parts.append(conclusion)

        full_content = "\n\n".join(parts)
        wc = len(full_content.split())

        article = {
            "title": title,
            "meta_description": meta_desc,
            "content": full_content,
            "word_count": wc,
            "sections": [
                {
                    "heading": s["heading"],
                    "word_count": len(s["content"].split()),
                }
                for s in sections
            ],
            "faq_section": faq_list,
            "estimated_reading_time": max(1, round(wc / 238)),
            "keyword": keyword,
            "tone": tone,
            "content_type": brief.get("content_type", "blog_post"),
        }
        logger.info(
            "Article written: %d words, ~%d min read",
            wc, article["estimated_reading_time"],
        )
        return article

    async def generate_outline(
        self,
        topic: str,
        content_type: str = "how_to",
    ) -> dict[str, Any]:
        """Generate an article outline with H2/H3 structure.

        Supports content_types: how_to, listicle, comparison, guide,
        review, case_study, news, opinion.
        """
        content_type = content_type if content_type in CONTENT_TYPES else "how_to"
        logger.info("Generating outline for %r (type=%s)", topic, content_type)

        type_guidance = {
            "how_to": "Create a step-by-step tutorial outline with numbered steps as H2 headings.",
            "listicle": "Create a numbered list outline where each list item is an H2 heading.",
            "comparison": "Create a comparison outline with sections for each option, pros/cons, and verdict.",
            "guide": "Create a comprehensive guide outline covering basics to advanced topics.",
            "review": "Create a review outline covering features, pros, cons, pricing, alternatives, and verdict.",
            "case_study": "Create a case study outline with background, challenge, solution, results, and takeaways.",
            "news": "Create a news article outline with summary, background, details, impact, and expert reactions.",
            "opinion": "Create an opinion piece outline with thesis, supporting arguments, counterpoints, and conclusion.",
            "blog_post": "Create a standard blog post outline with introduction, main sections, and conclusion.",
        }

        guidance = type_guidance.get(content_type, type_guidance["blog_post"])

        prompt = (
            'Generate a detailed article outline for the topic: "'
            + topic + '"\n'
            "Content type: " + content_type + "\n"
            "Guidance: " + guidance + "\n\n"
            "Return JSON with these exact keys:\n"
            '{"topic": "...",'
            ' "content_type": "...",'
            ' "suggested_title": "...",'
            ' "estimated_word_count": 1500,'
            ' "outline": [{"heading": "H2 heading", "subheadings": ["H3 a", "H3 b"],'
            ' "key_points": ["point1", "point2"], "estimated_words": 300}]}'
        )

        try:
            result = await self._llm.generate_json(
                prompt, system_prompt=_SYSTEM_PROMPT
            )
        except Exception as exc:
            logger.error("Outline generation failed: %s", exc)
            result = {
                "topic": topic,
                "content_type": content_type,
                "suggested_title": "Guide to " + topic,
                "estimated_word_count": 1500,
                "outline": [
                    {"heading": "Introduction", "subheadings": [],
                     "key_points": ["Overview of the topic"], "estimated_words": 200},
                    {"heading": "What is " + topic + "?", "subheadings": [],
                     "key_points": ["Definition and context"], "estimated_words": 300},
                    {"heading": "Key Considerations", "subheadings": [],
                     "key_points": ["Important factors"], "estimated_words": 400},
                    {"heading": "Best Practices", "subheadings": [],
                     "key_points": ["Recommended approaches"], "estimated_words": 400},
                    {"heading": "Conclusion", "subheadings": [],
                     "key_points": ["Summary and next steps"], "estimated_words": 200},
                ],
            }

        result["topic"] = topic
        result["content_type"] = content_type
        return result

    async def write_section(
        self,
        heading: str,
        key_points: list[str],
        context: str = "",
        word_count: int = 300,
    ) -> str:
        """Write a single section of content with SEO optimization."""
        if key_points:
            points_text = "\n".join("- " + p for p in key_points)
        else:
            points_text = "Cover this topic thoroughly."

        prompt = (
            'Write a blog section with the heading: "' + heading + '"\n'
            "Target word count: approximately " + str(word_count) + " words.\n\n"
        )
        if context:
            prompt += "Context:\n" + context + "\n\n"
        prompt += (
            "Key points to cover:\n" + points_text + "\n\n"
            "Requirements:\n"
            "- Start with the heading as ## Markdown heading\n"
            "- Write engaging, informative prose\n"
            "- Use short paragraphs (2-4 sentences)\n"
            "- Include transition sentences\n"
            "- Naturally incorporate relevant keywords\n"
            "- Use bullet points or numbered lists where appropriate\n"
            "- Do NOT include the article title or conclusion in this section\n"
            "- Write in Markdown format\n"
        )

        try:
            result = await self._llm.generate_text(
                prompt, system_prompt=_SYSTEM_PROMPT_TEXT, use_cache=False,
            )
            return result.strip()
        except Exception as exc:
            logger.error("Section writing failed for %r: %s", heading, exc)
            return "## " + heading + "\n\nContent for this section is being prepared."

    async def generate_faq(
        self,
        topic: str,
        count: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate FAQ section using PAA data from SERP + AI.

        Each FAQ has: question, answer, schema_ready (bool).
        """
        logger.info("Generating %d FAQs for %r", count, topic)

        # Fetch PAA questions from SERP
        paa = await self._safe_paa(topic)

        prompt = (
            "Generate " + str(count) + " FAQ items for the topic: "
            '"' + topic + '"\n\n'
        )
        if paa:
            paa_lines = "\n".join("- " + q for q in paa[:8])
            prompt += (
                "Here are real questions people ask (from Google):\n"
                + paa_lines + "\n\n"
                "Use some of these questions and add your own.\n\n"
            )
        prompt += (
            "Return a JSON array of objects with these keys:\n"
            '[{"question": "...", "answer": "...", "schema_ready": true}]\n\n'
            "Each answer should be 2-4 sentences. Answers should be factual and helpful.\n"
            "Set schema_ready to true if the Q&A pair is suitable for FAQ schema markup."
        )

        try:
            faqs = await self._llm.generate_json(
                prompt, system_prompt=_SYSTEM_PROMPT
            )
            if isinstance(faqs, list):
                return faqs[:count]
            return []
        except Exception as exc:
            logger.error("FAQ generation failed: %s", exc)
            return []

    async def suggest_titles(
        self,
        keyword: str,
        count: int = 5,
    ) -> list[dict[str, Any]]:
        """Generate SEO-optimized title options.

        Each title has: title, estimated_ctr_score (0-100), title_type.
        """
        logger.info("Suggesting %d titles for %r", count, keyword)

        prompt = (
            "Generate " + str(count)
            + " SEO-optimized blog post title options for the keyword: "
            '"' + keyword + '"\n\n'
            "Requirements:\n"
            "- Each title should be 50-65 characters\n"
            "- Include the target keyword naturally\n"
            "- Use power words to improve CTR\n"
            "- Vary the title types\n\n"
            "Return a JSON array with these keys:\n"
            '[{"title": "...", "estimated_ctr_score": 75, "title_type": "how-to"}]\n\n'
            "Title types: how-to, listicle, question, guide, comparison, review, ultimate, data-driven"
        )

        try:
            titles = await self._llm.generate_json(
                prompt, system_prompt=_SYSTEM_PROMPT
            )
            if isinstance(titles, list):
                return titles[:count]
            return []
        except Exception as exc:
            logger.error("Title suggestion failed: %s", exc)
            return []

    async def batch_generate(
        self,
        topics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate multiple articles from a list of topic dicts.

        Each topic dict should have: keyword, content_type (optional),
        word_count (optional).

        Returns a list of completed article dicts.
        """
        logger.info("Batch generating %d articles", len(topics))
        results: list[dict[str, Any]] = []

        for i, topic in enumerate(topics):
            kw = topic.get("keyword", "")
            if not kw:
                logger.warning("Skipping topic %d — no keyword", i)
                results.append({"error": "No keyword provided", "index": i})
                continue

            ct = topic.get("content_type", "blog_post")
            wc = topic.get("word_count", 1500)

            try:
                logger.info(
                    "Batch [%d/%d]: generating %r", i + 1, len(topics), kw
                )
                brief = await self.generate_brief(
                    kw, content_type=ct, target_word_count=wc
                )
                article = await self.write_article(brief)
                article["index"] = i
                results.append(article)
            except Exception as exc:
                logger.error("Batch item %d failed: %s", i, exc)
                results.append({"error": str(exc), "keyword": kw, "index": i})

        succeeded = sum(1 for r in results if "error" not in r)
        logger.info(
            "Batch complete: %d/%d succeeded", succeeded, len(topics)
        )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_introduction(
        self,
        keyword: str,
        title: str,
        secondary_kws: list[str],
        tone: str,
    ) -> str:
        """Write the article introduction."""
        kw_text = ", ".join(secondary_kws[:3]) if secondary_kws else ""
        prompt = (
            "Write an engaging introduction for a blog post.\n"
            "Title: " + title + "\n"
            "Target keyword: " + keyword + "\n"
        )
        if kw_text:
            prompt += "Secondary keywords to mention naturally: " + kw_text + "\n"
        prompt += (
            "Tone: " + tone + "\n\n"
            "Requirements:\n"
            "- 100-150 words\n"
            "- Hook the reader in the first sentence\n"
            "- Include the target keyword in the first 100 words\n"
            "- Preview what the reader will learn\n"
            "- Do NOT include the title heading (it is added separately)\n"
            "- Write in Markdown\n"
        )
        try:
            text = await self._llm.generate_text(
                prompt, system_prompt=_SYSTEM_PROMPT_TEXT, use_cache=False,
            )
            return text.strip()
        except Exception as exc:
            logger.error("Introduction writing failed: %s", exc)
            return (
                "In this article, we explore everything you need to know about "
                + keyword + "."
            )

    async def _write_conclusion(
        self,
        keyword: str,
        title: str,
        tone: str,
    ) -> str:
        """Write the article conclusion."""
        prompt = (
            "Write a conclusion for a blog post.\n"
            "Title: " + title + "\n"
            "Target keyword: " + keyword + "\n"
            "Tone: " + tone + "\n\n"
            "Requirements:\n"
            "- 80-120 words\n"
            "- Summarise key takeaways\n"
            "- Include a clear call to action\n"
            "- Start with ## Conclusion heading\n"
            "- Write in Markdown\n"
        )
        try:
            text = await self._llm.generate_text(
                prompt, system_prompt=_SYSTEM_PROMPT_TEXT, use_cache=False,
            )
            return text.strip()
        except Exception as exc:
            logger.error("Conclusion writing failed: %s", exc)
            return (
                "## Conclusion\n\nWe hope this guide on "
                + keyword + " has been helpful."
            )

    async def _safe_serp_search(self, query: str) -> dict[str, Any]:
        """Search SERP with error handling."""
        try:
            return await self._serp.search_google(query)
        except Exception as exc:
            logger.warning("SERP search failed for %r: %s", query, exc)
            return {
                "query": query,
                "organic_results": [],
                "people_also_ask": [],
                "related_searches": [],
            }

    async def _safe_paa(self, query: str) -> list[str]:
        """Get PAA questions with error handling."""
        try:
            return await self._serp.get_paa_questions(query)
        except Exception as exc:
            logger.warning("PAA failed for %r: %s", query, exc)
            return []

    async def _safe_autocomplete(self, query: str) -> list[str]:
        """Get autocomplete suggestions with error handling."""
        try:
            return await self._serp.get_autocomplete(query)
        except Exception as exc:
            logger.warning("Autocomplete failed for %r: %s", query, exc)
            return []

    @staticmethod
    def _section_word_target(total_words: int, num_sections: int) -> int:
        """Calculate target word count per section."""
        if num_sections <= 0:
            return 300
        # Reserve ~20% for intro, conclusion, FAQ
        available = int(total_words * 0.8)
        return max(150, available // max(num_sections, 1))

    @staticmethod
    def _fallback_brief(
        keyword: str,
        content_type: str,
        target_word_count: int,
    ) -> dict[str, Any]:
        """Return a minimal brief when LLM fails."""
        titled = keyword.title()
        return {
            "title_options": [
                "The Ultimate Guide to " + titled,
                "Everything You Need to Know About " + titled,
                titled + ": A Comprehensive Overview",
            ],
            "meta_description": (
                "Discover everything about " + keyword
                + ". This comprehensive guide covers key aspects, "
                "best practices, and expert tips."
            ),
            "target_keyword": keyword,
            "secondary_keywords": [],
            "outline": [
                {"heading": "What is " + titled + "?", "subheadings": [],
                 "key_points": ["Definition", "Importance"]},
                {"heading": "Key Benefits", "subheadings": [],
                 "key_points": ["Main advantages"]},
                {"heading": "How to Get Started", "subheadings": [],
                 "key_points": ["Step-by-step guide"]},
                {"heading": "Best Practices", "subheadings": [],
                 "key_points": ["Expert tips"]},
                {"heading": "Common Mistakes to Avoid", "subheadings": [],
                 "key_points": ["Pitfalls"]},
            ],
            "competitor_insights": [],
            "recommended_word_count": target_word_count,
            "internal_linking_suggestions": [],
            "cta_suggestions": ["Subscribe for more tips", "Share this guide"],
        }
