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


_db_failed = False


def db_enabled() -> bool:
    if _db_failed or not settings.db_enabled:
        return False
    return _session_factory is not None


def _ensure_owner_user() -> None:
    if _session_factory is None:
        return
    try:
        from app.db.models import User
        import uuid
        owner_uuid = uuid.UUID(settings.owner_id)
        with _session_factory() as session:
            if not session.get(User, owner_uuid):
                session.add(User(id=owner_uuid, name="Owner"))
                session.commit()
    except Exception as e:
        import logging
        logging.getLogger("umi.db").debug("Could not verify owner user: %s", e)


def init_db() -> None:
    """Create tables if the database is configured.

    If remote database fails (e.g. Supabase paused or unreachable),
    automatically falls back to local SQLite persistence (~/.umi/umi.db).
    """
    global _session_factory, _engine, _db_failed
    from pathlib import Path
    import logging
    from app.db import models  # noqa: F401  (register models on Base)

    engine = get_engine()
    if engine is not None:
        try:
            Base.metadata.create_all(engine)
            _ensure_owner_user()
            _db_failed = False
            logging.getLogger("umi.db").info("Connected to primary database.")
            return
        except Exception as exc:
            logging.getLogger("umi.db").warning(
                "Primary database connection failed (%s) — falling back to local SQLite", exc
            )

    # Automatic local SQLite fallback so memories and tasks always work
    try:
        local_db_path = Path.home() / ".umi" / "umi.db"
        local_db_path.parent.mkdir(parents=True, exist_ok=True)
        configure(f"sqlite:///{local_db_path}")
        Base.metadata.create_all(_engine)
        _db_failed = False
        _ensure_owner_user()
        logging.getLogger("umi.db").info("Local SQLite database active at %s", local_db_path)
    except Exception as exc:
        logging.getLogger("umi.db").error("Failed to initialize database: %s", exc)
        _db_failed = True
        _session_factory = None