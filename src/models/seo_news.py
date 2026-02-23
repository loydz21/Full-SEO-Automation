"""SEO News & Strategy models for tracking industry updates."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.database import Base


class SEONewsSource(Base):
    """RSS feeds and websites to scrape for SEO news."""
    __tablename__ = "seo_news_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    source_type = Column(String(50), default="rss")  # rss, blog, api
    category = Column(String(100), default="general")  # general, technical, content, local, linkbuilding
    reliability_score = Column(Float, default=0.8)  # 0-1 how trustworthy
    is_active = Column(Boolean, default=True)
    last_scraped = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    articles = relationship("SEONewsArticle", back_populates="source")


class SEONewsArticle(Base):
    """Individual SEO news articles scraped from sources."""
    __tablename__ = "seo_news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("seo_news_sources.id"), nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    summary = Column(Text, nullable=True)
    full_content = Column(Text, nullable=True)
    author = Column(String(200), nullable=True)
    published_at = Column(DateTime, nullable=True)
    category = Column(String(100), nullable=True)
    tags = Column(JSON, nullable=True)  # list of tags
    relevance_score = Column(Float, default=0.0)  # AI-scored 0-1
    is_actionable = Column(Boolean, default=False)  # contains actionable strategy
    scraped_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("SEONewsSource", back_populates="articles")
    strategies = relationship("SEOStrategy", back_populates="article")


class SEOStrategy(Base):
    """Extracted SEO strategies from news articles."""
    __tablename__ = "seo_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("seo_news_articles.id"), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)  # technical, content, local, linkbuilding, onpage, offpage
    strategy_type = Column(String(50), default="optimization")  # optimization, new_technique, algorithm_update, tool_recommendation
    implementation_steps = Column(JSON, nullable=True)  # list of step dicts
    estimated_impact = Column(String(20), default="medium")  # high, medium, low
    estimated_effort = Column(String(20), default="medium")  # easy, medium, hard
    confidence_score = Column(Float, default=0.5)  # AI confidence 0-1
    verification_status = Column(String(50), default="pending")  # pending, verified, rejected, testing
    verification_notes = Column(Text, nullable=True)
    applied = Column(Boolean, default=False)
    applied_at = Column(DateTime, nullable=True)
    results_after_applying = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    article = relationship("SEONewsArticle", back_populates="strategies")


class StrategyVerification(Base):
    """Verification records for SEO strategies."""
    __tablename__ = "strategy_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("seo_strategies.id"), nullable=False)
    verification_method = Column(String(100), nullable=False)  # ai_analysis, serp_test, expert_sources, ab_test
    is_valid = Column(Boolean, nullable=True)
    confidence = Column(Float, default=0.0)
    evidence = Column(Text, nullable=True)
    supporting_sources = Column(JSON, nullable=True)  # list of URLs
    tested_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

