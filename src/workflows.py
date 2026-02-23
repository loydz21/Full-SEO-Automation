"""Workflow engine connecting all modules into automated SEO pipelines."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Orchestrate multi-step SEO pipelines across all modules.

    Each pipeline method runs a sequence of steps. Every step is wrapped in
    try/except so that a single module failure does not abort the entire
    pipeline.  Results are collected per-step and returned as a dict.

    Usage::

        engine = WorkflowEngine()
        results = await engine.run_full_seo_pipeline("example.com", ["seo tools"])
    """

    def __init__(self) -> None:
        self._llm_client = None
        self._technical_auditor = None
        self._onpage_optimizer = None
        self._schema_generator = None
        self._keyword_researcher = None
        self._keyword_analyzer = None
        self._topical_researcher = None
        self._blog_writer = None
        self._quality_checker = None
        self._content_manager = None
        self._link_prospector = None
        self._outreach_manager = None
        self._backlink_monitor = None
        self._rank_tracker = None
        self._serp_analyzer = None
        self._local_seo_analyzer = None
        self._local_report_generator = None
        self._report_engine = None
        self._report_renderer = None
        self._seo_news_scraper = None
        self._pipeline_status: dict[str, Any] = {}
        logger.info("WorkflowEngine initialized.")

    # ------------------------------------------------------------------
    # Lazy-loaded module accessors
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        if self._llm_client is None:
            from src.integrations.llm_client import LLMClient
            self._llm_client = LLMClient()
            logger.debug("LLMClient created.")
        return self._llm_client

    def _get_technical_auditor(self):
        if self._technical_auditor is None:
            from src.modules.technical_audit import TechnicalAuditor
            self._technical_auditor = TechnicalAuditor(llm_client=self._get_llm_client())
            logger.debug("TechnicalAuditor created.")
        return self._technical_auditor

    def _get_onpage_optimizer(self):
        if self._onpage_optimizer is None:
            from src.modules.onpage_seo import OnPageOptimizer
            self._onpage_optimizer = OnPageOptimizer(llm_client=self._get_llm_client())
            logger.debug("OnPageOptimizer created.")
        return self._onpage_optimizer

    def _get_schema_generator(self):
        if self._schema_generator is None:
            from src.modules.onpage_seo import SchemaGenerator
            self._schema_generator = SchemaGenerator()
            logger.debug("SchemaGenerator created.")
        return self._schema_generator

    def _get_keyword_researcher(self):
        if self._keyword_researcher is None:
            from src.modules.keyword_research import KeywordResearcher
            self._keyword_researcher = KeywordResearcher(llm_client=self._get_llm_client())
            logger.debug("KeywordResearcher created.")
        return self._keyword_researcher

    def _get_keyword_analyzer(self):
        if self._keyword_analyzer is None:
            from src.modules.keyword_research import KeywordAnalyzer
            self._keyword_analyzer = KeywordAnalyzer()
            logger.debug("KeywordAnalyzer created.")
        return self._keyword_analyzer

    def _get_topical_researcher(self):
        if self._topical_researcher is None:
            from src.modules.topical_research import TopicalResearcher
            self._topical_researcher = TopicalResearcher(llm_client=self._get_llm_client())
            logger.debug("TopicalResearcher created.")
        return self._topical_researcher

    def _get_blog_writer(self):
        if self._blog_writer is None:
            from src.modules.blog_content import BlogContentWriter
            self._blog_writer = BlogContentWriter(llm_client=self._get_llm_client())
            logger.debug("BlogContentWriter created.")
        return self._blog_writer

    def _get_quality_checker(self):
        if self._quality_checker is None:
            from src.modules.blog_content import ContentQualityChecker
            self._quality_checker = ContentQualityChecker(llm_client=self._get_llm_client())
            logger.debug("ContentQualityChecker created.")
        return self._quality_checker

    def _get_content_manager(self):
        if self._content_manager is None:
            from src.modules.blog_content import ContentManager
            self._content_manager = ContentManager()
            logger.debug("ContentManager created.")
        return self._content_manager

    def _get_link_prospector(self):
        if self._link_prospector is None:
            from src.modules.link_building import LinkProspector
            self._link_prospector = LinkProspector(llm_client=self._get_llm_client())
            logger.debug("LinkProspector created.")
        return self._link_prospector

    def _get_outreach_manager(self):
        if self._outreach_manager is None:
            from src.modules.link_building import OutreachManager
            self._outreach_manager = OutreachManager(llm_client=self._get_llm_client())
            logger.debug("OutreachManager created.")
        return self._outreach_manager

    def _get_backlink_monitor(self):
        if self._backlink_monitor is None:
            from src.modules.link_building import BacklinkMonitor
            self._backlink_monitor = BacklinkMonitor(llm_client=self._get_llm_client())
            logger.debug("BacklinkMonitor created.")
        return self._backlink_monitor

    def _get_rank_tracker(self):
        if self._rank_tracker is None:
            from src.modules.rank_tracker import RankTracker
            self._rank_tracker = RankTracker()
            logger.debug("RankTracker created.")
        return self._rank_tracker

    def _get_serp_analyzer(self):
        if self._serp_analyzer is None:
            from src.modules.rank_tracker import SERPAnalyzer
            self._serp_analyzer = SERPAnalyzer()
            logger.debug("SERPAnalyzer created.")
        return self._serp_analyzer

    def _get_local_seo_analyzer(self):
        if self._local_seo_analyzer is None:
            from src.modules.local_seo import LocalSEOAnalyzer
            self._local_seo_analyzer = LocalSEOAnalyzer(llm_client=self._get_llm_client())
            logger.debug("LocalSEOAnalyzer created.")
        return self._local_seo_analyzer

    def _get_local_report_generator(self):
        if self._local_report_generator is None:
            from src.modules.local_seo import LocalSEOReportGenerator
            self._local_report_generator = LocalSEOReportGenerator()
            logger.debug("LocalSEOReportGenerator created.")
        return self._local_report_generator

    def _get_report_engine(self):
        if self._report_engine is None:
            from src.modules.reporting import ReportEngine
            self._report_engine = ReportEngine(llm=self._get_llm_client())
            logger.debug("ReportEngine created.")
        return self._report_engine

    def _get_report_renderer(self):
        if self._report_renderer is None:
            from src.modules.reporting import ReportRenderer
            self._report_renderer = ReportRenderer()
            logger.debug("ReportRenderer created.")
        return self._report_renderer

    def _get_seo_news_scraper(self):
        if self._seo_news_scraper is None:
            from src.modules.seo_news.scraper import SEONewsScraper
            self._seo_news_scraper = SEONewsScraper()
            logger.debug("SEONewsScraper created.")
        return self._seo_news_scraper

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log_step(
        self,
        pipeline: str,
        step: int,
        total: int,
        description: str,
        status: str = "running",
    ) -> None:
        """Log and record a pipeline step transition."""
        msg = f"[{pipeline}] Step {step}/{total}: {description} — {status}"
        if status == "error":
            logger.error(msg)
        else:
            logger.info(msg)
        self._pipeline_status[pipeline] = {
            "current_step": step,
            "total_steps": total,
            "description": description,
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Pipeline status
    # ------------------------------------------------------------------

    def get_pipeline_status(self) -> dict[str, Any]:
        """Return status of all pipelines that have been run."""
        return dict(self._pipeline_status)

    # ------------------------------------------------------------------
    # 1. Full SEO Pipeline (9 steps)
    # ------------------------------------------------------------------

    async def run_full_seo_pipeline(
        self,
        domain: str,
        keywords: list[str],
        business_name: Optional[str] = None,
        location: Optional[str] = None,
    ) -> dict[str, Any]:
        """Master pipeline running all SEO modules in sequence.

        Steps:
            1. Technical audit
            2. On-page analysis
            3. Keyword research
            4. Topical research
            5. Content generation (first keyword)
            6. Link building prospecting
            7. Rank tracking
            8. Local SEO (if business_name provided)
            9. Report generation
        """
        pipeline = "full_seo"
        total = 9
        results: dict[str, Any] = {"domain": domain, "keywords": keywords, "steps": {}}
        started = time.time()
        logger.info("Starting full SEO pipeline for %s with %d keywords", domain, len(keywords))

        # Step 1: Technical Audit
        self._log_step(pipeline, 1, total, "Technical audit")
        try:
            auditor = self._get_technical_auditor()
            url = domain if domain.startswith("http") else f"https://{domain}"
            audit_data = await auditor.run_full_audit(url)
            score_data = auditor.score_audit(audit_data)
            results["steps"]["technical_audit"] = {"status": "success", "data": audit_data, "score": score_data}
            self._log_step(pipeline, 1, total, "Technical audit", "done")
        except Exception as exc:
            logger.exception("Technical audit failed: %s", exc)
            results["steps"]["technical_audit"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 1, total, "Technical audit", "error")

        # Step 2: On-page analysis
        self._log_step(pipeline, 2, total, "On-page analysis")
        try:
            optimizer = self._get_onpage_optimizer()
            url = domain if domain.startswith("http") else f"https://{domain}"
            onpage_data = await optimizer.analyze_page(url)
            results["steps"]["onpage_analysis"] = {"status": "success", "data": onpage_data}
            self._log_step(pipeline, 2, total, "On-page analysis", "done")
        except Exception as exc:
            logger.exception("On-page analysis failed: %s", exc)
            results["steps"]["onpage_analysis"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 2, total, "On-page analysis", "error")

        # Step 3: Keyword research
        self._log_step(pipeline, 3, total, "Keyword research")
        try:
            researcher = self._get_keyword_researcher()
            kw_data = await researcher.full_research_pipeline(keywords)
            results["steps"]["keyword_research"] = {"status": "success", "data": kw_data}
            self._log_step(pipeline, 3, total, "Keyword research", "done")
        except Exception as exc:
            logger.exception("Keyword research failed: %s", exc)
            results["steps"]["keyword_research"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 3, total, "Keyword research", "error")

        # Step 4: Topical research
        self._log_step(pipeline, 4, total, "Topical research")
        try:
            topical = self._get_topical_researcher()
            niche = keywords[0] if keywords else domain
            topical_map = await topical.generate_topical_map(niche)
            results["steps"]["topical_research"] = {"status": "success", "data": topical_map}
            self._log_step(pipeline, 4, total, "Topical research", "done")
        except Exception as exc:
            logger.exception("Topical research failed: %s", exc)
            results["steps"]["topical_research"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 4, total, "Topical research", "error")

        # Step 5: Content generation
        self._log_step(pipeline, 5, total, "Content generation")
        try:
            writer = self._get_blog_writer()
            target_kw = keywords[0] if keywords else domain
            brief = await writer.generate_brief(target_kw, "blog_post")
            article = await writer.write_article(brief)
            checker = self._get_quality_checker()
            quality = checker.check_quality(article, target_kw)
            results["steps"]["content_generation"] = {
                "status": "success",
                "brief": brief,
                "article": article,
                "quality": quality,
            }
            self._log_step(pipeline, 5, total, "Content generation", "done")
        except Exception as exc:
            logger.exception("Content generation failed: %s", exc)
            results["steps"]["content_generation"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 5, total, "Content generation", "error")

        # Step 6: Link building prospecting
        self._log_step(pipeline, 6, total, "Link building")
        try:
            prospector = self._get_link_prospector()
            prospects = await prospector.find_prospects(domain, keywords)
            results["steps"]["link_building"] = {"status": "success", "prospects": prospects}
            self._log_step(pipeline, 6, total, "Link building", "done")
        except Exception as exc:
            logger.exception("Link building failed: %s", exc)
            results["steps"]["link_building"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 6, total, "Link building", "error")

        # Step 7: Rank tracking
        self._log_step(pipeline, 7, total, "Rank tracking")
        try:
            tracker = self._get_rank_tracker()
            rank_results = await tracker.track_keywords_bulk(domain, keywords)
            results["steps"]["rank_tracking"] = {"status": "success", "data": rank_results}
            self._log_step(pipeline, 7, total, "Rank tracking", "done")
        except Exception as exc:
            logger.exception("Rank tracking failed: %s", exc)
            results["steps"]["rank_tracking"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 7, total, "Rank tracking", "error")

        # Step 8: Local SEO (optional)
        self._log_step(pipeline, 8, total, "Local SEO")
        if business_name and location:
            try:
                local_analyzer = self._get_local_seo_analyzer()
                url = domain if domain.startswith("http") else f"https://{domain}"
                local_data = await local_analyzer.analyze_business(url, business_name, location)
                results["steps"]["local_seo"] = {"status": "success", "data": local_data}
                self._log_step(pipeline, 8, total, "Local SEO", "done")
            except Exception as exc:
                logger.exception("Local SEO failed: %s", exc)
                results["steps"]["local_seo"] = {"status": "error", "error": str(exc)}
                self._log_step(pipeline, 8, total, "Local SEO", "error")
        else:
            results["steps"]["local_seo"] = {"status": "skipped", "reason": "No business_name/location provided"}
            self._log_step(pipeline, 8, total, "Local SEO", "skipped")

        # Step 9: Report generation
        self._log_step(pipeline, 9, total, "Report generation")
        try:
            report_engine = self._get_report_engine()
            report_data = await report_engine.generate_full_report(domain)
            renderer = self._get_report_renderer()
            html_path = renderer.render_html(report_data)
            results["steps"]["report"] = {"status": "success", "data": report_data, "html_path": html_path}
            self._log_step(pipeline, 9, total, "Report generation", "done")
        except Exception as exc:
            logger.exception("Report generation failed: %s", exc)
            results["steps"]["report"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 9, total, "Report generation", "error")

        elapsed = time.time() - started
        results["elapsed_seconds"] = round(elapsed, 2)
        results["completed_at"] = datetime.utcnow().isoformat()
        step_statuses = [v.get("status", "unknown") for v in results["steps"].values()]
        success_count = step_statuses.count("success")
        total_count = len(step_statuses)
        results["summary"] = f"{success_count}/{total_count} steps succeeded in {elapsed:.1f}s"
        logger.info("Full SEO pipeline completed: %s", results["summary"])
        return results

    # ------------------------------------------------------------------
    # 2. Content Pipeline (7 steps)
    # ------------------------------------------------------------------

    async def run_content_pipeline(
        self,
        domain: str,
        keyword: str,
        content_type: str = "blog_post",
    ) -> dict[str, Any]:
        """Content creation pipeline from research to publish-ready article.

        Steps:
            1. Keyword expansion and intent classification
            2. SERP analysis
            3. Topical map and content gaps
            4. Content brief generation
            5. Article writing
            6. Quality check
            7. Schema generation
        """
        pipeline = "content"
        total = 7
        results: dict[str, Any] = {"domain": domain, "keyword": keyword, "steps": {}}
        started = time.time()
        logger.info("Starting content pipeline for keyword: %s", keyword)

        # Step 1: Keyword expansion
        self._log_step(pipeline, 1, total, "Keyword expansion")
        try:
            researcher = self._get_keyword_researcher()
            expanded = await researcher.expand_keywords([keyword])
            intent_data = await researcher.classify_intent([keyword] + expanded.get("keywords", [])[:10])
            results["steps"]["keyword_expansion"] = {"status": "success", "expanded": expanded, "intent": intent_data}
            self._log_step(pipeline, 1, total, "Keyword expansion", "done")
        except Exception as exc:
            logger.exception("Keyword expansion failed: %s", exc)
            results["steps"]["keyword_expansion"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 1, total, "Keyword expansion", "error")

        # Step 2: SERP analysis
        self._log_step(pipeline, 2, total, "SERP analysis")
        try:
            researcher = self._get_keyword_researcher()
            serp_data = await researcher.analyze_serp(keyword)
            results["steps"]["serp_analysis"] = {"status": "success", "data": serp_data}
            self._log_step(pipeline, 2, total, "SERP analysis", "done")
        except Exception as exc:
            logger.exception("SERP analysis failed: %s", exc)
            results["steps"]["serp_analysis"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 2, total, "SERP analysis", "error")

        # Step 3: Topical map and content gaps
        self._log_step(pipeline, 3, total, "Topical mapping")
        try:
            topical = self._get_topical_researcher()
            topical_map = await topical.generate_topical_map(keyword)
            content_gaps = await topical.find_content_gaps(keyword)
            results["steps"]["topical_mapping"] = {"status": "success", "map": topical_map, "gaps": content_gaps}
            self._log_step(pipeline, 3, total, "Topical mapping", "done")
        except Exception as exc:
            logger.exception("Topical mapping failed: %s", exc)
            results["steps"]["topical_mapping"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 3, total, "Topical mapping", "error")

        # Step 4: Content brief
        self._log_step(pipeline, 4, total, "Content brief")
        try:
            writer = self._get_blog_writer()
            brief = await writer.generate_brief(keyword, content_type)
            results["steps"]["content_brief"] = {"status": "success", "brief": brief}
            self._log_step(pipeline, 4, total, "Content brief", "done")
        except Exception as exc:
            logger.exception("Content brief failed: %s", exc)
            results["steps"]["content_brief"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 4, total, "Content brief", "error")

        # Step 5: Article writing
        self._log_step(pipeline, 5, total, "Article writing")
        try:
            writer = self._get_blog_writer()
            brief_data = results["steps"].get("content_brief", {}).get("brief", {})
            if not brief_data:
                brief_data = await writer.generate_brief(keyword, content_type)
            article = await writer.write_article(brief_data)
            results["steps"]["article_writing"] = {"status": "success", "article": article}
            self._log_step(pipeline, 5, total, "Article writing", "done")
        except Exception as exc:
            logger.exception("Article writing failed: %s", exc)
            results["steps"]["article_writing"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 5, total, "Article writing", "error")

        # Step 6: Quality check
        self._log_step(pipeline, 6, total, "Quality check")
        try:
            checker = self._get_quality_checker()
            article_data = results["steps"].get("article_writing", {}).get("article", {})
            if article_data:
                quality = checker.check_quality(article_data, keyword)
                results["steps"]["quality_check"] = {"status": "success", "quality": quality}
            else:
                results["steps"]["quality_check"] = {"status": "skipped", "reason": "No article to check"}
            self._log_step(pipeline, 6, total, "Quality check", "done")
        except Exception as exc:
            logger.exception("Quality check failed: %s", exc)
            results["steps"]["quality_check"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 6, total, "Quality check", "error")

        # Step 7: Schema generation
        self._log_step(pipeline, 7, total, "Schema generation")
        try:
            schema_gen = self._get_schema_generator()
            article_data = results["steps"].get("article_writing", {}).get("article", {})
            title = article_data.get("title", keyword) if isinstance(article_data, dict) else keyword
            schema = schema_gen.generate_article_schema(
                title=title,
                description=article_data.get("meta_description", "") if isinstance(article_data, dict) else "",
                url=f"https://{domain}/blog/{keyword.replace(' ', '-')}",
            )
            validation = schema_gen.validate_schema(schema)
            results["steps"]["schema"] = {"status": "success", "schema": schema, "validation": validation}
            self._log_step(pipeline, 7, total, "Schema generation", "done")
        except Exception as exc:
            logger.exception("Schema generation failed: %s", exc)
            results["steps"]["schema"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 7, total, "Schema generation", "error")

        elapsed = time.time() - started
        results["elapsed_seconds"] = round(elapsed, 2)
        results["completed_at"] = datetime.utcnow().isoformat()
        step_statuses = [v.get("status", "unknown") for v in results["steps"].values()]
        success_count = step_statuses.count("success")
        total_count = len(step_statuses)
        results["summary"] = f"{success_count}/{total_count} steps succeeded in {elapsed:.1f}s"
        logger.info("Content pipeline completed: %s", results["summary"])
        return results

    # ------------------------------------------------------------------
    # 3. Link Building Pipeline (5 steps)
    # ------------------------------------------------------------------

    async def run_link_building_pipeline(
        self,
        domain: str,
        keywords: list[str],
        competitors: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Link building pipeline from prospecting to outreach.

        Steps:
            1. Backlink profile analysis
            2. Competitor backlink discovery
            3. Link prospecting (guest posts, resource pages, broken links)
            4. Prospect scoring
            5. Outreach email generation
        """
        pipeline = "link_building"
        total = 5
        results: dict[str, Any] = {"domain": domain, "keywords": keywords, "steps": {}}
        started = time.time()
        logger.info("Starting link building pipeline for %s", domain)

        # Step 1: Backlink profile analysis
        self._log_step(pipeline, 1, total, "Backlink profile analysis")
        try:
            monitor = self._get_backlink_monitor()
            profile = await monitor.analyze_backlink_profile(domain)
            results["steps"]["backlink_profile"] = {"status": "success", "data": profile}
            self._log_step(pipeline, 1, total, "Backlink profile analysis", "done")
        except Exception as exc:
            logger.exception("Backlink profile analysis failed: %s", exc)
            results["steps"]["backlink_profile"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 1, total, "Backlink profile analysis", "error")

        # Step 2: Competitor backlinks
        self._log_step(pipeline, 2, total, "Competitor backlink discovery")
        try:
            prospector = self._get_link_prospector()
            comp_list = competitors or []
            comp_backlinks = []
            for comp in comp_list:
                try:
                    comp_links = await prospector.find_competitor_backlinks(comp)
                    comp_backlinks.append({"competitor": comp, "backlinks": comp_links})
                except Exception as inner_exc:
                    logger.warning("Competitor backlink check failed for %s: %s", comp, inner_exc)
                    comp_backlinks.append({"competitor": comp, "error": str(inner_exc)})
            results["steps"]["competitor_backlinks"] = {"status": "success", "data": comp_backlinks}
            self._log_step(pipeline, 2, total, "Competitor backlink discovery", "done")
        except Exception as exc:
            logger.exception("Competitor backlink discovery failed: %s", exc)
            results["steps"]["competitor_backlinks"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 2, total, "Competitor backlink discovery", "error")

        # Step 3: Link prospecting
        self._log_step(pipeline, 3, total, "Link prospecting")
        try:
            prospector = self._get_link_prospector()
            all_prospects = []
            try:
                guest_posts = await prospector.find_guest_post_opportunities(domain, keywords)
                all_prospects.extend(guest_posts if isinstance(guest_posts, list) else [])
            except Exception as gp_exc:
                logger.warning("Guest post prospecting failed: %s", gp_exc)
            try:
                resource_pages = await prospector.find_resource_page_links(domain, keywords)
                all_prospects.extend(resource_pages if isinstance(resource_pages, list) else [])
            except Exception as rp_exc:
                logger.warning("Resource page prospecting failed: %s", rp_exc)
            try:
                broken_links = await prospector.find_broken_link_opportunities(domain)
                all_prospects.extend(broken_links if isinstance(broken_links, list) else [])
            except Exception as bl_exc:
                logger.warning("Broken link prospecting failed: %s", bl_exc)
            results["steps"]["link_prospecting"] = {"status": "success", "prospects": all_prospects, "count": len(all_prospects)}
            self._log_step(pipeline, 3, total, "Link prospecting", "done")
        except Exception as exc:
            logger.exception("Link prospecting failed: %s", exc)
            results["steps"]["link_prospecting"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 3, total, "Link prospecting", "error")

        # Step 4: Prospect scoring
        self._log_step(pipeline, 4, total, "Prospect scoring")
        try:
            prospector = self._get_link_prospector()
            prospects_list = results["steps"].get("link_prospecting", {}).get("prospects", [])
            scored = []
            for prospect in prospects_list[:20]:
                try:
                    score_result = await prospector.score_prospect(prospect)
                    scored.append(score_result)
                except Exception as score_exc:
                    logger.warning("Prospect scoring error: %s", score_exc)
                    scored.append({"prospect": prospect, "score_error": str(score_exc)})
            scored.sort(key=lambda x: x.get("score", 0) if isinstance(x, dict) else 0, reverse=True)
            results["steps"]["prospect_scoring"] = {"status": "success", "scored_prospects": scored}
            self._log_step(pipeline, 4, total, "Prospect scoring", "done")
        except Exception as exc:
            logger.exception("Prospect scoring failed: %s", exc)
            results["steps"]["prospect_scoring"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 4, total, "Prospect scoring", "error")

        # Step 5: Outreach email generation
        self._log_step(pipeline, 5, total, "Outreach email generation")
        try:
            outreach = self._get_outreach_manager()
            scored_list = results["steps"].get("prospect_scoring", {}).get("scored_prospects", [])
            business_info = {"domain": domain, "name": domain.replace(".", " ").title()}
            emails = []
            for prospect in scored_list[:10]:
                try:
                    email = await outreach.generate_outreach_email(prospect, "guest_post", business_info)
                    emails.append(email)
                except Exception as email_exc:
                    logger.warning("Email generation error: %s", email_exc)
            results["steps"]["outreach_emails"] = {"status": "success", "emails": emails, "count": len(emails)}
            self._log_step(pipeline, 5, total, "Outreach email generation", "done")
        except Exception as exc:
            logger.exception("Outreach email generation failed: %s", exc)
            results["steps"]["outreach_emails"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 5, total, "Outreach email generation", "error")

        elapsed = time.time() - started
        results["elapsed_seconds"] = round(elapsed, 2)
        results["completed_at"] = datetime.utcnow().isoformat()
        step_statuses = [v.get("status", "unknown") for v in results["steps"].values()]
        success_count = step_statuses.count("success")
        total_count = len(step_statuses)
        results["summary"] = f"{success_count}/{total_count} steps succeeded in {elapsed:.1f}s"
        logger.info("Link building pipeline completed: %s", results["summary"])
        return results

    # ------------------------------------------------------------------
    # 4. Monitoring Pipeline (6 steps)
    # ------------------------------------------------------------------

    async def run_monitoring_pipeline(self, domain: str) -> dict[str, Any]:
        """Monitoring pipeline for ongoing SEO health checks.

        Steps:
            1. Backlink monitoring
            2. Toxic link detection
            3. Rank change detection
            4. SERP feature analysis
            5. SEO news scraping
            6. Summary report
        """
        pipeline = "monitoring"
        total = 6
        results: dict[str, Any] = {"domain": domain, "steps": {}}
        started = time.time()
        logger.info("Starting monitoring pipeline for %s", domain)

        # Step 1: Backlink monitoring
        self._log_step(pipeline, 1, total, "Backlink monitoring")
        try:
            monitor = self._get_backlink_monitor()
            backlinks = await monitor.check_backlinks(domain)
            results["steps"]["backlink_monitoring"] = {"status": "success", "data": backlinks}
            self._log_step(pipeline, 1, total, "Backlink monitoring", "done")
        except Exception as exc:
            logger.exception("Backlink monitoring failed: %s", exc)
            results["steps"]["backlink_monitoring"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 1, total, "Backlink monitoring", "error")

        # Step 2: Toxic link detection
        self._log_step(pipeline, 2, total, "Toxic link detection")
        try:
            monitor = self._get_backlink_monitor()
            bl_data = results["steps"].get("backlink_monitoring", {}).get("data", {})
            backlink_list = bl_data.get("backlinks", []) if isinstance(bl_data, dict) else []
            toxic = await monitor.detect_toxic_links(backlink_list)
            results["steps"]["toxic_links"] = {"status": "success", "data": toxic}
            self._log_step(pipeline, 2, total, "Toxic link detection", "done")
        except Exception as exc:
            logger.exception("Toxic link detection failed: %s", exc)
            results["steps"]["toxic_links"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 2, total, "Toxic link detection", "error")

        # Step 3: Rank change detection
        self._log_step(pipeline, 3, total, "Rank change detection")
        try:
            tracker = self._get_rank_tracker()
            changes = tracker.detect_ranking_changes(domain)
            results["steps"]["rank_changes"] = {"status": "success", "data": changes}
            self._log_step(pipeline, 3, total, "Rank change detection", "done")
        except Exception as exc:
            logger.exception("Rank change detection failed: %s", exc)
            results["steps"]["rank_changes"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 3, total, "Rank change detection", "error")

        # Step 4: SERP feature analysis
        self._log_step(pipeline, 4, total, "SERP feature analysis")
        try:
            analyzer = self._get_serp_analyzer()
            serp_features = await analyzer.analyze_serp_features(domain)
            results["steps"]["serp_features"] = {"status": "success", "data": serp_features}
            self._log_step(pipeline, 4, total, "SERP feature analysis", "done")
        except Exception as exc:
            logger.exception("SERP feature analysis failed: %s", exc)
            results["steps"]["serp_features"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 4, total, "SERP feature analysis", "error")

        # Step 5: SEO news scraping
        self._log_step(pipeline, 5, total, "SEO news scraping")
        try:
            scraper = self._get_seo_news_scraper()
            news = await scraper.scrape_all_sources()
            results["steps"]["seo_news"] = {"status": "success", "articles": news, "count": len(news)}
            self._log_step(pipeline, 5, total, "SEO news scraping", "done")
        except Exception as exc:
            logger.exception("SEO news scraping failed: %s", exc)
            results["steps"]["seo_news"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 5, total, "SEO news scraping", "error")

        # Step 6: Summary report
        self._log_step(pipeline, 6, total, "Summary report")
        try:
            report_engine = self._get_report_engine()
            summary = await report_engine.generate_executive_summary(results["steps"])
            results["steps"]["summary_report"] = {"status": "success", "summary": summary}
            self._log_step(pipeline, 6, total, "Summary report", "done")
        except Exception as exc:
            logger.exception("Summary report failed: %s", exc)
            results["steps"]["summary_report"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 6, total, "Summary report", "error")

        elapsed = time.time() - started
        results["elapsed_seconds"] = round(elapsed, 2)
        results["completed_at"] = datetime.utcnow().isoformat()
        step_statuses = [v.get("status", "unknown") for v in results["steps"].values()]
        success_count = step_statuses.count("success")
        total_count = len(step_statuses)
        results["summary"] = f"{success_count}/{total_count} steps succeeded in {elapsed:.1f}s"
        logger.info("Monitoring pipeline completed: %s", results["summary"])
        return results

    # ------------------------------------------------------------------
    # 5. Local SEO Pipeline (6 steps)
    # ------------------------------------------------------------------

    async def run_local_seo_pipeline(
        self,
        domain: str,
        business_name: str,
        location: str,
    ) -> dict[str, Any]:
        """Local SEO pipeline for local business optimization.

        Steps:
            1. Business analysis
            2. Citation checking
            3. GBP/GMB analysis
            4. Local keyword tracking
            5. Competitor analysis
            6. Local SEO report generation
        """
        pipeline = "local_seo"
        total = 6
        results: dict[str, Any] = {
            "domain": domain,
            "business_name": business_name,
            "location": location,
            "steps": {},
        }
        started = time.time()
        logger.info("Starting local SEO pipeline for %s (%s, %s)", domain, business_name, location)

        url = domain if domain.startswith("http") else f"https://{domain}"

        # Step 1: Business analysis
        self._log_step(pipeline, 1, total, "Business analysis")
        try:
            analyzer = self._get_local_seo_analyzer()
            analysis = await analyzer.analyze_business(url, business_name, location)
            results["steps"]["business_analysis"] = {"status": "success", "data": analysis}
            self._log_step(pipeline, 1, total, "Business analysis", "done")
        except Exception as exc:
            logger.exception("Business analysis failed: %s", exc)
            results["steps"]["business_analysis"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 1, total, "Business analysis", "error")

        # Step 2: Citation checking
        self._log_step(pipeline, 2, total, "Citation checking")
        try:
            from src.modules.local_seo import CitationChecker
            citation_checker = CitationChecker()
            citations = await citation_checker.check_all_citations(business_name, location)
            citation_summary = citation_checker.generate_citation_summary(citations)
            results["steps"]["citation_check"] = {"status": "success", "citations": citations, "summary": citation_summary}
            self._log_step(pipeline, 2, total, "Citation checking", "done")
        except Exception as exc:
            logger.exception("Citation checking failed: %s", exc)
            results["steps"]["citation_check"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 2, total, "Citation checking", "error")

        # Step 3: GBP/GMB analysis
        self._log_step(pipeline, 3, total, "GBP analysis")
        try:
            from src.modules.local_seo import GMBAnalyzer
            gmb = GMBAnalyzer()
            try:
                gbp_data = await gmb.analyze_gbp_listing(business_name, location)
                map_pack = await gmb.get_map_pack_results(business_name, location)
                results["steps"]["gbp_analysis"] = {"status": "success", "gbp": gbp_data, "map_pack": map_pack}
            finally:
                await gmb.close()
            self._log_step(pipeline, 3, total, "GBP analysis", "done")
        except Exception as exc:
            logger.exception("GBP analysis failed: %s", exc)
            results["steps"]["gbp_analysis"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 3, total, "GBP analysis", "error")

        # Step 4: Local keyword tracking
        self._log_step(pipeline, 4, total, "Local keyword tracking")
        try:
            tracker = self._get_rank_tracker()
            local_keywords = [
                f"{business_name} {location}",
                f"{business_name} near me",
                f"best {business_name} {location}",
            ]
            rank_results = await tracker.track_keywords_bulk(domain, local_keywords)
            results["steps"]["local_ranking"] = {"status": "success", "data": rank_results}
            self._log_step(pipeline, 4, total, "Local keyword tracking", "done")
        except Exception as exc:
            logger.exception("Local keyword tracking failed: %s", exc)
            results["steps"]["local_ranking"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 4, total, "Local keyword tracking", "error")

        # Step 5: Competitor analysis
        self._log_step(pipeline, 5, total, "Local competitor analysis")
        try:
            topical = self._get_topical_researcher()
            comp_data = await topical.analyze_competitors(business_name, location)
            results["steps"]["competitor_analysis"] = {"status": "success", "data": comp_data}
            self._log_step(pipeline, 5, total, "Local competitor analysis", "done")
        except Exception as exc:
            logger.exception("Local competitor analysis failed: %s", exc)
            results["steps"]["competitor_analysis"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 5, total, "Local competitor analysis", "error")

        # Step 6: Local SEO report
        self._log_step(pipeline, 6, total, "Local SEO report")
        try:
            report_gen = self._get_local_report_generator()
            audit_data = results["steps"].get("business_analysis", {}).get("data", {})
            if audit_data:
                html_report = report_gen.generate_html_report(audit_data)
                report_path = report_gen.save_report(html_report, f"local_seo_{domain.replace('.', '_')}")
                results["steps"]["local_report"] = {"status": "success", "report_path": report_path}
            else:
                results["steps"]["local_report"] = {"status": "skipped", "reason": "No analysis data available"}
            self._log_step(pipeline, 6, total, "Local SEO report", "done")
        except Exception as exc:
            logger.exception("Local SEO report failed: %s", exc)
            results["steps"]["local_report"] = {"status": "error", "error": str(exc)}
            self._log_step(pipeline, 6, total, "Local SEO report", "error")

        elapsed = time.time() - started
        results["elapsed_seconds"] = round(elapsed, 2)
        results["completed_at"] = datetime.utcnow().isoformat()
        step_statuses = [v.get("status", "unknown") for v in results["steps"].values()]
        success_count = step_statuses.count("success")
        total_count = len(step_statuses)
        results["summary"] = f"{success_count}/{total_count} steps succeeded in {elapsed:.1f}s"
        logger.info("Local SEO pipeline completed: %s", results["summary"])
        return results
