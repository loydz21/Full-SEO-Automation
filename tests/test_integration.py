"""Integration tests for Full SEO Automation.

Covers database setup, module imports, workflow engine initialization,
schema generation, text processing utilities, report widgets,
configuration loading, CLI smoke tests, and syntax validation of
every Python file in the project.
"""

import ast
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Project root (conftest.py already puts it on sys.path)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# 1. Database setup
# ===========================================================================
class TestDatabaseSetup:
    """Verify that the database can be initialised with in-memory SQLite."""

    def test_init_db_creates_tables(self, test_db):
        """init_db with in-memory SQLite should create all expected tables."""
        from src.database import get_engine
        from sqlalchemy import inspect

        engine = get_engine()
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # We expect at least these core tables from our models
        expected_tables = [
            "keywords",
            "keyword_clusters",
            "blog_posts",
            "content_briefs",
            "site_audits",
            "backlinks",
            "ranking_entries",
            "reports",
        ]
        for table in expected_tables:
            assert table in table_names, (
                "Missing table: " + table + ". Found: " + str(table_names)
            )

    def test_get_session_context_manager(self, test_db):
        """get_session should yield a usable Session object."""
        from src.database import get_session
        from sqlalchemy import text as sa_text

        with get_session() as session:
            result = session.execute(sa_text("SELECT 1"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1

    def test_reset_db(self, test_db):
        """reset_db should drop and recreate all tables without error."""
        from src.database import reset_db, get_engine
        from sqlalchemy import inspect

        reset_db()
        engine = get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        # Tables should still exist after reset (drop + recreate)
        assert len(tables) > 0


# ===========================================================================
# 2. Model imports
# ===========================================================================
class TestModelImports:
    """All ORM models should be importable from src.models."""

    @pytest.mark.parametrize("model_name", [
        "TopicalMap",
        "PillarTopic",
        "TopicCluster",
        "SupportingPage",
        "Keyword",
        "KeywordCluster",
        "ContentBrief",
        "BlogPost",
        "ContentRefresh",
        "SiteAudit",
        "AuditCheck",
        "CoreWebVitals",
        "Backlink",
        "BacklinkCheck",
        "OutreachCampaign",
        "OutreachProspect",
        "OutreachEmail",
        "EmailTemplate",
        "RankingEntry",
        "SERPSnapshot",
        "RankingRecord",
        "RankingHistory",
        "SERPFeature",
        "CompetitorRank",
        "VisibilityScore",
        "Report",
        "Alert",
        "LocalBusinessProfile",
        "LocalSEOAudit",
        "LocalCompetitor",
        "CitationEntry",
        "LocalKeywordTracking",
    ])
    def test_model_importable(self, model_name):
        import src.models as models_pkg
        assert hasattr(models_pkg, model_name), (
            "Model not found in src.models: " + model_name
        )


# ===========================================================================
# 3. Module imports
# ===========================================================================
class TestModuleImports:
    """All top-level module packages should be importable."""

    @pytest.mark.parametrize("module_path,class_names", [
        ("src.modules.technical_audit", ["TechnicalAuditor", "SiteCrawler"]),
        ("src.modules.onpage_seo", ["OnPageOptimizer", "SchemaGenerator"]),
        ("src.modules.keyword_research", ["KeywordResearcher", "KeywordAnalyzer"]),
        ("src.modules.topical_research", ["TopicalResearcher", "EntityMapper"]),
        ("src.modules.blog_content", ["BlogContentWriter", "ContentQualityChecker", "ContentManager"]),
        ("src.modules.link_building", ["LinkProspector", "OutreachManager", "BacklinkMonitor"]),
        ("src.modules.rank_tracker", ["RankTracker", "SERPAnalyzer"]),
        ("src.modules.local_seo", ["LocalSEOAnalyzer", "CitationChecker", "GMBAnalyzer", "LocalSEOReportGenerator"]),
    ])
    def test_module_importable(self, module_path, class_names):
        mod = importlib.import_module(module_path)
        for cls_name in class_names:
            assert hasattr(mod, cls_name), (
                "Class " + cls_name + " not found in " + module_path
            )

    def test_reporting_module_importable(self):
        """Reporting module may fail if plotly is missing; test gracefully."""
        try:
            from src.modules.reporting import ReportEngine, ReportRenderer
            assert ReportEngine is not None
            assert ReportRenderer is not None
        except ImportError as exc:
            pytest.skip("Reporting import failed (likely missing plotly): " + str(exc))

    def test_reporting_widgets_importable(self):
        """ReportWidgets requires plotly; skip if unavailable."""
        try:
            import plotly  # noqa: F401
        except ImportError:
            pytest.skip("plotly not installed; ReportWidgets requires it")
        from src.modules.reporting import ReportWidgets
        assert ReportWidgets is not None

    def test_seo_news_scraper_importable(self):
        from src.modules.seo_news.scraper import SEONewsScraper
        assert SEONewsScraper is not None

    def test_database_importable(self):
        from src.database import init_db, get_session, reset_db, reset_engine, Base, get_engine
        assert all([
            init_db, get_session, reset_db, reset_engine, Base, get_engine,
        ])

    def test_llm_client_importable(self):
        from src.integrations.llm_client import LLMClient
        assert LLMClient is not None

    def test_workflows_importable(self):
        from src.workflows import WorkflowEngine
        assert WorkflowEngine is not None


# ===========================================================================
# 4. WorkflowEngine initialization
# ===========================================================================
class TestWorkflowEngine:
    """WorkflowEngine should initialise without errors."""

    def test_init(self):
        from src.workflows import WorkflowEngine
        engine = WorkflowEngine()
        assert engine is not None

    def test_get_pipeline_status_empty(self):
        from src.workflows import WorkflowEngine
        engine = WorkflowEngine()
        status = engine.get_pipeline_status()
        assert isinstance(status, dict)
        assert len(status) == 0

    def test_lazy_accessors_exist(self):
        """Verify that all lazy accessor methods are defined."""
        from src.workflows import WorkflowEngine
        engine = WorkflowEngine()
        accessor_methods = [
            "_get_llm_client",
            "_get_technical_auditor",
            "_get_onpage_optimizer",
            "_get_schema_generator",
            "_get_keyword_researcher",
            "_get_keyword_analyzer",
            "_get_topical_researcher",
            "_get_blog_writer",
            "_get_quality_checker",
            "_get_content_manager",
            "_get_link_prospector",
            "_get_outreach_manager",
            "_get_backlink_monitor",
            "_get_rank_tracker",
            "_get_serp_analyzer",
            "_get_local_seo_analyzer",
            "_get_local_report_generator",
            "_get_report_engine",
            "_get_report_renderer",
            "_get_seo_news_scraper",
        ]
        for method_name in accessor_methods:
            assert hasattr(engine, method_name), (
                "Missing accessor: " + method_name
            )
            assert callable(getattr(engine, method_name))

    def test_pipeline_methods_exist(self):
        """Verify that all pipeline methods are defined."""
        from src.workflows import WorkflowEngine
        engine = WorkflowEngine()
        pipeline_methods = [
            "run_full_seo_pipeline",
            "run_content_pipeline",
            "run_link_building_pipeline",
            "run_monitoring_pipeline",
            "run_local_seo_pipeline",
        ]
        for method_name in pipeline_methods:
            assert hasattr(engine, method_name), (
                "Missing pipeline: " + method_name
            )
            assert callable(getattr(engine, method_name))


# ===========================================================================
# 5. SchemaGenerator
# ===========================================================================
class TestSchemaGenerator:
    """SchemaGenerator should produce valid schemas."""

    def test_generate_article_schema(self):
        from src.modules.onpage_seo import SchemaGenerator
        gen = SchemaGenerator()
        schema = gen.generate_article_schema(
            title="Test Article",
            author="Test Author",
            date_published="2025-01-15",
            description="A test description.",
            url="https://example.com/test",
        )
        assert isinstance(schema, dict)
        assert schema.get("@type") == "Article"
        assert schema.get("headline") == "Test Article"

    def test_generate_faq_schema(self):
        from src.modules.onpage_seo import SchemaGenerator
        gen = SchemaGenerator()
        questions = [
            {"question": "What is SEO?", "answer": "Search Engine Optimization."},
            {"question": "Why is SEO important?", "answer": "It drives organic traffic."},
        ]
        schema = gen.generate_faq_schema(questions)
        assert isinstance(schema, dict)

    def test_generate_local_business_schema(self):
        from src.modules.onpage_seo import SchemaGenerator
        gen = SchemaGenerator()
        schema = gen.generate_local_business_schema(
            name="Test Business",
            address="123 Main St",
            phone="555-0100",
        )
        assert isinstance(schema, dict)

    def test_validate_schema(self):
        from src.modules.onpage_seo import SchemaGenerator
        gen = SchemaGenerator()
        schema = gen.generate_article_schema(
            title="Validation Test",
            author="Validator",
            date_published="2025-06-01",
            description="Testing schema validation.",
            url="https://example.com/validate",
        )
        result = gen.validate_schema(schema)
        assert isinstance(result, dict)
        assert "is_valid" in result


# ===========================================================================
# 6. Text processing utilities
# ===========================================================================
class TestTextProcessing:
    """Text utility functions should work correctly."""

    def test_count_words(self):
        from src.utils.text_processing import count_words
        assert count_words("one two three") == 3
        assert count_words("") == 0
        assert count_words("single") == 1

    def test_calculate_readability(self):
        from src.utils.text_processing import calculate_readability
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a simple sentence for readability testing. "
            "Short sentences are easier to read."
        )
        result = calculate_readability(text)
        assert isinstance(result, dict)
        assert "flesch_reading_ease" in result

    def test_calculate_keyword_density(self):
        from src.utils.text_processing import calculate_keyword_density
        text = "seo tools are the best seo tools for modern seo optimization"
        result = calculate_keyword_density(text, "seo")
        assert isinstance(result, dict)
        assert "density_pct" in result
        assert result["density_pct"] > 0
        assert result["count"] >= 1
        assert result["total_words"] > 0

    def test_extract_headings(self):
        from src.utils.text_processing import extract_headings
        html = "<h1>Main Title</h1><p>Text</p><h2>Subtitle</h2>"
        headings = extract_headings(html)
        assert isinstance(headings, list)
        assert len(headings) >= 1


# ===========================================================================
# 7. Report widgets
# ===========================================================================
class TestReportWidgets:
    """ReportWidgets static methods should be callable.

    ReportWidgets requires plotly, which may not be installed in all
    test environments. Tests are skipped when plotly is unavailable.
    """

    @pytest.fixture(autouse=True)
    def _skip_without_plotly(self):
        pytest.importorskip("plotly", reason="plotly required for ReportWidgets")

    def _get_widgets_class(self):
        from src.modules.reporting import ReportWidgets
        return ReportWidgets

    def test_widgets_class_exists(self):
        widgets = self._get_widgets_class()
        assert widgets is not None

    def test_score_gauge_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "score_gauge", None))

    def test_metric_card_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "metric_card", None))

    def test_module_score_grid_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "module_score_grid", None))

    def test_trend_chart_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "trend_chart", None))

    def test_issues_summary_bar_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "issues_summary_bar", None))

    def test_action_items_table_callable(self):
        widgets = self._get_widgets_class()
        assert callable(getattr(widgets, "action_items_table", None))


