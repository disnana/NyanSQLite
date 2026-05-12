from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import chain
from typing import Any

import apsw

try:
    import orjson

    def _json_dumps(value: Any) -> str:
        return orjson.dumps(value).decode("utf-8")

    def _json_loads(value: Any):
        return orjson.loads(value)

except ImportError:
    import json

    def _json_dumps(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

    def _json_loads(value: Any):
        return json.loads(value)


__all__ = [
    "LazyJSON",
    "QueryResult",
    "StatementCache",
    "Table",
    "NyanSQLite",
]


# =========================================================
# Helpers
# =========================================================


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _normalize_json_path(path: str) -> str:
    if not path:
        raise ValueError("JSON path cannot be empty")
    if path.startswith("$"):
        return path
    return "$." + path


def _is_json_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value) and value[0] in "[{"
    if isinstance(value, (bytes, bytearray, memoryview)):
        if not value:
            return False
        return bytes(value[:1]) in (b"{", b"[")
    return False


# =========================================================
# Lazy JSON wrapper
# =========================================================


class LazyJSON:
    """Decode only when accessed."""

    __slots__ = ("_raw", "_decoded")

    def __init__(self, raw: Any):
        self._raw = raw
        self._decoded = None

    def value(self):
        decoded = self._decoded
        if decoded is None:
            decoded = _json_loads(self._raw)
            self._decoded = decoded
        return decoded

    def __getitem__(self, item):
        return self.value()[item]

    def __getattr__(self, item):
        try:
            return self.value()[item]
        except KeyError:
            raise AttributeError(item) from None

    def __iter__(self):
        return iter(self.value())

    def __len__(self):
        return len(self.value())

    def __repr__(self):
        return repr(self.value())


# =========================================================
# Statement cache
# =========================================================


class StatementCache:
    __slots__ = ("_cache",)

    def __init__(self):
        self._cache: dict[Any, str] = {}

    def get(self, key: Any, builder):
        value = self._cache.get(key)
        if value is not None:
            return value
        value = builder()
        self._cache[key] = value
        return value


# =========================================================
# Result container
# =========================================================


@dataclass(slots=True)
class QueryResult:
    rows_affected: int
    last_insert_rowid: int


# =========================================================
# Main wrapper
# =========================================================


