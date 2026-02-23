"""Main application orchestrator for Full SEO Automation."""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class SEOAutomation:
    """Central application class that wires together every module.

    Usage::

        app = SEOAutomation()
        app.initialize()
        app.run_pipeline("full")
        status = app.get_status()
    """

    def __init__(
        self,
        config_path: str = "config/settings.yaml",
        env_path: str = ".env",
    ):
        self._config_path = config_path
        self._env_path = env_path
        self.config: dict[str, Any] = {}
        self._initialized = False
        self._scheduler = None
        self._llm_client = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Load configuration, environment, initialise DB, and prepare modules."""
        if self._initialized:
            return

        # Load .env
        env_file = Path(self._env_path)
        if env_file.exists():
            load_dotenv(env_file)
            logger.info("Loaded environment from %s", self._env_path)

        # Load YAML config
        self.config = self._load_config()

        # Ensure data directories exist
        for dir_key in ("data_dir", "cache_dir", "export_dir"):
            dir_path = self.config.get("app", {}).get(dir_key, "")
            if dir_path:
                Path(dir_path).mkdir(parents=True, exist_ok=True)

        # Initialise database
        from src.database import init_db
        db_url = self.config.get("database", {}).get("url", None)
        db_echo = self.config.get("database", {}).get("echo", False)
        init_db(database_url=db_url, echo=db_echo)

        # Prepare LLM client (lazy — created on first pipeline use)
        self._llm_client = None

        # Prepare scheduler
        sched_cfg = self.config.get("scheduler", {})
        from src.scheduler import SEOScheduler
        self._scheduler = SEOScheduler(
            job_store_url=sched_cfg.get("job_store", "sqlite:///data/scheduler_jobs.db"),
            timezone=sched_cfg.get("timezone", "UTC"),
            max_workers=sched_cfg.get("max_concurrent_jobs", 3),
        )

        self._initialized = True
        logger.info("SEOAutomation initialised.")

    def _load_config(self) -> dict[str, Any]:
        """Load the YAML configuration file."""
        config_file = Path(self._config_path)
        if not config_file.exists():
            logger.warning("Config file not found: %s — using defaults.", self._config_path)
            return {}
        with open(config_file, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        logger.info("Configuration loaded from %s", self._config_path)
        return config

    def _get_llm_client(self):
        """Lazy-initialise and return the LLM client."""
        if self._llm_client is None:
            from src.integrations.llm_client import LLMClient
            llm_cfg = self.config.get("llm", {})
            primary = llm_cfg.get("primary", {})
            fallback = llm_cfg.get("fallback", {})
            emb_cfg = llm_cfg.get("embeddings", {})
            cache_cfg = llm_cfg.get("cache", {})
            budget_cfg = llm_cfg.get("budget", {})
            rl_cfg = self.config.get("rate_limits", {})

            self._llm_client = LLMClient(
                openai_model=primary.get("model", "gpt-4o-mini"),
                gemini_model=fallback.get("model", "gemini-2.0-flash"),
                embedding_model=emb_cfg.get("model", "text-embedding-3-small"),
                max_tokens=primary.get("max_tokens", 4096),
                temperature=primary.get("temperature", 0.7),
                timeout=primary.get("timeout", 60),
                openai_rpm=rl_cfg.get("openai", {}).get("requests_per_minute", 60),
                gemini_rpm=rl_cfg.get("gemini", {}).get("requests_per_minute", 15),
                cache_enabled=cache_cfg.get("enabled", True),
                cache_ttl_hours=cache_cfg.get("ttl_hours", 24),
                cache_max_size=cache_cfg.get("max_size", 10000),
                max_monthly_budget=budget_cfg.get("max_monthly_usd", 100.0),
                budget_warning_pct=budget_cfg.get("warning_threshold_pct", 80.0),
            )
        return self._llm_client

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    def run_pipeline(self, pipeline: str, **kwargs: Any) -> dict[str, Any]:
        """Route and execute a named pipeline.

        Args:
            pipeline: One of full, research, content, audit, backlinks, rank, report.
            **kwargs: Pipeline-specific parameters.

        Returns:
            Dict with execution results / summary.
        """
        self._ensure_initialized()
        logger.info("Running pipeline: %s (kwargs=%s)", pipeline, kwargs)

        dispatch = {
            "full": self._run_full,
            "research": self._run_research,
            "content": self._run_content,
            "audit": self._run_audit,
            "backlinks": self._run_backlinks,
            "rank": self._run_rank,
            "report": self._run_report,
        }
        handler = dispatch.get(pipeline)
        if handler is None:
            raise ValueError(f"Unknown pipeline: {pipeline!r}")
        return handler(**kwargs)

    def _run_full(self, **kwargs) -> dict[str, Any]:
        """Execute all pipelines in sequence."""
        results = {}
        for name in ("research", "content", "audit", "backlinks", "rank", "report"):
            try:
                results[name] = self.run_pipeline(name, **kwargs)
            except Exception as exc:
                logger.error("Pipeline %s failed: %s", name, exc)
                results[name] = {"status": "error", "error": str(exc)}
        return results

    def _run_research(self, **kwargs) -> dict[str, Any]:
        """Keyword and topical research pipeline."""
        logger.info("Research pipeline: %s", kwargs)
        # Phase 2 will implement full research logic here
        return {"status": "ok", "message": "Research pipeline placeholder", "params": kwargs}

    def _run_content(self, **kwargs) -> dict[str, Any]:
        """Content generation pipeline."""
        logger.info("Content pipeline: %s", kwargs)
        return {"status": "ok", "message": "Content pipeline placeholder", "params": kwargs}

    def _run_audit(self, **kwargs) -> dict[str, Any]:
        """Technical SEO audit pipeline."""
        logger.info("Audit pipeline: %s", kwargs)
        return {"status": "ok", "message": "Audit pipeline placeholder", "params": kwargs}

    def _run_backlinks(self, **kwargs) -> dict[str, Any]:
        """Backlink analysis and outreach pipeline."""
        logger.info("Backlinks pipeline: %s", kwargs)
        return {"status": "ok", "message": "Backlinks pipeline placeholder", "params": kwargs}

    def _run_rank(self, **kwargs) -> dict[str, Any]:
        """Rank tracking pipeline."""
        logger.info("Rank tracking pipeline: %s", kwargs)
        return {"status": "ok", "message": "Rank tracking pipeline placeholder", "params": kwargs}

    def _run_report(self, **kwargs) -> dict[str, Any]:
        """Report generation pipeline."""
        logger.info("Report pipeline: %s", kwargs)
        return {"status": "ok", "message": "Report pipeline placeholder", "params": kwargs}

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Return health status of all major components."""
        self._ensure_initialized()
        status: dict[str, dict[str, Any]] = {}

        # Database
        try:
            from src.database import get_session, Base
            from sqlalchemy import text
            with get_session() as session:
                tables = session.execute(
                    text("SELECT count(*) FROM sqlite_master WHERE type='table'")
                ).scalar()
            status["database"] = {"status": "ok", "details": f"{tables} tables"}
        except Exception as exc:
            status["database"] = {"status": "error", "details": str(exc)}

        # Scheduler
        try:
            jobs = self._scheduler.list_jobs() if self._scheduler else []
            sched_running = self._scheduler.is_running if self._scheduler else False
            status["scheduler"] = {
                "status": "ok" if self._scheduler else "warning",
                "details": f"{'running' if sched_running else 'stopped'}, {len(jobs)} jobs",
            }
        except Exception as exc:
            status["scheduler"] = {"status": "error", "details": str(exc)}

        # LLM
        openai_configured = bool(os.getenv("OPENAI_API_KEY"))
        gemini_configured = bool(os.getenv("GEMINI_API_KEY"))
        llm_status = "ok" if (openai_configured or gemini_configured) else "warning"
        providers = []
        if openai_configured:
            providers.append("OpenAI")
        if gemini_configured:
            providers.append("Gemini")
        status["llm"] = {
            "status": llm_status,
            "details": f"providers: {', '.join(providers) or 'none configured'}",
        }

        # Config
        status["config"] = {
            "status": "ok" if self.config else "warning",
            "details": f"{len(self.config)} sections loaded" if self.config else "no config",
        }

        return status

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Call initialize() before using the application.")
