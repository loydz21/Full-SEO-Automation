"""Shared pytest fixtures for Full SEO Automation integration tests."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure project root is on sys.path so 'src' is importable.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture(autouse=True)
def _reset_db_engine():
    """Autouse fixture: reset the global DB engine before and after every test.

    This prevents cross-test pollution when tests create their own in-memory
    databases.
    """
    from src.database import reset_engine
    reset_engine()
    yield
    reset_engine()


@pytest.fixture()
def test_db():
    """Provide an in-memory SQLite database with all tables created.

    Yields a database URL string. The engine is automatically torn down
    after the test by the autouse ``_reset_db_engine`` fixture.
    """
    from src.database import reset_engine, init_db
    reset_engine()
    db_url = "sqlite:///:memory:"
    init_db(database_url=db_url, echo=False)
    yield db_url


@pytest.fixture()
def mock_llm_client():
    """Return a mock LLMClient that returns canned responses."""
    client = MagicMock()

    # Async methods return canned data
    client.generate_text = AsyncMock(return_value="Mock LLM response text.")
    client.generate_json = AsyncMock(return_value={
        "keywords": ["seo tools", "best seo"],
        "summary": "Mock summary.",
        "score": 75,
    })
    client.generate_embeddings = AsyncMock(return_value=[[0.1] * 128])
    client.count_tokens = MagicMock(return_value=42)
    client.get_usage_stats = MagicMock(return_value={
        "total_requests": 0,
        "total_cost_usd": 0.0,
    })
    return client


@pytest.fixture()
def mock_serp_scraper():
    """Return a mock SERPScraper that returns canned search results."""
    scraper = MagicMock()
    scraper.search_google = AsyncMock(return_value=[
        {
            "title": "Mock Result 1",
            "url": "https://example.com/page1",
            "snippet": "This is a mock SERP snippet.",
            "position": 1,
        },
        {
            "title": "Mock Result 2",
            "url": "https://example.com/page2",
            "snippet": "Another mock snippet.",
            "position": 2,
        },
    ])
    scraper.get_paa_questions = AsyncMock(return_value=[
        "What is SEO?",
        "How does SEO work?",
    ])
    scraper.get_autocomplete = AsyncMock(return_value=[
        "seo tools",
        "seo meaning",
        "seo optimization",
    ])
    scraper.close = AsyncMock()
    return scraper
