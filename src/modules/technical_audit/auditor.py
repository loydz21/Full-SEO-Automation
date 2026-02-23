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
        """Export the audit to *filepath* in JSON or HTML format."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        if fmt == "html":
            html = self._render_html_report(audit_data)
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(html)
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
        """Produce a self-contained HTML audit report."""
        domain = d.get("domain", "Unknown")
        score = d.get("overall_score", 0)
        grade = d.get("grade", "?")
        cat_scores = d.get("category_scores", {})
        issues = d.get("issues", [])
        passed = d.get("passed_checks", [])
        recs = d.get("recommendations", [])
        summary = d.get("crawl_summary", {})
        ts = d.get("timestamp", "")

        grade_color = {
            "A": "#22c55e", "B": "#84cc16", "C": "#eab308",
            "D": "#f97316", "F": "#ef4444",
        }.get(grade, "#6b7280")

        # Build category rows
        cat_rows = ""
        for cat, val in cat_scores.items():
            bar_color = "#22c55e" if val >= 80 else ("#eab308" if val >= 60 else "#ef4444")
            cat_rows += (
                "<tr>"
                "<td style=\"padding:8px;text-transform:capitalize;\">{cat}</td>"
                "<td style=\"padding:8px;\"><div style=\"background:#e5e7eb;border-radius:6px;overflow:hidden;\">"
                "<div style=\"width:{val}%;background:{color};height:22px;border-radius:6px;\"></div></div></td>"
                "<td style=\"padding:8px;font-weight:bold;\">{val}</td>"
                "</tr>"
            ).format(cat=cat.replace("_", " "), val=val, color=bar_color)

        # Build issues rows
        issue_rows = ""
        sev_colors = {"error": "#ef4444", "warning": "#f97316", "info": "#3b82f6"}
        for iss in issues:
            sev = iss.get("severity", "info")
            sc = sev_colors.get(sev, "#6b7280")
            issue_rows += (
                "<tr>"
                "<td style=\"padding:6px;\"><span style=\"color:{sc};font-weight:bold;\">{sev}</span></td>"
                "<td style=\"padding:6px;\">{cat}</td>"
                "<td style=\"padding:6px;\">{desc}</td>"
                "<td style=\"padding:6px;\">{fix}</td>"
                "</tr>"
            ).format(
                sc=sc, sev=sev.upper(),
                cat=iss.get("category", ""),
                desc=iss.get("description", ""),
                fix=iss.get("how_to_fix", ""),
            )

        # Build passed items
        passed_items = ""
        for p in passed:
            passed_items += "<li style=\"padding:4px 0;color:#22c55e;\">{item}</li>".format(item=p)

        # Build recommendations
        rec_items = ""
        for r in recs:
            steps = ""
            for s in r.get("implementation_steps", []):
                steps += "<li>{s}</li>".format(s=s)
            rec_items += (
                "<div style=\"border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;\">" 
                "<h3 style=\"margin:0 0 8px;\">[{pri}] {title}</h3>"
                "<p>{desc}</p>"
                "<p><strong>Impact:</strong> {impact} | <strong>Category:</strong> {cat}</p>"
                "<ol>{steps}</ol>"
                "</div>"
            ).format(
                pri=r.get("priority", "P3"),
                title=r.get("title", ""),
                desc=r.get("description", ""),
                impact=r.get("estimated_impact", "?"),
                cat=r.get("category", ""),
                steps=steps,
            )

        html = (
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">"
            "<title>SEO Audit — {domain}</title>"
            "<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:0 auto;padding:20px;"
            "background:#f8fafc;color:#1e293b;}}table{{width:100%;border-collapse:collapse;}}"
            "th{{text-align:left;padding:8px;border-bottom:2px solid #e2e8f0;}}"
            "tr:nth-child(even){{background:#f1f5f9;}}</style></head><body>"
            "<h1>Technical SEO Audit Report</h1>"
            "<p><strong>Domain:</strong> {domain} | <strong>Date:</strong> {ts}</p>"
            "<div style=\"display:flex;gap:20px;margin:20px 0;\">"
            "<div style=\"background:white;padding:24px;border-radius:12px;text-align:center;"
            "border:1px solid #e2e8f0;flex:1;\">"
            "<div style=\"font-size:3rem;font-weight:bold;color:{gc};\">{grade}</div>"
            "<div>Overall Grade</div></div>"
            "<div style=\"background:white;padding:24px;border-radius:12px;text-align:center;"
            "border:1px solid #e2e8f0;flex:1;\">"
            "<div style=\"font-size:3rem;font-weight:bold;\">{score}</div>"
            "<div>Overall Score</div></div>"
            "<div style=\"background:white;padding:24px;border-radius:12px;text-align:center;"
            "border:1px solid #e2e8f0;flex:1;\">"
            "<div style=\"font-size:3rem;font-weight:bold;\">{npages}</div>"
            "<div>Pages Crawled</div></div></div>"
            "<h2>Category Scores</h2>"
            "<table>{cat_rows}</table>"
            "<h2>Issues ({ni})</h2>"
            "<table><tr><th>Severity</th><th>Category</th><th>Description</th><th>Fix</th></tr>"
            "{issue_rows}</table>"
            "<h2>Passed Checks</h2><ul>{passed_items}</ul>"
            "<h2>Recommendations</h2>{rec_items}"
            "</body></html>"
        ).format(
            domain=domain, ts=ts, gc=grade_color, grade=grade,
            score=score, npages=summary.get("total_pages", 0),
            cat_rows=cat_rows, ni=len(issues),
            issue_rows=issue_rows, passed_items=passed_items,
            rec_items=rec_items,
        )
        return html

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
