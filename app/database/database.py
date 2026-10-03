"""SQLite connection management, transactions, backup and restore."""

from __future__ import annotations

import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.utils.paths import AppPaths, app_paths


class DatabaseError(RuntimeError):
    """Raised for unrecoverable database problems."""


def utc_now() -> str:
    """Timestamp used for bookkeeping columns (audits, sync cursors)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    """Thin, thread-safe wrapper around a single SQLite file.

    A dedicated connection is used for the GUI thread and short-lived
    connections for services running in workers, guarded by a lock so that
    ``PRAGMA foreign_keys`` is always active.
    """

    def __init__(self, path: Path | str | None = None, paths: AppPaths | None = None) -> None:
        self.paths = paths or app_paths()
        self.path = Path(path) if path else self.paths.database_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()

    # -- connections ---------------------------------------------------------
    @property
    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=30.0,
                isolation_level=None,  # explicit transaction control
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside a single ``BEGIN IMMEDIATE`` transaction."""
        with self._lock:
            conn = self._connection
            if conn.in_transaction:
                # Nested use: reuse the outer transaction (no savepoints needed
                # because Shiftora services are not re-entrant on writes).
                yield conn
                return
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:  # pragma: no cover - already closed
                    pass
                raise
            else:
                if conn.in_transaction:
                    conn.execute("COMMIT")

    def executescript(self, script: str) -> None:
        """Run a multi-statement script.

        ``executescript`` commits any open transaction by design, so it must not
        be wrapped in :meth:`transaction`.
        """
        with self._lock:
            self._connection.executescript(script)

    # -- query helpers -------------------------------------------------------
    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._connection.execute(sql, tuple(params)).fetchall())

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._connection.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.execute(sql, tuple(params))

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.executemany(sql, [tuple(p) for p in seq])

    def insert_returning_id(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)

    # -- maintenance ---------------------------------------------------------
    def table_names(self) -> set[str]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
            "AND name NOT LIKE 'sqlite_%'"
        )
        return {row["name"] for row in rows}

    def integrity_check(self) -> tuple[bool, str]:
        try:
            result = self.scalar("PRAGMA integrity_check", default="unknown")
        except sqlite3.DatabaseError as exc:
            return False, str(exc)
        ok = str(result).lower() == "ok"
        return ok, str(result)

    def optimize(self) -> None:
        with self._lock:
            self._connection.execute("VACUUM")

    def close_all(self) -> None:
        with self._lock:
            self.close()

    # -- backup / restore ----------------------------------------------------
    def backup_to(self, destination: Path | str) -> Path:
        """Create a consistent copy using SQLite's online backup API."""
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            source = self._connection
            target = sqlite3.connect(str(dest))
            try:
                source.backup(target)
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                target.close()
        return dest

    def restore_from(self, source: Path | str) -> None:
        """Replace the live database with ``source`` after a safety copy."""
        src = Path(source)
        if not src.is_file():
            raise DatabaseError(f"Backup file not found: {src}")

        self.close()
        safety = self.path.with_name(self.path.stem + "_prerestore.db")
        for stale in (safety, safety.with_name(safety.name + "-wal"), safety.with_name(safety.name + "-shm")):
            if stale.exists():
                stale.unlink()
        if self.path.exists():
            shutil.copy2(self.path, safety)
        for suffix in ("-wal", "-shm"):
            extra = self.path.with_name(self.path.name + suffix)
            if extra.exists():
                extra.unlink()

        shutil.copy2(src, self.path)
        # Touch the connection so pragmas are re-applied to the new file.
        self._connection.execute("SELECT 1")

    def file_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Database {self.path}>"