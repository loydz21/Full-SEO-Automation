"""SERP ranking, history, and visibility SQLAlchemy models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, DateTime, JSON, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.keyword import Keyword


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today():
    return datetime.now(timezone.utc).date()


class RankingEntry(Base):
    """Point-in-time ranking position for a keyword + URL pair."""

    __tablename__ = "ranking_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    position_google_desktop: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_google_mobile: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_bing: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    serp_features_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="rankings")

    def __repr__(self) -> str:
        return (
            f"<RankingEntry id={self.id} kw_id={self.keyword_id} "
            f"desktop={self.position_google_desktop} mobile={self.position_google_mobile}>"
        )


class SERPSnapshot(Base):
    """Full SERP page snapshot stored as JSON for historical analysis."""

    __tablename__ = "serp_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="serp_snapshots")

    def __repr__(self) -> str:
        return f"<SERPSnapshot id={self.id} kw_id={self.keyword_id}>"


class RankingRecord(Base):
    """Detailed ranking record for a keyword-domain pair with device and location."""

    __tablename__ = "ranking_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url_ranked: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    serp_features_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    search_engine: Mapped[str] = mapped_column(String(50), default="google", nullable=False)
    device: Mapped[str] = mapped_column(String(20), default="desktop", nullable=False)
    location: Mapped[str] = mapped_column(String(100), default="us", nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<RankingRecord id={self.id} kw={self.keyword!r} "
            f"domain={self.domain!r} pos={self.position}>"
        )


class RankingHistory(Base):
    """Daily ranking position history for trend analysis."""

    __tablename__ = "ranking_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<RankingHistory id={self.id} kw={self.keyword!r} "
            f"pos={self.position} chg={self.change}>"
        )


class SERPFeature(Base):
    """Tracked SERP features per keyword."""

    __tablename__ = "serp_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    feature_type: Mapped[str] = mapped_column(String(100), nullable=False)
    owns_feature: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    competitor_in_feature: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<SERPFeature id={self.id} kw={self.keyword!r} "
            f"type={self.feature_type!r} owns={self.owns_feature}>"
        )


class CompetitorRank(Base):
    """Competitor ranking positions for tracked keywords."""

    __tablename__ = "competitor_ranks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    competitor_domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url_ranked: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<CompetitorRank id={self.id} kw={self.keyword!r} "
            f"comp={self.competitor_domain!r} pos={self.position}>"
        )


class VisibilityScore(Base):
    """Aggregated domain visibility score over time."""

    __tablename__ = "visibility_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    keyword_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top3_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top10_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top20_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<VisibilityScore id={self.id} domain={self.domain!r} "
            f"score={self.score} kws={self.keyword_count}>"
        )
