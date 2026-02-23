# 💰 API & Tools Selection — $100/Month Budget

> **Constraint:** Maximum $100/month total for all external APIs and tools.
> **Strategy:** Maximize free tools, use cheapest AI models, self-host where possible.

---

## 📊 Budget Allocation

| Category | Tool/API | Monthly Cost | Priority |
|----------|----------|:------------:|:--------:|
| **AI / LLM** | OpenAI GPT-4o-mini | ~$30-50 | 🔴 Critical |
| **AI / LLM (backup)** | Google Gemini 2.0 Flash | Free (15 RPM) / ~$0-10 | 🟡 Optional |
| **Search Data** | Google Search Console API | Free | 🔴 Critical |
| **Analytics** | Google Analytics 4 API | Free | 🔴 Critical |
| **Page Speed** | Google PageSpeed Insights API | Free | 🔴 Critical |
| **Trends** | Google Trends (pytrends) | Free | 🔴 Critical |
| **Keyword Volume** | Google Keyword Planner (Ads account) | Free | 🟡 Important |
| **SERP Scraping** | Custom Playwright scraper | Free (self-built) | 🔴 Critical |
| **SERP API (backup)** | SerpAPI (free tier) | Free (100 searches/mo) | 🟢 Nice-to-have |
| **NLP / Text** | spaCy (local) | Free | 🔴 Critical |
| **Grammar** | LanguageTool (self-hosted) | Free | 🟡 Important |
| **Web Crawling** | Playwright + BeautifulSoup | Free | 🔴 Critical |
| **Email Outreach** | Gmail SMTP (free tier) | Free | 🟡 Important |
| **Embeddings** | OpenAI text-embedding-3-small | ~$1-3 | 🟡 Important |
| **Rank Tracking** | Custom SERP scraper | Free (self-built) | 🔴 Critical |
| **Keyword Difficulty** | Estimate via SERP analysis | Free (self-built) | 🟡 Important |
| **Backlink Data** | CommonCrawl (free dataset) | Free | 🟢 Nice-to-have |
| **Content Uniqueness** | Custom TF-IDF similarity | Free (self-built) | 🟡 Important |
| **Scheduling** | APScheduler (local) | Free | 🔴 Critical |
| **Database** | SQLite | Free | 🔴 Critical |
| **Dashboard** | Streamlit | Free | 🔴 Critical |
| **Buffer/Reserve** | — | ~$10-20 | — |
| **TOTAL** | | **$41-83/mo** | ✅ |

---

## 🔍 Detailed Breakdown by Module

### Module 1: 🌐 Topical Research
| Need | Solution | Cost |
|------|----------|:----:|
| Topic expansion & mapping | GPT-4o-mini | Shared |
| Trend analysis | pytrends (Google Trends) | Free |
| Competitor site crawling | Playwright + BeautifulSoup | Free |
| Semantic entity extraction | spaCy (local NLP) | Free |
| Topic clustering | sentence-transformers (local) | Free |
| **Module Total** | | **~$5-10** |

### Module 2: 🔍 Keyword Research
| Need | Solution | Cost |
|------|----------|:----:|
| Search volume data | Google Keyword Planner (free with Ads account) | Free |
| Keyword expansion | GPT-4o-mini + Google Autocomplete scraping | Shared + Free |
| Search intent classification | GPT-4o-mini | Shared |
| SERP analysis | Custom Playwright scraper | Free |
| PAA/Related searches | Custom SERP scraper | Free |
| Keyword difficulty estimation | SERP analysis (DA of top 10 results) | Free |
| **Module Total** | | **~$5-10** |

### Module 3: 📝 Blog Content Creation
| Need | Solution | Cost |
|------|----------|:----:|
| Content brief generation | GPT-4o-mini | Shared |
| Blog writing (long-form) | GPT-4o-mini (bulk) | Shared |
| SERP content analysis | Custom scraper + GPT-4o-mini | Shared + Free |
| Outline generation | GPT-4o-mini | Shared |
| **Module Total** | | **~$15-25** |

### Module 4: ⚡ Content Optimization
| Need | Solution | Cost |
|------|----------|:----:|
| SEO scoring | Custom Python algorithm | Free |
| Readability analysis | textstat library (Python) | Free |
| Grammar check | LanguageTool (self-hosted Docker) | Free |
| Uniqueness check | Custom TF-IDF / simhash | Free |
| Keyword density analysis | Custom Python | Free |
| **Module Total** | | **$0** |

