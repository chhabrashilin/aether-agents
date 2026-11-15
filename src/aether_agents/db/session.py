"""Engine and session factory. Uses DATABASE_URL; SQLite works for local tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aether_agents.db.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _normalize_url(database_url: str) -> str:
    """Accept bare sqlite paths and postgres URLs without a driver suffix."""
    url = database_url.strip()
    if url.startswith("sqlite://") and not url.startswith("sqlite:///"):
        # sqlite:///:memory: is fine; sqlite://file.db is not; leave as-is.
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def get_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create (or return cached) SQLAlchemy engine for DATABASE_URL."""
    global _engine, _SessionLocal
    url = _normalize_url(database_url)
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Return a session factory, creating the engine if needed."""
    global _SessionLocal
    if _SessionLocal is None:
        if not database_url:
            raise RuntimeError("database_url required before session factory is initialized")
        get_engine(database_url)
    assert _SessionLocal is not None
    return _SessionLocal


def init_db(database_url: str, *, echo: bool = False) -> Engine:
    """Create all tables and return the engine."""
    engine = get_engine(database_url, echo=echo)
    Base.metadata.create_all(bind=engine)
    return engine


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    """Context-managed session with commit/rollback."""
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Drop cached engine/session (for tests that swap DATABASE_URL)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
