"""SEO Strategy Analyzer — AI-powered analysis, verification, and recommendation engine.

Analyzes scraped SEO articles, extracts actionable strategies,
verifies them against multiple sources, and generates upgrade recommendations.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# Strategy categories for classification
STRATEGY_CATEGORIES = [
    "technical_seo",
    "onpage_seo",
    "offpage_seo",
    "local_seo",
    "content_strategy",
    "link_building",
    "algorithm_update",
    "ai_and_search",
    "core_web_vitals",
    "schema_markup",
]


EXTRACT_STRATEGIES_PROMPT = """You are an expert SEO analyst. Analyze the following SEO article and extract any actionable strategies or techniques.

Article Title: {title}
Article Source: {source}
Article Content:
{content}

Extract ALL actionable SEO strategies from this article. For each strategy provide:
1. title: Short descriptive title
2. description: What the strategy is and why it works
3. category: One of: technical_seo, onpage_seo, offpage_seo, local_seo, content_strategy, link_building, algorithm_update, ai_and_search, core_web_vitals, schema_markup
4. strategy_type: One of: optimization, new_technique, algorithm_update, tool_recommendation, best_practice
5. implementation_steps: List of specific steps to implement
6. estimated_impact: high, medium, or low
7. estimated_effort: easy, medium, or hard
8. confidence_score: 0.0 to 1.0 how confident you are this is valid and effective

Return a JSON array of strategy objects. If no actionable strategies found, return an empty array [].
Only include strategies that are specific and implementable, not generic advice.
"""


VERIFY_STRATEGY_PROMPT = """You are an expert SEO analyst tasked with verifying an SEO strategy.

Strategy: {title}
Description: {description}
Category: {category}
Source: {source}

Verify this strategy by considering:
1. Is it consistent with current Google guidelines and best practices?
2. Is there evidence this technique actually works?
3. Could it be risky (penalties, algorithm changes)?
4. Is it a white-hat technique?
5. What are the potential downsides?

Respond in JSON format:
{
    "is_valid": true/false,
    "confidence": 0.0-1.0,
    "risk_level": "none", "low", "medium", or "high",
    "evidence": "explanation of why valid or not",
    "google_compliant": true/false,
    "potential_downsides": ["list of risks"],
    "recommended_action": "apply", "test_first", "monitor", or "avoid",
    "notes": "any additional context"
}
"""


UPGRADE_RECOMMENDATION_PROMPT = """You are an SEO automation system architect. Given the following verified SEO strategy, determine how to integrate it into our automation system.

Our system has these modules:
- Topical Research (niche analysis, topic mapping)
- Keyword Research (expansion, clustering, intent classification)
- Blog Content (AI writing, briefs, quality checking)
- Content Optimizer (SEO scoring, readability)
- On-Page SEO (meta tags, schema, internal linking)
- Technical Audit (crawling, Core Web Vitals, broken links)
- Link Building (prospecting, outreach)
- Rank Tracking (SERP monitoring)
- Local SEO (GBP analysis, citations, map pack)
- Reporting Dashboard

Strategy to integrate:
Title: {title}
Description: {description}
Category: {category}
Implementation Steps: {steps}