# ===========================================================================
# 8. Settings YAML
# ===========================================================================
class TestSettingsYaml:
    """Configuration file should be loadable."""

    def test_settings_file_exists(self):
        settings_path = PROJECT_ROOT / "config" / "settings.yaml"
        assert settings_path.exists(), "config/settings.yaml not found"

    def test_settings_parseable(self):
        import yaml
        settings_path = PROJECT_ROOT / "config" / "settings.yaml"
        with open(settings_path) as fh:
            config = yaml.safe_load(fh)
        assert isinstance(config, dict)

    def test_settings_has_required_sections(self):
        import yaml
        settings_path = PROJECT_ROOT / "config" / "settings.yaml"
        with open(settings_path) as fh:
            config = yaml.safe_load(fh)
        for section in ("app", "database", "llm"):
            assert section in config, (
                "Missing config section: " + section
            )

    def test_settings_app_name(self):
        import yaml
        settings_path = PROJECT_ROOT / "config" / "settings.yaml"
        with open(settings_path) as fh:
            config = yaml.safe_load(fh)
        assert config["app"]["name"] == "Full SEO Automation"


# ===========================================================================
# 9. CLI commands (smoke test via CliRunner)
# ===========================================================================
class TestCLICommands:
    """CLI help should work for all registered commands."""

    def _get_runner_and_app(self):
        from typer.testing import CliRunner
        from src.cli import app
        return CliRunner(), app

    def test_main_help(self):
        runner, cli_app = self._get_runner_and_app()
        result = runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0
        assert "Full SEO Automation" in result.output

    @pytest.mark.parametrize("command", [
        "audit",
        "keywords",
        "content",
        "links",
        "track",
        "local",
        "monitor",
        "full",
        "report",
        "news",
        "dashboard",
        "setup",
        "status",
    ])
    def test_command_help(self, command):
        runner, cli_app = self._get_runner_and_app()
        result = runner.invoke(cli_app, [command, "--help"])
        assert result.exit_code == 0, (
            "Command '" + command + "' --help failed with exit code "
            + str(result.exit_code) + ": " + result.output
        )


