"""Keyword and keyword-cluster SQLAlchemy models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.content import ContentBrief
    from src.models.ranking import RankingEntry, SERPSnapshot
    from src.models.topic import TopicCluster


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KeywordCluster(Base):
    """Logical grouping of semantically related keywords."""

    __tablename__ = "keyword_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    topic_cluster_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("topic_clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    keyword_count: Mapped[int] = mapped_column(Integer, default=0)

    topic_cluster: Mapped[Optional["TopicCluster"]] = relationship(
        "TopicCluster", back_populates="keyword_clusters"
    )
    keywords: Mapped[list["Keyword"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<KeywordCluster id={self.id} name={self.name!r}>"


class Keyword(Base):
    """Individual keyword with search metrics and scoring."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cpc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    trend: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cluster_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    cluster: Mapped[Optional["KeywordCluster"]] = relationship(back_populates="keywords")
    rankings: Mapped[list["RankingEntry"]] = relationship(
        "RankingEntry", back_populates="keyword", lazy="selectin"
    )
    serp_snapshots: Mapped[list["SERPSnapshot"]] = relationship(
        "SERPSnapshot", back_populates="keyword", lazy="selectin"
    )
    content_briefs: Mapped[list["ContentBrief"]] = relationship(
        "ContentBrief", back_populates="keyword", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Keyword id={self.id} text={self.text!r} vol={self.volume}>"
