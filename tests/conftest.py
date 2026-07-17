import pytest
from sqlalchemy.orm import Session

from app.db import engine


@pytest.fixture
def db():
    """A DB session wrapped in a transaction that's rolled back after the test,
    so constraint-violation tests never leave junk data behind."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