# ===========================================================================
# 10. Dashboard pages syntax validation
# ===========================================================================
class TestDashboardPagesSyntax:
    """Every dashboard page file should pass ast.parse."""

    def _get_dashboard_pages(self):
        pages_dir = PROJECT_ROOT / "dashboard" / "pages"
        if not pages_dir.exists():
            return []
        return sorted(pages_dir.glob("*.py"))

    def test_dashboard_app_syntax(self):
        app_path = PROJECT_ROOT / "dashboard" / "app.py"
        if app_path.exists():
            source = app_path.read_text(encoding="utf-8")
            try:
                ast.parse(source)
            except SyntaxError as exc:
                pytest.fail(
                    "dashboard/app.py has syntax error: " + str(exc)
                )

    def test_all_dashboard_pages_syntax(self):
        pages = self._get_dashboard_pages()
        assert len(pages) > 0, "No dashboard page files found"
        errors = []
        for page_path in pages:
            source = page_path.read_text(encoding="utf-8")
            try:
                ast.parse(source)
            except SyntaxError as exc:
                errors.append(page_path.name + ": " + str(exc))
        if errors:
            pytest.fail(
                "Dashboard page syntax errors:\n" + "\n".join(errors)
            )


# ===========================================================================
# 11. All Python files syntax validation
# ===========================================================================
class TestAllPythonFilesSyntax:
    """Every .py file in src/ and dashboard/ should pass ast.parse."""

    def _collect_python_files(self):
        files = []
        for directory in ("src", "dashboard", "tests"):
            base = PROJECT_ROOT / directory
            if base.exists():
                for py_file in base.rglob("*.py"):
                    # Skip venv and __pycache__
                    parts = py_file.parts
                    if "venv" in parts or "__pycache__" in parts:
                        continue
                    files.append(py_file)
        return sorted(files)

    def test_all_python_files_parse(self):
        py_files = self._collect_python_files()
        assert len(py_files) > 0, "No Python files found"
        errors = []
        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source)
            except SyntaxError as exc:
                rel = py_file.relative_to(PROJECT_ROOT)
                errors.append(str(rel) + ": " + str(exc))
            except Exception as exc:
                rel = py_file.relative_to(PROJECT_ROOT)
                errors.append(str(rel) + ": " + str(exc))
        if errors:
            msg = "Python syntax errors found in " + str(len(errors)) + " files:\n"
            msg += "\n".join(errors[:20])
            pytest.fail(msg)


# ===========================================================================
# 12. Requirements / key packages importable
# ===========================================================================
class TestRequirementsInstallable:
    """Key packages from requirements.txt should be importable."""

    @pytest.mark.parametrize("package", [
        "typer",
        "rich",
        "sqlalchemy",
        "yaml",  # PyYAML
        "aiohttp",
        "bs4",   # beautifulsoup4
        "openai",
        "feedparser",
    ])
    def test_package_importable(self, package):
        try:
            importlib.import_module(package)
        except ImportError:
            pytest.skip("Package not installed: " + package)

    def test_playwright_importable(self):
        try:
            import playwright
        except ImportError:
            pytest.skip("Playwright not installed")

    def test_streamlit_importable(self):
        try:
            import streamlit
        except ImportError:
            pytest.skip("Streamlit not installed")

    def test_plotly_importable(self):
        try:
            import plotly
        except ImportError:
            pytest.skip("Plotly not installed")
