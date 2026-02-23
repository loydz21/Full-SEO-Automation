"""Backlink and outreach campaign SQLAlchemy models."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Backlink(Base):
    """A discovered backlink pointing to or from the tracked site."""

    __tablename__ = "backlinks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    source_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    anchor_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    link_type: Mapped[str] = mapped_column(String(50), default="dofollow", nullable=False)
    dofollow: Mapped[bool] = mapped_column(Boolean, default=True)
    domain_authority: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    is_toxic: Mapped[bool] = mapped_column(Boolean, default=False)
    toxic_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    checks: Mapped[list["BacklinkCheck"]] = relationship(
        back_populates="backlink", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Backlink id={self.id} src={self.source_url[:50]!r} -> tgt={self.target_url[:50]!r}>"


class BacklinkCheck(Base):
    """Historical check record for a backlink."""

    __tablename__ = "backlink_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backlink_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("backlinks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_dofollow: Mapped[bool] = mapped_column(Boolean, default=True)
    anchor_text_found: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    backlink: Mapped["Backlink"] = relationship(back_populates="checks")

    def __repr__(self) -> str:
        return f"<BacklinkCheck id={self.id} backlink={self.backlink_id} status={self.status}>"


class OutreachCampaign(Base):
    """Link-building outreach campaign."""

    __tablename__ = "outreach_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    emails_sent: Mapped[int] = mapped_column(Integer, default=0)
    responses: Mapped[int] = mapped_column(Integer, default=0)
    links_acquired: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prospects: Mapped[list["OutreachProspect"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<OutreachCampaign id={self.id} name={self.name!r} status={self.status}>"


class OutreachProspect(Base):
    """Individual prospect within an outreach campaign."""

    __tablename__ = "outreach_prospects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("outreach_campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    da_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_contacted: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    campaign: Mapped[Optional["OutreachCampaign"]] = relationship(back_populates="prospects")
    emails: Mapped[list["OutreachEmail"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<OutreachProspect id={self.id} domain={self.domain!r} status={self.status}>"


class OutreachEmail(Base):
    """An outreach email sent or queued for a prospect."""

    __tablename__ = "outreach_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, default=1)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prospect: Mapped["OutreachProspect"] = relationship(back_populates="emails")

    def __repr__(self) -> str:
        return f"<OutreachEmail id={self.id} prospect={self.prospect_id} seq={self.sequence_number}>"


class EmailTemplate(Base):
    """Reusable email template for outreach."""

    __tablename__ = "email_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    template_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<EmailTemplate id={self.id} name={self.name!r} type={self.template_type}>"
