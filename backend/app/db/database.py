"""Database engine / session factory and initialisation."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Base

logger = get_logger(__name__)

_settings = get_settings()

# Ensure the SQLite directory exists before creating the engine.
_sqlite_path = _settings.sqlite_path
_sqlite_path.parent.mkdir(parents=True, exist_ok=True)

_is_sqlite = _settings.database_url.startswith("sqlite")
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Allow concurrent readers/writers when multiple workers touch the DB."""
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)


def init_db() -> None:
    """Create tables if they do not yet exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialised at %s", _sqlite_path)


@contextmanager
def session_scope() -> Iterator[OrmSession]:
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
        commit_with_retry(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def commit_with_retry(db: OrmSession, *, attempts: int = 5, base_delay_s: float = 0.05) -> None:
    """Commit with short retries - helps when SQLite is briefly locked by another writer."""
    import time

    from sqlalchemy.exc import OperationalError

    last: OperationalError | None = None
    for attempt in range(attempts):
        try:
            db.commit()
            return
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower() or attempt == attempts - 1:
                raise
            last = exc
            time.sleep(base_delay_s * (2**attempt))
    if last:
        raise last


def get_db() -> Iterator[OrmSession]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
