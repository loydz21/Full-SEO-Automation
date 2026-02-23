"""Local SEO SQLAlchemy models for business profiles, audits, competitors, citations, and keyword tracking."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalBusinessProfile(Base):
    """A local business entity tracked for Local SEO analysis."""

    __tablename__ = "local_business_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gbp_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    audits: Mapped[list["LocalSEOAudit"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    competitors: Mapped[list["LocalCompetitor"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    citations: Mapped[list["CitationEntry"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    keywords: Mapped[list["LocalKeywordTracking"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<LocalBusinessProfile id={self.id} name={self.business_name!r} domain={self.domain!r}>"


class LocalSEOAudit(Base):
    """Complete Local SEO audit run for a business, storing scores and recommendations."""

    __tablename__ = "local_seo_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("local_business_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    audit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    serp_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gmb_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    onpage_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offpage_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    citation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    top_issues_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    business: Mapped["LocalBusinessProfile"] = relationship(back_populates="audits")

    def __repr__(self) -> str:
        return (
            f"<LocalSEOAudit id={self.id} business_id={self.business_id} "
            f"overall={self.overall_score}>"
        )


class LocalCompetitor(Base):
    """A competitor found in the local SERP or map pack for a tracked business."""

    __tablename__ = "local_competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("local_business_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_name: Mapped[str] = mapped_column(String(500), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    gbp_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_map_pack: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    strengths_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    business: Mapped["LocalBusinessProfile"] = relationship(back_populates="competitors")

    def __repr__(self) -> str:
        return (
            f"<LocalCompetitor id={self.id} name={self.competitor_name!r} "
            f"map_pos={self.position_map_pack}>"
        )


class CitationEntry(Base):
    """A business directory citation entry tracking NAP consistency."""

    __tablename__ = "citation_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("local_business_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    directory_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    nap_consistent: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    business: Mapped["LocalBusinessProfile"] = relationship(back_populates="citations")

    def __repr__(self) -> str:
        return (
            f"<CitationEntry id={self.id} dir={self.directory_name!r} "
            f"nap_ok={self.nap_consistent} status={self.status!r}>"
        )


class LocalKeywordTracking(Base):
    """Track local keyword rankings including organic and map pack positions."""

    __tablename__ = "local_keyword_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("local_business_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    map_pack_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    competitor_positions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    business: Mapped["LocalBusinessProfile"] = relationship(back_populates="keywords")

    def __repr__(self) -> str:
        return (
            f"<LocalKeywordTracking id={self.id} kw={self.keyword!r} "
            f"pos={self.current_position} map={self.map_pack_position}>"
        )
