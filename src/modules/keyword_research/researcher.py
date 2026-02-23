"""Keyword Research module -- core researcher with AI-powered expansion, classification, clustering, and scoring."""

import asyncio
import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KeywordResearcher:
    """AI-powered keyword research pipeline.

    Integrates LLM, SERP scraping, and Google Trends to deliver
    comprehensive keyword expansion, intent classification,
    semantic clustering, opportunity scoring, and SERP analysis.

    Usage::

        from src.integrations.llm_client import LLMClient
        from src.integrations.serp_scraper import SERPScraper
        from src.integrations.google_trends import GoogleTrendsClient

        researcher = KeywordResearcher(
            llm_client=LLMClient(),
            serp_scraper=SERPScraper(),
            trends_client=GoogleTrendsClient(),
        )
        results = await researcher.full_research_pipeline(
            seed_keywords=["seo tools", "keyword research"],
            niche="digital marketing",
        )
    """

    def __init__(
        self,
        llm_client=None,
        serp_scraper=None,
        trends_client=None,
    ):
        from src.integrations.llm_client import LLMClient
        from src.integrations.serp_scraper import SERPScraper
        from src.integrations.google_trends import GoogleTrendsClient

        self._llm = llm_client or LLMClient()
        self._serp = serp_scraper or SERPScraper()
        self._trends = trends_client or GoogleTrendsClient()

    # ------------------------------------------------------------------
    # expand_keywords
    # ------------------------------------------------------------------

    async def expand_keywords(
        self,
        seed_keywords: list[str],
        niche: str = "",
    ) -> list[dict]:
        """Expand seed keywords using AI, SERP PAA, related searches, and autocomplete.

        Returns a deduplicated list of keyword dicts with:
        keyword, estimated_volume, intent, difficulty_estimate, source.
        """
        logger.info("Expanding %d seed keywords for niche=%r", len(seed_keywords), niche)
        all_raw_keywords: list[dict] = []

        # 1. Add seeds themselves
        for kw in seed_keywords:
            all_raw_keywords.append({"keyword": kw.strip().lower(), "source": "seed"})

        # 2. Gather SERP data (PAA + related) for each seed
        serp_tasks = [self._expand_from_serp(kw) for kw in seed_keywords[:10]]
        serp_results = await asyncio.gather(*serp_tasks, return_exceptions=True)
        for res in serp_results:
            if isinstance(res, Exception):
                logger.warning("SERP expansion error: %s", res)
                continue
            all_raw_keywords.extend(res)

        # 3. AI-generated keyword expansion
        try:
            ai_keywords = await self._expand_from_ai(seed_keywords, niche)
            all_raw_keywords.extend(ai_keywords)
        except Exception as exc:
            logger.warning("AI keyword expansion failed: %s", exc)

        # 4. Deduplicate by keyword text
        seen: set[str] = set()
        unique_keywords: list[dict] = []
        for entry in all_raw_keywords:
            kw_text = entry.get("keyword", "").strip().lower()
            if kw_text and kw_text not in seen:
                seen.add(kw_text)
                unique_keywords.append(entry)

        logger.info(
            "Expanded to %d unique keywords from %d raw",
            len(unique_keywords), len(all_raw_keywords),
        )

        # 5. AI enrichment: estimate volume, intent, difficulty for all
        enriched = await self._enrich_keywords_batch(unique_keywords, niche)
        return enriched

    async def _expand_from_serp(self, keyword: str) -> list[dict]:
        """Extract PAA and related searches from SERP for a single keyword."""
        results: list[dict] = []
        try:
            serp_data = await self._serp.search_google(keyword, num_results=10)
            for paa_q in serp_data.get("people_also_ask", []):
                cleaned = paa_q.strip()
                if cleaned:
                    results.append({"keyword": cleaned.lower(), "source": "paa"})
            for rel in serp_data.get("related_searches", []):
                cleaned = rel.strip()
                if cleaned:
                    results.append({"keyword": cleaned.lower(), "source": "related"})
        except Exception as exc:
            logger.warning("SERP expansion failed for %r: %s", keyword, exc)
        return results

    async def _expand_from_ai(
        self, seed_keywords: list[str], niche: str,
    ) -> list[dict]:
        """Use AI to generate additional keyword ideas from seeds."""
        seeds_str = ", ".join(seed_keywords[:20])
        niche_part = ""
        if niche:
            niche_part = " in the " + niche + " niche"

        prompt = (
            "You are an expert SEO keyword researcher. "
            "Given these seed keywords" + niche_part + ":\n\n"
            + seeds_str + "\n\n"
            "Generate 30 additional keyword ideas including:\n"
            "- Long-tail variations\n"
            "- Related topics and subtopics\n"
            "- Question-based keywords\n"
            "- Commercial/transactional variations\n"
            "- Comparison keywords\n\n"
            "Return ONLY a JSON array of objects with these fields:\n"
            "- \"keyword\": the keyword phrase\n"
            "- \"estimated_volume\": monthly search volume estimate (integer)\n"
            "- \"intent\": one of informational, transactional, commercial, navigational\n"
            "- \"difficulty_estimate\": 0-100 integer\n\n"
            "Return valid JSON array only, no other text."
        )

        data = await self._llm.generate_json(prompt)
        results: list[dict] = []
        items = data if isinstance(data, list) else data.get("keywords", [])
        for item in items:
            kw_text = str(item.get("keyword", "")).strip().lower()
            if kw_text:
                results.append({
                    "keyword": kw_text,
                    "source": "ai_generated",
                    "estimated_volume": int(item.get("estimated_volume", 0)),
                    "intent": str(item.get("intent", "informational")),
                    "difficulty_estimate": int(item.get("difficulty_estimate", 50)),
                })
        logger.info("AI generated %d keyword ideas", len(results))
        return results

    async def _enrich_keywords_batch(
        self, keywords: list[dict], niche: str,
    ) -> list[dict]:
        """Batch-enrich keywords that lack volume/intent/difficulty via AI."""
        needs_enrichment = []
        already_enriched = []
        for kw in keywords:
            has_vol = kw.get("estimated_volume") is not None
            has_intent = bool(kw.get("intent"))
            has_diff = kw.get("difficulty_estimate") is not None
            if has_vol and has_intent and has_diff:
                already_enriched.append(kw)
            else:
                needs_enrichment.append(kw)

        if not needs_enrichment:
            return already_enriched

        # Process in batches of 25
        batch_size = 25
        enriched_all: list[dict] = list(already_enriched)

        for i in range(0, len(needs_enrichment), batch_size):
            batch = needs_enrichment[i : i + batch_size]
            batch_texts = [kw["keyword"] for kw in batch]
            niche_part = ""
            if niche:
                niche_part = " in the " + niche + " niche"

            prompt = (
                "You are an SEO expert. For each keyword below" + niche_part + ", "
                "estimate the monthly search volume, search intent, and ranking difficulty.\n\n"
                "Keywords:\n"
                + "\n".join("- " + t for t in batch_texts) + "\n\n"
                "Return ONLY a JSON array with one object per keyword:\n"
                "- \"keyword\": exact keyword text\n"
                "- \"estimated_volume\": monthly volume estimate (integer)\n"
                "- \"intent\": one of informational, transactional, commercial, navigational\n"
                "- \"difficulty_estimate\": 0-100 integer\n\n"
                "Return valid JSON array only."
            )

            try:
                data = await self._llm.generate_json(prompt)
                items = data if isinstance(data, list) else []
                enrichment_map: dict[str, dict] = {}
                for item in items:
                    k = str(item.get("keyword", "")).strip().lower()
                    if k:
                        enrichment_map[k] = item

                for kw in batch:
                    kw_text = kw["keyword"]
                    if kw_text in enrichment_map:
                        info = enrichment_map[kw_text]
                        kw["estimated_volume"] = int(info.get("estimated_volume", 0))
                        kw["intent"] = str(info.get("intent", "informational"))
                        kw["difficulty_estimate"] = int(info.get("difficulty_estimate", 50))
                    else:
                        kw.setdefault("estimated_volume", 0)
                        kw.setdefault("intent", "informational")
                        kw.setdefault("difficulty_estimate", 50)
                    enriched_all.append(kw)
            except Exception as exc:
                logger.warning("Batch enrichment failed: %s", exc)
                for kw in batch:
                    kw.setdefault("estimated_volume", 0)
                    kw.setdefault("intent", "informational")
                    kw.setdefault("difficulty_estimate", 50)
                    enriched_all.append(kw)

        return enriched_all

    # ------------------------------------------------------------------
    # classify_intent
    # ------------------------------------------------------------------

    async def classify_intent(self, keywords: list[str]) -> list[dict]:
        """Batch-classify search intent for a list of keyword strings.

        Returns list of dicts: keyword, intent, confidence, suggested_content_type.
        """
        logger.info("Classifying intent for %d keywords", len(keywords))
        results: list[dict] = []
        batch_size = 30

        for i in range(0, len(keywords), batch_size):
            batch = keywords[i : i + batch_size]
            kw_list_str = "\n".join("- " + kw for kw in batch)

            prompt = (
                "You are an SEO search intent classifier. "
                "Classify each keyword below into one of these intents:\n"
                "- informational: user wants to learn something\n"
                "- transactional: user wants to buy/download/sign up\n"
                "- commercial: user is researching before buying\n"
                "- navigational: user wants a specific website/page\n\n"
                "Keywords:\n" + kw_list_str + "\n\n"
                "Return ONLY a JSON array with one object per keyword:\n"
                "- \"keyword\": exact keyword text\n"
                "- \"intent\": the classified intent\n"
                "- \"confidence\": confidence score 0.0 to 1.0\n"
                "- \"suggested_content_type\": best content format "
                "(e.g. blog post, product page, landing page, how-to guide, "
                "listicle, comparison, review, tutorial)\n\n"
                "Return valid JSON array only."
            )

            try:
                data = await self._llm.generate_json(prompt)
                items = data if isinstance(data, list) else []
                result_map: dict[str, dict] = {}
                for item in items:
                    k = str(item.get("keyword", "")).strip().lower()
                    if k:
                        result_map[k] = item

                for kw in batch:
                    kw_lower = kw.strip().lower()
                    if kw_lower in result_map:
                        info = result_map[kw_lower]
                        results.append({
                            "keyword": kw,
                            "intent": str(info.get("intent", "informational")),
                            "confidence": float(info.get("confidence", 0.5)),
                            "suggested_content_type": str(
                                info.get("suggested_content_type", "blog post")
                            ),
                        })
                    else:
                        results.append({
                            "keyword": kw,
                            "intent": "informational",
                            "confidence": 0.3,
                            "suggested_content_type": "blog post",
                        })
            except Exception as exc:
                logger.warning("Intent classification batch failed: %s", exc)
                for kw in batch:
                    results.append({
                        "keyword": kw,
                        "intent": "informational",
                        "confidence": 0.0,
                        "suggested_content_type": "blog post",
                    })

        logger.info("Classified intent for %d keywords", len(results))
        return results

    # ------------------------------------------------------------------
    # cluster_keywords
    # ------------------------------------------------------------------

    async def cluster_keywords(
        self,
        keywords: list[dict],
        method: str = "semantic",
    ) -> list[dict]:
        """Group keywords into semantic clusters.

        Supports 'semantic' (AI-based) or 'tfidf' (sklearn-based) clustering.
        Returns list of cluster dicts: cluster_name, cluster_intent,
        keywords, primary_keyword, estimated_total_volume.
        """
        logger.info("Clustering %d keywords with method=%s", len(keywords), method)
        if not keywords:
            return []

        if method == "tfidf":
            return await self._cluster_tfidf(keywords)
        return await self._cluster_semantic(keywords)

    async def _cluster_semantic(self, keywords: list[dict]) -> list[dict]:
        """AI-based semantic clustering."""
        kw_summaries = []
        for kw in keywords:
            text = kw.get("keyword", "")
            vol = kw.get("estimated_volume", 0)
            intent = kw.get("intent", "unknown")
            line = text + " (vol:" + str(vol) + ", intent:" + intent + ")"
            kw_summaries.append(line)

        kw_block = "\n".join(kw_summaries[:100])

        prompt = (
            "You are an expert SEO strategist. Group these keywords into semantic "
            "clusters based on topic similarity and search intent.\n\n"
            "Keywords:\n" + kw_block + "\n\n"
            "Create logical clusters where each cluster targets a single topic/subtopic.\n\n"
            "Return ONLY a JSON array of cluster objects:\n"
            "- \"cluster_name\": descriptive name for the cluster\n"
            "- \"cluster_intent\": dominant intent (informational/transactional/commercial/navigational)\n"
            "- \"keywords\": array of keyword strings in this cluster\n"
            "- \"primary_keyword\": the best keyword to target as the main term\n\n"
            "Return valid JSON array only."
        )

        try:
            data = await self._llm.generate_json(prompt)
            clusters_raw = data if isinstance(data, list) else []
        except Exception as exc:
            logger.error("Semantic clustering failed: %s", exc)
            return [self._make_single_cluster(keywords)]

        # Build a lookup for volume data
        vol_map: dict[str, int] = {}
        for kw in keywords:
            vol_map[kw.get("keyword", "").strip().lower()] = int(
                kw.get("estimated_volume", 0)
            )

        clusters: list[dict] = []
        for cl in clusters_raw:
            cl_keywords = cl.get("keywords", [])
            total_vol = 0
            for k in cl_keywords:
                total_vol += vol_map.get(str(k).strip().lower(), 0)

            primary = cl.get("primary_keyword", "")
            if not primary and cl_keywords:
                primary = cl_keywords[0]

            clusters.append({
                "cluster_name": str(cl.get("cluster_name", "Unnamed Cluster")),
                "cluster_intent": str(cl.get("cluster_intent", "informational")),
                "keywords": cl_keywords,
                "primary_keyword": str(primary),
                "estimated_total_volume": total_vol,
            })

        # Catch any keywords not assigned to clusters
        assigned: set[str] = set()
        for cl in clusters:
            for k in cl["keywords"]:
                assigned.add(str(k).strip().lower())

        unassigned = [
            kw for kw in keywords
            if kw.get("keyword", "").strip().lower() not in assigned
        ]
        if unassigned:
            unclustered = self._make_single_cluster(unassigned, name="Uncategorized")
            clusters.append(unclustered)

        logger.info("Created %d semantic clusters", len(clusters))
        return clusters

    async def _cluster_tfidf(self, keywords: list[dict]) -> list[dict]:
        """TF-IDF + KMeans clustering using sklearn."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.cluster import KMeans
        except ImportError:
            logger.warning("sklearn not installed, falling back to semantic clustering")
            return await self._cluster_semantic(keywords)

        texts = [kw.get("keyword", "") for kw in keywords]
        if len(texts) < 3:
            return [self._make_single_cluster(keywords)]

        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        tfidf_matrix = vectorizer.fit_transform(texts)

        n_clusters = min(max(len(texts) // 5, 2), 15)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(tfidf_matrix)

        # Group keywords by cluster label
        cluster_groups: dict[int, list[dict]] = {}
        for idx, label in enumerate(labels):
            label_int = int(label)
            if label_int not in cluster_groups:
                cluster_groups[label_int] = []
            cluster_groups[label_int].append(keywords[idx])

        # Build cluster dicts
        clusters: list[dict] = []
        for label_int, group in sorted(cluster_groups.items()):
            group_kws = [kw.get("keyword", "") for kw in group]
            total_vol = sum(int(kw.get("estimated_volume", 0)) for kw in group)

            # Pick primary keyword by highest volume
            primary = max(group, key=lambda x: int(x.get("estimated_volume", 0)))
            primary_kw = primary.get("keyword", group_kws[0] if group_kws else "")

            # Dominant intent
            intent_counts: dict[str, int] = {}
            for kw in group:
                iv = kw.get("intent", "informational")
                intent_counts[iv] = intent_counts.get(iv, 0) + 1
            dominant_intent = "informational"
            if intent_counts:
                dominant_intent = max(intent_counts, key=intent_counts.get)

            cluster_name = "Cluster " + str(label_int + 1) + ": " + primary_kw
            clusters.append({
                "cluster_name": cluster_name,
                "cluster_intent": dominant_intent,
                "keywords": group_kws,
                "primary_keyword": primary_kw,
                "estimated_total_volume": total_vol,
            })

        logger.info("Created %d TF-IDF clusters", len(clusters))
        return clusters

    @staticmethod
    def _make_single_cluster(
        keywords: list[dict], name: str = "All Keywords",
    ) -> dict:
        """Create a single cluster containing all keywords."""
        kw_texts = [kw.get("keyword", "") for kw in keywords]
        total_vol = sum(int(kw.get("estimated_volume", 0)) for kw in keywords)
        primary = {}
        if keywords:
            primary = max(keywords, key=lambda x: int(x.get("estimated_volume", 0)))
        return {
            "cluster_name": name,
            "cluster_intent": "informational",
            "keywords": kw_texts,
            "primary_keyword": primary.get("keyword", kw_texts[0] if kw_texts else ""),
            "estimated_total_volume": total_vol,
        }

    # ------------------------------------------------------------------
    # score_keywords
    # ------------------------------------------------------------------

    async def score_keywords(self, keywords: list[dict]) -> list[dict]:
        """AI-powered opportunity scoring for each keyword.

        Adds opportunity_score (0-100) and reasoning to each keyword dict.
        """
        logger.info("Scoring %d keywords", len(keywords))
        if not keywords:
            return []

        scored: list[dict] = []
        batch_size = 20

        for i in range(0, len(keywords), batch_size):
            batch = keywords[i : i + batch_size]
            kw_details = []
            for kw in batch:
                detail = (
                    kw.get("keyword", "")
                    + " | vol:" + str(kw.get("estimated_volume", 0))
                    + " | diff:" + str(kw.get("difficulty_estimate", 50))
                    + " | intent:" + str(kw.get("intent", "unknown"))
                )
                kw_details.append(detail)

            details_block = "\n".join(kw_details)

            prompt = (
                "You are an SEO opportunity analyst. Score each keyword below from "
                "0-100 based on the balance of search volume, ranking difficulty, "
                "search intent value, and competition level. Higher scores mean "
                "better opportunities.\n\n"
                "Keywords (keyword | volume | difficulty | intent):\n"
                + details_block + "\n\n"
                "Scoring guidelines:\n"
                "- High volume + low difficulty = high score\n"
                "- Transactional/commercial intent adds value\n"
                "- Very high difficulty reduces score significantly\n"
                "- Long-tail with decent volume scores well\n\n"
                "Return ONLY a JSON array with one object per keyword:\n"
                "- \"keyword\": exact keyword text\n"
                "- \"opportunity_score\": integer 0-100\n"
                "- \"reasoning\": brief explanation (1-2 sentences)\n\n"
                "Return valid JSON array only."
            )

            try:
                data = await self._llm.generate_json(prompt)
                items = data if isinstance(data, list) else []
                score_map: dict[str, dict] = {}
                for item in items:
                    k = str(item.get("keyword", "")).strip().lower()
                    if k:
                        score_map[k] = item

                for kw in batch:
                    kw_copy = dict(kw)
                    kw_lower = kw.get("keyword", "").strip().lower()
                    if kw_lower in score_map:
                        info = score_map[kw_lower]
                        kw_copy["opportunity_score"] = int(
                            info.get("opportunity_score", 50)
                        )
                        kw_copy["reasoning"] = str(info.get("reasoning", ""))
                    else:
                        kw_copy["opportunity_score"] = self._calculate_fallback_score(kw)
                        kw_copy["reasoning"] = "Score estimated from volume and difficulty metrics."
                    scored.append(kw_copy)
            except Exception as exc:
                logger.warning("Scoring batch failed: %s", exc)
                for kw in batch:
                    kw_copy = dict(kw)
                    kw_copy["opportunity_score"] = self._calculate_fallback_score(kw)
                    kw_copy["reasoning"] = "Fallback score due to AI error."
                    scored.append(kw_copy)

        logger.info("Scored %d keywords", len(scored))
        return scored

    @staticmethod
    def _calculate_fallback_score(kw: dict) -> int:
        """Calculate a simple opportunity score from volume and difficulty."""
        vol = int(kw.get("estimated_volume", 0))
        diff = int(kw.get("difficulty_estimate", 50))
        vol_score = min(math.log10(max(vol, 1)) * 20, 100)
        diff_penalty = diff
        score = int(vol_score * 0.6 + (100 - diff_penalty) * 0.4)
        return max(0, min(100, score))

    # ------------------------------------------------------------------
    # analyze_serp
    # ------------------------------------------------------------------

    async def analyze_serp(self, keyword: str) -> dict:
        """Detailed SERP analysis for a single keyword.

        Returns top results, content types, SERP features, PAA questions,
        and AI-estimated avg word count.
        """
        logger.info("Analyzing SERP for %r", keyword)
        result: dict[str, Any] = {
            "keyword": keyword,
            "top_results": [],
            "content_types": [],
            "featured_snippet": None,
            "paa_questions": [],
            "related_searches": [],
            "serp_features": {},
            "avg_word_count_estimate": 0,
            "analysis_summary": "",
            "dominant_format": "",
            "authority_level": "medium",
        }

        try:
            serp_data = await self._serp.search_google(keyword, num_results=10)
        except Exception as exc:
            logger.error("SERP fetch failed for %r: %s", keyword, exc)
            result["analysis_summary"] = "SERP data unavailable: " + str(exc)
            return result

        organic = serp_data.get("organic_results", [])
        result["top_results"] = organic[:10]
        result["featured_snippet"] = serp_data.get("featured_snippet")
        result["paa_questions"] = serp_data.get("people_also_ask", [])
        result["related_searches"] = serp_data.get("related_searches", [])

        result["serp_features"] = {
            "has_featured_snippet": serp_data.get("featured_snippet") is not None,
            "has_paa": len(serp_data.get("people_also_ask", [])) > 0,
            "has_related_searches": len(serp_data.get("related_searches", [])) > 0,
            "organic_count": len(organic),
        }

        if organic:
            lines = []
            for idx, r in enumerate(organic[:10]):
                line = str(idx + 1) + ". " + r.get("title", "") + " -- " + r.get("url", "")
                lines.append(line)
            titles_block = "\n".join(lines)

            prompt = (
                "Analyze these Google SERP results for the keyword: "
                + keyword + "\n\n"
                "Top results:\n" + titles_block + "\n\n"
                "Provide a JSON object with:\n"
                "- \"content_types\": array of content types ranking "
                "(e.g. \"blog post\", \"product page\", \"listicle\")\n"
                "- \"avg_word_count_estimate\": estimated average word count "
                "of top results (integer)\n"
                "- \"analysis_summary\": 2-3 sentence analysis of what it takes to rank\n"
                "- \"dominant_format\": most common content format\n"
                "- \"authority_level\": \"high\", \"medium\", or \"low\" "
                "based on domains ranking\n\n"
                "Return valid JSON object only."
            )

            try:
                analysis = await self._llm.generate_json(prompt)
                result["content_types"] = analysis.get("content_types", [])
                result["avg_word_count_estimate"] = int(
                    analysis.get("avg_word_count_estimate", 0)
                )
                result["analysis_summary"] = str(
                    analysis.get("analysis_summary", "")
                )
                result["dominant_format"] = str(
                    analysis.get("dominant_format", "")
                )
                result["authority_level"] = str(
                    analysis.get("authority_level", "medium")
                )
            except Exception as exc:
                logger.warning("AI SERP analysis failed: %s", exc)
                result["analysis_summary"] = "AI analysis unavailable."

        return result

    # ------------------------------------------------------------------
    # get_keyword_difficulty
    # ------------------------------------------------------------------

    async def get_keyword_difficulty(self, keyword: str) -> dict:
        """Estimate keyword difficulty by analyzing SERP competition.

        Returns difficulty_score, difficulty_label, top_competitors,
        ranking_factors.
        """
        logger.info("Estimating difficulty for %r", keyword)

        result: dict[str, Any] = {
            "keyword": keyword,
            "difficulty_score": 50,
            "difficulty_label": "medium",
            "top_competitors": [],
            "ranking_factors": [],
            "estimated_time_to_rank": "3-6 months",
            "content_requirements": "",
        }

        try:
            serp_data = await self._serp.search_google(keyword, num_results=10)
        except Exception as exc:
            logger.error("SERP fetch failed for difficulty: %s", exc)
            return result

        organic = serp_data.get("organic_results", [])
        if not organic:
            result["difficulty_score"] = 20
            result["difficulty_label"] = "easy"
            return result

        competitors = []
        for r in organic[:10]:
            url = r.get("url", "")
            title = r.get("title", "")
            domain = url
            if "//" in url:
                domain = url.split("//")[-1].split("/")[0]
            else:
                domain = url.split("/")[0]
            competitors.append({
                "position": r.get("position", 0),
                "domain": domain,
                "title": title,
                "url": url,
            })
        result["top_competitors"] = competitors

        comp_lines = []
        for c in competitors:
            line = "#" + str(c["position"]) + " " + c["domain"] + " -- " + c["title"]
            comp_lines.append(line)
        comp_block = "\n".join(comp_lines)

        paa_count = len(serp_data.get("people_also_ask", []))
        has_snippet = serp_data.get("featured_snippet") is not None

        prompt = (
            "Analyze keyword difficulty for: " + keyword + "\n\n"
            "Current SERP competitors:\n" + comp_block + "\n\n"
            "SERP features: PAA questions=" + str(paa_count)
            + ", Featured snippet=" + str(has_snippet) + "\n\n"
            "Estimate the difficulty considering:\n"
            "- Domain authority of ranking sites\n"
            "- Content quality signals from titles\n"
            "- SERP feature competition\n"
            "- Number of strong brands ranking\n\n"
            "Return a JSON object with:\n"
            "- \"difficulty_score\": 0-100 integer\n"
            "- \"difficulty_label\": \"easy\" (0-30), \"medium\" (31-60), "
            "\"hard\" (61-80), \"very hard\" (81-100)\n"
            "- \"ranking_factors\": array of key factors affecting difficulty\n"
            "- \"estimated_time_to_rank\": estimated months to reach page 1\n"
            "- \"content_requirements\": what content approach is needed\n\n"
            "Return valid JSON object only."
        )

        try:
            analysis = await self._llm.generate_json(prompt)
            result["difficulty_score"] = int(analysis.get("difficulty_score", 50))
            result["difficulty_label"] = str(analysis.get("difficulty_label", "medium"))
            result["ranking_factors"] = analysis.get("ranking_factors", [])
            result["estimated_time_to_rank"] = str(
                analysis.get("estimated_time_to_rank", "3-6 months")
            )
            result["content_requirements"] = str(
                analysis.get("content_requirements", "")
            )
        except Exception as exc:
            logger.warning("AI difficulty analysis failed: %s", exc)
            result["difficulty_score"] = min(50 + len(competitors) * 3, 95)
            diff_val = result["difficulty_score"]
            if diff_val <= 30:
                result["difficulty_label"] = "easy"
            elif diff_val <= 60:
                result["difficulty_label"] = "medium"
            elif diff_val <= 80:
                result["difficulty_label"] = "hard"
            else:
                result["difficulty_label"] = "very hard"

        return result

    # ------------------------------------------------------------------
    # suggest_long_tail
    # ------------------------------------------------------------------

    async def suggest_long_tail(
        self, seed: str, count: int = 20,
    ) -> list[dict]:
        """AI generates long-tail variations of a seed keyword.

        Returns list of dicts with keyword, estimated_volume, intent.
        """
        logger.info("Generating %d long-tail suggestions for %r", count, seed)

        prompt = (
            "You are an SEO keyword specialist. Generate exactly "
            + str(count) + " long-tail keyword variations for the seed keyword: "
            + seed + "\n\n"
            "Include variations like:\n"
            "- Question-based (how, what, why, when, where)\n"
            "- Comparison keywords (vs, alternative, compared to)\n"
            "- Modifier keywords (best, top, free, cheap, near me)\n"
            "- Specific/niche variations\n"
            "- Problem/solution keywords\n\n"
            "Return ONLY a JSON array of objects:\n"
            "- \"keyword\": the long-tail keyword phrase\n"
            "- \"estimated_volume\": monthly search volume estimate (integer)\n"
            "- \"intent\": one of informational, transactional, commercial, navigational\n\n"
            "Return valid JSON array only."
        )

        try:
            data = await self._llm.generate_json(prompt)
            items = data if isinstance(data, list) else []
            results: list[dict] = []
            for item in items:
                kw_text = str(item.get("keyword", "")).strip()
                if kw_text:
                    results.append({
                        "keyword": kw_text.lower(),
                        "estimated_volume": int(item.get("estimated_volume", 0)),
                        "intent": str(item.get("intent", "informational")),
                        "source": "ai_long_tail",
                    })
            logger.info("Generated %d long-tail keywords", len(results))
            return results[:count]
        except Exception as exc:
            logger.error("Long-tail generation failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # full_research_pipeline
    # ------------------------------------------------------------------

    async def full_research_pipeline(
        self,
        seed_keywords: list[str],
        niche: str,
    ) -> dict:
        """Run the complete keyword research pipeline:
        expand -> classify -> cluster -> score.

        Returns comprehensive results dict with all phases.
        """
        logger.info(
            "Starting full research pipeline: seeds=%s, niche=%r",
            seed_keywords, niche,
        )

        pipeline_result: dict[str, Any] = {
            "niche": niche,
            "seed_keywords": seed_keywords,
            "expanded_keywords": [],
            "classified_keywords": [],
            "clusters": [],
            "scored_keywords": [],
            "summary": {},
        }

        # Step 1: Expand
        try:
            expanded = await self.expand_keywords(seed_keywords, niche)
            pipeline_result["expanded_keywords"] = expanded
            logger.info("Pipeline step 1/4 (expand): %d keywords", len(expanded))
        except Exception as exc:
            logger.error("Pipeline expand failed: %s", exc)
            expanded = []
            for kw in seed_keywords:
                expanded.append({
                    "keyword": kw,
                    "estimated_volume": 0,
                    "intent": "informational",
                    "difficulty_estimate": 50,
                    "source": "seed",
                })
            pipeline_result["expanded_keywords"] = expanded

        # Step 2: Classify intent
        try:
            kw_texts = [kw.get("keyword", "") for kw in expanded]
            classified = await self.classify_intent(kw_texts)
            pipeline_result["classified_keywords"] = classified

            classify_map: dict[str, dict] = {}
            for cl in classified:
                classify_map[cl.get("keyword", "").strip().lower()] = cl

            for kw in expanded:
                kw_lower = kw.get("keyword", "").strip().lower()
                if kw_lower in classify_map:
                    cl_info = classify_map[kw_lower]
                    kw["intent"] = cl_info.get("intent", kw.get("intent", "informational"))
                    kw["confidence"] = cl_info.get("confidence", 0.5)
                    kw["suggested_content_type"] = cl_info.get(
                        "suggested_content_type", "blog post"
                    )

            logger.info("Pipeline step 2/4 (classify): %d classified", len(classified))
        except Exception as exc:
            logger.error("Pipeline classify failed: %s", exc)

        # Step 3: Cluster
        try:
            clusters = await self.cluster_keywords(expanded)
            pipeline_result["clusters"] = clusters
            logger.info("Pipeline step 3/4 (cluster): %d clusters", len(clusters))
        except Exception as exc:
            logger.error("Pipeline cluster failed: %s", exc)

        # Step 4: Score
        try:
            scored = await self.score_keywords(expanded)
            pipeline_result["scored_keywords"] = scored
            pipeline_result["expanded_keywords"] = scored
            logger.info("Pipeline step 4/4 (score): %d scored", len(scored))
        except Exception as exc:
            logger.error("Pipeline score failed: %s", exc)

        # Build summary
        all_kws = pipeline_result.get("scored_keywords", [])
        if not all_kws:
            all_kws = pipeline_result.get("expanded_keywords", [])

        total_vol = sum(int(kw.get("estimated_volume", 0)) for kw in all_kws)
        avg_diff = 0
        if all_kws:
            avg_diff = sum(
                int(kw.get("difficulty_estimate", 50)) for kw in all_kws
            ) // len(all_kws)

        avg_score = 0
        scored_kws = [
            kw for kw in all_kws if kw.get("opportunity_score") is not None
        ]
        if scored_kws:
            avg_score = sum(
                int(kw.get("opportunity_score", 0)) for kw in scored_kws
            ) // len(scored_kws)

        intent_distribution: dict[str, int] = {}
        for kw in all_kws:
            iv = kw.get("intent", "unknown")
            intent_distribution[iv] = intent_distribution.get(iv, 0) + 1

        source_distribution: dict[str, int] = {}
        for kw in all_kws:
            src = kw.get("source", "unknown")
            source_distribution[src] = source_distribution.get(src, 0) + 1

        top_opportunities = sorted(
            [kw for kw in all_kws if kw.get("opportunity_score") is not None],
            key=lambda x: int(x.get("opportunity_score", 0)),
            reverse=True,
        )[:10]

        pipeline_result["summary"] = {
            "total_keywords": len(all_kws),
            "total_estimated_volume": total_vol,
            "average_difficulty": avg_diff,
            "average_opportunity_score": avg_score,
            "total_clusters": len(pipeline_result.get("clusters", [])),
            "intent_distribution": intent_distribution,
            "source_distribution": source_distribution,
            "top_opportunities": top_opportunities,
        }

        logger.info(
            "Pipeline complete: %d keywords, %d clusters, avg score=%d",
            len(all_kws),
            len(pipeline_result.get("clusters", [])),
            avg_score,
        )
        return pipeline_result