### Module 5: 📄 On-Page SEO
| Need | Solution | Cost |
|------|----------|:----:|
| Meta tag generation | GPT-4o-mini | Shared |
| Schema markup generation | Custom Python templates | Free |
| Internal link suggestions | SQLite content DB + fuzzy matching | Free |
| Image alt text | GPT-4o-mini | Shared |
| **Module Total** | | **~$2-5** |

### Module 6: 🔧 Technical SEO Audit
| Need | Solution | Cost |
|------|----------|:----:|
| Site crawling | Playwright + BeautifulSoup | Free |
| Core Web Vitals | Google PageSpeed Insights API | Free |
| Sitemap validation | Custom Python (lxml) | Free |
| Broken link checking | Custom crawler (aiohttp) | Free |
| Security headers | Custom Python (requests) | Free |
| Mobile check | PageSpeed API (mobile mode) | Free |
| Robots.txt analysis | Custom Python | Free |
| **Module Total** | | **$0** |

### Module 7: 🔗 Link Building
| Need | Solution | Cost |
|------|----------|:----:|
| Competitor backlinks | CommonCrawl dataset (free) | Free |
| Prospect finding | Custom Playwright scraper | Free |
| Email finding | Pattern matching + website scraping | Free |
| Outreach emails | Gmail SMTP (500/day free) | Free |
| Email personalization | GPT-4o-mini | Shared |
| Backlink monitoring | Custom crawler (periodic) | Free |
| **Module Total** | | **~$2-5** |

### Module 8: 📊 Rank Tracking
| Need | Solution | Cost |
|------|----------|:----:|
| Daily rankings | Google Search Console API | Free |
| SERP position checking | Custom Playwright SERP scraper | Free |
| SERP features detection | Custom scraper (parse SERP HTML) | Free |
| Competitor tracking | Custom SERP scraper | Free |
| **Module Total** | | **$0** |

### Module 9: 📈 Reporting Dashboard
| Need | Solution | Cost |
|------|----------|:----:|
| Dashboard UI | Streamlit (local) | Free |
| Charts/Graphs | Plotly / Altair (Python) | Free |
| PDF export | WeasyPrint / ReportLab | Free |
| Report generation | Jinja2 templates | Free |
| **Module Total** | | **$0** |

---

## 🤖 AI Model Details (Primary Cost)

### OpenAI GPT-4o-mini — Primary AI Engine (~$30-50/mo)
| Usage | Pricing | Est. Monthly Use | Est. Cost |
|-------|---------|:-----------------:|:---------:|
| Input tokens | $0.15 / 1M tokens | ~30M tokens | $4.50 |
| Output tokens | $0.60 / 1M tokens | ~15M tokens | $9.00 |
| Content writing (heavy) | — | ~50M input, 25M output | ~$22.50 |
| **Total AI estimate** | | | **$30-50** |

#### What GPT-4o-mini handles:
- Topical map generation
- Keyword expansion & intent classification
- Content briefs & outlines
- Full blog post writing (all types)
- Meta tag & alt text generation
- Email outreach personalization
- Data analysis & insights

### Google Gemini 2.0 Flash — Free Backup
- **Free tier:** 15 requests/minute, 1M tokens/minute, 1,500 requests/day
- **Use for:** Non-critical tasks, bulk classification, second opinion on content
- **Cost:** $0 (within free tier) or ~$0.10/1M tokens if exceeded

### Embeddings — OpenAI text-embedding-3-small (~$1-3/mo)
- $0.02 / 1M tokens
- Used for: keyword clustering, content similarity, semantic search
- Very cheap even with heavy usage

---

## 🆓 Free Tools & Libraries (No API Cost)

### Python Libraries (pip install)
| Library | Purpose |
|---------|--------|
| `playwright` | Web scraping, SERP scraping, JS rendering |
| `beautifulsoup4` | HTML parsing |
| `spacy` | NLP, entity extraction, text analysis |
| `sentence-transformers` | Semantic similarity, clustering |
| `textstat` | Readability scoring (Flesch-Kincaid, etc.) |
| `scikit-learn` | TF-IDF, clustering algorithms |
| `pandas` | Data manipulation |
| `plotly` | Interactive charts |
| `streamlit` | Local web dashboard |
| `apscheduler` | Task scheduling |
| `sqlalchemy` | Database ORM |
| `aiohttp` | Async HTTP requests |
| `lxml` | XML/HTML parsing |
| `jinja2` | Report templates |
| `weasyprint` | PDF generation |
| `python-dotenv` | Environment variables |
| `typer` | CLI interface |
| `pytrends` | Google Trends data |
| `feedparser` | RSS feed parsing |

