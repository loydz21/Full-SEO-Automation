"""SEO task scheduler built on APScheduler with SQLite persistent job store."""

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class SEOScheduler:
    """Wrapper around APScheduler for recurring SEO pipeline jobs.

    Usage::

        sched = SEOScheduler()
        sched.start()
        sched.add_job(
            job_id="rank_tracking",
            func=my_rank_tracker,
            cron="0 6 * * *",
        )
        sched.list_jobs()
        sched.stop()
    """

    def __init__(
        self,
        job_store_url: str = "sqlite:///data/scheduler_jobs.db",
        timezone: str = "UTC",
        max_workers: int = 3,
    ):
        # Ensure job store directory exists
        if job_store_url.startswith("sqlite:///"):
            db_path = job_store_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        jobstores = {
            "default": SQLAlchemyJobStore(url=job_store_url),
        }
        executors = {
            "default": ThreadPoolExecutor(max_workers=max_workers),
        }
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        }

        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone,
        )
        self._timezone = timezone
        self._running = False
        logger.info(
            "SEOScheduler initialized (store=%s, tz=%s, workers=%d)",
            job_store_url, timezone, max_workers,
        )

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently active."""
        return self._running

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running.")
            return
        self._scheduler.start()
        self._running = True
        logger.info("Scheduler started.")

    def stop(self, wait: bool = True) -> None:
        """Shut down the scheduler."""
        if not self._running:
            return
        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("Scheduler stopped.")

    def add_job(
        self,
        job_id: str,
        func: Callable,
        cron: str,
        args: Optional[tuple] = None,
        kwargs: Optional[dict[str, Any]] = None,
        replace_existing: bool = True,
    ) -> None:
        """Add or replace a cron-triggered job.

        Args:
            job_id: Unique identifier for the job.
            func: Callable to execute.
            cron: Cron expression string (5 fields: min hour day month weekday).
            args: Positional arguments for func.
            kwargs: Keyword arguments for func.
            replace_existing: Overwrite if job_id already exists.
        """
        parts = cron.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: {cron!r}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=self._timezone,
        )
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            args=args or (),
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        logger.info("Job added: %s [%s]", job_id, cron)

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job by ID.

        Returns:
            True if the job was found and removed, False otherwise.
        """
        try:
            self._scheduler.remove_job(job_id)
            logger.info("Job removed: %s", job_id)
            return True
        except Exception:
            logger.warning("Job not found: %s", job_id)
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs with their details.

        Returns:
            List of job info dicts.
        """
        jobs = self._scheduler.get_jobs()
        result = []
        for job in jobs:
            result.append({
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "pending": job.pending,
            })
        return result

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        """Get details for a specific job."""
        job = self._scheduler.get_job(job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "name": job.name,
            "trigger": str(job.trigger),
            "next_run_time": (
                job.next_run_time.isoformat() if job.next_run_time else None
            ),
            "pending": job.pending,
        }

    def pause_job(self, job_id: str) -> None:
        """Pause a scheduled job."""
        self._scheduler.pause_job(job_id)
        logger.info("Job paused: %s", job_id)

    def resume_job(self, job_id: str) -> None:
        """Resume a paused job."""
        self._scheduler.resume_job(job_id)
        logger.info("Job resumed: %s", job_id)

    def run_job_now(self, job_id: str) -> None:
        """Trigger a job to run immediately (in addition to its schedule)."""
        job = self._scheduler.get_job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        job.modify(next_run_time=None)
        self._scheduler.modify_job(job_id, next_run_time=None)
        logger.info("Job triggered for immediate execution: %s", job_id)
