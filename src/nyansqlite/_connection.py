from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

try:
    import apsw
except ImportError:
    apsw = None

try:
    import sqlite3
except ImportError:
    sqlite3 = None


class NyanConnection:
    """Uniform dict-row interface over apsw (preferred) or sqlite3 (fallback).

    WAL mode, 64 MB page cache, and foreign keys are enabled by default.
    """

    _backend: str
    _conn: Any

    def __init__(self, path: str, wal: bool = True):
        try:
            import apsw

            self._conn    = apsw.Connection(path)
            self._backend = "apsw"
        except ImportError:
            import sqlite3

            self._conn               = sqlite3.connect(path, check_same_thread=False)
            self._conn.isolation_level = None   # manual transaction control
            self._backend            = "sqlite3"

        pragmas = [
            ("journal_mode", "WAL" if wal else "DELETE"),
            ("foreign_keys", "ON"),
            ("synchronous",  "NORMAL"),
            ("cache_size",   "-65536"),   # 64 MB
            ("temp_store",   "MEMORY"),
            ("mmap_size",    "268435456"),  # 256 MB
        ]
        for pragma, value in pragmas:
            self._raw(f"PRAGMA {pragma} = {value}")

    # ── low-level execute ────────────────────────────────────────────── #

    def _raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        if self._backend == "apsw":
            cur = self._conn.cursor()
            result = cur.execute(sql, params)

            # APSW用の修正: description取得を安全に行う
            description = None
            try:
                description = cur.description
            except (apsw.ExecutionCompleteError, AttributeError):
                # 実行が完了している、または結果がない場合はここに来る
                pass

            if description:
                cols = [d[0] for d in description]
                return [dict(zip(cols, row)) for row in result]
            return []

        else:
            # sqlite3 backend
            cur = self._conn.execute(sql, params)
            if cur.description:
                cols = [d[0] for d in cur.description]
                # fetchall() でリスト化して返す
                return [dict(zip(cols, row)) for row in cur.fetchall()]
            return []

    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return self._raw(sql, params)

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        if self._backend == "apsw":
            self._conn.cursor().executemany(sql, rows)
        else:
            self._conn.executemany(sql, rows)

    # ── transaction ──────────────────────────────────────────────────── #

    def in_transaction(self) -> bool:
        """Whether the connection is currently in a transaction."""
        if self._backend == "sqlite3":
            return self._conn.in_transaction
        return self._conn.getautocommit() is False

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        if self.in_transaction():
            yield
            return

        self._raw("BEGIN")
        try:
            yield
            self._raw("COMMIT")
        except Exception:
            self._raw("ROLLBACK")
            raise

    # ── util ─────────────────────────────────────────────────────────── #

    def changes(self) -> int:
        """Number of rows affected by the last DML statement."""
        if self._backend == "apsw":
            return self._conn.changes()
        rows = self._raw("SELECT changes() AS c")
        return rows[0]["c"] if rows else 0

    def close(self) -> None:
        self._conn.close()

    @property
    def backend(self) -> str:
        return self._backend
