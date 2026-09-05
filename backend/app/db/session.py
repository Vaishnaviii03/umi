from fastapi import HTTPException

from app.db.engine import db_enabled, get_session_factory


def get_db():
    """FastAPI dependency yielding a DB session.

    When the database is not configured, yields ``None`` so callers can degrade
    gracefully (chat still works) or raise a clear 503 for DB-only features.
    """
    if not db_enabled():
        yield None
        return
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def require_db(db):
    if db is None:
        raise HTTPException(status_code=503, detail="Umi's database isn't configured yet.")
    return db