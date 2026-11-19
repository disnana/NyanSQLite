from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from numbers import Integral
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

    def __init__(self, path: str, wal: bool = True, statement_cache_size: int | None = None):
        self._savepoint_counter = 0
        self.path = path
        if statement_cache_size is not None:
            if isinstance(statement_cache_size, bool) or not isinstance(statement_cache_size, Integral):
                raise ValueError("statement_cache_size must be a non-negative integer")
            statement_cache_size = int(statement_cache_size)
            if statement_cache_size < 0:
                raise ValueError("statement_cache_size must be a non-negative integer")

        try:
            import apsw

            cache_options = {} if statement_cache_size is None else {"statementcachesize": statement_cache_size}
            self._conn    = apsw.Connection(path, **cache_options)
            self._backend = "apsw"
        except ImportError:
            import sqlite3

            cache_options = {} if statement_cache_size is None else {"cached_statements": statement_cache_size}
            self._conn               = sqlite3.connect(path, check_same_thread=False, **cache_options)
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

    def execute_write(self, sql: str, params: tuple) -> None:
        """Execute a single statement that does not return rows."""
        self._conn.execute(sql, params)

    def execute_rows(self, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
        """Fetch raw rows for model construction without building intermediate dicts."""
        if self._backend == "apsw":
            cur = self._conn.cursor()
            result = cur.execute(sql, params)
            try:
                cols = [column[0] for column in cur.description]
            except (apsw.ExecutionCompleteError, AttributeError):
                return [], []
            return cols, list(result)
        cur = self._conn.execute(sql, params)
        if cur.description is None:
            return [], []
        return [column[0] for column in cur.description], cur.fetchall()

    def executemany(self, sql: str, rows: Iterable[tuple]) -> None:
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
        scope = self.transaction_scope()
        try:
            scope.begin()
            yield
            scope.commit()
        except BaseException as error:
            try:
                scope.rollback()
            except Exception as rollback_error:
                raise error from rollback_error
            raise

    def transaction_scope(self) -> _TransactionScope:
        return _TransactionScope(self)

    def rollback_if_open(self) -> None:
        if self.in_transaction():
            self._raw("ROLLBACK")

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


class _TransactionScope:
    """A transaction or savepoint whose state is shared with the async worker."""

    def __init__(self, connection: NyanConnection):
        self.connection = connection
        self.savepoint: str | None = None
        self.active = False
        self.committed = False

    def begin(self) -> None:
        if self.connection.in_transaction():
            self.connection._savepoint_counter += 1
            self.savepoint = f'"nyan_sp_{self.connection._savepoint_counter}"'
            self.connection._raw(f"SAVEPOINT {self.savepoint}")
        else:
            self.connection._raw("BEGIN")
        self.active = True

    def commit(self) -> None:
        if self.savepoint is None:
            self.connection._raw("COMMIT")
        else:
            self.connection._raw(f"RELEASE SAVEPOINT {self.savepoint}")
        self.active = False
        self.committed = True

    def rollback(self) -> None:
        if not self.active:
            return
        if self.savepoint is None:
            self.connection.rollback_if_open()
        elif self.connection.in_transaction():
            self.connection._raw(f"ROLLBACK TO SAVEPOINT {self.savepoint}")
            self.connection._raw(f"RELEASE SAVEPOINT {self.savepoint}")
        self.active = False
