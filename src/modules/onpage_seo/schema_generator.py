"""Schema Markup Generator — produces valid JSON-LD structured data.

Supports Article, LocalBusiness, FAQ, HowTo, BreadcrumbList, Product,
Organization, and Review schema types with validation and auto-detection.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required-field registry used by validate_schema()
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "Article": ["headline", "author", "datePublished"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "NewsArticle": ["headline", "author", "datePublished"],
    "LocalBusiness": ["name", "address"],
    "FAQPage": ["mainEntity"],
    "HowTo": ["name", "step"],
    "BreadcrumbList": ["itemListElement"],
    "Product": ["name"],
    "Organization": ["name", "url"],
    "Review": ["itemReviewed", "reviewRating", "author"],
}

_RECOMMENDED_FIELDS: dict[str, list[str]] = {
    "Article": ["image", "dateModified", "publisher", "description"],
    "BlogPosting": ["image", "dateModified", "publisher", "description"],
    "LocalBusiness": ["telephone", "openingHoursSpecification", "geo", "url"],
    "FAQPage": [],
    "HowTo": ["description", "totalTime", "tool", "supply"],
    "BreadcrumbList": [],
    "Product": ["description", "image", "offers", "brand", "aggregateRating"],
    "Organization": ["logo", "sameAs", "contactPoint"],
}


class SchemaGenerator:
    """Generate and validate JSON-LD structured data for SEO.

    Usage::

        gen = SchemaGenerator()
        faq = gen.generate_faq_schema([
            {"question": "What is SEO?", "answer": "Search Engine Optimization."},
        ])
        validation = gen.validate_schema(faq)
    """

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Article / BlogPosting
    # ------------------------------------------------------------------

    def generate_article_schema(
        self,
        title: str,
        author: str,
        date_published: str,
        date_modified: str = "",
        description: str = "",
        image_url: str = "",
        publisher_name: str = "",
        publisher_logo: str = "",
        url: str = "",
        word_count: int = 0,
    ) -> dict:
        """Generate Article / BlogPosting JSON-LD."""
        schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title[:110],
            "author": {
                "@type": "Person",
                "name": author,
            },
            "datePublished": self._normalise_date(date_published),
        }
        if date_modified:
            schema["dateModified"] = self._normalise_date(date_modified)
        if description:
            schema["description"] = description[:300]
        if image_url:
            schema["image"] = image_url
        if url:
            schema["mainEntityOfPage"] = {"@type": "WebPage", "@id": url}
        if word_count > 0:
            schema["wordCount"] = word_count
        if publisher_name:
            publisher: dict[str, Any] = {
                "@type": "Organization",
                "name": publisher_name,
            }
            if publisher_logo:
                publisher["logo"] = {
                    "@type": "ImageObject",
                    "url": publisher_logo,
                }
            schema["publisher"] = publisher
        logger.debug("Generated Article schema for: %s", title)
        return schema

    # ------------------------------------------------------------------
    # LocalBusiness
    # ------------------------------------------------------------------

    def generate_local_business_schema(
        self,
        name: str,
        address: dict | str = "",
        phone: str = "",
        hours: list[dict] | None = None,
        geo_lat: float | None = None,
        geo_lng: float | None = None,
        category: str = "LocalBusiness",
        url: str = "",
        rating: float | None = None,
        review_count: int | None = None,
        price_range: str = "",
        image: str = "",
    ) -> dict:
        """Generate LocalBusiness JSON-LD."""
        biz_type = category if category else "LocalBusiness"
        schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": biz_type,
            "name": name,
        }

        # Address
        if isinstance(address, dict):
            schema["address"] = {"@type": "PostalAddress", **address}
        elif isinstance(address, str) and address:
            schema["address"] = {
                "@type": "PostalAddress",
                "streetAddress": address,
            }

        if phone:
            schema["telephone"] = phone
        if url:
            schema["url"] = url
        if image:
            schema["image"] = image
        if price_range:
            schema["priceRange"] = price_range

        # Geo coordinates
        if geo_lat is not None and geo_lng is not None:
            schema["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": geo_lat,
                "longitude": geo_lng,
            }

        # Opening hours
        if hours:
            specs = []
            for entry in hours:
                spec: dict[str, Any] = {
                    "@type": "OpeningHoursSpecification",
                }
                if "dayOfWeek" in entry:
                    spec["dayOfWeek"] = entry["dayOfWeek"]
                if "opens" in entry:
                    spec["opens"] = entry["opens"]
                if "closes" in entry:
                    spec["closes"] = entry["closes"]
                specs.append(spec)
            schema["openingHoursSpecification"] = specs

        # Aggregate rating
        if rating is not None and review_count is not None:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": str(rating),
                "reviewCount": str(review_count),
            }

        logger.debug("Generated LocalBusiness schema for: %s", name)
        return schema

    # ------------------------------------------------------------------
    # FAQPage
    # ------------------------------------------------------------------

    def generate_faq_schema(self, questions: list[dict]) -> dict:
        """Generate FAQPage JSON-LD from list of {question, answer} dicts."""
        entities = []
        for qa in questions:
            q = qa.get("question", "").strip()
            a = qa.get("answer", "").strip()
            if not q or not a:
                continue
            entities.append({
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": a,
                },
            })

        schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": entities,
        }
        logger.debug("Generated FAQ schema with %d questions", len(entities))
        return schema

    # ------------------------------------------------------------------
    # HowTo
    # ------------------------------------------------------------------

    def generate_howto_schema(
        self,
        name: str,
        description: str = "",
        steps: list[dict] | None = None,
        total_time: str = "",
        tools: list[str] | None = None,
        supplies: list[str] | None = None,
        image: str = "",
    ) -> dict:
        """Generate HowTo JSON-LD."""
        schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": name,
        }
        if description:
            schema["description"] = description
        if image:
            schema["image"] = image
        if total_time:
            schema["totalTime"] = total_time  # ISO 8601 duration e.g. PT30M

        if tools:
            schema["tool"] = [
                {"@type": "HowToTool", "name": t} for t in tools
            ]
        if supplies:
            schema["supply"] = [
                {"@type": "HowToSupply", "name": s} for s in supplies
            ]

        step_list = []
        for idx, step in enumerate(steps or [], start=1):
            s: dict[str, Any] = {
                "@type": "HowToStep",
                "position": idx,
            }
            if "name" in step:
                s["name"] = step["name"]
            if "text" in step:
                s["text"] = step["text"]
            if "image" in step:
                s["image"] = step["image"]
            if "url" in step:
                s["url"] = step["url"]
            step_list.append(s)
        schema["step"] = step_list

        logger.debug("Generated HowTo schema: %s (%d steps)", name, len(step_list))
        return schema

    # ------------------------------------------------------------------
    # BreadcrumbList
    # ------------------------------------------------------------------

    def generate_breadcrumb_schema(self, breadcrumbs: list[dict]) -> dict:
        """Generate BreadcrumbList JSON-LD from [{name, url}] list."""
        items = []
        for idx, crumb in enumerate(breadcrumbs, start=1):
            items.append({
                "@type": "ListItem",
                "position": idx,
                "name": crumb.get("name", ""),
                "item": crumb.get("url", ""),
            })

        schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items,
        }
        logger.debug("Generated BreadcrumbList schema with %d items", len(items))
        return schema

    # ------------------------------------------------------------------
    # Product
    # ------------------------------------------------------------------

    def generate_product_schema(
        self,
        name: str,
        description: str = "",
        image: str = "",
        price: float | str = "",
        currency: str = "USD",
        availability: str = "InStock",
        brand: str = "",
        rating: float | None = None,
        review_count: int | None = None,
        sku: str = "",
        url: str = "",
    ) -> dict:
        """Generate Product JSON-LD."""
        schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
        }
        if description:
            schema["description"] = description
        if image:
            schema["image"] = image
        if sku:
            schema["sku"] = sku
        if url:
            schema["url"] = url
        if brand:
            schema["brand"] = {"@type": "Brand", "name": brand}

        # Offer
        if price:
            avail_base = "https://schema.org/"
            if not str(availability).startswith("http"):
                availability_url = avail_base + str(availability)
            else:
                availability_url = str(availability)
            schema["offers"] = {
                "@type": "Offer",
                "price": str(price),
                "priceCurrency": currency,
                "availability": availability_url,
            }

        # Aggregate rating
        if rating is not None and review_count is not None:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": str(rating),
                "reviewCount": str(review_count),
            }

        logger.debug("Generated Product schema for: %s", name)
        return schema

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    def generate_organization_schema(
        self,
        name: str,
        url: str = "",
        logo: str = "",
        social_profiles: list[str] | None = None,
        contact_phone: str = "",
        contact_email: str = "",
        contact_type: str = "customer service",
        description: str = "",
        founding_date: str = "",
    ) -> dict:
        """Generate Organization JSON-LD."""
        schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": name,
        }
        if url:
            schema["url"] = url
        if logo:
            schema["logo"] = logo
        if description:
            schema["description"] = description
        if founding_date:
            schema["foundingDate"] = founding_date
        if social_profiles:
            schema["sameAs"] = social_profiles

        if contact_phone or contact_email:
            contact: dict[str, Any] = {
                "@type": "ContactPoint",
                "contactType": contact_type,
            }
            if contact_phone:
                contact["telephone"] = contact_phone
            if contact_email:
                contact["email"] = contact_email
            schema["contactPoint"] = contact

        logger.debug("Generated Organization schema for: %s", name)
        return schema

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_schema(self, schema: dict) -> dict:
        """Validate a JSON-LD schema dict for required fields and types.

        Returns dict with ``is_valid``, ``errors``, ``warnings``, and
        ``schema_type``.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Basic structure checks
        if not isinstance(schema, dict):
            return {
                "is_valid": False,
                "errors": ["Schema must be a dict"],
                "warnings": [],
                "schema_type": None,
            }

        if schema.get("@context") != "https://schema.org":
            errors.append("Missing or incorrect @context (expected https://schema.org)")

        schema_type = schema.get("@type", "")
        if not schema_type:
            errors.append("Missing @type field")
            return {
                "is_valid": False,
                "errors": errors,
                "warnings": warnings,
                "schema_type": None,
            }

        # Check required fields
        required = _REQUIRED_FIELDS.get(schema_type, [])
        for fld in required:
            if fld not in schema:
                errors.append("Missing required field: " + fld)
            elif not schema[fld]:
                errors.append("Empty required field: " + fld)

        # Check recommended fields
        recommended = _RECOMMENDED_FIELDS.get(schema_type, [])
        for fld in recommended:
            if fld not in schema:
                warnings.append("Missing recommended field: " + fld)

        # Type-specific validations
        if schema_type in ("Article", "BlogPosting", "NewsArticle"):
            headline = schema.get("headline", "")
            if len(headline) > 110:
                warnings.append(
                    "Headline exceeds 110 characters (Google may truncate)"
                )
            dp = schema.get("datePublished", "")
            if dp and not self._is_valid_date(dp):
                errors.append("datePublished is not a valid ISO 8601 date")

        if schema_type == "FAQPage":
            entities = schema.get("mainEntity", [])
            if not isinstance(entities, list) or len(entities) == 0:
                errors.append("FAQPage must contain at least one Question")
            for i, entity in enumerate(entities):
                if entity.get("@type") != "Question":
                    err_msg = "mainEntity[" + str(i) + "] must have @type Question"
                    errors.append(err_msg)

        if schema_type == "HowTo":
            steps = schema.get("step", [])
            if not isinstance(steps, list) or len(steps) == 0:
                errors.append("HowTo must contain at least one step")

        if schema_type == "BreadcrumbList":
            items = schema.get("itemListElement", [])
            if not isinstance(items, list) or len(items) == 0:
                errors.append("BreadcrumbList must have at least one item")

        if schema_type == "Product":
            offers = schema.get("offers")
            if offers and isinstance(offers, dict):
                if "price" not in offers:
                    warnings.append("Product offer missing price")
                if "priceCurrency" not in offers:
                    warnings.append("Product offer missing priceCurrency")

        # Verify JSON serialisability
        try:
            json.dumps(schema)
        except (TypeError, ValueError) as exc:
            errors.append("Schema is not JSON serialisable: " + str(exc))

        is_valid = len(errors) == 0
        logger.debug(
            "Schema validation for %s: valid=%s, errors=%d, warnings=%d",
            schema_type, is_valid, len(errors), len(warnings),
        )
        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "schema_type": schema_type,
        }

    # ------------------------------------------------------------------
    # Page-type detection (AI-powered when LLM available)
    # ------------------------------------------------------------------

    async def detect_page_type(self, url: str, content: str) -> str:
        """Detect the best schema type for a page based on its content.

        Returns one of: Article, LocalBusiness, FAQPage, HowTo, Product,
        BreadcrumbList, Organization.
        """
        # Heuristic detection (fast, no API call)
        detected = self._heuristic_detect(url, content)

        # Refine with LLM when available
        if self._llm and detected == "Article":
            try:
                prompt = (
                    "Analyze the following webpage content snippet and determine "
                    "the single BEST schema.org type from this list: "
                    "Article, LocalBusiness, FAQPage, HowTo, Product, Organization.\n\n"
                    "URL: " + url + "\n\n"
                    "Content (first 1500 chars):\n" + content[:1500] + "\n\n"
                    "Respond with ONLY the schema type name, nothing else."
                )
                result = await self._llm.generate_text(
                    prompt,
                    system_prompt="You are a structured-data expert. Return only the schema type.",
                    max_tokens=20,
                    temperature=0.0,
                )
                cleaned = result.strip().split("\n")[0].strip()
                valid_types = {
                    "Article", "LocalBusiness", "FAQPage",
                    "HowTo", "Product", "Organization",
                }
                if cleaned in valid_types:
                    detected = cleaned
            except Exception as exc:
                logger.warning("LLM page-type detection failed: %s", exc)

        logger.info("Detected page type for %s: %s", url, detected)
        return detected

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _heuristic_detect(self, url: str, content: str) -> str:
        """Rule-based page type detection using content signals."""
        lower = content.lower()
        url_lower = url.lower()

        # FAQ signals
        faq_signals = lower.count("?") > 5
        faq_keywords = any(
            kw in lower
            for kw in ["faq", "frequently asked", "common questions"]
        )
        if faq_signals and faq_keywords:
            return "FAQPage"

        # HowTo signals
        howto_keywords = any(
            kw in lower
            for kw in ["how to", "step 1", "step-by-step", "instructions", "tutorial"]
        )
        step_pattern = len(re.findall(r"step\s*\d", lower))
        if howto_keywords and step_pattern >= 2:
            return "HowTo"

        # Product signals
        product_keywords = any(
            kw in lower
            for kw in ["add to cart", "buy now", "price", "$", "in stock", "out of stock"]
        )
        if product_keywords and any(
            kw in url_lower for kw in ["/product", "/shop", "/item"]
        ):
            return "Product"

        # LocalBusiness signals
        local_keywords = any(
            kw in lower
            for kw in [
                "our location", "visit us", "opening hours",
                "business hours", "our address", "get directions",
            ]
        )
        phone_pattern = bool(re.search(r"\(\d{3}\)\s*\d{3}[-.\s]\d{4}", content))
        if local_keywords or phone_pattern:
            return "LocalBusiness"

        # Organization signals
        if any(kw in url_lower for kw in ["/about", "/company", "/team"]):
            return "Organization"

        # Default to Article
        return "Article"

    @staticmethod
    def _normalise_date(date_str: str) -> str:
        """Try to normalise a date string to ISO 8601."""
        if not date_str:
            return ""
        # Already ISO-like
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return date_str
        # Try common formats
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    @staticmethod
    def _is_valid_date(date_str: str) -> bool:
        """Check if a string is a valid ISO 8601 date."""
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return True
        try:
            datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return True
        except (ValueError, AttributeError):
            return False
