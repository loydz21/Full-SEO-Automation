"""Database engine, session management, and initialization for SQLite + SQLAlchemy."""

import os
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


_engine = None
_SessionFactory: sessionmaker | None = None


def _enable_wal(dbapi_conn, connection_record):
    """Enable WAL journal mode and other SQLite pragmas for better concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.close()


def get_engine(database_url: str | None = None, echo: bool = False):
    """Return (and cache) the global SQLAlchemy engine.

    Args:
        database_url: SQLite connection string.  Falls back to the
                      ``DATABASE_URL`` env-var or a sensible default.
        echo: Whether to log every SQL statement.
    """
    global _engine
    if _engine is not None:
        return _engine

    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///data/seo_automation.db")

    # Ensure the directory for the SQLite file exists.
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        database_url,
        echo=echo,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    # Register the WAL-mode pragma listener.
    event.listen(_engine, "connect", _enable_wal)
    logger.info("Database engine created: %s", database_url)
    return _engine


def get_session_factory(engine=None) -> sessionmaker:
    """Return (and cache) the global session factory."""
    global _SessionFactory
    if _SessionFactory is not None:
        return _SessionFactory
    if engine is None:
        engine = get_engine()
    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session via context manager.

    Usage::

        with get_session() as session:
            session.add(obj)
            session.commit()
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: str | None = None, echo: bool = False) -> None:
    """Create all tables that do not yet exist.

    Imports every model package so that ``Base.metadata`` is fully
    populated before issuing ``CREATE TABLE`` statements.
    """
    engine = get_engine(database_url=database_url, echo=echo)
    # Side-effect import: registers all models with Base.metadata
    import src.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("All database tables created / verified.")


def reset_db(database_url: str | None = None) -> None:
    """Drop and recreate every table.  **Destructive** — use only in tests."""
    engine = get_engine(database_url=database_url)
    import src.models  # noqa: F401
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.warning("Database has been reset (all tables dropped and recreated).")


def reset_engine() -> None:
    """Dispose of the cached engine and session factory (useful for tests)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
