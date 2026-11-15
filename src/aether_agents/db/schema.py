"""Schema bootstrap helpers (create/drop tables)."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from aether_agents.db.models import Base
from aether_agents.db.session import get_engine


def create_schema(database_url: str, *, echo: bool = False) -> Engine:
    """Create all ORM tables for the given DATABASE_URL."""
    engine = get_engine(database_url, echo=echo)
    Base.metadata.create_all(bind=engine)
    return engine


def drop_schema(database_url: str, *, echo: bool = False) -> Engine:
    """Drop all ORM tables (destructive; tests/dev only)."""
    engine = get_engine(database_url, echo=echo)
    Base.metadata.drop_all(bind=engine)
    return engine
