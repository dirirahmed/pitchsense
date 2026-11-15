"""Database engine and connectivity helpers."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from pitchsense.core.config import get_settings

CONNECT_TIMEOUT_SECONDS = 5


def build_engine(database_url: str) -> Engine:
    # pool_pre_ping discards stale pooled connections, e.g. after a serverless
    # Postgres (Neon) scales to zero and drops idle connections.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings().database_url)


def database_is_available(engine: Engine | None = None) -> bool:
    """Return True if a trivial query succeeds, False on any database error."""
    if engine is None:
        engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
