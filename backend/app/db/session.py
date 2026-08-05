"""Engine and per-request session management."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # a recycled MySQL connection must not 500 the first request
    pool_recycle=280,     # below MySQL's default wait_timeout
    future=True,
    echo=settings.sql_echo,
)

# expire_on_commit=False so response serialization after a commit does not fire a
# second round of SELECTs. Consequence: the in-memory value of the DB-computed
# appointments.occupies_slot_id goes stale after a status change — never read it in
# Python, it exists purely for the database's unique index.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Rolls back on any exception so a failed request can never
    leave a half-applied booking transaction behind."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
