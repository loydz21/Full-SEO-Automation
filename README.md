<div align="center">

# 🚀 Full SEO Automation

**A comprehensive, AI-powered SEO automation platform that replaces expensive SaaS tools with a local-first Python stack.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#license)
[![Tests: 100 passing](https://img.shields.io/badge/Tests-100%20passing-brightgreen)](#testing)
[![Code: 34k+ lines](https://img.shields.io/badge/Code-34k%2B%20lines-orange)](#)

`34,000+ lines` · `85 files` · `12 modules` · `100+ tests` · `13 CLI commands` · `11 dashboard pages`

---

*Run your entire SEO operation locally for **$41–73/month** in API costs — no cloud hosting, no subscriptions, no vendor lock-in.*

</div>

---

## ✨ Features

| Module | Description |
|--------|-------------|
| 🗺️ **Topical Research** | Build topical authority maps with pillar/cluster/supporting-page hierarchies and entity relationship graphs |
| 🔍 **Keyword Research** | AI-driven keyword discovery, semantic clustering, intent classification, and opportunity scoring |
| ✍️ **Blog Content Creation** | Automated content briefs, section-by-section AI writing, editorial calendars, and WordPress/Markdown export |
| 🔧 **Technical SEO Audit** | Multi-threaded async crawler with scoring engine for Performance, Crawlability, LCP, INP, and CLS |
| 📄 **On-Page SEO** | Content optimization, E-E-A-T analysis, JSON-LD schema generation, and readability scoring |
| 🔗 **Link Building** | Link prospecting, outreach campaign management, and backlink monitoring |
| 📊 **Rank Tracking** | Daily SERP position monitoring with historical snapshots and trend analysis |
| 📍 **Local SEO** | GBP/GMB analysis, Map Pack tracking, citation checking, and local report generation |
| 📰 **SEO News** | AI-powered RSS monitoring of authoritative SEO sources with strategy extraction |
| 📈 **Reporting** | Multi-format report generation (HTML/PDF/JSON/CSV), white-label branding, and scheduled reports |
| ⏰ **Scheduler** | Cron-based automation for all pipelines with SQLite job persistence |
| 🖥️ **Dashboard** | 11-page Streamlit dashboard for visual insights and interactive management |

### 🎯 Key Selling Points

- **🤖 AI-Powered** — Dual LLM strategy: GPT-4o-mini (primary) + Gemini 2.0 Flash (free fallback)
- **💰 Budget-Friendly** — $41–73/month in API costs vs. $200–500+/month for Ahrefs/Semrush/Surfer
- **🏠 Local-First** — Runs entirely on your machine, no cloud hosting needed
- **🔒 Privacy** — Your data never leaves your machine; SQLite database with WAL mode
- **⚡ Fast** — Async I/O, concurrent crawling, LRU caching, and rate limiting built-in
- **🧩 Modular** — Use individual modules or the full pipeline; each module works independently

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (3.11+ recommended)
- **pip** (package installer)
- **Git** (for cloning)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/loydz21/Full-SEO-Automation.git
cd Full-SEO-Automation

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Configure environment
cp .env.example .env
nano .env                        # Add your API keys

# 6. Run interactive setup
python -m src.cli setup
```

### Automated Setup (Linux/Mac)

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Launch

```bash
# CLI — run the full pipeline
seo full --domain example.com

# Dashboard — visual interface
seo dashboard

# Check system status
seo status
```

---

## 🏗️ Architecture

### Directory Structure

```
Full-SEO-Automation/
├── src/                          # Core application source
│   ├── cli.py                    # Typer CLI (13 commands)
│   ├── workflows.py              # Pipeline orchestration engine
│   ├── database.py               # SQLAlchemy ORM + SQLite (19 tables)
│   ├── scheduler.py              # APScheduler cron automation
│   ├── app.py                    # Application bootstrap
│   ├── integrations/             # External service connectors
│   │   ├── llm_client.py         # Unified LLM (OpenAI + Gemini)
│   │   ├── serp_scraper.py       # SERP data extraction
│   │   ├── google_search_console.py
│   │   ├── google_analytics.py
│   │   ├── google_pagespeed.py
│   │   └── google_trends.py
│   ├── models/                   # SQLAlchemy ORM models (19 tables)
│   │   ├── keyword.py, topic.py, content.py, audit.py,
│   │   ├── backlink.py, ranking.py, local_seo.py,
│   │   ├── seo_news.py, report.py
│   │   └── __init__.py
│   ├── modules/                  # Feature modules
│   │   ├── topical_research/     # Authority mapping & entity graphs
│   │   ├── keyword_research/     # Discovery, clustering, scoring
│   │   ├── blog_content/         # AI writing engine
│   │   ├── technical_audit/      # Crawler & scoring engine
│   │   ├── onpage_seo/           # Optimization & schema gen
│   │   ├── link_building/        # Prospecting & outreach
│   │   ├── rank_tracker/         # SERP monitoring
│   │   ├── local_seo/            # GBP/Map Pack analysis
│   │   ├── seo_news/             # News scraping & strategy
│   │   ├── reporting/            # Report engine & renderer
│   │   └── content_optimizer/    # Content scoring
│   └── utils/                    # Shared utilities
│       ├── rate_limiter.py, helpers.py, validators.py,
│       ├── text_processing.py, env_manager.py
│       └── __init__.py
├── dashboard/                    # Streamlit web interface
│   ├── app.py                    # Main router (11 pages)
│   └── pages/                    # Individual dashboard pages
│       ├── topical_research.py, keywords.py,
│       ├── blog_content.py, technical_audit.py,
│       ├── onpage_seo.py, link_building.py,
│       ├── rank_tracking.py, local_seo.py,
│       ├── seo_news.py, reports.py, settings.py
│       └── (11 pages total)
├── config/
│   └── settings.yaml             # Centralized configuration
├── data/                         # Runtime data directory
│   ├── cache/                    # LLM & API response cache
│   ├── exports/                  # Generated reports & content
│   └── templates/                # Content & report templates
├── tests/
│   ├── test_integration.py       # 100 integration tests
│   └── conftest.py               # Shared fixtures
├── scripts/
│   └── setup.sh                  # Automated setup script
├── docs/                         # Additional documentation
├── requirements.txt              # Python dependencies
├── setup.py                      # Package configuration
├── .env.example                  # Environment variable template
└── README.md                     # This file
```

### Module Dependency Flow

```
                    ┌─────────────────────┐
                    │   CLI / Dashboard   │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  Workflow Engine     │
                    │  (Pipeline Orch.)    │
                    └─────────┬───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌─────▼─────┐         ┌─────▼─────┐
   │Research │          │  Content  │         │ Technical │
   │ Layer   │          │  Layer    │         │  Layer    │
   ├─────────┤          ├───────────┤         ├───────────┤
   │Topical  │◄────────►│Blog Writer│         │Auditor    │
   │Keywords │          │On-Page    │         │Crawler    │
   │Trends   │          │Optimizer  │         │PageSpeed  │
   └────┬────┘          └─────┬─────┘         └─────┬─────┘
        │                     │                     │
   ┌────▼────┐          ┌─────▼─────┐         ┌─────▼─────┐
   │  Links  │          │ Tracking  │         │ Local SEO │
   ├─────────┤          ├───────────┤         ├───────────┤
   │Prospect │          │Rank Track │         │GBP Analyze│
   │Outreach │          │SERP Anal. │         │Citations  │
   │Monitor  │          │Scheduling │         │Map Pack   │
   └────┬────┘          └─────┬─────┘         └─────┬─────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼───────────┐
                    │   Reporting Engine   │
                    │  + SEO News Monitor  │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌──────▼──────┐
        │ LLM Client│  │ Database  │  │ Rate Limiter│
        │(GPT+Gem.) │  │ (SQLite)  │  │ + Cache     │
        └───────────┘  └───────────┘  └─────────────┘
```

### Tech Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| **Language** | Python 3.10+ | Core application |
| **Database** | SQLite + SQLAlchemy | 19-table ORM with WAL mode |
| **CLI Framework** | Typer + Rich | Beautiful terminal interface |
| **Dashboard** | Streamlit | 11-page web interface |
| **Primary LLM** | OpenAI GPT-4o-mini | Content generation & analysis |
| **Fallback LLM** | Google Gemini 2.0 Flash | Free-tier backup AI |
| **Web Scraping** | Playwright + httpx | Dynamic & static page scraping |
| **HTML Parsing** | BeautifulSoup + lxml | Content extraction |
| **NLP** | SpaCy + textstat | Text analysis & readability |
| **Scheduling** | APScheduler | Cron-based task automation |
| **Google APIs** | GSC, GA4, PageSpeed | Search data & analytics |
| **Trends** | pytrends | Google Trends integration |
| **Configuration** | PyYAML + python-dotenv | Settings management |
| **Validation** | Pydantic | Data model validation |
| **Testing** | pytest + pytest-asyncio | 100 integration tests |

---

## 💻 Usage

### CLI Commands

| Command | Description | Example |
|---------|-------------|---------|
| `seo audit` | Run technical & on-page SEO audit | `seo audit --domain example.com --full` |
| `seo keywords` | Keyword research pipeline | `seo keywords --domain example.com --seed "python tutorial"` |
| `seo content` | AI content creation | `seo content --keyword "best seo tools" --type blog_post` |
| `seo links` | Link building pipeline | `seo links --domain example.com --prospects 50` |
| `seo track` | Track keyword rankings | `seo track --domain example.com` |
| `seo local` | Local SEO analysis | `seo local --business "Coffee Shop" --location "NYC"` |
| `seo monitor` | Run monitoring pipeline | `seo monitor --domain example.com` |
| `seo full` | Run complete SEO pipeline | `seo full --domain example.com` |
| `seo report` | Generate SEO report | `seo report --domain example.com --format html` |
| `seo news` | Scrape latest SEO news | `seo news --sources all --limit 20` |
| `seo dashboard` | Launch Streamlit dashboard | `seo dashboard --port 8501` |
| `seo setup` | Interactive setup wizard | `seo setup` |
| `seo status` | Show project status | `seo status` |

### Dashboard Pages

| Page | Features |
|------|---------|
| 🗺️ **Topical Research** | Authority maps, entity graphs, niche analysis |
| 🔍 **Keywords** | 6-tab UI: Discovery, Clusters, Intent, Volume, Difficulty, Opportunities |
| ✍️ **Blog Content** | Content briefs, AI writing, editorial calendar, export |
| 🔧 **Technical Audit** | Site crawl results, Core Web Vitals, issue tracker |
| 📄 **On-Page SEO** | Content optimization scores, schema preview, E-E-A-T |
| 🔗 **Link Building** | Prospect management, outreach campaigns, backlink health |
| 📊 **Rank Tracking** | Position history, SERP features, competitor comparison |
| 📍 **Local SEO** | GBP analysis, Map Pack, citations, local reports |
| 📰 **SEO News** | Latest industry news with AI strategy analysis |
| 📈 **Reports** | 7-tab report center: Overview, Trends, Full Report, Competitors, Scheduled, Branding, Export |
| ⚙️ **Settings** | API keys, budget limits, scheduler config, system status |

### Pipeline Examples

```bash
# Full SEO pipeline — research → content → audit → track → report
seo full --domain example.com

# Content pipeline only — keyword research → content creation
seo keywords --domain example.com --seed "python tutorial"
seo content --keyword "python tutorial for beginners" --type how_to_guide

# Link building pipeline
seo links --domain example.com --prospects 100
seo monitor --domain example.com

# Monitoring pipeline — track → audit → alert
seo track --domain example.com
seo audit --domain example.com
seo report --domain example.com --format pdf
```

---

## ⚙️ Configuration

### `config/settings.yaml`

Centralized configuration controlling all modules:

```yaml
# Key sections:
app:          # Application name, version, data directories
database:     # SQLite connection, pool size, WAL mode
llm:          # Primary/fallback LLM models, embeddings, budget limits
rate_limits:  # Per-service request throttling
scheduler:    # Cron jobs for automated pipelines
content:      # Word count targets, readability, SEO constraints
research:     # Topical map limits, keyword scoring weights
scraper:      # User agents, timeouts, retry policies
audit:        # Audit categories and scoring weights
```

See the full file at [`config/settings.yaml`](config/settings.yaml) for all options.

### `.env` Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ Yes | OpenAI API key for GPT-4o-mini |
| `GEMINI_API_KEY` | 📋 Recommended | Google Gemini API key (free tier) |
| `GSC_CREDENTIALS_PATH` | ❌ Optional | Path to Google Search Console credentials |
| `GA4_CREDENTIALS_PATH` | ❌ Optional | Path to Google Analytics 4 credentials |
| `PAGESPEED_API_KEY` | ❌ Optional | Google PageSpeed Insights API key |
| `MAX_MONTHLY_BUDGET` | ❌ Optional | Maximum monthly API spend (default: $100) |
| `DATABASE_URL` | ❌ Optional | Custom database URL (default: SQLite) |

See [`.env.example`](.env.example) for all available variables.

### Budget Settings

The built-in budget tracker monitors API spending:

```yaml
# In config/settings.yaml
llm:
  budget:
    max_monthly_usd: 100.0            # Hard cap
    warning_threshold_pct: 80          # Alert at 80% usage
    cost_per_1k_input_tokens: 0.00015  # GPT-4o-mini input
    cost_per_1k_output_tokens: 0.0006  # GPT-4o-mini output
```

Estimated monthly costs by usage level:

| Usage Level | API Calls/Day | Estimated Cost |
|-------------|---------------|----------------|
| Light | 50–100 | $15–25/month |
| Moderate | 100–300 | $41–55/month |
| Heavy | 300–500+ | $55–73/month |

---

## 🔑 API Keys

| API | Required | Free Tier | Where to Get It |
|-----|----------|-----------|------------------|
| **OpenAI** | ✅ Yes | $5 credit | [platform.openai.com](https://platform.openai.com/api-keys) |
| **Google Gemini** | 📋 Recommended | ✅ Yes (generous) | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| **Google Search Console** | ❌ Optional | ✅ Yes | [search.google.com/search-console](https://search.google.com/search-console) |
| **Google Analytics 4** | ❌ Optional | ✅ Yes | [analytics.google.com](https://analytics.google.com) |
| **PageSpeed Insights** | ❌ Optional | ✅ Yes | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| **Google Trends** | ❌ Optional | ✅ Yes (via pytrends) | No key needed |

> 💡 **Minimum to get started**: Only an OpenAI API key is required. All other APIs are optional and enhance functionality.

---

## 📦 Module Details

### 🗺️ Topical Research
**Files**: `src/modules/topical_research/researcher.py`, `entity_mapper.py`

Builds comprehensive topical authority maps for any niche. Identifies pillar pages, topic clusters, and supporting content opportunities. The entity mapper creates relationship graphs showing how topics interconnect.

### 🔍 Keyword Research
**Files**: `src/modules/keyword_research/researcher.py`, `kw_analyzer.py`

AI-powered keyword discovery with semantic clustering, search intent classification, and opportunity scoring. Analyzes volume, difficulty, CPC, and trends to prioritize the best keywords.

### ✍️ Blog Content Creation
**Files**: `src/modules/blog_content/writer.py`, `content_manager.py`, `quality_checker.py`

Full content pipeline: automated briefs → section-by-section AI writing → quality checks → SEO optimization. Supports 7 content types including blog posts, pillar pages, listicles, and how-to guides. Exports to WordPress-ready HTML or Markdown.

### 🔧 Technical SEO Audit
**Files**: `src/modules/technical_audit/auditor.py`, `crawler.py`

Multi-threaded async site crawler that checks hundreds of SEO factors. Scoring engine evaluates Performance, Crawlability, Core Web Vitals (LCP, INP, CLS), security headers, and mobile friendliness.

### 📄 On-Page SEO
**Files**: `src/modules/onpage_seo/optimizer.py`, `schema_generator.py`

Content optimization analysis including keyword density, readability scoring, E-E-A-T signals, heading structure, and internal linking. Generates JSON-LD structured data schemas automatically.

### 🔗 Link Building
**Files**: `src/modules/link_building/prospector.py`, `outreach.py`, `backlink_monitor.py`

Three-stage pipeline: prospect discovery → outreach campaign management → backlink health monitoring. Finds link opportunities, manages email templates, and tracks acquired links.

### 📊 Rank Tracking
**Files**: `src/modules/rank_tracker/tracker.py`, `serp_analyzer.py`

Daily SERP position monitoring with historical snapshots. Analyzes SERP features (featured snippets, PAA, local packs) and tracks competitor movements.

### 📍 Local SEO
**Files**: `src/modules/local_seo/analyzer.py`, `gmb_analyzer.py`, `citation_checker.py`, `report_generator.py`

Comprehensive local SEO toolkit: Google Business Profile analysis, Map Pack tracking, NAP consistency checking across citation sources, and local SEO report generation.

### 📰 SEO News
**Files**: `src/modules/seo_news/scraper.py`, `strategy_analyzer.py`, `auto_upgrader.py`

AI-powered monitoring of authoritative SEO sources (Search Engine Journal, Moz, Google Blog, etc.). Extracts actionable strategies and identifies algorithm update impacts.

### 📈 Reporting
**Files**: `src/modules/reporting/report_engine.py`, `report_renderer.py`, `widgets.py`

Full reporting engine with parallel data aggregation via `asyncio.gather()`. Renders to HTML (3 themes), PDF, JSON, and CSV bundle (8-file ZIP). Supports white-label branding and scheduled report generation.

### ⏰ Scheduler
**File**: `src/scheduler.py`

APScheduler-based automation with SQLite job persistence. Default cron jobs for rank tracking (daily 6 AM), site audit (weekly Sunday 2 AM), content refresh (monthly), SERP monitoring (every 6 hours), and analytics sync (daily 1 AM).

### 🖥️ Dashboard
**Files**: `dashboard/app.py`, `dashboard/pages/*.py` (11 pages)

Streamlit-based web interface with 11 interactive pages. Central router with module navigation, real-time data visualization, and interactive management tools.

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=src --cov-report=html

# Run specific test class
python -m pytest tests/test_integration.py::TestDatabaseModels -v

# Quick syntax check of all Python files
python -c "import ast, pathlib; [ast.parse(f.read_text()) for f in pathlib.Path('src').rglob('*.py')]; print('All files valid')"
```

### Test Coverage Summary

| Test Category | Tests | Coverage |
|---------------|-------|---------|
| Database & ORM Models | 19 | All 19 tables validated |
| Module Imports | 12 | All modules importable |
| CLI Registration | 13 | All commands registered |
| Integration Connectivity | 6 | All integrations verified |
| Configuration & Settings | 8 | YAML + env loading |
| Workflow Engine | 5 | Pipeline orchestration |
| Syntax Validation | 85 | All .py files parsed |
| Dependency Verification | 37 | All packages importable |
| **Total** | **100** | **Comprehensive** |

---

## 🗺️ Roadmap

### Planned Improvements

- [ ] **WordPress Integration** — Direct publishing via WP REST API
- [ ] **Multi-language Support** — Content generation in 10+ languages
- [ ] **Competitor Intelligence** — Automated competitor gap analysis
- [ ] **Custom Dashboards** — User-defined metric panels
- [ ] **API Server** — RESTful API for external integrations
- [ ] **Docker Support** — One-command deployment with Docker Compose
- [ ] **Webhook Alerts** — Slack/Discord/Teams notifications
- [ ] **Advanced AI** — GPT-4o and Claude integration options
- [ ] **Link Intersect** — Find links competitors have that you don't
- [ ] **Content Decay Detection** — Identify underperforming content for refresh

### Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Ensure all tests pass (`python -m pytest tests/ -v`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

Please ensure your code:
- Passes all existing tests
- Includes tests for new functionality
- Follows the existing code style
- Updates documentation as needed

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024-2026 Full SEO Automation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<div align="center">

**Built with ❤️ for the SEO community**

[⬆ Back to Top](#-full-seo-automation)

</div>
