"""Configurable async-compatible rate limiter with sliding window."""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter supporting both sync and async usage.

    Usage::

        limiter = RateLimiter(requests_per_minute=30)

        # Async
        async with limiter:
            await make_request()

        # Sync
        with limiter:
            make_request()
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: Optional[int] = None,
        name: str = "default",
    ):
        self._rpm = requests_per_minute
        self._rph = requests_per_hour
        self._name = name
        self._minute_window: list[float] = []
        self._hour_window: list[float] = []
        self._async_lock = asyncio.Lock()

    def _clean_windows(self, now: float) -> None:
        """Remove expired timestamps from sliding windows."""
        self._minute_window = [t for t in self._minute_window if now - t < 60.0]
        if self._rph:
            self._hour_window = [t for t in self._hour_window if now - t < 3600.0]

    def _wait_time(self) -> float:
        """Calculate how long to wait before the next request is allowed."""
        now = time.monotonic()
        self._clean_windows(now)
        wait = 0.0
        if len(self._minute_window) >= self._rpm:
            wait = max(wait, 60.0 - (now - self._minute_window[0]))
        if self._rph and len(self._hour_window) >= self._rph:
            wait = max(wait, 3600.0 - (now - self._hour_window[0]))
        return wait

    def _record(self) -> None:
        """Record a request timestamp."""
        now = time.monotonic()
        self._minute_window.append(now)
        if self._rph:
            self._hour_window.append(now)

    def acquire_sync(self) -> None:
        """Block until a request slot is available (synchronous)."""
        while True:
            wait = self._wait_time()
            if wait <= 0:
                break
            logger.debug("RateLimiter(%s) sleeping %.2fs", self._name, wait)
            time.sleep(wait)
        self._record()

    async def acquire(self) -> None:
        """Wait until a request slot is available (async)."""
        async with self._async_lock:
            while True:
                wait = self._wait_time()
                if wait <= 0:
                    break
                logger.debug("RateLimiter(%s) async sleeping %.2fs", self._name, wait)
                await asyncio.sleep(wait)
            self._record()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        pass

    def __enter__(self):
        self.acquire_sync()
        return self

    def __exit__(self, *args):
        pass

    @property
    def requests_in_last_minute(self) -> int:
        """Number of requests made in the last 60 seconds."""
        self._clean_windows(time.monotonic())
        return len(self._minute_window)

    @property
    def requests_in_last_hour(self) -> int:
        """Number of requests made in the last 3600 seconds."""
        self._clean_windows(time.monotonic())
        return len(self._hour_window)
