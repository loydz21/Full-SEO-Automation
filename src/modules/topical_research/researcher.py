"""Topical research module for comprehensive niche analysis and topical map generation."""

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TopicalResearcher:
    """Comprehensive topical research engine for SEO niche analysis.

    Combines LLM-powered analysis with SERP data and Google Trends
    to produce actionable topical maps, content gap analyses, and
    competitor intelligence.

    Usage::

        from src.integrations.llm_client import LLMClient
        from src.integrations.serp_scraper import SERPScraper
        from src.integrations.google_trends import GoogleTrendsClient

        researcher = TopicalResearcher(
            llm_client=LLMClient(),
            scraper=SERPScraper(),
            trends_client=GoogleTrendsClient(),
        )
        analysis = await researcher.analyze_niche("home automation")
        topical_map = await researcher.generate_topical_map("home automation")
    """

    def __init__(
        self,
        llm_client: Any = None,
        scraper: Any = None,
        trends_client: Any = None,
    ) -> None:
        """Initialize the TopicalResearcher.

        Args:
            llm_client: An instance of LLMClient for AI-powered analysis.
            scraper: An instance of SERPScraper for search result data.
            trends_client: An instance of GoogleTrendsClient for trend data.
        """
        self.llm_client = llm_client
        self.scraper = scraper
        self.trends_client = trends_client

        if self.llm_client is None:
            try:
                from src.integrations.llm_client import LLMClient
                self.llm_client = LLMClient()
                logger.info("Created default LLMClient instance")
            except Exception as exc:
                logger.warning("Could not create default LLMClient: %s", exc)

        if self.scraper is None:
            try:
                from src.integrations.serp_scraper import SERPScraper
                self.scraper = SERPScraper()
                logger.info("Created default SERPScraper instance")
            except Exception as exc:
                logger.warning("Could not create default SERPScraper: %s", exc)

        if self.trends_client is None:
            try:
                from src.integrations.google_trends import GoogleTrendsClient
                self.trends_client = GoogleTrendsClient()
                logger.info("Created default GoogleTrendsClient instance")
            except Exception as exc:
                logger.warning("Could not create default GoogleTrendsClient: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_niche(
        self,
        niche: str,
        location: str = "",
    ) -> dict[str, Any]:
        """Perform a comprehensive niche analysis using AI and live data.

        Generates market size estimation, competition level assessment,
        monetization potential, and trending subtopics for a given niche.

        Args:
            niche: The niche/industry to analyze (e.g. "home automation").
            location: Optional geographic focus (e.g. "US", "United Kingdom").

        Returns:
            Dict containing scores, insights, and subtopic recommendations.
        """
        logger.info("Analyzing niche: %r (location=%r)", niche, location)
        result: dict[str, Any] = {
            "niche": niche,
            "location": location,
            "market_analysis": {},
            "competition": {},
            "monetization": {},
            "trending_subtopics": [],
            "serp_insights": {},
            "recommendations": [],
        }

        # --- Step 1: Gather SERP data for the niche ---
        serp_data: dict[str, Any] = {}
        if self.scraper:
            try:
                serp_data = await self.scraper.search_google(
                    query=niche, num_results=10
                )
                organic = serp_data.get("organic_results", [])
                top_domains = []
                for r in organic[:5]:
                    url = r.get("url", "")
                    parts = url.split("/")
                    dom = parts[2] if len(parts) > 2 else url
                    top_domains.append(dom)
                result["serp_insights"] = {
                    "organic_count": len(organic),
                    "has_featured_snippet": serp_data.get("featured_snippet") is not None,
                    "paa_questions": serp_data.get("people_also_ask", []),
                    "related_searches": serp_data.get("related_searches", []),
                    "top_domains": top_domains,
                }
                logger.info("SERP data collected: %d results", len(organic))
            except Exception as exc:
                logger.error("SERP scraping failed for niche analysis: %s", exc)

        # --- Step 2: Gather trends data ---
        trends_data: dict[str, Any] = {}
        if self.trends_client:
            try:
                geo_code = location if len(location) == 2 else ""
                interest = await self.trends_client.get_interest_over_time(
                    keywords=[niche],
                    timeframe="today 12-m",
                    geo=geo_code,
                )
                related = await self.trends_client.get_related_queries(
                    keyword=niche,
                    timeframe="today 12-m",
                    geo=geo_code,
                )
                trends_data = {
                    "interest_data": interest,
                    "related_top": related.get("top", [])[:10],
                    "related_rising": related.get("rising", [])[:10],
                }
                logger.info("Trends data collected: %d interest points", len(interest))
            except Exception as exc:
                logger.error("Google Trends data collection failed: %s", exc)

        # --- Step 3: AI-powered comprehensive analysis ---
        location_str = " in " + location if location else ""
        serp_context = ""
        if serp_data.get("organic_results"):
            top_titles = [r.get("title", "") for r in serp_data["organic_results"][:5]]
            top_doms = result["serp_insights"].get("top_domains", [])
            paa = serp_data.get("people_also_ask", [])
            serp_context = (
                "\nTop ranking pages: " + json.dumps(top_titles)
                + "\nTop domains: " + json.dumps(top_doms)
                + "\nPeople Also Ask: " + json.dumps(paa)
            )

        trends_context = ""
        if trends_data.get("related_rising"):
            rising_queries = [q.get("query", "") for q in trends_data["related_rising"][:5]]
            trends_context = "\nRising search queries: " + json.dumps(rising_queries)

        prompt = (
            'Analyze the niche "' + niche + '"' + location_str + ' for SEO content strategy.'
            + serp_context + trends_context
            + '\n\nProvide a comprehensive JSON analysis with this exact structure:'
            + '\n{'
            + '\n  "market_analysis": {'
            + '\n    "estimated_market_size": "description of market size",'
            + '\n    "market_size_score": "1-10 integer",'
            + '\n    "growth_trend": "growing|stable|declining",'
            + '\n    "audience_size": "description",'
            + '\n    "search_demand": "high|medium|low"'
            + '\n  },'
            + '\n  "competition": {'
            + '\n    "level": "high|medium|low",'
            + '\n    "competition_score": "1-10 integer",'
            + '\n    "dominant_players": ["list of top competitors"],'
            + '\n    "entry_difficulty": "description",'
            + '\n    "content_saturation": "high|medium|low"'
            + '\n  },'
            + '\n  "monetization": {'
            + '\n    "potential_score": "1-10 integer",'
            + '\n    "revenue_models": ["affiliate", "ads", "products", "services"],'
            + '\n    "avg_cpc_estimate": "$X.XX",'
            + '\n    "affiliate_potential": "high|medium|low",'
            + '\n    "product_opportunities": ["list"]'
            + '\n  },'
            + '\n  "trending_subtopics": ['
            + '\n    {"topic": "name", "trend_direction": "up|stable|down", "opportunity_score": "1-10", "reason": "why trending"}'
            + '\n  ],'
            + '\n  "recommendations": ['
            + '\n    {"action": "description", "priority": "high|medium|low", "impact": "description", "effort": "high|medium|low"}'
            + '\n  ],'
            + '\n  "overall_opportunity_score": "1-10 integer"'
            + '\n}'
        )

        try:
            ai_analysis = await self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=(
                    "You are an expert SEO strategist and market analyst. "
                    "Analyze niches with data-driven insights. "
                    "Respond ONLY with valid JSON matching the requested structure."
                ),
                max_tokens=3000,
                temperature=0.4,
            )
            result["market_analysis"] = ai_analysis.get("market_analysis", {})
            result["competition"] = ai_analysis.get("competition", {})
            result["monetization"] = ai_analysis.get("monetization", {})
            result["trending_subtopics"] = ai_analysis.get("trending_subtopics", [])
            result["recommendations"] = ai_analysis.get("recommendations", [])
            result["overall_opportunity_score"] = ai_analysis.get("overall_opportunity_score", 5)
            logger.info("AI niche analysis complete for %r", niche)
        except Exception as exc:
            logger.error("LLM call failed during niche analysis: %s", exc)
            result["error"] = "AI analysis failed: " + str(exc)

        return result

    async def generate_topical_map(
        self,
        niche: str,
        num_pillars: int = 5,
    ) -> dict[str, Any]:
        """Generate a full topical map hierarchy for a niche.

        Creates a structured content plan with Pillar Topics, Cluster
        Topics, and Supporting Articles optimized for topical authority.

        Args:
            niche: The niche to map (e.g. "home automation").
            num_pillars: Number of pillar topics to generate (default 5).

        Returns:
            Nested dict with pillars -> clusters -> supporting articles,
            each annotated with intent, keywords, difficulty, and content_type.
        """
        logger.info("Generating topical map for %r with %d pillars", niche, num_pillars)

        prompt = (
            'Create a comprehensive topical map for the niche "' + niche
            + '" with exactly ' + str(num_pillars) + ' pillar topics.'
            + '\n\nFor each pillar, generate 3-5 cluster topics. '
            + 'For each cluster, generate 3-5 supporting articles.'
            + '\n\nReturn valid JSON with this exact structure:'
            + '\n{'
            + '\n  "niche": "' + niche + '",'
            + '\n  "pillars": ['
            + '\n    {'
            + '\n      "title": "Pillar Topic Name",'
            + '\n      "description": "Brief description of pillar scope",'
            + '\n      "search_intent": "informational|transactional|navigational|commercial",'
            + '\n      "suggested_keywords": ["kw1", "kw2", "kw3"],'
            + '\n      "estimated_difficulty": 45,'
            + '\n      "content_type": "guide|listicle|howto|comparison|review",'
            + '\n      "clusters": ['
            + '\n        {'
            + '\n          "title": "Cluster Topic Name",'
            + '\n          "search_intent": "informational|transactional|navigational|commercial",'
            + '\n          "suggested_keywords": ["kw1", "kw2"],'
            + '\n          "estimated_difficulty": 35,'
            + '\n          "content_type": "guide|listicle|howto|comparison|review",'
            + '\n          "supporting_articles": ['
            + '\n            {'
            + '\n              "title": "Article Title",'
            + '\n              "search_intent": "informational|transactional|navigational|commercial",'
            + '\n              "suggested_keywords": ["kw1", "kw2"],'
            + '\n              "estimated_difficulty": 25,'
            + '\n              "content_type": "guide|listicle|howto|comparison|review",'
            + '\n              "word_count_target": 1500'
            + '\n            }'
            + '\n          ]'
            + '\n        }'
            + '\n      ]'
            + '\n    }'
            + '\n  ],'
            + '\n  "total_articles": 0,'
            + '\n  "estimated_completion_months": 6'
            + '\n}'
        )

        try:
            topical_map = await self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=(
                    "You are an expert SEO content strategist specializing in topical authority. "
                    "Create comprehensive topical maps that cover a niche thoroughly. "
                    "Each topic must have realistic difficulty scores (1-100) and appropriate content types. "
                    "Respond ONLY with valid JSON matching the requested structure."
                ),
                max_tokens=4096,
                temperature=0.5,
            )
            # Compute totals
            total_articles = 0
            for pillar in topical_map.get("pillars", []):
                for cluster in pillar.get("clusters", []):
                    total_articles += len(cluster.get("supporting_articles", []))
            topical_map["total_articles"] = total_articles
            logger.info(
                "Topical map generated: %d pillars, %d total articles",
                len(topical_map.get("pillars", [])),
                total_articles,
            )
            return topical_map
        except Exception as exc:
            logger.error("LLM call failed during topical map generation: %s", exc)
            return {
                "niche": niche,
                "pillars": [],
                "total_articles": 0,
                "error": "Topical map generation failed: " + str(exc),
            }

    async def find_content_gaps(
        self,
        domain: str,
        niche: str,
    ) -> list[dict[str, Any]]:
        """Find content gaps by comparing target domain against competitors.

        Scrapes SERP results for niche-related queries to discover topics
        that competitors rank for but the target domain does not.

        Args:
            domain: The target domain to analyze (e.g. "example.com").
            niche: The niche to search within.

        Returns:
            List of gap topic dicts with difficulty and opportunity scores.
        """
        logger.info("Finding content gaps for %r in niche %r", domain, niche)
        gaps: list[dict[str, Any]] = []

        if not self.scraper:
            logger.error("SERPScraper is required for content gap analysis")
            return gaps

        # Step 1: Generate seed queries for the niche
        seed_queries: list[str] = []
        try:
            seed_prompt = (
                'Generate 15 diverse search queries that someone interested in "'
                + niche + '" would search for on Google. Include a mix of '
                + 'informational, commercial, and transactional queries. '
                + 'Return as a JSON array of strings.'
            )
            seed_queries = await self.llm_client.generate_json(
                prompt=seed_prompt,
                system_prompt=(
                    "You are an SEO keyword researcher. "
                    "Respond ONLY with a JSON array of search query strings."
                ),
                max_tokens=1000,
                temperature=0.6,
            )
            if not isinstance(seed_queries, list):
                if isinstance(seed_queries, dict):
                    seed_queries = seed_queries.get("queries", [])
                else:
                    seed_queries = []
            logger.info("Generated %d seed queries for gap analysis", len(seed_queries))
        except Exception as exc:
            logger.error("Failed to generate seed queries: %s", exc)
            seed_queries = [
                niche,
                "best " + niche,
                niche + " guide",
                "how to " + niche,
            ]

        # Step 2: Scrape SERP for each query and collect competitor URLs
        domain_clean = domain.lower().replace("https://", "").replace(
            "http://", ""
        ).replace("www.", "").rstrip("/")
        competitor_topics: dict[str, list[str]] = {}
        domain_rankings: list[str] = []

        for query in seed_queries[:15]:
            try:
                serp = await self.scraper.search_google(query=query, num_results=10)
                domain_found = False
                for serp_result in serp.get("organic_results", []):
                    result_url = serp_result.get("url", "").lower()
                    parts = result_url.split("/")
                    result_domain = parts[2] if len(parts) > 2 else ""
                    result_domain = result_domain.replace("www.", "")

                    if domain_clean in result_domain:
                        domain_found = True
                        domain_rankings.append(query)
                    else:
                        if result_domain not in competitor_topics:
                            competitor_topics[result_domain] = []
                        competitor_topics[result_domain].append(query)

                if not domain_found:
                    organic = serp.get("organic_results", [])
                    top_result = organic[0] if organic else {}
                    gaps.append({
                        "query": query,
                        "gap_type": "missing",
                        "top_competitor": top_result.get("url", "N/A"),
                        "top_competitor_title": top_result.get("title", "N/A"),
                        "difficulty": 0,
                        "opportunity_score": 0,
                    })
            except Exception as exc:
                logger.warning("SERP scraping failed for query %r: %s", query, exc)
                continue

        # Step 3: Use AI to score the gaps
        if gaps:
            try:
                gap_queries = [g["query"] for g in gaps]
                scoring_prompt = (
                    'Score these content gap opportunities for the domain "'
                    + domain + '" in the "' + niche + '" niche.'
                    + '\n\nGap topics (queries where the domain does NOT rank):'
                    + '\n' + json.dumps(gap_queries)
                    + '\n\nFor each query, provide:'
                    + '\n- difficulty (1-100): how hard it is to rank'
                    + '\n- opportunity_score (1-100): how valuable this gap is to fill'
                    + '\n- suggested_content_type: guide|listicle|howto|comparison|review'
                    + '\n- priority: high|medium|low'
                    + '\n\nReturn JSON array matching the order of queries:'
                    + '\n[{"query": "...", "difficulty": 50, '
                    + '"opportunity_score": 75, "suggested_content_type": "guide", '
                    + '"priority": "high"}]'
                )
                scored = await self.llm_client.generate_json(
                    prompt=scoring_prompt,
                    system_prompt=(
                        "You are an SEO gap analysis expert. "
                        "Score content opportunities accurately. "
                        "Respond ONLY with valid JSON."
                    ),
                    max_tokens=2000,
                    temperature=0.3,
                )
                if isinstance(scored, list):
                    for i, score_data in enumerate(scored):
                        if i < len(gaps):
                            gaps[i]["difficulty"] = score_data.get("difficulty", 50)
                            gaps[i]["opportunity_score"] = score_data.get(
                                "opportunity_score", 50
                            )
                            gaps[i]["suggested_content_type"] = score_data.get(
                                "suggested_content_type", "guide"
                            )
                            gaps[i]["priority"] = score_data.get("priority", "medium")
                logger.info("Scored %d content gaps", len(gaps))
            except Exception as exc:
                logger.error("Failed to score content gaps: %s", exc)

        # Sort by opportunity score descending
        gaps.sort(key=lambda g: g.get("opportunity_score", 0), reverse=True)

        logger.info(
            "Content gap analysis complete: %d gaps found for %r",
            len(gaps), domain,
        )
        return gaps

    async def build_content_silo(
        self,
        topical_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a content silo structure from a topical map.

        Takes an existing topical map and organizes it into hub-and-spoke
        silo structures with an internal linking plan and linking matrix.

        Args:
            topical_map: A topical map dict as returned by generate_topical_map().

        Returns:
            Silo structure dict with hub pages, spoke articles, and linking_matrix.
        """
        niche = topical_map.get("niche", "unknown")
        logger.info("Building content silo for niche: %r", niche)

        pillars = topical_map.get("pillars", [])
        if not pillars:
            logger.warning("No pillars in topical map, cannot build silo")
            return {
                "niche": niche,
                "silos": [],
                "linking_matrix": {},
                "error": "No pillars found",
            }

        # Build the silo structure
        silos: list[dict[str, Any]] = []
        all_pages: list[str] = []

        for pillar in pillars:
            pillar_title = pillar.get("title", "Untitled Pillar")
            hub_slug = pillar_title.lower().replace(" ", "-")[:60]

            silo: dict[str, Any] = {
                "hub_page": {
                    "title": pillar_title,
                    "slug": "/" + hub_slug + "/",
                    "content_type": pillar.get("content_type", "guide"),
                    "role": "hub",
                    "internal_links_to": [],
                },
                "spoke_articles": [],
                "total_spokes": 0,
            }
            all_pages.append(pillar_title)

            for cluster in pillar.get("clusters", []):
                cluster_title = cluster.get("title", "Untitled Cluster")
                cluster_slug = cluster_title.lower().replace(" ", "-")[:60]

                cluster_page: dict[str, Any] = {
                    "title": cluster_title,
                    "slug": "/" + hub_slug + "/" + cluster_slug + "/",
                    "content_type": cluster.get("content_type", "guide"),
                    "role": "sub-hub",
                    "parent_hub": pillar_title,
                    "internal_links_to": [pillar_title],
                    "supporting_articles": [],
                }
                all_pages.append(cluster_title)
                silo["hub_page"]["internal_links_to"].append(cluster_title)

                for article in cluster.get("supporting_articles", []):
                    article_title = article.get("title", "Untitled Article")
                    article_slug = article_title.lower().replace(" ", "-")[:60]

                    spoke: dict[str, Any] = {
                        "title": article_title,
                        "slug": (
                            "/" + hub_slug + "/" + cluster_slug
                            + "/" + article_slug + "/"
                        ),
                        "content_type": article.get("content_type", "howto"),
                        "role": "spoke",
                        "parent_cluster": cluster_title,
                        "parent_hub": pillar_title,
                        "internal_links_to": [cluster_title, pillar_title],
                        "search_intent": article.get("search_intent", "informational"),
                        "estimated_difficulty": article.get("estimated_difficulty", 50),
                        "word_count_target": article.get("word_count_target", 1500),
                    }
                    cluster_page["supporting_articles"].append(spoke)
                    cluster_page["internal_links_to"].append(article_title)
                    all_pages.append(article_title)
                    silo["total_spokes"] += 1

                silo["spoke_articles"].append(cluster_page)

            silos.append(silo)

        # Build linking matrix using AI for cross-silo opportunities
        linking_matrix: dict[str, list[str]] = {}
        try:
            silo_desc_parts = []
            for silo_item in silos:
                hub_title = silo_item["hub_page"]["title"]
                spoke_titles = []
                for cluster_p in silo_item.get("spoke_articles", []):
                    spoke_titles.append(cluster_p["title"])
                    for art in cluster_p.get("supporting_articles", []):
                        spoke_titles.append(art["title"])
                titles_json = json.dumps(spoke_titles[:10])
                silo_desc_parts.append(
                    "\nSilo: " + hub_title + "\n  Pages: " + titles_json
                )

            silo_desc = "".join(silo_desc_parts)
            matrix_prompt = (
                'Given these content pages for a "' + niche
                + '" website, suggest cross-silo internal linking opportunities. '
                + 'Each page should link to 2-3 related pages from OTHER silos '
                + '(not its own pillar).\n\nPages by silo:'
                + silo_desc
                + '\n\nReturn JSON object where keys are page titles and values '
                + 'are arrays of page titles to link TO (from other silos):'
                + '\n{"Page Title A": ["Page Title X", "Page Title Y"]}'
            )

            cross_links = await self.llm_client.generate_json(
                prompt=matrix_prompt,
                system_prompt=(
                    "You are an SEO internal linking expert. "
                    "Suggest topically relevant cross-silo links. "
                    "Respond ONLY with valid JSON."
                ),
                max_tokens=2000,
                temperature=0.3,
            )
            if isinstance(cross_links, dict):
                linking_matrix = cross_links
                logger.info(
                    "Generated cross-silo linking matrix with %d entries",
                    len(linking_matrix),
                )
        except Exception as exc:
            logger.error("Failed to generate linking matrix: %s", exc)

        silo_summary = []
        for s in silos:
            silo_summary.append({
                "hub": s["hub_page"]["title"],
                "clusters": len(s["spoke_articles"]),
                "total_spokes": s["total_spokes"],
            })

        result = {
            "niche": niche,
            "silos": silos,
            "total_silos": len(silos),
            "total_pages": len(all_pages),
            "linking_matrix": linking_matrix,
            "silo_summary": silo_summary,
        }
        logger.info(
            "Content silo built: %d silos, %d total pages",
            len(silos), len(all_pages),
        )
        return result

    async def analyze_competitors(
        self,
        niche: str,
        num_competitors: int = 5,
    ) -> list[dict[str, Any]]:
        """Analyze top competitors in a niche by scraping SERP data.

        Identifies the strongest competitors, evaluates their topical
        coverage, and identifies their strengths and content gaps.

        Args:
            niche: The niche to analyze competitors in.
            num_competitors: Maximum number of competitors to analyze.

        Returns:
            List of competitor analysis dicts with strengths and gaps.
        """
        logger.info("Analyzing competitors for niche: %r", niche)
        competitors: dict[str, dict[str, Any]] = {}

        # Step 1: Generate diverse queries to discover competitors
        queries: list[str] = []
        try:
            query_prompt = (
                'Generate 10 high-volume search queries for the "' + niche
                + '" niche. Include a mix of informational, commercial, and '
                + 'transactional queries. Return as a JSON array of strings.'
            )
            queries = await self.llm_client.generate_json(
                prompt=query_prompt,
                system_prompt=(
                    "You are an SEO researcher. "
                    "Return ONLY a JSON array of search query strings."
                ),
                max_tokens=500,
                temperature=0.5,
            )
            if not isinstance(queries, list):
                queries = [niche]
        except Exception as exc:
            logger.error("Failed to generate competitor queries: %s", exc)
            queries = [niche, "best " + niche, niche + " guide"]

        # Step 2: Scrape SERPs and collect competitor data
        skip_domains = [
            "wikipedia.org", "youtube.com", "reddit.com",
            "quora.com", "amazon.com", "facebook.com",
            "twitter.com", "linkedin.com", "pinterest.com",
        ]

        if self.scraper:
            for query in queries[:10]:
                try:
                    serp = await self.scraper.search_google(
                        query=query, num_results=10
                    )
                    for serp_result in serp.get("organic_results", []):
                        url = serp_result.get("url", "")
                        if not url:
                            continue
                        parts = url.split("/")
                        comp_domain = parts[2] if len(parts) > 2 else ""
                        comp_domain = comp_domain.replace("www.", "")

                        if any(sd in comp_domain for sd in skip_domains):
                            continue

                        if comp_domain not in competitors:
                            competitors[comp_domain] = {
                                "domain": comp_domain,
                                "rankings": [],
                                "avg_position": 0.0,
                                "total_appearances": 0,
                                "topics_covered": [],
                                "top_pages": [],
                            }

                        competitors[comp_domain]["rankings"].append({
                            "query": query,
                            "position": serp_result.get("position", 0),
                            "title": serp_result.get("title", ""),
                            "url": url,
                        })
                        competitors[comp_domain]["total_appearances"] += 1
                        competitors[comp_domain]["topics_covered"].append(query)
                except Exception as exc:
                    logger.warning(
                        "SERP failed for competitor query %r: %s", query, exc
                    )

        # Step 3: Calculate metrics and sort
        for comp_data in competitors.values():
            positions = [r["position"] for r in comp_data["rankings"]]
            if positions:
                comp_data["avg_position"] = sum(positions) / len(positions)
            else:
                comp_data["avg_position"] = 0
            comp_data["topics_covered"] = list(set(comp_data["topics_covered"]))
            comp_data["top_pages"] = sorted(
                comp_data["rankings"], key=lambda r: r["position"]
            )[:5]

        sorted_competitors = sorted(
            competitors.values(),
            key=lambda c: c["total_appearances"],
            reverse=True,
        )[:num_competitors]

        # Step 4: Use AI to analyze strengths and gaps
        if sorted_competitors:
            try:
                comp_summary = []
                for comp in sorted_competitors:
                    comp_summary.append({
                        "domain": comp["domain"],
                        "appearances": comp["total_appearances"],
                        "avg_position": round(comp["avg_position"], 1),
                        "topics": comp["topics_covered"][:8],
                    })

                analysis_prompt = (
                    'Analyze these competitors in the "' + niche + '" niche:'
                    + '\n' + json.dumps(comp_summary, indent=2)
                    + '\n\nFor each competitor, provide:'
                    + '\n- strengths: list of 3-5 content/SEO strengths'
                    + '\n- weaknesses: list of 2-3 gaps or weaknesses'
                    + '\n- content_strategy: brief description of their approach'
                    + '\n- threat_level: high|medium|low'
                    + '\n- topics_to_steal: 2-3 topic ideas to compete on'
                    + '\n\nReturn JSON array:'
                    + '\n[{"domain": "...", "strengths": [...], '
                    + '"weaknesses": [...], "content_strategy": "...", '
                    + '"threat_level": "...", "topics_to_steal": [...]}]'
                )
                ai_analysis = await self.llm_client.generate_json(
                    prompt=analysis_prompt,
                    system_prompt=(
                        "You are a competitive SEO analyst. "
                        "Analyze competitors objectively. "
                        "Respond ONLY with valid JSON."
                    ),
                    max_tokens=2000,
                    temperature=0.4,
                )
                if isinstance(ai_analysis, list):
                    for i, analysis in enumerate(ai_analysis):
                        if i < len(sorted_competitors):
                            sorted_competitors[i]["strengths"] = analysis.get(
                                "strengths", []
                            )
                            sorted_competitors[i]["weaknesses"] = analysis.get(
                                "weaknesses", []
                            )
                            sorted_competitors[i]["content_strategy"] = analysis.get(
                                "content_strategy", ""
                            )
                            sorted_competitors[i]["threat_level"] = analysis.get(
                                "threat_level", "medium"
                            )
                            sorted_competitors[i]["topics_to_steal"] = analysis.get(
                                "topics_to_steal", []
                            )
                logger.info(
                    "AI competitor analysis complete for %d competitors",
                    len(sorted_competitors),
                )
            except Exception as exc:
                logger.error("AI competitor analysis failed: %s", exc)

        logger.info(
            "Competitor analysis complete: %d competitors found",
            len(sorted_competitors),
        )
        return sorted_competitors

    async def get_trending_topics(
        self,
        niche: str,
    ) -> list[dict[str, Any]]:
        """Find trending subtopics within a niche using Google Trends.

        Combines Google Trends data with AI analysis to identify
        emerging content opportunities with trend scores and seasonality.

        Args:
            niche: The niche to find trends for.

        Returns:
            List of trending topic dicts with trend_score, growth_direction,
            and seasonality information.
        """
        logger.info("Getting trending topics for niche: %r", niche)
        trending: list[dict[str, Any]] = []

        # Step 1: Get related queries from Google Trends
        related_rising: list[dict[str, Any]] = []
        related_top: list[dict[str, Any]] = []

        if self.trends_client:
            try:
                related = await self.trends_client.get_related_queries(
                    keyword=niche,
                    timeframe="today 12-m",
                )
                related_rising = related.get("rising", [])
                related_top = related.get("top", [])
                logger.info(
                    "Trends data: %d rising, %d top queries",
                    len(related_rising), len(related_top),
                )
            except Exception as exc:
                logger.error("Failed to get related queries from Trends: %s", exc)

            try:
                interest_data = await self.trends_client.get_interest_over_time(
                    keywords=[niche],
                    timeframe="today 12-m",
                )
                logger.info("Interest data: %d points", len(interest_data))
            except Exception as exc:
                logger.error("Failed to get interest over time: %s", exc)

            # Get keyword suggestions
            try:
                suggestions = await self.trends_client.get_keyword_suggestions(
                    keyword=niche,
                    timeframe="today 12-m",
                )
                for sug in suggestions[:10]:
                    related_top.append({
                        "query": sug.get("topic_title", ""),
                        "value": sug.get("value", 0),
                    })
            except Exception as exc:
                logger.error("Failed to get keyword suggestions: %s", exc)

        # Step 2: Process rising queries
        for item in related_rising[:15]:
            query_text = item.get("query", "")
            raw_value = item.get("value", 0)
            if isinstance(raw_value, str) and "Breakout" in str(raw_value):
                trend_score = 100
                growth = "breakout"
            else:
                try:
                    trend_score = min(int(raw_value), 100)
                except (ValueError, TypeError):
                    trend_score = 50
                growth = "rising"

            trending.append({
                "topic": query_text,
                "trend_score": trend_score,
                "growth_direction": growth,
                "source": "google_trends_rising",
                "seasonality": "unknown",
                "opportunity_notes": "",
            })

        # Step 3: Process top queries
        for item in related_top[:10]:
            query_text = item.get("query", "") or item.get("topic_title", "")
            raw_value = item.get("value", 0)
            try:
                trend_score = min(int(raw_value), 100)
            except (ValueError, TypeError):
                trend_score = 50

            existing_topics = [t["topic"] for t in trending]
            if query_text and query_text not in existing_topics:
                trending.append({
                    "topic": query_text,
                    "trend_score": trend_score,
                    "growth_direction": "stable",
                    "source": "google_trends_top",
                    "seasonality": "unknown",
                    "opportunity_notes": "",
                })

        # Step 4: Enrich with AI analysis for seasonality and opportunity
        if trending and self.llm_client:
            try:
                topics_list = [t["topic"] for t in trending[:20]]
                enrich_prompt = (
                    'Analyze these trending topics related to "' + niche
                    + '" for SEO content planning.'
                    + '\n\nTopics: ' + json.dumps(topics_list)
                    + '\n\nFor each topic provide:'
                    + '\n- seasonality: evergreen|seasonal_q1|seasonal_q2|'
                    + 'seasonal_q3|seasonal_q4|event_driven'
                    + '\n- opportunity_notes: brief note on content opportunity'
                    + '\n- content_angle: suggested angle or approach'
                    + '\n\nReturn JSON array in the same order as input:'
                    + '\n[{"topic": "...", "seasonality": "...", '
                    + '"opportunity_notes": "...", "content_angle": "..."}]'
                )
                enriched = await self.llm_client.generate_json(
                    prompt=enrich_prompt,
                    system_prompt=(
                        "You are an SEO trend analyst. "
                        "Analyze content timing and opportunities. "
                        "Respond ONLY with valid JSON."
                    ),
                    max_tokens=2000,
                    temperature=0.3,
                )
                if isinstance(enriched, list):
                    for i, enrichment in enumerate(enriched):
                        if i < len(trending):
                            trending[i]["seasonality"] = enrichment.get(
                                "seasonality", "unknown"
                            )
                            trending[i]["opportunity_notes"] = enrichment.get(
                                "opportunity_notes", ""
                            )
                            trending[i]["content_angle"] = enrichment.get(
                                "content_angle", ""
                            )
                logger.info(
                    "Enriched %d trending topics with AI analysis",
                    len(trending),
                )
            except Exception as exc:
                logger.error("AI enrichment of trending topics failed: %s", exc)

        # Sort by trend score descending
        trending.sort(key=lambda t: t.get("trend_score", 0), reverse=True)

        logger.info(
            "Trending topics analysis complete: %d topics found",
            len(trending),
        )
        return trending
