"""Engine/session lifecycle for the Umi database.

When no ``DATABASE_URL`` is configured, all helpers here are no-ops and the
application runs without persistence (graceful degradation), so the chat still
works while memory/conversation features report the database as unavailable.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.base import Base

_engine = None
_session_factory = None


def normalize_url(url: str) -> str:
    """Translate a bare postgres URL into one SQLAlchemy can use with psycopg."""
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            rest = url[len(prefix) :]
            return f"postgresql+psycopg://{rest}"
    return url


def configure(url: str) -> None:
    global _engine, _session_factory
    _engine = create_engine(normalize_url(url), pool_pre_ping=True, future=True)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def configure_test(url: str) -> None:
    """Configure an explicit engine from tests (in-memory SQLite)."""
    global _engine, _session_factory
    _engine = create_engine(
        url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        future=True,
    )
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def get_engine():
    if _engine is None:
        if not settings.db_enabled:
            return None
        configure(settings.database_url)
    return _engine


def get_session_factory():
    get_engine()
    return _session_factory


def db_enabled() -> bool:
    if _session_factory is not None:
        return True
    return settings.db_enabled


def init_db() -> None:
    """Create tables if the database is configured.

    Also usable for test databases (pass a URL via ``configure`` first).
    """
    from app.db import models  # noqa: F401  (register models on Base)

    engine = get_engine()
    if engine is None:
        return
    Base.metadata.create_all(engine)