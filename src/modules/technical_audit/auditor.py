"""Technical SEO auditor — orchestrates all crawl and analysis checks.

Brings together SiteCrawler, PageSpeedInsights and LLMClient to produce a
scored, actionable audit report.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight configuration for scoring categories
# ---------------------------------------------------------------------------

_CATEGORY_WEIGHTS: dict[str, float] = {
    "crawlability": 0.20,
    "performance": 0.25,
    "security": 0.15,
    "mobile": 0.15,
    "content_quality": 0.15,
    "indexability": 0.10,
}

_GRADE_MAP = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


def _grade_for(score: float) -> str:
    for threshold, letter in _GRADE_MAP:
        if score >= threshold:
            return letter
    return "F"


# ---------------------------------------------------------------------------
# TechnicalAuditor
# ---------------------------------------------------------------------------

class TechnicalAuditor:
    """Orchestrate a full technical SEO audit for a domain."""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        pagespeed_client: Optional[Any] = None,
    ) -> None:
        self._llm = llm_client
        self._psi = pagespeed_client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run_full_audit(
        self,
        domain: str,
        max_pages: int = 100,
        check_speed: bool = True,
        check_security: bool = True,
    ) -> dict[str, Any]:
        """Run every check and return a comprehensive audit dict."""
        from src.modules.technical_audit.crawler import SiteCrawler

        start = time.monotonic()
        url = domain if domain.startswith("http") else f"https://{domain}"
        clean_domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

        logger.info("Starting full technical audit for %s", clean_domain)

        crawler = SiteCrawler(max_pages=max_pages)

        # --- Stage 1: Crawl ---
        crawl_result = await crawler.crawl_site(url)
        pages = crawl_result.get("pages", [])
        crawl_stats = crawl_result.get("crawl_stats", {})
        sitemap_data = crawl_result.get("sitemap_data", {})
        robots_data = crawl_result.get("robots_data", {})

        # --- Stage 2: Broken links ---
        broken_links = await crawler.find_broken_links(pages)

        # --- Stage 3: Redirects ---
        redirect_chains = await crawler.check_redirects(pages)

        # --- Stage 4: Duplicate / content issues ---
        content_issues = await crawler.check_duplicate_content(pages)

        # --- Stage 5: Performance (optional) ---
        speed_data: dict[str, Any] = {}
        if check_speed:
            try:
                speed_data = await crawler.analyze_page_speed(url)
            except Exception as exc:
                logger.warning("PageSpeed check failed: %s", exc)
                speed_data = {"error": str(exc)}

        # --- Stage 6: Mobile friendliness ---
        mobile_data: dict[str, Any] = {}
        try:
            mobile_data = await crawler.check_mobile_friendly(url)
        except Exception as exc:
            logger.warning("Mobile check failed: %s", exc)
            mobile_data = {"error": str(exc)}

        # --- Stage 7: Security (optional) ---
        security_data: dict[str, Any] = {}
        if check_security:
            try:
                security_data = await crawler.check_security(clean_domain)
            except Exception as exc:
                logger.warning("Security check failed: %s", exc)
                security_data = {"error": str(exc)}

        # --- Aggregate raw data ---
        audit_data: dict[str, Any] = {
            "domain": clean_domain,
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "crawl_stats": crawl_stats,
            "pages": pages,
            "sitemap_data": sitemap_data,
            "robots_data": robots_data,
            "broken_links": broken_links,
            "redirect_chains": redirect_chains,
            "content_issues": content_issues,
            "speed_data": speed_data,
            "mobile_data": mobile_data,
            "security_data": security_data,
        }

        # --- Scoring ---
        scores = self.score_audit(audit_data)
        audit_data["overall_score"] = scores["overall"]
        audit_data["grade"] = scores["grade"]
        audit_data["category_scores"] = scores["categories"]

        # --- Build issues list ---
        issues = self._compile_issues(audit_data)
        audit_data["issues"] = issues

        # --- Passed checks ---
        audit_data["passed_checks"] = self._compile_passed(audit_data)

        # --- Crawl summary ---
        audit_data["crawl_summary"] = self._build_crawl_summary(audit_data)

        # --- Recommendations (AI) ---
        recommendations = await self.generate_recommendations(audit_data)
        audit_data["recommendations"] = recommendations

        elapsed = round(time.monotonic() - start, 2)
        audit_data["elapsed_seconds"] = elapsed

        # --- Persist to DB ---
        self._persist_audit(audit_data)

        logger.info(
            "Audit complete for %s — score=%s grade=%s in %.1fs",
            clean_domain, scores["overall"], scores["grade"], elapsed,
        )
        return audit_data

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_audit(self, audit_data: dict[str, Any]) -> dict[str, Any]:
        """Calculate weighted scores per category and overall."""
        cats: dict[str, float] = {}

        # Crawlability (20%)
        cats["crawlability"] = self._score_crawlability(audit_data)

        # Performance (25%)
        cats["performance"] = self._score_performance(audit_data)

        # Security (15%)
        cats["security"] = self._score_security(audit_data)

        # Mobile (15%)
        cats["mobile"] = self._score_mobile(audit_data)

        # Content quality (15%)
        cats["content_quality"] = self._score_content(audit_data)

        # Indexability (10%)
        cats["indexability"] = self._score_indexability(audit_data)

        overall = sum(
            cats[c] * _CATEGORY_WEIGHTS[c] for c in _CATEGORY_WEIGHTS
        )
        overall = round(min(max(overall, 0), 100), 1)

        return {
            "categories": {k: round(v, 1) for k, v in cats.items()},
            "overall": overall,
            "grade": _grade_for(overall),
        }

    # --- per-category helpers ---

    @staticmethod
    def _score_crawlability(d: dict) -> float:
        score = 100.0
        pages = d.get("pages", [])
        broken = d.get("broken_links", [])
        redirects = d.get("redirect_chains", [])
        robots = d.get("robots_data", {})
        sitemap = d.get("sitemap_data", {})

        if not pages:
            return 0.0

        # Broken links penalty
        broken_ratio = len(broken) / max(len(pages), 1)
        score -= min(broken_ratio * 100, 30)

        # Redirect chains penalty
        long_chains = [r for r in redirects if r.get("chain_length", 0) > 1]
        score -= min(len(long_chains) * 3, 20)

        loops = [r for r in redirects if r.get("is_loop")]
        score -= len(loops) * 10

        # Robots.txt bonus
        if not robots.get("exists"):
            score -= 5

        # Sitemap bonus
        if not sitemap.get("found"):
            score -= 10

        # 4xx/5xx pages
        error_pages = [p for p in pages if p.get("status_code", 200) >= 400]
        score -= min(len(error_pages) * 5, 20)

        return max(score, 0)

    @staticmethod
    def _score_performance(d: dict) -> float:
        speed = d.get("speed_data", {})
        if speed.get("error") or not speed:
            return 50.0  # neutral when unavailable

        mobile = speed.get("mobile", {})
        desktop = speed.get("desktop", {})
        m_score = mobile.get("performance_score", 50)
        d_score = desktop.get("performance_score", 50)

        # Weighted average (mobile matters more)
        combined = m_score * 0.6 + d_score * 0.4

        # Penalise bad LCP
        lcp = mobile.get("lcp")
        if lcp is not None:
            if lcp > 4000:
                combined -= 10
            elif lcp > 2500:
                combined -= 5

        # CLS penalty
        cls_val = mobile.get("cls")
        if cls_val is not None and cls_val > 0.25:
            combined -= 10

        return max(min(combined, 100), 0)

    @staticmethod
    def _score_security(d: dict) -> float:
        sec = d.get("security_data", {})
        if sec.get("error") or not sec:
            return 50.0

        score = 100.0
        if not sec.get("ssl_valid"):
            score -= 40
        if not sec.get("https_enforced"):
            score -= 15
        mixed = sec.get("mixed_content", [])
        score -= min(len(mixed) * 5, 15)

        headers = sec.get("security_headers", {})
        critical = ["HSTS", "X-Content-Type-Options", "X-Frame-Options"]
        for h in critical:
            info = headers.get(h, {})
            if not info.get("present"):
                score -= 10

        return max(score, 0)

    @staticmethod
    def _score_mobile(d: dict) -> float:
        mob = d.get("mobile_data", {})
        if mob.get("error") or not mob:
            return 50.0

        score = 100.0
        if not mob.get("viewport_set"):
            score -= 30
        if not mob.get("text_size_ok"):
            score -= 15
        if not mob.get("tap_targets_ok"):
            score -= 15
        if not mob.get("content_width_ok"):
            score -= 20
        issues = mob.get("issues", [])
        score -= min(len(issues) * 5, 20)
        return max(score, 0)

    @staticmethod
    def _score_content(d: dict) -> float:
        issues = d.get("content_issues", [])
        pages = d.get("pages", [])
        if not pages:
            return 0.0

        score = 100.0
        dup_titles = [i for i in issues if i.get("type") == "duplicate_title"]
        dup_descs = [i for i in issues if i.get("type") == "duplicate_description"]
        thin = [i for i in issues if i.get("type") == "thin_content"]
        missing_titles = [i for i in issues if i.get("type") == "missing_title"]
        missing_h1 = [i for i in issues if i.get("type") == "missing_h1"]
        missing_desc = [i for i in issues if i.get("type") == "missing_description"]
        no_alt = [i for i in issues if i.get("type") == "images_missing_alt"]

        score -= min(len(dup_titles) * 5, 15)
        score -= min(len(dup_descs) * 3, 10)
        score -= min(len(thin) * 3, 15)
        score -= min(len(missing_titles) * 8, 20)
        score -= min(len(missing_h1) * 4, 10)
        score -= min(len(missing_desc) * 3, 10)
        score -= min(len(no_alt) * 2, 10)

        return max(score, 0)

    @staticmethod
    def _score_indexability(d: dict) -> float:
        pages = d.get("pages", [])
        if not pages:
            return 0.0

        score = 100.0
        html_pages = [p for p in pages if p.get("is_html", True) and p.get("status_code") == 200]
        total = max(len(html_pages), 1)

        # noindex penalty
        noindex_count = sum(
            1 for p in html_pages if "noindex" in (p.get("robots_meta") or "").lower()
        )
        score -= min((noindex_count / total) * 60, 30)

        # Missing canonical
        no_canonical = sum(1 for p in html_pages if not p.get("canonical_url"))
        score -= min((no_canonical / total) * 40, 20)

        # Sitemap coverage
        sitemap = d.get("sitemap_data", {})
        if not sitemap.get("found"):
            score -= 15

        return max(score, 0)

    # ------------------------------------------------------------------
    # Issue compilation
    # ------------------------------------------------------------------

    def _compile_issues(self, d: dict) -> list[dict[str, Any]]:
        """Flatten all detected problems into a uniform issues list."""
        issues: list[dict[str, Any]] = []

        # Broken links
        for bl in d.get("broken_links", []):
            issues.append({
                "severity": "error",
                "category": "crawlability",
                "description": "Broken link (status {status}) on {src}".format(
                    status=bl.get("status_code", "?"),
                    src=bl.get("source_page", "?"),
                ),
                "how_to_fix": "Remove or update the link pointing to " + bl.get("broken_url", ""),
                "affected_url": bl.get("broken_url", ""),
            })

        # Redirect chains
        for rc in d.get("redirect_chains", []):
            if rc.get("chain_length", 0) > 1:
                severity = "error" if rc.get("is_loop") else "warning"
                issues.append({
                    "severity": severity,
                    "category": "crawlability",
                    "description": "Redirect chain ({n} hops) from {url}".format(
                        n=rc.get("chain_length", 0),
                        url=rc.get("original_url", ""),
                    ),
                    "how_to_fix": "Update links to point directly to " + rc.get("final_url", ""),
                    "affected_url": rc.get("original_url", ""),
                })

        # Content issues
        for ci in d.get("content_issues", []):
            ci_type = ci.get("type", "")
            if ci_type == "duplicate_title":
                issues.append({
                    "severity": "warning",
                    "category": "content_quality",
                    "description": "Duplicate title across {n} pages".format(n=len(ci.get("urls", []))),
                    "how_to_fix": "Write unique title tags for each page",
                    "affected_url": ", ".join(ci.get("urls", [])[:3]),
                })
            elif ci_type == "duplicate_description":
                issues.append({
                    "severity": "warning",
                    "category": "content_quality",
                    "description": "Duplicate meta description across {n} pages".format(n=len(ci.get("urls", []))),
                    "how_to_fix": "Write unique meta descriptions for each page",
                    "affected_url": ", ".join(ci.get("urls", [])[:3]),
                })
            elif ci_type == "thin_content":
                issues.append({
                    "severity": ci.get("severity", "warning"),
                    "category": "content_quality",
                    "description": "Thin content ({wc} words) at {url}".format(
                        wc=ci.get("word_count", 0),
                        url=ci.get("url", ""),
                    ),
                    "how_to_fix": "Expand content to at least 300 words or consolidate with related pages",
                    "affected_url": ci.get("url", ""),
                })
            elif ci_type == "missing_title":
                issues.append({
                    "severity": "error",
                    "category": "content_quality",
                    "description": "Missing title tag at " + ci.get("url", ""),
                    "how_to_fix": "Add a unique, descriptive title tag",
                    "affected_url": ci.get("url", ""),
                })
            elif ci_type == "missing_description":
                issues.append({
                    "severity": "warning",
                    "category": "content_quality",
                    "description": "Missing meta description at " + ci.get("url", ""),
                    "how_to_fix": "Add a compelling meta description (150-160 characters)",
                    "affected_url": ci.get("url", ""),
                })
            elif ci_type == "missing_h1":
                issues.append({
                    "severity": "warning",
                    "category": "content_quality",
                    "description": "Missing H1 tag at " + ci.get("url", ""),
                    "how_to_fix": "Add a single, descriptive H1 heading",
                    "affected_url": ci.get("url", ""),
                })
            elif ci_type == "images_missing_alt":
                issues.append({
                    "severity": "warning",
                    "category": "content_quality",
                    "description": "{n} images missing alt text at {url}".format(
                        n=ci.get("count", 0),
                        url=ci.get("url", ""),
                    ),
                    "how_to_fix": "Add descriptive alt attributes to all images",
                    "affected_url": ci.get("url", ""),
                })

        # Security issues
        sec = d.get("security_data", {})
        if sec and not sec.get("error"):
            if not sec.get("ssl_valid"):
                issues.append({
                    "severity": "error",
                    "category": "security",
                    "description": "SSL certificate is invalid or missing",
                    "how_to_fix": "Install a valid SSL certificate (free via Let's Encrypt)",
                    "affected_url": d.get("url", ""),
                })
            if not sec.get("https_enforced"):
                issues.append({
                    "severity": "warning",
                    "category": "security",
                    "description": "HTTP does not redirect to HTTPS",
                    "how_to_fix": "Configure server to 301 redirect HTTP to HTTPS",
                    "affected_url": d.get("url", ""),
                })
            for mc in sec.get("mixed_content", []):
                issues.append({
                    "severity": "warning",
                    "category": "security",
                    "description": "Mixed content: {tag} loads over HTTP".format(tag=mc.get("tag", "")),
                    "how_to_fix": "Update resource URL to HTTPS: " + mc.get("url", ""),
                    "affected_url": mc.get("url", ""),
                })
            for hdr_name, hdr_info in sec.get("security_headers", {}).items():
                if not hdr_info.get("present"):
                    issues.append({
                        "severity": "info",
                        "category": "security",
                        "description": "Missing security header: " + hdr_name,
                        "how_to_fix": "Add the " + hdr_name + " header to server responses",
                        "affected_url": d.get("url", ""),
                    })

        # Mobile issues
        mob = d.get("mobile_data", {})
        if mob and not mob.get("error"):
            for issue_text in mob.get("issues", []):
                issues.append({
                    "severity": "warning",
                    "category": "mobile",
                    "description": issue_text,
                    "how_to_fix": "Review mobile responsiveness and fix the reported issue",
                    "affected_url": d.get("url", ""),
                })

        # Performance issues
        speed = d.get("speed_data", {})
        if speed and not speed.get("error"):
            mobile_perf = speed.get("mobile", {})
            if mobile_perf.get("performance_score", 100) < 50:
                issues.append({
                    "severity": "error",
                    "category": "performance",
                    "description": "Poor mobile performance score: {s}".format(
                        s=mobile_perf.get("performance_score", "?"),
                    ),
                    "how_to_fix": "Optimise images, reduce JavaScript, enable caching",
                    "affected_url": d.get("url", ""),
                })
            lcp = mobile_perf.get("lcp")
            if lcp is not None and lcp > 2500:
                issues.append({
                    "severity": "warning" if lcp < 4000 else "error",
                    "category": "performance",
                    "description": "LCP is {v}ms (target <2500ms)".format(v=round(lcp)),
                    "how_to_fix": "Optimise largest contentful paint element",
                    "affected_url": d.get("url", ""),
                })

        return issues

    # ------------------------------------------------------------------
    # Passed checks
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_passed(d: dict) -> list[str]:
        passed: list[str] = []
        robots = d.get("robots_data", {})
        if robots.get("exists"):
            passed.append("robots.txt is present and accessible")
        sitemap = d.get("sitemap_data", {})
        if sitemap.get("found"):
            passed.append("XML sitemap found with {n} URLs".format(n=sitemap.get("total_urls", 0)))
        if not d.get("broken_links"):
            passed.append("No broken links detected")
        sec = d.get("security_data", {})
        if sec.get("ssl_valid"):
            passed.append("Valid SSL certificate")
        if sec.get("https_enforced"):
            passed.append("HTTP to HTTPS redirect is in place")
        if not sec.get("mixed_content"):
            passed.append("No mixed content detected")
        mob = d.get("mobile_data", {})
        if mob.get("is_mobile_friendly"):
            passed.append("Page is mobile-friendly")
        if mob.get("viewport_set"):
            passed.append("Viewport meta tag is set")
        speed = d.get("speed_data", {})
        mobile_perf = speed.get("mobile", {})
        if mobile_perf.get("performance_score", 0) >= 90:
            passed.append("Excellent mobile performance score")
        return passed

    # ------------------------------------------------------------------
    # Crawl summary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_crawl_summary(d: dict) -> dict[str, Any]:
        pages = d.get("pages", [])
        html_pages = [p for p in pages if p.get("is_html", True)]
        status_2xx = [p for p in pages if 200 <= p.get("status_code", 0) < 300]
        status_3xx = [p for p in pages if 300 <= p.get("status_code", 0) < 400]
        status_4xx = [p for p in pages if 400 <= p.get("status_code", 0) < 500]
        status_5xx = [p for p in pages if p.get("status_code", 0) >= 500]

        avg_word_count = 0
        word_counts = [p.get("word_count", 0) for p in html_pages if p.get("word_count", 0) > 0]
        if word_counts:
            avg_word_count = round(sum(word_counts) / len(word_counts))

        total_internal = sum(len(p.get("internal_links", [])) for p in pages)
        total_external = sum(len(p.get("external_links", [])) for p in pages)
        total_images = sum(len(p.get("images", [])) for p in pages)

        return {
            "total_pages": len(pages),
            "html_pages": len(html_pages),
            "status_2xx": len(status_2xx),
            "status_3xx": len(status_3xx),
            "status_4xx": len(status_4xx),
            "status_5xx": len(status_5xx),
            "avg_word_count": avg_word_count,
            "total_internal_links": total_internal,
            "total_external_links": total_external,
            "total_images": total_images,
        }

    # ------------------------------------------------------------------
    # AI-powered recommendations
    # ------------------------------------------------------------------

    async def generate_recommendations(
        self, audit_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Use the LLM to produce prioritised, actionable recommendations."""
        if self._llm is None:
            return self._fallback_recommendations(audit_data)

        issues_summary = []
        for issue in audit_data.get("issues", [])[:30]:
            issues_summary.append(
                "{sev}: {desc}".format(
                    sev=issue.get("severity", "info").upper(),
                    desc=issue.get("description", ""),
                )
            )

        scores = audit_data.get("category_scores", {})
        prompt = (
            "You are an expert technical SEO consultant. Based on the following "
            "audit results for the domain {domain}, provide exactly 5 to 8 "
            "prioritised recommendations in valid JSON array format.\n\n"
            "Category Scores: {scores}\n"
            "Overall Score: {overall}\n\n"
            "Top Issues:\n{issues}\n\n"
            "Each recommendation JSON object must have these keys:\n"
            '"title", "description", "category", "priority" (P1/P2/P3), '
            '"estimated_impact" (high/medium/low), '
            '"implementation_steps" (list of strings), '
            '"affected_urls" (list of strings, can be empty).\n\n'
            "Return ONLY the JSON array, no markdown fences."
        ).format(
            domain=audit_data.get("domain", ""),
            scores=json.dumps(scores),
            overall=audit_data.get("overall_score", "?"),
            issues="\n".join(issues_summary) if issues_summary else "No critical issues found.",
        )

        try:
            raw = await self._llm.generate_text(
                prompt=prompt,
                system_prompt="You are a technical SEO expert. Return only valid JSON.",
                max_tokens=2000,
                temperature=0.3,
            )
            # Strip potential markdown fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
            recs = json.loads(cleaned)
            if isinstance(recs, list):
                return recs
            logger.warning("LLM returned non-list for recommendations")
        except Exception as exc:
            logger.warning("LLM recommendation generation failed: %s", exc)

        return self._fallback_recommendations(audit_data)

    @staticmethod
    def _fallback_recommendations(audit_data: dict) -> list[dict[str, Any]]:
        """Deterministic recommendations when LLM is unavailable."""
        recs: list[dict[str, Any]] = []
        issues = audit_data.get("issues", [])
        scores = audit_data.get("category_scores", {})

        error_issues = [i for i in issues if i.get("severity") == "error"]
        if error_issues:
            recs.append({
                "title": "Fix Critical Errors",
                "description": "There are {n} critical errors that need immediate attention.".format(
                    n=len(error_issues)
                ),
                "category": "general",
                "priority": "P1",
                "estimated_impact": "high",
                "implementation_steps": [
                    "Review the issues list for all error-severity items",
                    "Prioritise broken links and missing SSL",
                    "Fix each issue and re-audit",
                ],
                "affected_urls": [i.get("affected_url", "") for i in error_issues[:5]],
            })

        if scores.get("performance", 100) < 70:
            recs.append({
                "title": "Improve Page Performance",
                "description": "Performance score is below 70. Focus on Core Web Vitals.",
                "category": "performance",
                "priority": "P1",
                "estimated_impact": "high",
                "implementation_steps": [
                    "Optimise and compress images",
                    "Minify CSS and JavaScript",
                    "Enable browser caching",
                    "Consider a CDN",
                ],
                "affected_urls": [],
            })

        if scores.get("security", 100) < 80:
            recs.append({
                "title": "Strengthen Security",
                "description": "Security score needs improvement.",
                "category": "security",
                "priority": "P2",
                "estimated_impact": "medium",
                "implementation_steps": [
                    "Ensure valid SSL certificate",
                    "Add missing security headers",
                    "Fix mixed content issues",
                ],
                "affected_urls": [],
            })

        if scores.get("content_quality", 100) < 80:
            recs.append({
                "title": "Improve Content Quality",
                "description": "Content quality issues detected.",
                "category": "content_quality",
                "priority": "P2",
                "estimated_impact": "medium",
                "implementation_steps": [
                    "Fix duplicate titles and descriptions",
                    "Expand thin content pages",
                    "Add missing meta tags and alt text",
                ],
                "affected_urls": [],
            })

        if not recs:
            recs.append({
                "title": "Maintain Current Standards",
                "description": "The site is in good technical health. Continue monitoring.",
                "category": "general",
                "priority": "P3",
                "estimated_impact": "low",
                "implementation_steps": [
                    "Schedule regular monthly audits",
                    "Monitor Core Web Vitals",
                    "Keep content fresh and updated",
                ],
                "affected_urls": [],
            })

        return recs

    # ------------------------------------------------------------------
    # Compare two audits
    # ------------------------------------------------------------------

    def compare_audits(
        self, audit1: dict[str, Any], audit2: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two audit snapshots and highlight changes."""
        cat1 = audit1.get("category_scores", {})
        cat2 = audit2.get("category_scores", {})

        all_cats = set(list(cat1.keys()) + list(cat2.keys()))
        changes: dict[str, dict[str, Any]] = {}
        for cat in sorted(all_cats):
            old = cat1.get(cat, 0)
            new = cat2.get(cat, 0)
            diff = round(new - old, 1)
            changes[cat] = {
                "old": old,
                "new": new,
                "diff": diff,
                "direction": "improved" if diff > 0 else ("regressed" if diff < 0 else "unchanged"),
            }

        overall1 = audit1.get("overall_score", 0)
        overall2 = audit2.get("overall_score", 0)

        issues1_count = len(audit1.get("issues", []))
        issues2_count = len(audit2.get("issues", []))

        return {
            "domain": audit2.get("domain", audit1.get("domain", "")),
            "audit1_date": audit1.get("timestamp", ""),
            "audit2_date": audit2.get("timestamp", ""),
            "overall_change": {
                "old": overall1,
                "new": overall2,
                "diff": round(overall2 - overall1, 1),
            },
            "grade_change": {
                "old": audit1.get("grade", "?"),
                "new": audit2.get("grade", "?"),
            },
            "category_changes": changes,
            "issues_change": {
                "old_count": issues1_count,
                "new_count": issues2_count,
                "diff": issues2_count - issues1_count,
            },
        }
    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_audit_report(
        self,
        audit_data: dict[str, Any],
        filepath: str,
        fmt: str = "json",
    ) -> str:
        """Export the audit to *filepath* in JSON, HTML, or PDF format."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        if fmt == "html":
            html = self._render_html_report(audit_data)
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(html)
        elif fmt == "pdf":
            self.export_as_pdf(audit_data, filepath)
        else:
            safe = self._make_serialisable(audit_data)
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(safe, fh, indent=2, default=str)

        logger.info("Audit report exported to %s", filepath)
        return filepath

    @staticmethod
    def _make_serialisable(obj: Any) -> Any:
        """Recursively strip non-serialisable objects."""
        if isinstance(obj, dict):
            return {k: TechnicalAuditor._make_serialisable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [TechnicalAuditor._make_serialisable(i) for i in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        return str(obj)

    @staticmethod
    def _render_html_report(d: dict) -> str:
        """Produce a self-contained, professional HTML audit report."""
        domain = d.get("domain", "Unknown")
        score = d.get("overall_score", 0)
        grade = d.get("grade", "?")
        cat_scores = d.get("category_scores", {})
        issues = d.get("issues", [])
        passed = d.get("passed_checks", [])
        recs = d.get("recommendations", [])
        summary = d.get("crawl_summary", {})
        ts = d.get("timestamp", "")
        speed_data = d.get("speed_data", {})
        elapsed = d.get("elapsed_seconds", 0)

        grade_colors = {
            "A": "#10b981", "B": "#22c55e", "C": "#eab308",
            "D": "#f97316", "F": "#ef4444",
        }
        grade_color = grade_colors.get(grade, "#6b7280")

        error_count = len([i for i in issues if i.get("severity") == "error"])
        warning_count = len([i for i in issues if i.get("severity") == "warning"])
        info_count = len([i for i in issues if i.get("severity") == "info"])

        # --- Category score bars ---
        cat_rows = ""
        for cat, val in cat_scores.items():
            if val >= 80:
                bar_color = "#10b981"
                label_class = "score-good"
            elif val >= 60:
                bar_color = "#eab308"
                label_class = "score-warn"
            else:
                bar_color = "#ef4444"
                label_class = "score-bad"
            cat_label = cat.replace("_", " ").title()
            cat_rows += (
                "<div class=\"cat-row\">\n"
                "  <div class=\"cat-name\">{cat}</div>\n"
                "  <div class=\"cat-bar-track\">\n"
                "    <div class=\"cat-bar-fill\" style=\"width:{val}%;background:{color};\"></div>\n"
                "  </div>\n"
                "  <div class=\"cat-val {cls}\">{val}</div>\n"
                "</div>\n"
            ).format(cat=cat_label, val=val, color=bar_color, cls=label_class)

        # --- Issues table rows ---
        issue_rows = ""
        sev_badge = {
            "error": "<span class=\"badge badge-error\">ERROR</span>",
            "warning": "<span class=\"badge badge-warning\">WARNING</span>",
            "info": "<span class=\"badge badge-info\">INFO</span>",
        }
        for iss in issues:
            sev = iss.get("severity", "info")
            badge = sev_badge.get(sev, sev_badge["info"])
            issue_rows += (
                "<tr>\n"
                "  <td>{badge}</td>\n"
                "  <td>{cat}</td>\n"
                "  <td>{desc}</td>\n"
                "  <td class=\"fix-cell\">{fix}</td>\n"
                "</tr>\n"
            ).format(
                badge=badge,
                cat=iss.get("category", "").replace("_", " ").title(),
                desc=iss.get("description", ""),
                fix=iss.get("how_to_fix", ""),
            )

        # --- Core Web Vitals ---
        cwv_html = ""
        mobile_perf = speed_data.get("mobile", {}) if isinstance(speed_data, dict) else {}
        desktop_perf = speed_data.get("desktop", {}) if isinstance(speed_data, dict) else {}
        if mobile_perf or desktop_perf:
            def _cwv_card(label, value, unit, good_threshold, poor_threshold):
                if value is None:
                    return (
                        "<div class=\"cwv-card\">\n"
                        "  <div class=\"cwv-label\">{label}</div>\n"
                        "  <div class=\"cwv-value cwv-na\">N/A</div>\n"
                        "</div>\n"
                    ).format(label=label)
                if isinstance(value, float) and value < 1:
                    display = "{:.3f}".format(value)
                else:
                    display = str(round(value))
                if value <= good_threshold:
                    cls = "cwv-good"
                elif value <= poor_threshold:
                    cls = "cwv-warn"
                else:
                    cls = "cwv-bad"
                return (
                    "<div class=\"cwv-card\">\n"
                    "  <div class=\"cwv-label\">{label}</div>\n"
                    "  <div class=\"cwv-value {cls}\">{val}{unit}</div>\n"
                    "</div>\n"
                ).format(label=label, cls=cls, val=display, unit=unit)

            lcp = mobile_perf.get("lcp")
            fid = mobile_perf.get("fid")
            cls_val = mobile_perf.get("cls")
            fcp = mobile_perf.get("fcp")
            ttfb = mobile_perf.get("ttfb")
            m_score = mobile_perf.get("performance_score")
            d_score = desktop_perf.get("performance_score")

            perf_score_html = ""
            if m_score is not None or d_score is not None:
                perf_score_html = "<div class=\"perf-scores\">\n"
                if m_score is not None:
                    perf_score_html += (
                        "  <div class=\"perf-score-item\">\n"
                        "    <span class=\"perf-label\">Mobile</span>\n"
                        "    <span class=\"perf-val\">{s}</span>\n"
                        "  </div>\n"
                    ).format(s=m_score)
                if d_score is not None:
                    perf_score_html += (
                        "  <div class=\"perf-score-item\">\n"
                        "    <span class=\"perf-label\">Desktop</span>\n"
                        "    <span class=\"perf-val\">{s}</span>\n"
                        "  </div>\n"
                    ).format(s=d_score)
                perf_score_html += "</div>\n"

            cwv_cards = ""
            cwv_cards += _cwv_card("LCP", lcp, "ms", 2500, 4000)
            cwv_cards += _cwv_card("FID", fid, "ms", 100, 300)
            cwv_cards += _cwv_card("CLS", cls_val, "", 0.1, 0.25)
            cwv_cards += _cwv_card("FCP", fcp, "ms", 1800, 3000)
            cwv_cards += _cwv_card("TTFB", ttfb, "ms", 800, 1800)

            cwv_html = (
                "<div class=\"section\">\n"
                "  <h2>Core Web Vitals</h2>\n"
                "  {perf_scores}\n"
                "  <div class=\"cwv-grid\">\n"
                "    {cards}\n"
                "  </div>\n"
                "</div>\n"
            ).format(perf_scores=perf_score_html, cards=cwv_cards)

        # --- Passed checks ---
        passed_html = ""
        for p in passed:
            passed_html += (
                "<div class=\"passed-item\">\n"
                "  <span class=\"check-icon\">&#10004;</span>\n"
                "  <span>{item}</span>\n"
                "</div>\n"
            ).format(item=p)

        # --- Recommendations ---
        rec_html = ""
        for idx, r in enumerate(recs, 1):
            pri = r.get("priority", "P3")
            pri_cls = "pri-high" if pri in ("P1", "P0") else ("pri-med" if pri == "P2" else "pri-low")
            steps_html = ""
            for s in r.get("implementation_steps", []):
                steps_html += "<li>{s}</li>\n".format(s=s)
            rec_html += (
                "<div class=\"rec-card\">\n"
                "  <div class=\"rec-header\">\n"
                "    <span class=\"rec-num\">{idx}</span>\n"
                "    <span class=\"rec-title\">{title}</span>\n"
                "    <span class=\"badge {pri_cls}\">{pri}</span>\n"
                "  </div>\n"
                "  <p class=\"rec-desc\">{desc}</p>\n"
                "  <div class=\"rec-meta\">\n"
                "    <span><strong>Impact:</strong> {impact}</span>\n"
                "    <span><strong>Category:</strong> {cat}</span>\n"
                "  </div>\n"
                "  <ol class=\"rec-steps\">{steps}</ol>\n"
                "</div>\n"
            ).format(
                idx=idx,
                title=r.get("title", ""),
                pri=pri, pri_cls=pri_cls,
                desc=r.get("description", ""),
                impact=r.get("estimated_impact", "Unknown"),
                cat=r.get("category", "").replace("_", " ").title(),
                steps=steps_html,
            )

        # --- Crawl summary stats ---
        crawl_stats_html = ""
        stat_items = [
            ("Total Pages", summary.get("total_pages", 0)),
            ("HTML Pages", summary.get("html_pages", 0)),
            ("2xx Responses", summary.get("status_2xx", 0)),
            ("3xx Redirects", summary.get("status_3xx", 0)),
            ("4xx Errors", summary.get("status_4xx", 0)),
            ("5xx Errors", summary.get("status_5xx", 0)),
            ("Avg Word Count", summary.get("avg_word_count", 0)),
            ("Internal Links", summary.get("total_internal_links", 0)),
            ("External Links", summary.get("total_external_links", 0)),
            ("Images Found", summary.get("total_images", 0)),
        ]
        for label, val in stat_items:
            crawl_stats_html += (
                "<div class=\"stat-card\">\n"
                "  <div class=\"stat-value\">{val}</div>\n"
                "  <div class=\"stat-label\">{label}</div>\n"
                "</div>\n"
            ).format(val=val, label=label)

        # --- Full HTML ---
        html = (
            "<!DOCTYPE html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            "<title>Technical SEO Audit &mdash; {domain}</title>\n"
            "<style>\n"
            "  :root {{\n"
            "    --navy: #0f172a;\n"
            "    --navy-light: #1e293b;\n"
            "    --blue: #3b82f6;\n"
            "    --blue-light: #dbeafe;\n"
            "    --green: #10b981;\n"
            "    --green-light: #d1fae5;\n"
            "    --yellow: #eab308;\n"
            "    --yellow-light: #fef9c3;\n"
            "    --red: #ef4444;\n"
            "    --red-light: #fee2e2;\n"
            "    --orange: #f97316;\n"
            "    --gray-50: #f8fafc;\n"
            "    --gray-100: #f1f5f9;\n"
            "    --gray-200: #e2e8f0;\n"
            "    --gray-300: #cbd5e1;\n"
            "    --gray-500: #64748b;\n"
            "    --gray-700: #334155;\n"
            "    --gray-900: #0f172a;\n"
            "    --white: #ffffff;\n"
            "    --shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);\n"
            "    --shadow-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.06);\n"
            "    --radius: 12px;\n"
            "  }}\n"
            "  * {{ margin: 0; padding: 0; box-sizing: border-box; }}\n"
            "  body {{\n"
            "    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;\n"
            "    background: var(--gray-50);\n"
            "    color: var(--gray-900);\n"
            "    line-height: 1.6;\n"
            "    -webkit-print-color-adjust: exact;\n"
            "    print-color-adjust: exact;\n"
            "  }}\n"
            "  .container {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}\n"
            "  \n"
            "  /* Header */\n"
            "  .header {{\n"
            "    background: linear-gradient(135deg, var(--navy) 0%, var(--navy-light) 100%);\n"
            "    color: var(--white);\n"
            "    padding: 48px 0 40px;\n"
            "  }}\n"
            "  .header-inner {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; }}\n"
            "  .brand {{ font-size: 13px; text-transform: uppercase; letter-spacing: 3px; opacity: 0.7; margin-bottom: 8px; }}\n"
            "  .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}\n"
            "  .header-meta {{ font-size: 14px; opacity: 0.8; }}\n"
            "  .header-badge {{\n"
            "    text-align: center;\n"
            "    background: rgba(255,255,255,0.1);\n"
            "    border-radius: var(--radius);\n"
            "    padding: 20px 32px;\n"
            "    backdrop-filter: blur(10px);\n"
            "  }}\n"
            "  .header-badge .grade {{\n"
            "    font-size: 56px; font-weight: 800; line-height: 1;\n"
            "  }}\n"
            "  .header-badge .grade-label {{ font-size: 13px; opacity: 0.8; margin-top: 4px; }}\n"
            "  \n"
            "  /* Sections */\n"
            "  .section {{ margin: 32px 0; }}\n"
            "  .section h2 {{\n"
            "    font-size: 20px; font-weight: 700; color: var(--navy);\n"
            "    border-bottom: 2px solid var(--gray-200); padding-bottom: 8px; margin-bottom: 20px;\n"
            "  }}\n"
            "  \n"
            "  /* Executive Summary Cards */\n"
            "  .summary-grid {{\n"
            "    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 32px 0;\n"
            "  }}\n"
            "  .summary-card {{\n"
            "    background: var(--white); border-radius: var(--radius); padding: 24px;\n"
            "    text-align: center; box-shadow: var(--shadow); border: 1px solid var(--gray-200);\n"
            "  }}\n"
            "  .summary-card .big-num {{ font-size: 36px; font-weight: 800; line-height: 1.2; }}\n"
            "  .summary-card .card-label {{ font-size: 13px; color: var(--gray-500); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}\n"
            "  \n"
            "  /* Category scores */\n"
            "  .cat-row {{ display: flex; align-items: center; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--gray-100); }}\n"
            "  .cat-name {{ width: 160px; font-weight: 600; font-size: 14px; }}\n"
            "  .cat-bar-track {{ flex: 1; height: 24px; background: var(--gray-100); border-radius: 12px; overflow: hidden; }}\n"
            "  .cat-bar-fill {{ height: 100%; border-radius: 12px; transition: width 0.3s; min-width: 4px; }}\n"
            "  .cat-val {{ width: 48px; text-align: right; font-weight: 700; font-size: 15px; }}\n"
            "  .score-good {{ color: var(--green); }}\n"
            "  .score-warn {{ color: var(--yellow); }}\n"
            "  .score-bad {{ color: var(--red); }}\n"
            "  \n"
            "  /* CWV */\n"
            "  .cwv-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }}\n"
            "  .cwv-card {{\n"
            "    background: var(--white); border-radius: var(--radius); padding: 20px;\n"
            "    text-align: center; box-shadow: var(--shadow); border: 1px solid var(--gray-200);\n"
            "  }}\n"
            "  .cwv-label {{ font-size: 12px; font-weight: 700; color: var(--gray-500); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}\n"
            "  .cwv-value {{ font-size: 24px; font-weight: 800; }}\n"
            "  .cwv-good {{ color: var(--green); }}\n"
            "  .cwv-warn {{ color: var(--yellow); }}\n"
            "  .cwv-bad {{ color: var(--red); }}\n"
            "  .cwv-na {{ color: var(--gray-300); }}\n"
            "  .perf-scores {{ display: flex; gap: 24px; margin-bottom: 16px; }}\n"
            "  .perf-score-item {{ display: flex; align-items: center; gap: 8px; }}\n"
            "  .perf-label {{ font-size: 13px; color: var(--gray-500); font-weight: 600; }}\n"
            "  .perf-val {{ font-size: 18px; font-weight: 800; color: var(--navy); }}\n"
            "  \n"
            "  /* Issues table */\n"
            "  .issues-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}\n"
            "  .issues-table th {{\n"
            "    background: var(--navy); color: var(--white); padding: 12px 16px;\n"
            "    text-align: left; font-weight: 600; font-size: 13px;\n"
            "    text-transform: uppercase; letter-spacing: 0.5px;\n"
            "  }}\n"
            "  .issues-table th:first-child {{ border-radius: 8px 0 0 0; }}\n"
            "  .issues-table th:last-child {{ border-radius: 0 8px 0 0; }}\n"
            "  .issues-table td {{ padding: 10px 16px; border-bottom: 1px solid var(--gray-100); vertical-align: top; }}\n"
            "  .issues-table tr:nth-child(even) {{ background: var(--gray-50); }}\n"
            "  .issues-table tr:hover {{ background: var(--blue-light); }}\n"
            "  .fix-cell {{ font-size: 13px; color: var(--gray-700); }}\n"
            "  \n"
            "  /* Badges */\n"
            "  .badge {{\n"
            "    display: inline-block; padding: 3px 10px; border-radius: 20px;\n"
            "    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;\n"
            "  }}\n"
            "  .badge-error {{ background: var(--red-light); color: var(--red); }}\n"
            "  .badge-warning {{ background: var(--yellow-light); color: #92400e; }}\n"
            "  .badge-info {{ background: var(--blue-light); color: var(--blue); }}\n"
            "  .pri-high {{ background: var(--red-light); color: var(--red); }}\n"
            "  .pri-med {{ background: var(--yellow-light); color: #92400e; }}\n"
            "  .pri-low {{ background: var(--green-light); color: #065f46; }}\n"
            "  \n"
            "  /* Passed checks */\n"
            "  .passed-item {{\n"
            "    display: flex; align-items: center; gap: 10px;\n"
            "    padding: 8px 16px; margin-bottom: 4px;\n"
            "    background: var(--white); border-radius: 8px; border: 1px solid var(--gray-100);\n"
            "  }}\n"
            "  .check-icon {{ color: var(--green); font-size: 18px; font-weight: bold; }}\n"
            "  \n"
            "  /* Recommendations */\n"
            "  .rec-card {{\n"
            "    background: var(--white); border-radius: var(--radius); padding: 24px;\n"
            "    margin-bottom: 16px; box-shadow: var(--shadow); border: 1px solid var(--gray-200);\n"
            "  }}\n"
            "  .rec-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}\n"
            "  .rec-num {{\n"
            "    background: var(--navy); color: var(--white); width: 32px; height: 32px;\n"
            "    border-radius: 50%; display: flex; align-items: center; justify-content: center;\n"
            "    font-weight: 700; font-size: 14px; flex-shrink: 0;\n"
            "  }}\n"
            "  .rec-title {{ font-weight: 700; font-size: 16px; flex: 1; }}\n"
            "  .rec-desc {{ color: var(--gray-700); margin-bottom: 12px; font-size: 14px; }}\n"
            "  .rec-meta {{ display: flex; gap: 24px; font-size: 13px; color: var(--gray-500); margin-bottom: 12px; }}\n"
            "  .rec-steps {{ padding-left: 20px; font-size: 14px; color: var(--gray-700); }}\n"
            "  .rec-steps li {{ margin-bottom: 4px; }}\n"
            "  \n"
            "  /* Crawl stats */\n"
            "  .stats-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }}\n"
            "  .stat-card {{\n"
            "    background: var(--white); border-radius: var(--radius); padding: 20px;\n"
            "    text-align: center; box-shadow: var(--shadow); border: 1px solid var(--gray-200);\n"
            "  }}\n"
            "  .stat-value {{ font-size: 24px; font-weight: 800; color: var(--navy); }}\n"
            "  .stat-label {{ font-size: 12px; color: var(--gray-500); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}\n"
            "  \n"
            "  /* Footer */\n"
            "  .footer {{\n"
            "    margin-top: 48px; padding: 24px 0; border-top: 2px solid var(--gray-200);\n"
            "    text-align: center; font-size: 13px; color: var(--gray-500);\n"
            "  }}\n"
            "  .footer strong {{ color: var(--navy); }}\n"
            "  \n"
            "  /* Print */\n"
            "  @media print {{\n"
            "    body {{ background: white; }}\n"
            "    .container {{ max-width: 100%; padding: 0; }}\n"
            "    .section {{ page-break-inside: avoid; }}\n"
            "    .rec-card {{ page-break-inside: avoid; }}\n"
            "    .summary-grid {{ page-break-inside: avoid; }}\n"
            "    .header {{ page-break-after: avoid; }}\n"
            "    h2 {{ page-break-after: avoid; }}\n"
            "    .issues-table {{ font-size: 12px; }}\n"
            "    .issues-table tr {{ page-break-inside: avoid; }}\n"
            "  }}\n"
            "  @page {{ margin: 1.5cm; size: A4; }}\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            "\n"
            "<!-- Header -->\n"
            "<div class=\"header\">\n"
            "  <div class=\"container\">\n"
            "    <div class=\"header-inner\">\n"
            "      <div>\n"
            "        <div class=\"brand\">Technical SEO Audit</div>\n"
            "        <h1>{domain}</h1>\n"
            "        <div class=\"header-meta\">Generated on {ts} &bull; Completed in {elapsed}s</div>\n"
            "      </div>\n"
            "      <div class=\"header-badge\">\n"
            "        <div class=\"grade\" style=\"color:{gc};\">{grade}</div>\n"
            "        <div class=\"grade-label\">Overall Grade</div>\n"
            "      </div>\n"
            "    </div>\n"
            "  </div>\n"
            "</div>\n"
            "\n"
            "<div class=\"container\">\n"
            "\n"
            "<!-- Executive Summary -->\n"
            "<div class=\"summary-grid\">\n"
            "  <div class=\"summary-card\">\n"
            "    <div class=\"big-num\" style=\"color:{gc};\">{score}</div>\n"
            "    <div class=\"card-label\">Overall Score</div>\n"
            "  </div>\n"
            "  <div class=\"summary-card\">\n"
            "    <div class=\"big-num\" style=\"color:var(--red);\">{errors}</div>\n"
            "    <div class=\"card-label\">Errors</div>\n"
            "  </div>\n"
            "  <div class=\"summary-card\">\n"
            "    <div class=\"big-num\" style=\"color:var(--orange);\">{warnings}</div>\n"
            "    <div class=\"card-label\">Warnings</div>\n"
            "  </div>\n"
            "  <div class=\"summary-card\">\n"
            "    <div class=\"big-num\">{npages}</div>\n"
            "    <div class=\"card-label\">Pages Crawled</div>\n"
            "  </div>\n"
            "</div>\n"
            "\n"
            "<!-- Category Scores -->\n"
            "<div class=\"section\">\n"
            "  <h2>Category Scores</h2>\n"
            "  {cat_rows}\n"
            "</div>\n"
            "\n"
            "<!-- Core Web Vitals -->\n"
            "{cwv_html}\n"
            "\n"
            "<!-- Issues -->\n"
            "<div class=\"section\">\n"
            "  <h2>Issues ({ni})</h2>\n"
            "  <div style=\"margin-bottom:12px;\">\n"
            "    <span class=\"badge badge-error\">{errors} Errors</span>&nbsp;\n"
            "    <span class=\"badge badge-warning\">{warnings} Warnings</span>&nbsp;\n"
            "    <span class=\"badge badge-info\">{infos} Info</span>\n"
            "  </div>\n"
            "  <table class=\"issues-table\">\n"
            "    <thead><tr><th>Severity</th><th>Category</th><th>Description</th><th>How to Fix</th></tr></thead>\n"
            "    <tbody>{issue_rows}</tbody>\n"
            "  </table>\n"
            "</div>\n"
            "\n"
            "<!-- Passed Checks -->\n"
            "<div class=\"section\">\n"
            "  <h2>Passed Checks ({np})</h2>\n"
            "  {passed_html}\n"
            "</div>\n"
            "\n"
            "<!-- Recommendations -->\n"
            "<div class=\"section\">\n"
            "  <h2>Prioritized Recommendations</h2>\n"
            "  {rec_html}\n"
            "</div>\n"
            "\n"
            "<!-- Crawl Summary -->\n"
            "<div class=\"section\">\n"
            "  <h2>Crawl Summary</h2>\n"
            "  <div class=\"stats-grid\">\n"
            "    {crawl_stats}\n"
            "  </div>\n"
            "</div>\n"
            "\n"
            "<!-- Footer -->\n"
            "<div class=\"footer\">\n"
            "  <p><strong>Technical SEO Audit Report</strong> &mdash; {domain}</p>\n"
            "  <p>Generated on {ts} &bull; Powered by Full SEO Automation</p>\n"
            "</div>\n"
            "\n"
            "</div><!-- /container -->\n"
            "</body>\n"
            "</html>\n"
        ).format(
            domain=domain,
            ts=ts,
            elapsed=elapsed,
            gc=grade_color,
            grade=grade,
            score=score,
            errors=error_count,
            warnings=warning_count,
            infos=info_count,
            npages=summary.get("total_pages", 0),
            cat_rows=cat_rows,
            cwv_html=cwv_html,
            ni=len(issues),
            issue_rows=issue_rows,
            passed_html=passed_html,
            rec_html=rec_html,
            crawl_stats=crawl_stats_html,
            **{"np": len(passed)}
        )
        return html

    @staticmethod
    def export_as_pdf(audit_data: dict, filepath: str) -> str:
        """Convert the HTML audit report to PDF using weasyprint."""
        try:
            from weasyprint import HTML as WeasyprintHTML
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF export. "
                "Install it with: pip install weasyprint"
            )

        html_content = TechnicalAuditor._render_html_report(audit_data)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        WeasyprintHTML(string=html_content).write_pdf(filepath)
        logger.info("PDF report exported to %s", filepath)
        return filepath


    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _persist_audit(audit_data: dict) -> None:
        """Save audit summary to the database."""
        try:
            from src.database import get_session
            from src.models.audit import SiteAudit

            with get_session() as session:
                record = SiteAudit(
                    domain=audit_data.get("domain", ""),
                    audit_type="full",
                    overall_score=audit_data.get("overall_score"),
                    issues_json={
                        "issues_count": len(audit_data.get("issues", [])),
                        "category_scores": audit_data.get("category_scores", {}),
                        "grade": audit_data.get("grade", ""),
                    },
                )
                session.add(record)
                logger.info("Audit persisted to database for %s", audit_data.get("domain"))
        except Exception as exc:
            logger.warning("Failed to persist audit to DB: %s", exc)
