"""Google Trends integration using the pytrends library."""

import asyncio
import logging
import time
from typing import Any, Optional

from pytrends.request import TrendReq

logger = logging.getLogger(__name__)


class GoogleTrendsClient:
    """Client for Google Trends data via pytrends.

    Usage::

        trends = GoogleTrendsClient()
        interest = await trends.get_interest_over_time(["seo tools", "seo software"])
        related = await trends.get_related_queries("seo tools")
        trending = await trends.get_trending_topics(geo="US")
    """

    def __init__(
        self,
        hl: str = "en-US",
        tz: int = 360,
        geo: str = "",
        timeout: tuple[int, int] = (10, 30),
        retries: int = 3,
        backoff_factor: float = 1.5,
        requests_per_minute: int = 10,
    ):
        self._hl = hl
        self._tz = tz
        self._geo = geo
        self._timeout = timeout
        self._retries = retries
        self._backoff_factor = backoff_factor
        self._rpm = requests_per_minute
        self._request_timestamps: list[float] = []

    def _get_pytrends(self) -> TrendReq:
        """Create a fresh TrendReq session."""
        return TrendReq(
            hl=self._hl,
            tz=self._tz,
            timeout=self._timeout,
            retries=self._retries,
            backoff_factor=self._backoff_factor,
        )

    def _rate_limit_sync(self) -> None:
        """Simple synchronous rate limiter."""
        now = time.monotonic()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < 60.0
        ]
        if len(self._request_timestamps) >= self._rpm:
            wait = 60.0 - (now - self._request_timestamps[0])
            if wait > 0:
                logger.debug("Google Trends rate limit: sleeping %.1fs", wait)
                time.sleep(wait)
        self._request_timestamps.append(time.monotonic())

    async def get_interest_over_time(
        self,
        keywords: list[str],
        timeframe: str = "today 12-m",
        geo: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get search interest over time for given keywords.

        Args:
            keywords: Up to 5 keywords to compare.
            timeframe: Timeframe string (e.g. 'today 12-m', 'today 3-m', '2024-01-01 2024-12-31').
            geo: Country code (e.g. 'US', 'GB'). Empty string for worldwide.

        Returns:
            List of dicts with date and interest values per keyword.
        """
        geo = geo if geo is not None else self._geo

        def _fetch():
            self._rate_limit_sync()
            pt = self._get_pytrends()
            pt.build_payload(keywords[:5], timeframe=timeframe, geo=geo)
            df = pt.interest_over_time()
            if df.empty:
                return []
            df = df.drop(columns=["isPartial"], errors="ignore")
            df = df.reset_index()
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            return df.to_dict(orient="records")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch)
        logger.info("Trends interest_over_time: %d data points for %s", len(result), keywords)
        return result

    async def get_related_queries(
        self,
        keyword: str,
        timeframe: str = "today 12-m",
        geo: Optional[str] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get related queries (top and rising) for a keyword.

        Returns:
            Dict with 'top' and 'rising' lists of query dicts.
        """
        geo = geo if geo is not None else self._geo

        def _fetch():
            self._rate_limit_sync()
            pt = self._get_pytrends()
            pt.build_payload([keyword], timeframe=timeframe, geo=geo)
            related = pt.related_queries()
            result = {"top": [], "rising": []}
            kw_data = related.get(keyword, {})
            if kw_data:
                top_df = kw_data.get("top")
                if top_df is not None and not top_df.empty:
                    result["top"] = top_df.to_dict(orient="records")
                rising_df = kw_data.get("rising")
                if rising_df is not None and not rising_df.empty:
                    result["rising"] = rising_df.to_dict(orient="records")
            return result

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch)
        logger.info(
            "Trends related_queries for %r: %d top, %d rising",
            keyword, len(result["top"]), len(result["rising"]),
        )
        return result

    async def get_trending_topics(
        self,
        geo: str = "US",
    ) -> list[dict[str, Any]]:
        """Get currently trending search topics.

        Args:
            geo: Country code for trending topics.

        Returns:
            List of trending topic dicts with title and traffic.
        """
        def _fetch():
            self._rate_limit_sync()
            pt = self._get_pytrends()
            df = pt.trending_searches(pn=geo.lower() if len(geo) == 2 else geo)
            if df.empty:
                return []
            df.columns = ["topic"]
            df["rank"] = range(1, len(df) + 1)
            return df.to_dict(orient="records")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch)
        logger.info("Trends trending_topics for %s: %d topics", geo, len(result))
        return result

    async def get_keyword_suggestions(
        self,
        keyword: str,
        timeframe: str = "today 12-m",
        geo: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get keyword suggestions using related topics.

        Returns:
            List of suggested topic dicts.
        """
        geo = geo if geo is not None else self._geo

        def _fetch():
            self._rate_limit_sync()
            pt = self._get_pytrends()
            pt.build_payload([keyword], timeframe=timeframe, geo=geo)
            related = pt.related_topics()
            result = []
            kw_data = related.get(keyword, {})
            if kw_data:
                top_df = kw_data.get("top")
                if top_df is not None and not top_df.empty:
                    for _, row in top_df.iterrows():
                        result.append({
                            "topic_title": row.get("topic_title", ""),
                            "topic_type": row.get("topic_type", ""),
                            "value": row.get("value", 0),
                        })
            return result

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch)
        logger.info("Trends keyword_suggestions for %r: %d suggestions", keyword, len(result))
        return result
