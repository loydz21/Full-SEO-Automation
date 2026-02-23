"""Outreach management for link building campaigns.

Handles AI-powered email generation, sequence management,
outreach tracking, template CRUD, and CSV export.
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.database import get_session
from src.integrations.llm_client import LLMClient
from src.models.backlink import (
    EmailTemplate,
    OutreachCampaign,
    OutreachEmail,
    OutreachProspect,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Default email templates
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Guest Post Pitch",
        "template_type": "guest_post",
        "subject": "Guest Post Idea for {site_name}",
        "body": (
            "Hi {contact_name},\n\n"
            "I came across {site_name} and really enjoyed your content on {topic}. "
            "I have an idea for a guest post that I think would be a great fit for your audience:\n\n"
            "{pitch_summary}\n\n"
            "I have published on sites like {credentials} and would love to contribute "
            "high-quality content to your site.\n\n"
            "Would you be open to this?\n\n"
            "Best regards,\n{sender_name}"
        ),
        "follow_up_body": (
            "Hi {contact_name},\n\n"
            "Just following up on my previous email about a guest post for {site_name}. "
            "I understand you are busy, but I wanted to check if you had a chance to "
            "consider my proposal.\n\n"
            "I am flexible on the topic and happy to discuss alternatives.\n\n"
            "Best regards,\n{sender_name}"
        ),
        "is_default": True,
    },
    {
        "name": "Resource Link Request",
        "template_type": "resource_link",
        "subject": "Suggestion for your {page_title} page",
        "body": (
            "Hi {contact_name},\n\n"
            "I found your excellent resource page on {topic} and noticed it links to "
            "several great tools in this space.\n\n"
            "I recently published a comprehensive guide on {resource_topic} that I think "
            "would be a valuable addition for your readers: {resource_url}\n\n"
            "It covers {resource_highlights}.\n\n"
            "Would you consider adding it to your page?\n\n"
            "Thanks for your time,\n{sender_name}"
        ),
        "follow_up_body": (
            "Hi {contact_name},\n\n"
            "Just circling back on my suggestion for your {page_title} page. "
            "I thought our resource on {resource_topic} would complement "
            "the existing links nicely.\n\n"
            "Let me know if you have any questions.\n\n"
            "Cheers,\n{sender_name}"
        ),
        "is_default": True,
    },
    {
        "name": "Broken Link Replacement",
        "template_type": "broken_link",
        "subject": "Found a broken link on {site_name}",
        "body": (
            "Hi {contact_name},\n\n"
            "I was reading your article on {page_title} and noticed that the link to "
            "{broken_url} appears to be broken (404 error).\n\n"
            "I actually have a similar resource that covers the same topic: {replacement_url}\n\n"
            "It might be a good replacement to keep your page up to date.\n\n"
            "Either way, just wanted to give you a heads up about the broken link.\n\n"
            "Best,\n{sender_name}"
        ),
        "follow_up_body": (
            "Hi {contact_name},\n\n"
            "Quick follow-up about the broken link I found on your {page_title} page. "
            "The link to {broken_url} is still returning a 404.\n\n"
            "Happy to help if you need a replacement resource.\n\n"
            "Cheers,\n{sender_name}"
        ),
        "is_default": True,
    },
    {
        "name": "Collaboration Proposal",
        "template_type": "collaboration",
        "subject": "Collaboration idea - {sender_name} x {site_name}",
        "body": (
            "Hi {contact_name},\n\n"
            "I am {sender_name} from {sender_site}. I have been following {site_name} "
            "for a while and love your work on {topic}.\n\n"
            "I think there is a great opportunity for us to collaborate. "
            "Here is what I had in mind:\n\n{collaboration_details}\n\n"
            "Would you be interested in exploring this?\n\n"
            "Looking forward to hearing from you,\n{sender_name}"
        ),
        "follow_up_body": None,
        "is_default": True,
    },
    {
        "name": "Testimonial Offer",
        "template_type": "testimonial",
        "subject": "I would love to write a testimonial for {site_name}",
        "body": (
            "Hi {contact_name},\n\n"
            "I have been using {product_name} for {usage_duration} and it has been "
            "a game changer for {use_case}.\n\n"
            "I would love to write a testimonial for your website. In return, "
            "it would be great if you could include a link back to {sender_site}.\n\n"
            "Here is a draft testimonial:\n{testimonial_draft}\n\n"
            "Feel free to edit it as you see fit.\n\n"
            "Best,\n{sender_name}"
        ),
        "follow_up_body": None,
        "is_default": True,
    },
]


class OutreachManager:
    """Manages outreach campaigns, AI email generation, and tracking.

    Usage::

        manager = OutreachManager()
        email = await manager.generate_outreach_email(
            prospect={"domain": "blog.example.com", "strategy_type": "guest_post"},
            template_type="guest_post",
            business_info={"name": "My SEO Agency", "site": "https://mysite.com"},
        )
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client or LLMClient()
        self._ensure_default_templates()

    # ------------------------------------------------------------------
    # AI Email Generation
    # ------------------------------------------------------------------

    async def generate_outreach_email(
        self,
        prospect: dict,
        template_type: str,
        business_info: dict,
    ) -> dict:
        """Generate a personalised outreach email using AI.

        Args:
            prospect: Prospect data dict (domain, url, strategy_type, title, etc.).
            template_type: One of guest_post, resource_link, broken_link,
                           collaboration, testimonial.
            business_info: Sender details (name, site, credentials, topic, etc.).

        Returns:
            Dict with subject, body, follow_up_body keys.
        """
        template = self._get_template(template_type)

        prompt_parts = [
            "Generate a personalised outreach email for link building.",
            "",
            "Context:",
            "- Prospect domain: " + prospect.get("domain", "Unknown"),
            "- Prospect URL: " + prospect.get("url", ""),
            "- Prospect page title: " + prospect.get("title", ""),
            "- Strategy type: " + prospect.get("strategy_type", template_type),
            "- Notes: " + prospect.get("notes", ""),
            "",
            "Sender info:",
            "- Name: " + business_info.get("name", "SEO Professional"),
            "- Website: " + business_info.get("site", ""),
            "- Credentials: " + business_info.get("credentials", ""),
            "- Topic/Niche: " + business_info.get("topic", ""),
            "",
        ]

        if template:
            prompt_parts.append("Use this template as a starting point but personalise it:")
            prompt_parts.append("Subject: " + template.get("subject", ""))
            prompt_parts.append("Body: " + template.get("body", "")[:500])
            prompt_parts.append("")

        prompt_parts.extend([
            "Requirements:",
            "- Make it personal and genuine, not spammy",
            "- Reference something specific about their site",
            "- Keep it concise (under 200 words)",
            "- Include a clear value proposition",
            "- Professional but friendly tone",
            "",
            "Return a JSON object with keys: subject, body, follow_up_body",
            "follow_up_body should be a shorter follow-up email (under 100 words)",
        ])

        prompt = "\n".join(prompt_parts)

        try:
            result = await self._llm.generate_json(prompt)
            return {
                "subject": result.get("subject", "Link Building Opportunity"),
                "body": result.get("body", ""),
                "follow_up_body": result.get("follow_up_body", ""),
            }
        except Exception as exc:
            logger.error("AI email generation failed: %s", exc)
            # Fall back to template
            if template:
                return {
                    "subject": template.get("subject", "Link Building Opportunity"),
                    "body": template.get("body", ""),
                    "follow_up_body": template.get("follow_up_body", ""),
                }
            raise

    async def generate_email_sequence(
        self,
        prospect: dict,
        business_info: dict,
    ) -> list[dict]:
        """Create a 3-email outreach sequence.

        Returns list of dicts, each with: sequence_number, subject, body,
        send_delay_days.
        """
        strategy = prospect.get("strategy_type", "guest_post")
        template_type = strategy
        if template_type == "competitor_backlinks":
            template_type = "resource_link"
        if template_type == "unlinked_mentions":
            template_type = "collaboration"
        if template_type == "local_links":
            template_type = "resource_link"

        prompt_parts = [
            "Generate a 3-email outreach sequence for link building.",
            "",
            "Context:",
            "- Prospect domain: " + prospect.get("domain", ""),
            "- Prospect URL: " + prospect.get("url", ""),
            "- Page title: " + prospect.get("title", ""),
            "- Strategy: " + strategy,
            "- Notes: " + prospect.get("notes", ""),
            "",
            "Sender:",
            "- Name: " + business_info.get("name", "SEO Professional"),
            "- Website: " + business_info.get("site", ""),
            "- Topic: " + business_info.get("topic", ""),
            "",
            "Create 3 emails:",
            "1. Initial outreach (send immediately) - friendly, specific, value-driven",
            "2. Follow-up (3 days later) - brief reminder, add new angle",
            "3. Final follow-up (7 days later) - last chance, keep it short and graceful",
            "",
            'Return a JSON array of 3 objects, each with: "sequence_number", "subject", "body", "send_delay_days"',
            'send_delay_days should be 0, 3, 7 respectively',
        ]

        prompt = "\n".join(prompt_parts)

        try:
            result = await self._llm.generate_json(prompt)
            if isinstance(result, list):
                return result[:3]
            # Handle case where LLM wraps in an object
            if isinstance(result, dict) and "emails" in result:
                return result["emails"][:3]
            return []
        except Exception as exc:
            logger.error("Email sequence generation failed: %s", exc)
            # Return basic fallback sequence
            initial = await self.generate_outreach_email(
                prospect, template_type, business_info
            )
            return [
                {
                    "sequence_number": 1,
                    "subject": initial["subject"],
                    "body": initial["body"],
                    "send_delay_days": 0,
                },
                {
                    "sequence_number": 2,
                    "subject": "Re: " + initial["subject"],
                    "body": initial.get("follow_up_body", "Just following up on my previous email."),
                    "send_delay_days": 3,
                },
                {
                    "sequence_number": 3,
                    "subject": "Re: " + initial["subject"],
                    "body": "Hi, just one last follow-up. No worries if this is not a fit. Best regards.",
                    "send_delay_days": 7,
                },
            ]

    # ------------------------------------------------------------------
    # Outreach Tracking
    # ------------------------------------------------------------------

    def track_outreach(
        self, prospect_id: int, status: str, notes: str = ""
    ) -> dict:
        """Update outreach status for a prospect.

        Valid statuses: new, sent, opened, replied, accepted, rejected.
        """
        valid_statuses = {"new", "sent", "opened", "replied", "accepted", "rejected"}
        if status not in valid_statuses:
            raise ValueError(
                "Invalid status: " + status + ". Must be one of: " + ", ".join(sorted(valid_statuses))
            )

        with get_session() as session:
            prospect = session.query(OutreachProspect).filter_by(id=prospect_id).first()
            if not prospect:
                raise ValueError("Prospect not found: " + str(prospect_id))

            old_status = prospect.status
            prospect.status = status
            if notes:
                existing = prospect.notes or ""
                prospect.notes = existing + "\n" + notes if existing else notes
            if status == "sent":
                prospect.last_contacted = _utcnow()

            # Update campaign counters if linked
            if prospect.campaign_id:
                campaign = session.query(OutreachCampaign).filter_by(
                    id=prospect.campaign_id
                ).first()
                if campaign:
                    if status == "sent" and old_status != "sent":
                        campaign.emails_sent += 1
                    if status == "replied" and old_status != "replied":
                        campaign.responses += 1
                    if status == "accepted" and old_status != "accepted":
                        campaign.links_acquired += 1

            result = {
                "id": prospect.id,
                "domain": prospect.domain,
                "old_status": old_status,
                "new_status": status,
                "notes": prospect.notes,
            }

        logger.info(
            "Updated prospect %d status: %s -> %s",
            prospect_id, old_status, status,
        )
        return result

    def save_email_to_db(
        self,
        prospect_id: int,
        subject: str,
        body: str,
        sequence_number: int = 1,
        status: str = "draft",
    ) -> int:
        """Save a generated email to the database."""
        with get_session() as session:
            email = OutreachEmail(
                prospect_id=prospect_id,
                sequence_number=sequence_number,
                subject=subject,
                body=body,
                status=status,
            )
            session.add(email)
            session.flush()
            email_id = email.id
        logger.info("Saved email %d for prospect %d", email_id, prospect_id)
        return email_id

    # ------------------------------------------------------------------
    # Outreach Statistics
    # ------------------------------------------------------------------

    def get_outreach_stats(self) -> dict:
        """Return outreach metrics summary."""
        with get_session() as session:
            all_prospects = session.query(OutreachProspect).all()
            total = len(all_prospects)
            if total == 0:
                return {
                    "total_prospects": 0,
                    "total_sent": 0,
                    "total_replied": 0,
                    "total_accepted": 0,
                    "total_rejected": 0,
                    "response_rate": 0.0,
                    "acceptance_rate": 0.0,
                    "by_strategy": {},
                    "by_status": {},
                }

            status_counts: dict[str, int] = {}
            strategy_counts: dict[str, dict[str, int]] = {}

            for p in all_prospects:
                # Count by status
                s = p.status or "new"
                status_counts[s] = status_counts.get(s, 0) + 1

                # Count by strategy
                st = p.strategy_type or "unknown"
                if st not in strategy_counts:
                    strategy_counts[st] = {"total": 0, "sent": 0, "replied": 0, "accepted": 0}
                strategy_counts[st]["total"] += 1
                if s in ("sent", "opened", "replied", "accepted", "rejected"):
                    strategy_counts[st]["sent"] += 1
                if s in ("replied", "accepted"):
                    strategy_counts[st]["replied"] += 1
                if s == "accepted":
                    strategy_counts[st]["accepted"] += 1

            sent = status_counts.get("sent", 0) + status_counts.get("opened", 0) + \
                status_counts.get("replied", 0) + status_counts.get("accepted", 0) + \
                status_counts.get("rejected", 0)
            replied = status_counts.get("replied", 0) + status_counts.get("accepted", 0)
            accepted = status_counts.get("accepted", 0)

            response_rate = (replied / sent * 100) if sent > 0 else 0.0
            acceptance_rate = (accepted / sent * 100) if sent > 0 else 0.0

            return {
                "total_prospects": total,
                "total_sent": sent,
                "total_replied": replied,
                "total_accepted": accepted,
                "total_rejected": status_counts.get("rejected", 0),
                "response_rate": round(response_rate, 1),
                "acceptance_rate": round(acceptance_rate, 1),
                "by_strategy": strategy_counts,
                "by_status": status_counts,
            }

    # ------------------------------------------------------------------
    # Template Management
    # ------------------------------------------------------------------

    def manage_templates(
        self, action: str, template: Optional[dict] = None
    ) -> list[dict]:
        """CRUD for email templates.

        Actions: list, create, update, delete.
        """
        with get_session() as session:
            if action == "list":
                rows = session.query(EmailTemplate).all()
                return [
                    {
                        "id": r.id,
                        "name": r.name,
                        "template_type": r.template_type,
                        "subject": r.subject,
                        "body": r.body,
                        "follow_up_body": r.follow_up_body,
                        "is_default": r.is_default,
                    }
                    for r in rows
                ]

            if action == "create" and template:
                obj = EmailTemplate(
                    name=template.get("name", "Custom Template"),
                    template_type=template.get("template_type", "custom"),
                    subject=template.get("subject", ""),
                    body=template.get("body", ""),
                    follow_up_body=template.get("follow_up_body"),
                    is_default=False,
                )
                session.add(obj)
                session.flush()
                logger.info("Created template: %s", obj.name)

            elif action == "update" and template:
                obj = session.query(EmailTemplate).filter_by(
                    id=template.get("id")
                ).first()
                if obj:
                    if "name" in template:
                        obj.name = template["name"]
                    if "subject" in template:
                        obj.subject = template["subject"]
                    if "body" in template:
                        obj.body = template["body"]
                    if "follow_up_body" in template:
                        obj.follow_up_body = template["follow_up_body"]
                    obj.updated_at = _utcnow()
                    logger.info("Updated template: %s", obj.name)

            elif action == "delete" and template:
                obj = session.query(EmailTemplate).filter_by(
                    id=template.get("id")
                ).first()
                if obj and not obj.is_default:
                    session.delete(obj)
                    logger.info("Deleted template: %s", obj.name)
                elif obj and obj.is_default:
                    logger.warning("Cannot delete default template: %s", obj.name)

            # Return current list
            rows = session.query(EmailTemplate).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "template_type": r.template_type,
                    "subject": r.subject,
                    "body": r.body,
                    "follow_up_body": r.follow_up_body,
                    "is_default": r.is_default,
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # CSV Export
    # ------------------------------------------------------------------

    def export_outreach_csv(self, filters: Optional[dict] = None) -> str:
        """Export outreach data to CSV string."""
        with get_session() as session:
            query = session.query(OutreachProspect)
            if filters:
                if filters.get("status"):
                    query = query.filter(OutreachProspect.status == filters["status"])
                if filters.get("strategy_type"):
                    query = query.filter(
                        OutreachProspect.strategy_type == filters["strategy_type"]
                    )
                if filters.get("campaign_id"):
                    query = query.filter(
                        OutreachProspect.campaign_id == filters["campaign_id"]
                    )
            rows = query.order_by(OutreachProspect.created_at.desc()).all()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ID", "Domain", "URL", "Contact Email", "Contact Name",
                "DA Estimate", "Relevance Score", "Strategy", "Status",
                "Notes", "Last Contacted", "Created At",
            ])

            for r in rows:
                writer.writerow([
                    r.id,
                    r.domain,
                    r.url,
                    r.contact_email or "",
                    r.contact_name or "",
                    r.da_estimate or "",
                    r.relevance_score or "",
                    r.strategy_type or "",
                    r.status,
                    r.notes or "",
                    str(r.last_contacted) if r.last_contacted else "",
                    str(r.created_at) if r.created_at else "",
                ])

        csv_str = output.getvalue()
        logger.info("Exported %d prospects to CSV", len(rows))
        return csv_str

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_default_templates(self) -> None:
        """Create default email templates if they do not exist."""
        try:
            with get_session() as session:
                existing = session.query(EmailTemplate).filter_by(is_default=True).count()
                if existing > 0:
                    return
                for tmpl in DEFAULT_TEMPLATES:
                    obj = EmailTemplate(
                        name=tmpl["name"],
                        template_type=tmpl["template_type"],
                        subject=tmpl["subject"],
                        body=tmpl["body"],
                        follow_up_body=tmpl.get("follow_up_body"),
                        is_default=tmpl.get("is_default", False),
                    )
                    session.add(obj)
                logger.info("Inserted %d default email templates", len(DEFAULT_TEMPLATES))
        except Exception as exc:
            logger.warning("Could not ensure default templates: %s", exc)

    def _get_template(self, template_type: str) -> Optional[dict]:
        """Load a template by type from the database."""
        try:
            with get_session() as session:
                row = session.query(EmailTemplate).filter_by(
                    template_type=template_type
                ).first()
                if row:
                    return {
                        "name": row.name,
                        "template_type": row.template_type,
                        "subject": row.subject,
                        "body": row.body,
                        "follow_up_body": row.follow_up_body,
                    }
        except Exception as exc:
            logger.warning("Template lookup failed: %s", exc)

        # Fallback to hardcoded defaults
        for tmpl in DEFAULT_TEMPLATES:
            if tmpl["template_type"] == template_type:
                return tmpl
        return None
