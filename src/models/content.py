"""Blog content, brief, and refresh SQLAlchemy models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.keyword import Keyword


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentBrief(Base):
    """Pre-writing brief that guides blog post creation."""

    __tablename__ = "content_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    target_word_count: Mapped[int] = mapped_column(Integer, default=1500)
    content_type: Mapped[str] = mapped_column(String(100), default="blog_post")
    outline_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    keyword: Mapped[Optional["Keyword"]] = relationship(
        "Keyword", back_populates="content_briefs"
    )
    blog_post: Mapped[Optional["BlogPost"]] = relationship(
        back_populates="brief", uselist=False, lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ContentBrief id={self.id} title={self.title!r}>"


class BlogPost(Base):
    """Published or draft blog post with content and scoring."""

    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brief_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_briefs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    content_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    seo_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    brief: Mapped[Optional["ContentBrief"]] = relationship(back_populates="blog_post")
    refreshes: Mapped[list["ContentRefresh"]] = relationship(
        back_populates="blog_post", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<BlogPost id={self.id} slug={self.slug!r}>"


class ContentRefresh(Base):
    """Suggestion for refreshing / updating an existing blog post."""

    __tablename__ = "content_refreshes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    suggested_changes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    blog_post: Mapped["BlogPost"] = relationship(back_populates="refreshes")

    def __repr__(self) -> str:
        return f"<ContentRefresh id={self.id} post_id={self.post_id}>"
