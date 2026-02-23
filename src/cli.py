"""Typer CLI application for Full SEO Automation.

Provides commands for all SEO pipelines: auditing, keyword research,
content generation, link building, rank tracking, local SEO, monitoring,
and reporting.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()
app = typer.Typer(
    name="seo",
    help="Full SEO Automation -- research, content, audits, rank tracking & reporting.",
    add_completion=False,
    no_args_is_help=True,
)


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging level and format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _run_async(coro):
    """Run an async coroutine from synchronous CLI context."""
    return asyncio.run(coro)


def _get_workflow_engine():
    """Lazy-import and return a WorkflowEngine instance."""
    from src.workflows import WorkflowEngine
    return WorkflowEngine()


def _print_results(results: dict, title: str = "Results") -> None:
    """Pretty-print pipeline results using Rich."""
    steps = results.get("steps", {})
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Step", style="cyan", min_width=25)
    table.add_column("Status", min_width=10)
    table.add_column("Details", max_width=60)

    for step_name, step_data in steps.items():
        status = step_data.get("status", "unknown")
        if status == "success":
            status_display = "[green]\u2714 success[/green]"
        elif status == "error":
            status_display = "[red]\u2718 error[/red]"
        elif status == "skipped":
            status_display = "[yellow]\u25cb skipped[/yellow]"
        else:
            status_display = status

        detail_parts = []
        if status == "error":
            err_text = step_data.get("error", "")[:80]
            detail_parts.append(err_text)
        elif status == "skipped":
            detail_parts.append(step_data.get("reason", ""))
        else:
            for key in ("count", "score", "html_path", "report_path"):
                if key in step_data:
                    val = step_data[key]
                    detail_parts.append(f"{key}={val}")
        detail_str = "; ".join(detail_parts) if detail_parts else ""
        display_name = step_name.replace("_", " ").title()
        table.add_row(display_name, status_display, detail_str)

    console.print(table)
    summary = results.get("summary", "")
    elapsed = results.get("elapsed_seconds", 0)
    if summary:
        console.print(f"\n[bold]{summary}[/bold]")
    if elapsed:
        console.print(f"Elapsed: {elapsed}s")


# ------------------------------------------------------------------
# audit
# ------------------------------------------------------------------
@app.command()
def audit(
    domain: str = typer.Argument(..., help="Domain to audit (e.g. example.com)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run technical and on-page SEO audit on a domain."""
    _setup_logging(verbose)
    console.print(Panel(f"[bold cyan]SEO Audit: {domain}[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Running technical + on-page audit...", total=None)
        engine = _get_workflow_engine()

        async def _run():
            results = {"domain": domain, "steps": {}}
            try:
                auditor = engine._get_technical_auditor()
                url = domain if domain.startswith("http") else "https://" + domain
                audit_data = await auditor.run_full_audit(url)
                score_data = auditor.score_audit(audit_data)
                results["steps"]["technical_audit"] = {"status": "success", "data": audit_data, "score": score_data}
            except Exception as exc:
                results["steps"]["technical_audit"] = {"status": "error", "error": str(exc)}
            try:
                optimizer = engine._get_onpage_optimizer()
                url = domain if domain.startswith("http") else "https://" + domain
                onpage_data = await optimizer.analyze_page(url)
                results["steps"]["onpage_analysis"] = {"status": "success", "data": onpage_data}
            except Exception as exc:
                results["steps"]["onpage_analysis"] = {"status": "error", "error": str(exc)}
            return results

        results = _run_async(_run())

    _print_results(results, title="Audit Results: " + domain)
    console.print("[green]\u2714[/green] Audit complete.")


# ------------------------------------------------------------------
# keywords
# ------------------------------------------------------------------
@app.command()
def keywords(
    domain: str = typer.Argument(..., help="Target domain."),
    seed_keywords: str = typer.Argument(..., help="Comma-separated seed keywords."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run keyword research pipeline for a domain."""
    _setup_logging(verbose)
    kw_list = [kw.strip() for kw in seed_keywords.split(",") if kw.strip()]
    kw_display = ", ".join(kw_list)
    console.print(Panel("[bold cyan]Keyword Research: " + kw_display + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Researching keywords...", total=None)

        async def _run():
            engine = _get_workflow_engine()
            researcher = engine._get_keyword_researcher()
            results = {"domain": domain, "steps": {}}
            try:
                kw_data = await researcher.full_research_pipeline(kw_list)
                results["steps"]["keyword_research"] = {"status": "success", "data": kw_data}
            except Exception as exc:
                results["steps"]["keyword_research"] = {"status": "error", "error": str(exc)}
            try:
                analyzer = engine._get_keyword_analyzer()
                kw_result = results["steps"].get("keyword_research", {}).get("data", {})
                report = await analyzer.generate_keyword_report(kw_result)
                results["steps"]["keyword_report"] = {"status": "success", "data": report}
            except Exception as exc:
                results["steps"]["keyword_report"] = {"status": "error", "error": str(exc)}
            return results

        results = _run_async(_run())

    _print_results(results, title="Keyword Research Results")
    console.print("[green]\u2714[/green] Keyword research complete.")


# ------------------------------------------------------------------
# content
# ------------------------------------------------------------------
@app.command()
def content(
    keyword: str = typer.Argument(..., help="Target keyword for content."),
    content_type: str = typer.Option("blog_post", "--type", "-t", help="Content type (blog_post, pillar, guide)."),
    domain: str = typer.Option("example.com", "--domain", "-d", help="Target domain."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run content creation pipeline for a keyword."""
    _setup_logging(verbose)
    label = keyword + " (" + content_type + ")"
    console.print(Panel("[bold cyan]Content Pipeline: " + label + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Generating content...", total=None)
        engine = _get_workflow_engine()
        results = _run_async(engine.run_content_pipeline(domain, keyword, content_type))

    _print_results(results, title="Content Pipeline Results")
    console.print("[green]\u2714[/green] Content pipeline complete.")


# ------------------------------------------------------------------
# links
# ------------------------------------------------------------------
@app.command()
def links(
    domain: str = typer.Argument(..., help="Target domain for link building."),
    kw: str = typer.Option("", "--keywords", "-k", help="Comma-separated keywords."),
    competitors: str = typer.Option("", "--competitors", "-c", help="Comma-separated competitor domains."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run link building pipeline."""
    _setup_logging(verbose)
    console.print(Panel("[bold cyan]Link Building: " + domain + "[/bold cyan]"))
    kw_list = [k.strip() for k in kw.split(",") if k.strip()] if kw else [domain]
    comp_list = [c.strip() for c in competitors.split(",") if c.strip()] if competitors else None

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Prospecting and scoring links...", total=None)
        engine = _get_workflow_engine()
        results = _run_async(engine.run_link_building_pipeline(domain, kw_list, comp_list))

    _print_results(results, title="Link Building Results")
    console.print("[green]\u2714[/green] Link building pipeline complete.")


# ------------------------------------------------------------------
# track
# ------------------------------------------------------------------
@app.command()
def track(
    domain: str = typer.Argument(..., help="Domain to track."),
    kw: str = typer.Option("", "--keywords", "-k", help="Comma-separated keywords to track."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Track keyword rankings for a domain."""
    _setup_logging(verbose)
    kw_list = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
    if not kw_list:
        console.print("[yellow]Please provide keywords with --keywords/-k[/yellow]")
        raise typer.Exit(code=1)

    kw_display = ", ".join(kw_list)
    console.print(Panel("[bold cyan]Rank Tracking: " + domain + " (" + kw_display + ")[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Tracking rankings...", total=None)

        async def _run():
            engine = _get_workflow_engine()
            tracker = engine._get_rank_tracker()
            results = {"domain": domain, "steps": {}}
            try:
                rank_data = await tracker.track_keywords_bulk(domain, kw_list)
                results["steps"]["rank_tracking"] = {"status": "success", "data": rank_data}
            except Exception as exc:
                results["steps"]["rank_tracking"] = {"status": "error", "error": str(exc)}
            try:
                changes = tracker.detect_ranking_changes(domain)
                results["steps"]["rank_changes"] = {"status": "success", "data": changes}
            except Exception as exc:
                results["steps"]["rank_changes"] = {"status": "error", "error": str(exc)}
            return results

        results = _run_async(_run())

    _print_results(results, title="Rank Tracking Results")
    console.print("[green]\u2714[/green] Rank tracking complete.")


# ------------------------------------------------------------------
# local
# ------------------------------------------------------------------
@app.command()
def local(
    domain: str = typer.Argument(..., help="Business domain."),
    business: str = typer.Option(..., "--business", "-b", help="Business name."),
    location: str = typer.Option(..., "--location", "-l", help="Business location (City, State)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run local SEO analysis pipeline."""
    _setup_logging(verbose)
    label = business + " in " + location
    console.print(Panel("[bold cyan]Local SEO: " + label + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Analyzing local SEO...", total=None)
        engine = _get_workflow_engine()
        results = _run_async(engine.run_local_seo_pipeline(domain, business, location))

    _print_results(results, title="Local SEO Results")
    console.print("[green]\u2714[/green] Local SEO pipeline complete.")


# ------------------------------------------------------------------
# monitor
# ------------------------------------------------------------------
@app.command()
def monitor(
    domain: str = typer.Argument(..., help="Domain to monitor."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run SEO monitoring pipeline (backlinks, rankings, news)."""
    _setup_logging(verbose)
    console.print(Panel("[bold cyan]SEO Monitoring: " + domain + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Monitoring SEO metrics...", total=None)
        engine = _get_workflow_engine()
        results = _run_async(engine.run_monitoring_pipeline(domain))

    _print_results(results, title="Monitoring Results")
    console.print("[green]\u2714[/green] Monitoring pipeline complete.")


# ------------------------------------------------------------------
# full
# ------------------------------------------------------------------
@app.command()
def full(
    domain: str = typer.Argument(..., help="Domain for full SEO pipeline."),
    kw: str = typer.Option("", "--keywords", "-k", help="Comma-separated keywords."),
    business: Optional[str] = typer.Option(None, "--business", "-b", help="Business name for local SEO."),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Business location."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run the complete SEO pipeline (all modules)."""
    _setup_logging(verbose)
    kw_list = [k.strip() for k in kw.split(",") if k.strip()] if kw else [domain]
    console.print(Panel("[bold cyan]Full SEO Pipeline: " + domain + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Running full SEO pipeline...", total=None)
        engine = _get_workflow_engine()
        results = _run_async(
            engine.run_full_seo_pipeline(domain, kw_list, business, location)
        )

    _print_results(results, title="Full SEO Pipeline: " + domain)
    console.print("[green]\u2714[/green] Full SEO pipeline complete.")


# ------------------------------------------------------------------
# report
# ------------------------------------------------------------------
@app.command()
def report(
    domain: str = typer.Argument(..., help="Domain to report on."),
    fmt: str = typer.Option("html", "--format", "-f", help="Output format: html, pdf, json."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Generate an SEO report for a domain."""
    _setup_logging(verbose)
    label = domain + " (" + fmt + ")"
    console.print(Panel("[bold cyan]Report Generation: " + label + "[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Generating report...", total=None)

        async def _run():
            engine = _get_workflow_engine()
            report_engine = engine._get_report_engine()
            renderer = engine._get_report_renderer()
            report_data = await report_engine.generate_full_report(domain)
            if fmt == "html":
                rendered = renderer.render_html(report_data)
            elif fmt == "pdf":
                rendered = renderer.render_pdf(report_data)
            elif fmt == "json":
                rendered = renderer.render_json(report_data)
            else:
                rendered = renderer.render_html(report_data)
            return {"report_data": report_data, "rendered": rendered, "format": fmt}

        result = _run_async(_run())

    rendered_path = result.get("rendered", "")
    if output and rendered_path and os.path.exists(str(rendered_path)):
        import shutil
        shutil.copy2(str(rendered_path), output)
        console.print("Report saved to: [bold]" + output + "[/bold]")
    elif rendered_path:
        console.print("Report generated: [bold]" + str(rendered_path) + "[/bold]")
    console.print("[green]\u2714[/green] Report generation complete.")


# ------------------------------------------------------------------
# news
# ------------------------------------------------------------------
@app.command()
def news(
    limit: int = typer.Option(20, "--limit", "-l", help="Max articles to display."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Scrape and display latest SEO news."""
    _setup_logging(verbose)
    console.print(Panel("[bold cyan]SEO News Scraper[/bold cyan]"))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        progress.add_task(description="Scraping SEO news sources...", total=None)

        async def _run():
            from src.modules.seo_news.scraper import SEONewsScraper
            scraper = SEONewsScraper()
            try:
                articles = await scraper.scrape_all_sources()
                return articles
            finally:
                await scraper.close()

        articles = _run_async(_run())

    table = Table(title="Latest SEO News", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", min_width=40)
    table.add_column("Source", min_width=15)
    table.add_column("Category", min_width=12)

    for idx, article in enumerate(articles[:limit], 1):
        title = article.get("title", "Untitled")[:60]
        source = article.get("source_name", "Unknown")[:20]
        category = article.get("category", "")[:15]
        table.add_row(str(idx), title, source, category)

    total = len(articles)
    console.print(table)
    console.print("\nFound [bold]" + str(total) + "[/bold] articles.")
    console.print("[green]\u2714[/green] News scraping complete.")


# ------------------------------------------------------------------
# dashboard
# ------------------------------------------------------------------
@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p", help="Streamlit server port."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Launch the Streamlit SEO dashboard."""
    _setup_logging(verbose)
    console.print("[bold cyan]Launching dashboard on port " + str(port) + "...[/bold cyan]")
    import subprocess
    subprocess.run(
        ["streamlit", "run", "dashboard/app.py", "--server.port", str(port)],
        check=False,
    )


# ------------------------------------------------------------------
# setup
# ------------------------------------------------------------------
@app.command()
def setup(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Interactive setup wizard for Full SEO Automation."""
    _setup_logging(verbose)
    console.print(Panel("[bold cyan]Full SEO Automation Setup Wizard[/bold cyan]"))

    # Step 1: Database
    console.print("\n[bold]Step 1: Database Initialization[/bold]")
    from src.database import init_db
    try:
        init_db()
        console.print("[green]\u2714[/green] Database tables created.")
    except Exception as exc:
        console.print("[red]\u2718[/red] Database error: " + str(exc))

    # Step 2: Directories
    console.print("\n[bold]Step 2: Data Directories[/bold]")
    dirs = ["data", "data/cache", "data/exports", "data/templates"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        console.print("[green]\u2714[/green] " + d + "/")

    # Step 3: Configuration
    console.print("\n[bold]Step 3: Configuration[/bold]")
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        console.print("[green]\u2714[/green] config/settings.yaml found.")
    else:
        console.print("[yellow]\u26a0[/yellow] config/settings.yaml not found. Using defaults.")

    # Step 4: Environment
    console.print("\n[bold]Step 4: Environment Variables[/bold]")
    env_path = Path(".env")
    if env_path.exists():
        console.print("[green]\u2714[/green] .env file found.")
    else:
        console.print("[yellow]\u26a0[/yellow] .env file not found.")
        console.print("  Create .env with your API keys (OPENAI_API_KEY, GEMINI_API_KEY).")

    # Step 5: API key check
    console.print("\n[bold]Step 5: API Key Verification[/bold]")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if openai_key:
        masked = openai_key[:8] + "..." + openai_key[-4:]
        console.print("[green]\u2714[/green] OPENAI_API_KEY: " + masked)
    else:
        console.print("[yellow]\u26a0[/yellow] OPENAI_API_KEY not set.")
    if gemini_key:
        masked = gemini_key[:8] + "..." + gemini_key[-4:]
        console.print("[green]\u2714[/green] GEMINI_API_KEY: " + masked)
    else:
        console.print("[yellow]\u26a0[/yellow] GEMINI_API_KEY not set.")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("Run [bold]seo status[/bold] to verify system health.")


# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------
@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Show project status: database, modules, configuration."""
    _setup_logging(verbose)
    console.print(Panel("[bold cyan]System Status[/bold cyan]"))

    table = Table(title="Component Status", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan", min_width=25)
    table.add_column("Status", min_width=10)
    table.add_column("Details", max_width=50)

    # Database
    try:
        from src.database import get_engine
        engine = get_engine()
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        table.add_row("Database", "[green]\u2714 OK[/green]", "SQLite connected")
    except Exception as exc:
        table.add_row("Database", "[red]\u2718 Error[/red]", str(exc)[:50])

    # Configuration
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        table.add_row("Configuration", "[green]\u2714 OK[/green]", "settings.yaml found")
    else:
        table.add_row("Configuration", "[yellow]\u26a0 Missing[/yellow]", "settings.yaml not found")

    # API Keys
    openai_ok = bool(os.getenv("OPENAI_API_KEY", ""))
    gemini_ok = bool(os.getenv("GEMINI_API_KEY", ""))
    api_status = []
    if openai_ok:
        api_status.append("OpenAI")
    if gemini_ok:
        api_status.append("Gemini")
    if api_status:
        providers = ", ".join(api_status)
        table.add_row("API Keys", "[green]\u2714 OK[/green]", providers)
    else:
        table.add_row("API Keys", "[red]\u2718 Missing[/red]", "No API keys configured")

    # Module imports
    modules_ok = 0
    modules_total = 0
    module_names = [
        ("Technical Audit", "src.modules.technical_audit"),
        ("On-Page SEO", "src.modules.onpage_seo"),
        ("Keyword Research", "src.modules.keyword_research"),
        ("Topical Research", "src.modules.topical_research"),
        ("Blog Content", "src.modules.blog_content"),
        ("Link Building", "src.modules.link_building"),
        ("Rank Tracker", "src.modules.rank_tracker"),
        ("Local SEO", "src.modules.local_seo"),
        ("Reporting", "src.modules.reporting"),
    ]
    for display_name, mod_path in module_names:
        modules_total += 1
        try:
            __import__(mod_path)
            modules_ok += 1
        except Exception:
            pass
    mod_status = str(modules_ok) + "/" + str(modules_total) + " modules importable"
    if modules_ok == modules_total:
        table.add_row("Modules", "[green]\u2714 OK[/green]", mod_status)
    else:
        table.add_row("Modules", "[yellow]\u26a0 Partial[/yellow]", mod_status)

    # Workflow engine
    try:
        from src.workflows import WorkflowEngine
        engine_instance = WorkflowEngine()
        pipeline_status = engine_instance.get_pipeline_status()
        running = sum(1 for v in pipeline_status.values() if v.get("status") == "running")
        table.add_row("Workflow Engine", "[green]\u2714 OK[/green]", str(running) + " pipelines running")
    except Exception as exc:
        table.add_row("Workflow Engine", "[red]\u2718 Error[/red]", str(exc)[:50])

    console.print(table)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
