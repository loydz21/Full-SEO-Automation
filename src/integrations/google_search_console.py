"""Google Search Console integration for performance data and index coverage."""

import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GoogleSearchConsole:
    """Client for the Google Search Console API.

    Usage::

        gsc = GoogleSearchConsole(
            credentials_path="config/gsc_credentials.json",
            property_url="https://example.com",
        )
        gsc.authenticate()
        data = gsc.get_performance_data(days=30)
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        property_url: Optional[str] = None,
    ):
        self._credentials_path = credentials_path or os.getenv(
            "GSC_CREDENTIALS_PATH", "config/gsc_credentials.json"
        )
        self._property_url = property_url or os.getenv(
            "GSC_PROPERTY_URL", ""
        )
        self._service = None

    def authenticate(self) -> None:
        """Authenticate using a service account JSON key file."""
        if not os.path.isfile(self._credentials_path):
            raise FileNotFoundError(
                f"GSC credentials not found: {self._credentials_path}"
            )
        credentials = service_account.Credentials.from_service_account_file(
            self._credentials_path, scopes=GSC_SCOPES
        )
        self._service = build("searchconsole", "v1", credentials=credentials)
        logger.info("Authenticated with Google Search Console.")

    def _ensure_auth(self) -> None:
        if self._service is None:
            self.authenticate()

    def get_performance_data(
        self,
        days: int = 30,
        dimensions: Optional[list[str]] = None,
        row_limit: int = 1000,
        start_row: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch search performance data (clicks, impressions, CTR, position).

        Args:
            days: Number of past days to query.
            dimensions: Grouping dimensions (query, page, country, device, date).
            row_limit: Max rows per request (API max 25000).
            start_row: Offset for pagination.

        Returns:
            List of row dicts with keys and metrics.
        """
        self._ensure_auth()
        dimensions = dimensions or ["query", "page"]
        end_date = date.today() - timedelta(days=3)  # GSC data lags ~3 days
        start_date = end_date - timedelta(days=days)

        all_rows: list[dict[str, Any]] = []
        current_start = start_row

        while True:
            body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": dimensions,
                "rowLimit": min(row_limit, 25000),
                "startRow": current_start,
            }
            try:
                response = (
                    self._service.searchanalytics()
                    .query(siteUrl=self._property_url, body=body)
                    .execute()
                )
            except HttpError as exc:
                logger.error("GSC API error: %s", exc)
                raise

            rows = response.get("rows", [])
            if not rows:
                break

            for row in rows:
                entry: dict[str, Any] = {}
                for i, dim in enumerate(dimensions):
                    entry[dim] = row["keys"][i]
                entry["clicks"] = row.get("clicks", 0)
                entry["impressions"] = row.get("impressions", 0)
                entry["ctr"] = round(row.get("ctr", 0.0), 4)
                entry["position"] = round(row.get("position", 0.0), 1)
                all_rows.append(entry)

            current_start += len(rows)
            if len(rows) < row_limit:
                break

        logger.info("GSC performance: fetched %d rows", len(all_rows))
        return all_rows

    def get_index_coverage(
        self,
    ) -> dict[str, Any]:
        """Fetch index coverage summary for the property.

        Returns:
            Dict with coverage status counts.
        """
        self._ensure_auth()
        try:
            response = (
                self._service.urlInspection()
                .index()
                .inspect(
                    body={
                        "inspectionUrl": self._property_url,
                        "siteUrl": self._property_url,
                    }
                )
                .execute()
            )
            result = response.get("inspectionResult", {})
            index_status = result.get("indexStatusResult", {})
            return {
                "verdict": index_status.get("verdict", "UNKNOWN"),
                "coverage_state": index_status.get("coverageState", "UNKNOWN"),
                "indexing_state": index_status.get("indexingState", "UNKNOWN"),
                "last_crawl_time": index_status.get("lastCrawlTime"),
                "page_fetch_state": index_status.get("pageFetchState"),
                "robots_txt_state": index_status.get("robotsTxtState"),
            }
        except HttpError as exc:
            logger.error("GSC index coverage error: %s", exc)
            raise

    def get_sitemaps(self) -> list[dict[str, Any]]:
        """List all sitemaps submitted for the property.

        Returns:
            List of sitemap dicts with path, type, and status.
        """
        self._ensure_auth()
        try:
            response = (
                self._service.sitemaps()
                .list(siteUrl=self._property_url)
                .execute()
            )
            sitemaps = response.get("sitemap", [])
            results = []
            for sm in sitemaps:
                results.append({
                    "path": sm.get("path", ""),
                    "type": sm.get("type", ""),
                    "last_submitted": sm.get("lastSubmitted"),
                    "last_downloaded": sm.get("lastDownloaded"),
                    "is_pending": sm.get("isPending", False),
                    "warnings": sm.get("warnings", 0),
                    "errors": sm.get("errors", 0),
                })
            logger.info("GSC sitemaps: found %d", len(results))
            return results
        except HttpError as exc:
            logger.error("GSC sitemaps error: %s", exc)
            raise
