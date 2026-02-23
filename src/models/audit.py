"""Technical SEO audit SQLAlchemy models."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SiteAudit(Base):
    """High-level record for a complete site audit run."""

    __tablename__ = "site_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    audit_type: Mapped[str] = mapped_column(String(100), default="full")
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    issues_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    checks: Mapped[list["AuditCheck"]] = relationship(
        back_populates="audit", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SiteAudit id={self.id} domain={self.domain!r} score={self.overall_score}>"


class AuditCheck(Base):
    """Individual check result within an audit."""

    __tablename__ = "audit_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("site_audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="info", nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(50), default="medium", nullable=False)

    audit: Mapped["SiteAudit"] = relationship(back_populates="checks")

    def __repr__(self) -> str:
        return f"<AuditCheck id={self.id} name={self.check_name!r} status={self.status}>"


class CoreWebVitals(Base):
    """Core Web Vitals measurement for a single URL."""

    __tablename__ = "core_web_vitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    lcp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # Largest Contentful Paint (ms)
    inp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # Interaction to Next Paint (ms)
    cls: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # Cumulative Layout Shift
    ttfb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # Time to First Byte (ms)
    performance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<CoreWebVitals id={self.id} url={self.url[:60]!r} perf={self.performance_score}>"
