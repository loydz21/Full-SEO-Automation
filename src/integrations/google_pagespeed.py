"""Google PageSpeed Insights integration for Core Web Vitals and performance."""

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedInsights:
    """Client for the Google PageSpeed Insights API.

    Usage::

        psi = PageSpeedInsights(api_key="your-key")
        result = await psi.analyze_url("https://example.com")
        cwv = await psi.get_core_web_vitals("https://example.com")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        requests_per_minute: int = 10,
        timeout: int = 60,
    ):
        self._api_key = api_key or os.getenv("PAGESPEED_API_KEY", "")
        self._rpm = requests_per_minute
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(2)  # max concurrent requests
        self._request_timestamps: list[float] = []

    async def _rate_limit(self) -> None:
        """Simple rate limiter."""
        import time
        now = time.monotonic()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < 60.0
        ]
        if len(self._request_timestamps) >= self._rpm:
            wait = 60.0 - (now - self._request_timestamps[0])
            if wait > 0:
                logger.debug("PageSpeed rate limit: sleeping %.1fs", wait)
                await asyncio.sleep(wait)
        self._request_timestamps.append(time.monotonic())

    async def analyze_url(
        self,
        url: str,
        strategy: str = "mobile",
        categories: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Run a full PageSpeed analysis on a URL.

        Args:
            url: The URL to analyze.
            strategy: 'mobile' or 'desktop'.
            categories: List of categories (performance, accessibility, seo, best-practices).

        Returns:
            Dict with scores, audits, and Core Web Vitals metrics.
        """
        categories = categories or ["performance", "seo", "accessibility", "best-practices"]
        await self._rate_limit()

        params: dict[str, Any] = {
            "url": url,
            "strategy": strategy,
        }
        if self._api_key:
            params["key"] = self._api_key
        for cat in categories:
            params.setdefault("category", [])
            # httpx handles repeated params via list
        # Build category params manually
        category_params = "&".join(f"category={c}" for c in categories)
        request_url = f"{PAGESPEED_API_URL}?{category_params}"

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                try:
                    response = await client.get(request_url, params=params)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPError as exc:
                    logger.error("PageSpeed API error for %s: %s", url, exc)
                    raise

        # Parse results
        lighthouse = data.get("lighthouseResult", {})
        category_scores = {}
        for cat_key, cat_data in lighthouse.get("categories", {}).items():
            category_scores[cat_key] = round(cat_data.get("score", 0) * 100, 1)

        audits = lighthouse.get("audits", {})
        result = {
            "url": url,
            "strategy": strategy,
            "scores": category_scores,
            "performance_score": category_scores.get("performance", 0),
            "seo_score": category_scores.get("seo", 0),
            "accessibility_score": category_scores.get("accessibility", 0),
            "best_practices_score": category_scores.get("best-practices", 0),
            "metrics": self._extract_metrics(audits),
            "opportunities": self._extract_opportunities(audits),
        }

        logger.info("PageSpeed analysis for %s: perf=%.0f", url, result["performance_score"])
        return result

    async def get_core_web_vitals(
        self,
        url: str,
        strategy: str = "mobile",
    ) -> dict[str, Any]:
        """Extract Core Web Vitals for a URL.

        Returns:
            Dict with LCP, INP, CLS, TTFB, FCP, and performance score.
        """
        analysis = await self.analyze_url(url, strategy=strategy, categories=["performance"])
        metrics = analysis.get("metrics", {})
        return {
            "url": url,
            "strategy": strategy,
            "lcp": metrics.get("largest-contentful-paint"),
            "inp": metrics.get("interaction-to-next-paint"),
            "cls": metrics.get("cumulative-layout-shift"),
            "ttfb": metrics.get("server-response-time"),
            "fcp": metrics.get("first-contentful-paint"),
            "performance_score": analysis.get("performance_score", 0),
        }

    async def batch_analyze(
        self,
        urls: list[str],
        strategy: str = "mobile",
        categories: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Analyze multiple URLs concurrently (respecting rate limits).

        Returns:
            List of analysis result dicts.
        """
        tasks = [
            self.analyze_url(url, strategy=strategy, categories=categories)
            for url in urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.error("Failed to analyze %s: %s", url, result)
                output.append({"url": url, "error": str(result)})
            else:
                output.append(result)
        return output

    @staticmethod
    def _extract_metrics(audits: dict) -> dict[str, Optional[float]]:
        """Extract key performance metrics from Lighthouse audits."""
        metric_keys = [
            "first-contentful-paint",
            "largest-contentful-paint",
            "interaction-to-next-paint",
            "cumulative-layout-shift",
            "speed-index",
            "total-blocking-time",
            "server-response-time",
        ]
        metrics = {}
        for key in metric_keys:
            audit = audits.get(key, {})
            val = audit.get("numericValue")
            metrics[key] = round(val, 2) if val is not None else None
        return metrics

    @staticmethod
    def _extract_opportunities(audits: dict) -> list[dict[str, Any]]:
        """Extract optimization opportunities from audits."""
        opportunities = []
        for key, audit in audits.items():
            if audit.get("details", {}).get("type") == "opportunity":
                savings = audit.get("details", {}).get("overallSavingsMs", 0)
                if savings > 0:
                    opportunities.append({
                        "id": key,
                        "title": audit.get("title", key),
                        "description": audit.get("description", ""),
                        "savings_ms": savings,
                        "score": audit.get("score"),
                    })
        opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)
        return opportunities
