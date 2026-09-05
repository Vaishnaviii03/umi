import pytest

import app.db.models  # noqa: F401  (register models on Base)
from app.db import engine as db_engine
from app.db.base import Base


@pytest.fixture(scope="session", autouse=True)
def sqlite_db():
    db_engine.configure_test("sqlite://")
    Base.metadata.create_all(db_engine.get_engine())
    yield


@pytest.fixture()
def db_session():
    factory = db_engine.get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_tables(db_session):
    from app.db import models

    db_session.query(models.Memory).delete()
    db_session.query(models.Message).delete()
    db_session.query(models.Conversation).delete()
    db_session.commit()
    yield