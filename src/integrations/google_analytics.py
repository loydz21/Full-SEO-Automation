"""Google Analytics 4 integration for traffic data, top pages, and conversions."""

import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)

logger = logging.getLogger(__name__)

GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


class GoogleAnalytics:
    """Client for the Google Analytics 4 Data API.

    Usage::

        ga = GoogleAnalytics(
            credentials_path="config/ga4_credentials.json",
            property_id="properties/123456789",
        )
        ga.authenticate()
        traffic = ga.get_traffic_data(days=30)
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        property_id: Optional[str] = None,
    ):
        self._credentials_path = credentials_path or os.getenv(
            "GA4_CREDENTIALS_PATH", "config/ga4_credentials.json"
        )
        self._property_id = property_id or os.getenv("GA4_PROPERTY_ID", "")
        self._client: Optional[BetaAnalyticsDataClient] = None

    def authenticate(self) -> None:
        """Authenticate using a service account JSON key file."""
        if not os.path.isfile(self._credentials_path):
            raise FileNotFoundError(
                f"GA4 credentials not found: {self._credentials_path}"
            )
        credentials = service_account.Credentials.from_service_account_file(
            self._credentials_path, scopes=GA4_SCOPES
        )
        self._client = BetaAnalyticsDataClient(credentials=credentials)
        logger.info("Authenticated with Google Analytics 4.")

    def _ensure_auth(self) -> None:
        if self._client is None:
            self.authenticate()

    def _run_report(
        self,
        dimensions: list[str],
        metrics: list[str],
        days: int = 30,
        limit: int = 100,
        order_by_metric: Optional[str] = None,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """Run a GA4 report and return parsed rows."""
        self._ensure_auth()
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days)

        request = RunReportRequest(
            property=self._property_id,
            date_ranges=[DateRange(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )],
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            limit=limit,
        )

        if order_by_metric:
            request.order_bys = [
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name=order_by_metric),
                    desc=descending,
                )
            ]

        response = self._client.run_report(request)
        rows: list[dict[str, Any]] = []
        for row in response.rows:
            entry: dict[str, Any] = {}
            for i, dim in enumerate(dimensions):
                entry[dim] = row.dimension_values[i].value
            for i, met in enumerate(metrics):
                val = row.metric_values[i].value
                try:
                    entry[met] = int(val)
                except ValueError:
                    try:
                        entry[met] = float(val)
                    except ValueError:
                        entry[met] = val
            rows.append(entry)

        logger.info("GA4 report: %d rows", len(rows))
        return rows

    def get_traffic_data(
        self, days: int = 30, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get daily traffic overview (sessions, users, pageviews, bounce rate).

        Returns:
            List of daily traffic dicts.
        """
        return self._run_report(
            dimensions=["date"],
            metrics=[
                "sessions",
                "totalUsers",
                "screenPageViews",
                "bounceRate",
                "averageSessionDuration",
            ],
            days=days,
            limit=limit,
            order_by_metric="date",
            descending=False,
        )

    def get_top_pages(
        self, days: int = 30, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get top pages by pageviews.

        Returns:
            List of page dicts with path, title, pageviews, and avg time.
        """
        return self._run_report(
            dimensions=["pagePath", "pageTitle"],
            metrics=[
                "screenPageViews",
                "totalUsers",
                "averageSessionDuration",
                "bounceRate",
            ],
            days=days,
            limit=limit,
            order_by_metric="screenPageViews",
            descending=True,
        )

    def get_conversions(
        self, days: int = 30, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get conversion events summary.

        Returns:
            List of event dicts with event name, count, and users.
        """
        return self._run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            days=days,
            limit=limit,
            order_by_metric="eventCount",
            descending=True,
        )
