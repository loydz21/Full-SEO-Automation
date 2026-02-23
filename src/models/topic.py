"""Topical map SQLAlchemy models for pillar/cluster/supporting-page hierarchy."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.keyword import KeywordCluster


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TopicalMap(Base):
    """Root entity representing a niche-level topical map."""

    __tablename__ = "topical_maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    niche: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    pillars: Mapped[list["PillarTopic"]] = relationship(
        back_populates="topical_map", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<TopicalMap id={self.id} niche={self.niche!r}>"


class PillarTopic(Base):
    """A high-level pillar topic within a topical map."""

    __tablename__ = "pillar_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    map_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topical_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competition: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    topical_map: Mapped["TopicalMap"] = relationship(back_populates="pillars")
    clusters: Mapped[list["TopicCluster"]] = relationship(
        back_populates="pillar", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<PillarTopic id={self.id} name={self.name!r}>"


class TopicCluster(Base):
    """A cluster of related subtopics under a pillar."""

    __tablename__ = "topic_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pillar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pillar_topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_count: Mapped[int] = mapped_column(Integer, default=0)

    pillar: Mapped["PillarTopic"] = relationship(back_populates="clusters")
    supporting_pages: Mapped[list["SupportingPage"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", lazy="selectin"
    )
    keyword_clusters: Mapped[list["KeywordCluster"]] = relationship(
        back_populates="topic_cluster", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<TopicCluster id={self.id} name={self.name!r}>"


class SupportingPage(Base):
    """Individual page/article idea within a cluster."""

    __tablename__ = "supporting_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topic_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    cluster: Mapped["TopicCluster"] = relationship(back_populates="supporting_pages")

    def __repr__(self) -> str:
        return f"<SupportingPage id={self.id} topic={self.topic!r}>"
