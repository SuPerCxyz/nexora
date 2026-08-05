"""SQLite engine and session lifecycle."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from nexora.config import Settings


class Database:
    """Own the process-wide SQLAlchemy engine and session factory."""

    def __init__(self, settings: Settings) -> None:
        settings.database_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.engine = _create_engine(
            settings.database_path,
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        )
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a short transaction-scoped session."""

        with self._session_factory.begin() as session:
            yield session

    def check_health(self) -> None:
        """Raise when SQLite cannot execute a trivial query."""

        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()

    def dispose(self) -> None:
        """Close pooled database connections."""

        self.engine.dispose()


def _create_engine(path: Path, *, busy_timeout_ms: int) -> Engine:
    url = URL.create("sqlite+pysqlite", database=str(path))
    engine = create_engine(url, connect_args={"timeout": busy_timeout_ms / 1_000})

    @event.listens_for(engine, "connect")
    def configure_sqlite(
        dbapi_connection: sqlite3.Connection,
        _connection_record: Any,
    ) -> None:
        previous_autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
        finally:
            dbapi_connection.autocommit = previous_autocommit

    return engine