class NyanSQLite:
    """
    SQLite-native APSW wrapper.

    Focus:
    - dict rows
    - codegen row builder
    - lazy JSON decode
    - SQLite JSONB support
    - very low Python overhead
    - no ORM layer
    """

    __slots__ = (
        "connection",
        "_statement_cache",
        "_schema_cache",
        "_row_index_cache",
        "_row_factory_cache",
        "_json_columns",
        "_json_mode",
        "_ultra_fast",
    )

    def __init__(
        self,
        path: str,
        *,
        wal: bool = True,
        foreign_keys: bool = True,
        busy_timeout_ms: int = 5000,
        json_mode: str = "auto",
        ultra_fast: bool = False,
    ):
        self.connection = apsw.Connection(path)
        self._statement_cache = StatementCache()
        self._schema_cache: dict[str, tuple[str, ...]] = {}
        self._row_index_cache: dict[tuple[str, ...], dict[str, int]] = {}
        self._row_factory_cache: dict[tuple[tuple[str, ...], tuple[str, ...]], Any] = {}
        self._json_columns: dict[str, set[str]] = {}
        self._json_mode = self._resolve_json_mode(json_mode)
        self._ultra_fast = ultra_fast

        self._setup(
            wal=wal,
            foreign_keys=foreign_keys,
            busy_timeout_ms=busy_timeout_ms,
        )

    # -----------------------------------------------------
    # Configuration
    # -----------------------------------------------------

    def _resolve_json_mode(self, requested: str) -> str:
        requested = requested.lower()
        if requested not in {"auto", "text", "jsonb"}:
            raise ValueError("json_mode must be one of: auto, text, jsonb")
        if requested != "auto":
            return requested
        version = tuple(int(part) for part in apsw.sqlitelibversion().split("."))
        return "jsonb" if version >= (3, 45, 0) else "text"

    def _setup(self, *, wal: bool, foreign_keys: bool, busy_timeout_ms: int):
        cur = self.connection.cursor()

        if wal:
            cur.execute("PRAGMA journal_mode=WAL")

        if foreign_keys:
            cur.execute("PRAGMA foreign_keys=ON")

        cur.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA mmap_size=268435456")

        if self._ultra_fast:
            cur.execute("PRAGMA synchronous=OFF")
            cur.execute("PRAGMA cache_size=-200000")
            cur.execute("PRAGMA trusted_schema=OFF")
        else:
            cur.execute("PRAGMA synchronous=NORMAL")

    @property
    def supports_jsonb(self) -> bool:
        return self._json_mode == "jsonb"

    @property
    def json_mode(self) -> str:
        return self._json_mode

    # -----------------------------------------------------
    # Schema helpers
    # -----------------------------------------------------

    def table_columns(self, table: str) -> tuple[str, ...]:
        cached = self._schema_cache.get(table)
        if cached is not None:
            return cached

        cur = self.connection.cursor()
        rows = cur.execute(f"PRAGMA table_info({_quote_ident(table)})")
        columns = tuple(row[1] for row in rows)
        self._schema_cache[table] = columns
        return columns

    def register_json_columns(self, table: str, columns: Iterable[str]):
        self._json_columns[table] = set(columns)

    def json_columns(self, table: str) -> frozenset[str]:
        return frozenset(self._json_columns.get(table, set()))

    # -----------------------------------------------------
    # Table access
    # -----------------------------------------------------

    def table(self, name: str) -> "Table":
        return Table(self, name)

    def __getattr__(self, item: str) -> "Table":
        return Table(self, item)

    def __getitem__(self, item: str) -> "Table":
        return Table(self, item)

    # -----------------------------------------------------
    # Transaction helpers
    # -----------------------------------------------------

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.connection.__exit__(exc_type, exc, tb)

    @contextmanager
    def transaction(self):
        with self.connection:
            yield self

    # -----------------------------------------------------
    # Raw execution
    # -----------------------------------------------------

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        cur = self.connection.cursor()
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        return cur

    def _row_index(self, columns: tuple[str, ...]) -> dict[str, int]:
        cached = self._row_index_cache.get(columns)
        if cached is not None:
            return cached
        index = {name: i for i, name in enumerate(columns)}
        self._row_index_cache[columns] = index
        return index

    def _row_factory(
        self,
        columns: tuple[str, ...],
        json_columns: frozenset[str],
    ):
        key = (columns, tuple(sorted(json_columns)))
        cached = self._row_factory_cache.get(key)
        if cached is not None:
            return cached

        parts: list[str] = []
        for i, name in enumerate(columns):
            if name in json_columns:
                parts.append(
                    f"{name!r}: (LazyJSON(row[{i}]) if _is_json_text(row[{i}]) else row[{i}])"
                )
            else:
                parts.append(f"{name!r}: row[{i}]")

        src = "def build(row, LazyJSON=LazyJSON, _is_json_text=_is_json_text):\n"
        src += "    return {" + ", ".join(parts) + "}\n"

        ns = {
            "LazyJSON": LazyJSON,
            "_is_json_text": _is_json_text,
        }
        exec(src, ns)
        fn = ns["build"]
        self._row_factory_cache[key] = fn
        return fn

    def query_iter(
        self,
        sql: str,
        params: Iterable[Any] | None = None,
        *,
        json_columns: Iterable[str] = (),
    ) -> Iterator[dict[str, Any]]:
        cur = self.connection.cursor()
        rows = cur.execute(sql) if params is None else cur.execute(sql, params)

        description = cur.getdescription()
        columns = tuple(col[0] for col in description)
        factory = self._row_factory(columns, frozenset(json_columns))

        for raw in rows:
            yield factory(raw)

    def query(
        self,
        sql: str,
        params: Iterable[Any] | None = None,
        *,
        json_columns: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        return list(self.query_iter(sql, params, json_columns=json_columns))

    def query_one(
        self,
        sql: str,
        params: Iterable[Any] | None = None,
        *,
        json_columns: Iterable[str] = (),
    ) -> dict[str, Any] | None:
        for row in self.query_iter(sql, params, json_columns=json_columns):
            return row
        return None

    def scalar(self, sql: str, params: Iterable[Any] | None = None):
        row = self.query_one(sql, params)
        if row is None:
            return None
        return next(iter(row.values()))

    def close(self):
        self.connection.close()

    # -----------------------------------------------------
    # PRAGMAs and utility SQL
    # -----------------------------------------------------

    def pragma(self, name: str, value: Any | None = None):
        cur = self.connection.cursor()
        if value is None:
            rows = cur.execute(f"PRAGMA {name}")
            return [tuple(row) for row in rows]
        cur.execute(f"PRAGMA {name}={value}")
        return None

    def vacuum(self):
        self.execute("VACUUM")

    def integrity_check(self):
        return self.query("PRAGMA integrity_check")

    # -----------------------------------------------------
    # JSON index helper
    # -----------------------------------------------------

    def create_json_index(
        self,
        table: str,
        json_column: str,
        path: str,
        *,
        unique: bool = False,
    ):
        sqlite_path = _normalize_json_path(path)
        safe_path = path.replace(".", "_").replace("[", "_").replace("]", "_")
        unique_sql = "UNIQUE " if unique else ""

        sql = f"""
        CREATE {unique_sql}INDEX IF NOT EXISTS
        {_quote_ident(f'idx_{table}_{json_column}_{safe_path}')}
        ON {_quote_ident(table)} (
            json_extract({_quote_ident(json_column)}, {sqlite_path!r})
        )
        """
        self.execute(sql)

    # -----------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------

    def _json_column_set(self, table: str) -> set[str]:
        return self._json_columns.get(table, set())

    def _json_value_expr(self, *, column_is_json: bool) -> str:
        if column_is_json and self._json_mode == "jsonb":
            return "jsonb(?)"
        return "?"

    def _json_value_param(self, value: Any, *, column_is_json: bool) -> Any:
        if isinstance(value, LazyJSON):
            value = value.value()

        if isinstance(value, (dict, list)):
            payload = _json_dumps(value)
            if column_is_json and self._json_mode == "jsonb":
                return payload
            return payload

        if column_is_json and self._json_mode == "jsonb" and _is_json_text(value):
            return value

        return value


# =========================================================
# Table proxy
# =========================================================


class Table:
    __slots__ = ("db", "name")

    def __init__(self, db: NyanSQLite, name: str):
        self.db = db
        self.name = name

    # -----------------------------------------------------
    # Insert / Upsert
    # -----------------------------------------------------

    def insert(self, data: Mapping[str, Any]) -> QueryResult:
        columns = tuple(data.keys())
        json_cols = self.db._json_column_set(self.name)

        sql_key = ("insert", self.name, columns, tuple(sorted(json_cols)), self.db.json_mode)
        sql = self.db._statement_cache.get(sql_key, lambda: self._build_insert_sql(columns, json_cols))

        params = [self.db._json_value_param(value, column_is_json=key in json_cols) for key, value in data.items()]

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    def insert_many(self, rows: Iterable[Mapping[str, Any]]) -> QueryResult:
        iterator = iter(rows)
        first = next(iterator, None)
        if first is None:
            return QueryResult(0, 0)

        columns = tuple(first.keys())
        json_cols = self.db._json_column_set(self.name)
        sql_key = ("insert_many", self.name, columns, tuple(sorted(json_cols)), self.db.json_mode)
        sql = self.db._statement_cache.get(sql_key, lambda: self._build_insert_sql(columns, json_cols))

        def payload_iter():
            for row in chain((first,), iterator):
                yield tuple(
                    self.db._json_value_param(row[col], column_is_json=col in json_cols)
                    for col in columns
                )

        with self.db.transaction():
            cur = self.db.connection.cursor()
            cur.executemany(sql, payload_iter())

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    def upsert(
        self,
        data: Mapping[str, Any],
        *,
        conflict: Sequence[str],
        update: Mapping[str, Any] | None = None,
    ) -> QueryResult:
        columns = tuple(data.keys())
        json_cols = self.db._json_column_set(self.name)
        conflict_tuple = tuple(conflict)
        update_literal = update is not None

        if update_literal:
            update_map = dict(update)
            update_columns = tuple(update_map.keys())
        else:
            update_map = {}
            update_columns = tuple(col for col in columns if col not in conflict_tuple)

        sql_key = (
            "upsert",
            self.name,
            columns,
            conflict_tuple,
            update_columns,
            update_literal,
            tuple(sorted(json_cols)),
            self.db.json_mode,
        )
        sql = self.db._statement_cache.get(
            sql_key,
            lambda: self._build_upsert_sql(
                columns,
                conflict_tuple,
                update_columns,
                json_cols,
                update_literal=update_literal,
            ),
        )

        params = [self.db._json_value_param(value, column_is_json=key in json_cols) for key, value in data.items()]

        if update_literal:
            params.extend(
                self.db._json_value_param(update_map[key], column_is_json=key in json_cols)
                for key in update_columns
            )

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    def _build_insert_sql(self, columns: tuple[str, ...], json_cols: set[str]) -> str:
        col_sql = ", ".join(_quote_ident(col) for col in columns)
        values_sql = [self.db._json_value_expr(column_is_json=col in json_cols) for col in columns]
        return f"INSERT INTO {_quote_ident(self.name)} ({col_sql}) VALUES ({', '.join(values_sql)})"

    def _build_upsert_sql(
        self,
        columns: tuple[str, ...],
        conflict: tuple[str, ...],
        update_columns: tuple[str, ...],
        json_cols: set[str],
        *,
        update_literal: bool,
    ) -> str:
        insert_sql = self._build_insert_sql(columns, json_cols)
        conflict_sql = ", ".join(_quote_ident(col) for col in conflict)

        updates = []
        if update_literal:
            for col in update_columns:
                updates.append(f"{_quote_ident(col)} = {self.db._json_value_expr(column_is_json=col in json_cols)}")
        else:
            for col in update_columns:
                updates.append(f"{_quote_ident(col)} = excluded.{_quote_ident(col)}")

        if not updates:
            updates.append("rowid = rowid")

        return f"{insert_sql} ON CONFLICT({conflict_sql}) DO UPDATE SET {', '.join(updates)}"

    # -----------------------------------------------------
    # Select
    # -----------------------------------------------------

    def select(
        self,
        where: Mapping[str, Any] | None = None,
        columns: str | Sequence[str] = "*",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.select_iter(where=where, columns=columns, limit=limit))

    def select_iter(
        self,
        where: Mapping[str, Any] | None = None,
        columns: str | Sequence[str] = "*",
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        json_cols = self.db._json_column_set(self.name)
        select_sql, projected_json_cols = self._build_select_sql(columns, json_cols)

        sql = f"SELECT {select_sql} FROM {_quote_ident(self.name)}"
        params: list[Any] = []

        if where:
            clauses = []
            for key, value in where.items():
                clauses.append(f"{_quote_ident(key)} = ?")
                params.append(value)
            sql += " WHERE " + " AND ".join(clauses)

        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        yield from self.db.query_iter(sql, params, json_columns=projected_json_cols)

    def one(
        self,
        where: Mapping[str, Any] | None = None,
        columns: str | Sequence[str] = "*",
    ) -> dict[str, Any] | None:
        for row in self.select_iter(where=where, columns=columns, limit=1):
            return row
        return None

    def all(
        self,
        where: Mapping[str, Any] | None = None,
        columns: str | Sequence[str] = "*",
    ) -> list[dict[str, Any]]:
        return self.select(where=where, columns=columns)

    def _build_select_sql(
        self,
        columns: str | Sequence[str],
        json_cols: set[str],
    ) -> tuple[str, tuple[str, ...]]:
        if isinstance(columns, str) and columns != "*":
            return columns, tuple()

        if columns == "*":
            try:
                cols = self.db.table_columns(self.name)
            except Exception:
                return "*", tuple()
        else:
            cols = tuple(columns)

        projected: list[str] = []
        projected_json_cols: list[str] = []

        for col in cols:
            if col in json_cols and self.db.json_mode == "jsonb":
                projected.append(f"json({_quote_ident(col)}) AS {_quote_ident(col)}")
                projected_json_cols.append(col)
            else:
                projected.append(_quote_ident(col))
                if col in json_cols:
                    projected_json_cols.append(col)

        return ", ".join(projected), tuple(projected_json_cols)

    # -----------------------------------------------------
    # Update / Delete
    # -----------------------------------------------------

    def update(
        self,
        values: Mapping[str, Any],
        where: Mapping[str, Any],
    ) -> QueryResult:
        json_cols = self.db._json_column_set(self.name)
        set_parts = []
        params: list[Any] = []

        for key, value in values.items():
            set_parts.append(f"{_quote_ident(key)} = {self.db._json_value_expr(column_is_json=key in json_cols)}")
            params.append(self.db._json_value_param(value, column_is_json=key in json_cols))

        where_parts = []
        for key, value in where.items():
            where_parts.append(f"{_quote_ident(key)} = ?")
            params.append(value)

        sql = (
            f"UPDATE {_quote_ident(self.name)} "
            f"SET {', '.join(set_parts)} "
            f"WHERE {' AND '.join(where_parts)}"
        )

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    def delete(self, where: Mapping[str, Any]) -> QueryResult:
        where_parts = []
        params: list[Any] = []

        for key, value in where.items():
            where_parts.append(f"{_quote_ident(key)} = ?")
            params.append(value)

        sql = f"DELETE FROM {_quote_ident(self.name)} WHERE {' AND '.join(where_parts)}"

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    # -----------------------------------------------------
    # JSON helpers
    # -----------------------------------------------------

    def json_set(
        self,
        json_column: str,
        path: str,
        value: Any,
        *,
        where: Mapping[str, Any],
    ) -> QueryResult:
        return self._json_mutate("json_set", json_column, path, value, where=where)

    def json_insert(
        self,
        json_column: str,
        path: str,
        value: Any,
        *,
        where: Mapping[str, Any],
    ) -> QueryResult:
        return self._json_mutate("json_insert", json_column, path, value, where=where)

    def json_replace(
        self,
        json_column: str,
        path: str,
        value: Any,
        *,
        where: Mapping[str, Any],
    ) -> QueryResult:
        return self._json_mutate("json_replace", json_column, path, value, where=where)

    def json_remove(
        self,
        json_column: str,
        path: str,
        *,
        where: Mapping[str, Any],
    ) -> QueryResult:
        sqlite_path = _normalize_json_path(path)
        where_parts = []
        params: list[Any] = [sqlite_path]

        for key, value in where.items():
            where_parts.append(f"{_quote_ident(key)} = ?")
            params.append(value)

        sql = f"""
        UPDATE {_quote_ident(self.name)}
        SET {_quote_ident(json_column)} = json_remove({_quote_ident(json_column)}, ?)
        WHERE {' AND '.join(where_parts)}
        """

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    def json_extract(
        self,
        json_column: str,
        path: str,
        *,
        where: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        sqlite_path = _normalize_json_path(path)
        sql = (
            f"SELECT json_extract({_quote_ident(json_column)}, ?) AS value "
            f"FROM {_quote_ident(self.name)}"
        )
        params: list[Any] = [sqlite_path]

        if where:
            clauses = []
            for key, value in where.items():
                clauses.append(f"{_quote_ident(key)} = ?")
                params.append(value)
            sql += " WHERE " + " AND ".join(clauses)

        return self.db.query(sql, params)

    def _json_mutate(
        self,
        func: str,
        json_column: str,
        path: str,
        value: Any,
        *,
        where: Mapping[str, Any],
    ) -> QueryResult:
        sqlite_path = _normalize_json_path(path)
        json_cols = self.db._json_column_set(self.name)
        column_is_json = json_column in json_cols

        where_parts = []
        params: list[Any] = [sqlite_path, self.db._json_value_param(value, column_is_json=column_is_json)]
        for key, wv in where.items():
            where_parts.append(f"{_quote_ident(key)} = ?")
            params.append(wv)

        sql = f"""
        UPDATE {_quote_ident(self.name)}
        SET {_quote_ident(json_column)} = {func}({_quote_ident(json_column)}, ?, {self.db._json_value_expr(column_is_json=column_is_json)})
        WHERE {' AND '.join(where_parts)}
        """

        with self.db.connection:
            cur = self.db.connection.cursor()
            cur.execute(sql, params)

        return QueryResult(
            rows_affected=self.db.connection.changes(),
            last_insert_rowid=self.db.connection.last_insert_rowid(),
        )

    # -----------------------------------------------------
    # Convenience
    # -----------------------------------------------------

    def exists(self, where: Mapping[str, Any]) -> bool:
        sql = f"SELECT 1 FROM {_quote_ident(self.name)}"
        params: list[Any] = []
        if where:
            clauses = []
            for key, value in where.items():
                clauses.append(f"{_quote_ident(key)} = ?")
                params.append(value)
            sql += " WHERE " + " AND ".join(clauses)
        sql += " LIMIT 1"
        return self.db.query_one(sql, params) is not None


# =========================================================
# Example
# =========================================================


if __name__ == "__main__":
    db = NyanSQLite(
        "nyan.db",
        json_mode="auto",
        ultra_fast=False,
    )

    db.execute("DROP TABLE IF EXISTS users")
    db.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            profile_json TEXT,
            name TEXT
        )
        """
    )

    db.register_json_columns("users", ["profile_json"])

    db.users.insert(
        {
            "id": 1,
            "name": "nana",
            "profile_json": {
                "stats": {"logins": 5},
                "online": True,
            },
        }
    )

    user = db.users.one(where={"id": 1})
    print(user)
    print(user["name"])
    print(user["profile_json"]["stats"])

    db.users.json_set(
        "profile_json",
        "stats.logins",
        999,
        where={"id": 1},
    )

    updated = db.users.one(where={"id": 1})
    print(updated["profile_json"])

    rows = db.query("SELECT id, name FROM users")
    print(rows[0])