### Self-Hosted Services
| Service | Purpose | How |
|---------|---------|-----|
| **LanguageTool** | Grammar checking | Docker: `docker run -p 8081:8010 erikvl87/languagetool` |

### Free APIs
| API | Rate Limit | Purpose |
|-----|-----------|--------|
| Google Search Console | 2,000 req/day | Rankings, clicks, impressions |
| Google Analytics 4 | 10,000 req/day | Traffic, conversions |
| PageSpeed Insights | 25,000 req/day | Core Web Vitals, performance |
| Google Trends (pytrends) | ~10 req/min | Trend data, seasonality |
| Google Keyword Planner | Requires Ads account (free) | Search volume, CPC |
| SerpAPI (free tier) | 100 searches/month | Backup SERP data |
| CommonCrawl | Unlimited (dataset) | Backlink discovery |

---

## 📋 Monthly Budget Summary

```
┌─────────────────────────────────────────────────────┐
│          MONTHLY BUDGET: $100 MAX                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  🤖 AI APIs                                          │
│  ├── OpenAI GPT-4o-mini ........... $30 - $50       │
│  ├── OpenAI Embeddings ............ $ 1 - $ 3        │
│  └── Google Gemini Flash .......... $ 0 (free tier)  │
│                                                      │
│  🔍 Search & Data APIs                               │
│  ├── Google Search Console ........ $ 0 (free)       │
│  ├── Google Analytics 4 ........... $ 0 (free)       │
│  ├── PageSpeed Insights ........... $ 0 (free)       │
│  ├── Google Trends ................ $ 0 (free)       │
│  ├── Google Keyword Planner ....... $ 0 (free)       │
│  └── SerpAPI (free tier) .......... $ 0 (free)       │
│                                                      │
│  🛠️ Self-Built / Self-Hosted                         │
│  ├── Custom SERP Scraper .......... $ 0 (Playwright) │
│  ├── LanguageTool ................. $ 0 (Docker)     │
│  ├── NLP (spaCy) .................. $ 0 (local)      │
│  ├── Embeddings (sentence-trans) .. $ 0 (local)      │
│  └── All Python libraries ......... $ 0 (pip)        │
│                                                      │
│  💾 Infrastructure                                    │
│  ├── Database (SQLite) ............ $ 0              │
│  ├── Dashboard (Streamlit) ........ $ 0              │
│  └── Scheduler (APScheduler) ...... $ 0              │
│                                                      │
│  🔄 Buffer/Reserve ................. $10 - $20       │
│                                                      │
├─────────────────────────────────────────────────────┤
│  ESTIMATED TOTAL:  $41 - $73 / month                │
│  REMAINING BUDGET: $27 - $59 / month (reserve)      │
└─────────────────────────────────────────────────────┘
```

---

## ⚡ Cost Optimization Tips

1. **Batch AI requests** — Group multiple tasks into single API calls to reduce overhead
2. **Cache everything** — Cache SERP results, keyword data, AI responses to avoid duplicate calls
3. **Use Gemini Flash for bulk** — Route simple classification tasks to free Gemini API
4. **Prompt efficiency** — Shorter, focused prompts = fewer tokens = less cost
5. **Local embeddings** — Use `sentence-transformers` locally instead of OpenAI for clustering
6. **Incremental crawling** — Only re-crawl changed pages, not entire site every time
7. **Rate limit respect** — Stay within free tiers by scheduling requests throughout the day
8. **Content templates** — Use boilerplate structures to reduce AI-generated token count

---

## 🔄 Upgrade Path (When Budget Grows)

| Budget | Add This | Benefit |
|:------:|----------|--------|
| $150/mo | DataForSEO API ($50/mo) | Accurate keyword volume & difficulty |
| $200/mo | + Claude Sonnet for content ($50/mo) | Higher quality long-form content |
| $300/mo | + Ahrefs Lite ($99/mo) | Professional backlink data |
| $500/mo | + SEMrush ($130/mo) | Full competitive intelligence |

---

*Last Updated: 2026-02-23*
*Budget Target: ≤ $100/month*
