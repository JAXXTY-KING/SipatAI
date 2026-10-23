from collections.abc import Generator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from app.core.config import get_gaussdb_dsn


class DatabaseNotConfigured(RuntimeError):
    """Raised when a database operation is requested without a private DSN."""


class DatabaseUnavailable(RuntimeError):
    """Raised when GaussDB cannot complete a database operation."""


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    """Open a short-lived GaussDB connection without exposing its DSN."""
    dsn = get_gaussdb_dsn()
    if dsn is None:
        raise DatabaseNotConfigured("GaussDB is not configured.")

    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            yield connection
    except psycopg.Error as error:
        raise DatabaseUnavailable("GaussDB request failed.") from error