Provide a JSON response with:
{
    "affected_modules": ["list of modules that need updating"],
    "changes_required": [
        {
            "module": "module_name",
            "change_type": "new_feature", "enhancement", "config_update", or "new_check",
            "description": "what to change",
            "implementation_detail": "specific code/config changes needed",
            "priority": "high", "medium", or "low"
        }
    ],
    "estimated_dev_time": "time estimate",
    "auto_applicable": true/false (can be applied automatically without code changes),
    "config_changes": {"key": "value"} (if auto_applicable)
}
"""


class SEOStrategyAnalyzer:
    """Analyzes scraped SEO articles and extracts/verifies strategies."""

    def __init__(self, llm_client=None):
        """Initialize with LLM client for AI analysis.

        Args:
            llm_client: Instance of LLMClient from src.integrations.llm_client
        """
        self.llm_client = llm_client
        self._strategies_cache: list[dict] = []

    async def extract_strategies(self, article: dict) -> list[dict]:
        """Extract actionable SEO strategies from an article using AI.

        Args:
            article: Dict with title, url, summary, full_content, source_name

        Returns:
            List of strategy dicts
        """
        content = article.get("full_content") or article.get("summary", "")
        if not content or len(content) < 100:
            logger.info("Skipping article with insufficient content: %s", article.get("title", ""))
            return []

        # Truncate content to save tokens
        content = content[:5000]

        prompt = EXTRACT_STRATEGIES_PROMPT.format(
            title=article.get("title", "Unknown"),
            source=article.get("source_name", "Unknown"),
            content=content,
        )

        try:
            if self.llm_client:
                response = await self.llm_client.generate_json(prompt=prompt)
            else:
                logger.warning("No LLM client configured, returning empty strategies")
                return []

            if isinstance(response, list):
                strategies = response
            elif isinstance(response, dict) and "strategies" in response:
                strategies = response["strategies"]
            else:
                strategies = []

            # Enrich each strategy with article metadata
            for strategy in strategies:
                strategy["source_article"] = {
                    "title": article.get("title"),
                    "url": article.get("url"),
                    "source_name": article.get("source_name"),
                    "published_at": str(article.get("published_at", "")),
                }
                strategy["extracted_at"] = datetime.utcnow().isoformat()
                strategy.setdefault("verification_status", "pending")

            logger.info(
                "Extracted %d strategies from: %s",
                len(strategies), article.get("title", "")
            )
            return strategies

        except Exception as e:
            logger.error("Strategy extraction failed for %s: %s", article.get("title", ""), e)
            return []

    async def verify_strategy(self, strategy: dict) -> dict:
        """Verify a strategy using AI analysis.

        Args:
            strategy: Strategy dict from extract_strategies()

        Returns:
            Verification result dict
        """
        source_info = strategy.get("source_article", {})
        prompt = VERIFY_STRATEGY_PROMPT.format(
            title=strategy.get("title", ""),
            description=strategy.get("description", ""),
            category=strategy.get("category", ""),
            source=source_info.get("source_name", "Unknown"),
        )

        try:
            if self.llm_client:
                result = await self.llm_client.generate_json(prompt=prompt)
            else:
                return {
                    "is_valid": None,
                    "confidence": 0.0,
                    "evidence": "No LLM client configured for verification",
                    "recommended_action": "monitor",
                }

            # Update strategy with verification results
            strategy["verification_status"] = (
                "verified" if result.get("is_valid") else "rejected"
            )
            strategy["verification_result"] = result
            strategy["confidence_score"] = result.get("confidence", 0.0)

            logger.info(
                "Strategy '%s' verification: %s (confidence: %.1f)",
                strategy.get("title", ""),
                strategy["verification_status"],
                strategy["confidence_score"],
            )
            return result

        except Exception as e:
            logger.error("Verification failed for %s: %s", strategy.get("title", ""), e)
            return {
                "is_valid": None,
                "confidence": 0.0,
                "evidence": f"Verification error: {e}",
                "recommended_action": "monitor",
            }

    async def generate_upgrade_plan(self, strategy: dict) -> dict:
        """Generate an upgrade plan for applying a verified strategy.

        Args:
            strategy: Verified strategy dict

        Returns:
            Upgrade plan dict with affected modules and changes
        """
        steps = strategy.get("implementation_steps", [])
        if isinstance(steps, list):
            steps_text = "\n".join(f"- {s}" for s in steps)
        else:
            steps_text = str(steps)

        prompt = UPGRADE_RECOMMENDATION_PROMPT.format(
            title=strategy.get("title", ""),
            description=strategy.get("description", ""),
            category=strategy.get("category", ""),
            steps=steps_text,
        )

        try:
            if self.llm_client:
                plan = await self.llm_client.generate_json(prompt=prompt)
            else:
                return {
                    "affected_modules": [],
                    "changes_required": [],
                    "auto_applicable": False,
                    "estimated_dev_time": "unknown",
                }

            strategy["upgrade_plan"] = plan
            return plan

        except Exception as e:
            logger.error("Upgrade plan generation failed: %s", e)
            return {"affected_modules": [], "changes_required": [], "error": str(e)}

    async def full_pipeline(self, articles: list[dict]) -> dict:
        """Run the complete analysis pipeline on scraped articles.

        Pipeline:
        1. Extract strategies from all articles
        2. Verify each strategy
        3. Generate upgrade plans for verified strategies
        4. Return prioritized results

        Args:
            articles: List of article dicts from scraper

        Returns:
            dict with strategies, verified, upgrade_plans, summary
        """
        all_strategies = []
        verified_strategies = []
        upgrade_plans = []

        # Step 1: Extract strategies from actionable articles
        actionable = [a for a in articles if a.get("is_actionable", False)]
        logger.info("Analyzing %d actionable articles out of %d total", len(actionable), len(articles))

        for article in actionable:
            strategies = await self.extract_strategies(article)
            all_strategies.extend(strategies)
            await asyncio.sleep(0.5)  # Rate limit

        logger.info("Extracted %d total strategies", len(all_strategies))

        # Step 2: Verify strategies with confidence > 0.5
        promising = [s for s in all_strategies if s.get("confidence_score", 0.5) >= 0.5]

        for strategy in promising:
            verification = await self.verify_strategy(strategy)
            if verification.get("is_valid") and verification.get("confidence", 0) >= 0.6:
                verified_strategies.append(strategy)
            await asyncio.sleep(0.5)  # Rate limit

        logger.info("%d strategies verified out of %d", len(verified_strategies), len(promising))

        # Step 3: Generate upgrade plans for verified strategies
        for strategy in verified_strategies:
            plan = await self.generate_upgrade_plan(strategy)
            upgrade_plans.append({
                "strategy": strategy,
                "plan": plan,
            })
            await asyncio.sleep(0.5)

        # Step 4: Sort by impact and confidence
        impact_order = {"high": 3, "medium": 2, "low": 1}
        verified_strategies.sort(
            key=lambda s: (
                impact_order.get(s.get("estimated_impact", "medium"), 2),
                s.get("confidence_score", 0),
            ),
            reverse=True,
        )

        return {
            "total_articles_analyzed": len(actionable),
            "total_strategies_extracted": len(all_strategies),
            "verified_strategies": len(verified_strategies),
            "strategies": all_strategies,
            "verified": verified_strategies,
            "upgrade_plans": upgrade_plans,
            "summary": self._generate_summary(all_strategies, verified_strategies),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    def _generate_summary(self, all_strategies: list, verified: list) -> dict:
        """Generate a summary of the analysis results."""
        categories = {}
        for s in all_strategies:
            cat = s.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        high_impact = [s for s in verified if s.get("estimated_impact") == "high"]
        quick_wins = [
            s for s in verified
            if s.get("estimated_effort") == "easy" and s.get("estimated_impact") in ("high", "medium")
        ]

        return {
            "total_found": len(all_strategies),
            "verified_count": len(verified),
            "high_impact_count": len(high_impact),
            "quick_wins_count": len(quick_wins),
            "categories": categories,
            "top_recommendation": verified[0].get("title") if verified else None,
        }

    def filter_strategies(
        self,
        strategies: list[dict],
        category: Optional[str] = None,
        min_confidence: float = 0.0,
        impact: Optional[str] = None,
        effort: Optional[str] = None,
        verified_only: bool = False,
    ) -> list[dict]:
        """Filter strategies by various criteria."""
        filtered = strategies

        if category:
            filtered = [s for s in filtered if s.get("category") == category]
        if min_confidence > 0:
            filtered = [s for s in filtered if s.get("confidence_score", 0) >= min_confidence]
        if impact:
            filtered = [s for s in filtered if s.get("estimated_impact") == impact]
        if effort:
            filtered = [s for s in filtered if s.get("estimated_effort") == effort]
        if verified_only:
            filtered = [s for s in filtered if s.get("verification_status") == "verified"]

        return filtered
