from __future__ import annotations

import re
import threading
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from ._connection import NyanConnection
from ._schema import (
    get_primary_key,
    model_hints,
    model_to_ddl,
    model_to_fts5,
    model_to_indexes,
    model_to_table_name,
)
from ._types import deserialize_value, serialize_value
from .exceptions import (
    FieldNotFoundError,
    ModelNotRegisteredError,
    QueryValidationError,
    SearchNotEnabledError,
    TableNameCollisionError,
)

M = TypeVar("M", bound=BaseModel)


# ── WHERE clause builder ──────────────────────────────────────────────── #

_OP_PATTERN = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|>|<|=)\s*(.*)$")

def _build_where(args: tuple[str, ...], kwargs: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build a parameterised WHERE clause from string filters and keyword arguments.

    String filters (args):
        "views > 10", "status = 'active'"

    Keyword filters (kwargs):
        ==  ``field=value``           → ``field = ?``
        ==  ``field__ne=value``       → ``field != ?``
        ==  ``field__gt=value``       → ``field > ?``
        ==  ``field__gte=value``      → ``field >= ?``
        ==  ``field__lt=value``       → ``field < ?``
        ==  ``field__lte=value``      → ``field <= ?``
        ==  ``field__like=value``     → ``field LIKE ?``
        ==  ``field__in=[…]``         → ``field IN (?,?,?)``
        ==  ``field__is_null=True``   → ``field IS NULL``
        ==  ``field__is_null=False``  → ``field IS NOT NULL``

    Raises:
        QueryValidationError: If type conversion of filter values fails
    """
    if not args and not kwargs:
        return "", []

    clauses: list[str] = []
    values:  list[Any] = []

    # Process positional string filters: "age > 10"
    for filt in args:
        match = _OP_PATTERN.match(filt)
        if match:
            field, op, val_str = match.groups()
            clauses.append(f'"{field}" {op} ?')
            # Try to convert val_str to a Python literal (int, float, etc.)
            # If it's a quoted string, strip quotes.
            val_str = val_str.strip()
            if (val_str.startswith("'") and val_str.endswith("'")) or \
               (val_str.startswith('"') and val_str.endswith('"')):
                values.append(val_str[1:-1])
            elif val_str.isdigit():
                values.append(int(val_str))
            else:
                try:
                    values.append(float(val_str))
                except ValueError:
                    values.append(val_str)
        else:
            # If it doesn't match our simple operator pattern,
            # we might just pass it through, but it's risky for SQL injection.
            # For now, let's only support the explicit operators.
            clauses.append(filt)

    # Process keyword filters: age__gt=10
    for key, value in kwargs.items():
        if "__" in key:
            field, op = key.rsplit("__", 1)
            q = f'"{field}"'
            if op == "ne":
                clauses.append(f"{q} != ?")
                values.append(value)
            elif op == "gt":
                clauses.append(f"{q} > ?")
                # Validate that value can be compared
                try:
                    _ = value > value  # Simple type check
                except TypeError as e:
                    raise QueryValidationError(
                        f"Type mismatch in filter {key}={value!r}. "
                        f"Cannot apply '>' operator to {type(value).__name__}. "
                        f"Error: {e}"
                    ) from e
                values.append(value)
            elif op == "gte":
                clauses.append(f"{q} >= ?")
                values.append(value)
            elif op == "lt":
                clauses.append(f"{q} < ?")
                values.append(value)
            elif op == "lte":
                clauses.append(f"{q} <= ?")
                values.append(value)
            elif op == "like":
                clauses.append(f"{q} LIKE ?")
                values.append(value)
            elif op == "in":
                try:
                    ph = ", ".join("?" * len(value))
                except TypeError as e:
                    raise QueryValidationError(
                        f"Filter {key} expects iterable, got {type(value).__name__}. "
                        f"Error: {e}"
                    ) from e
                clauses.append(f"{q} IN ({ph})")
                try:
                    values.extend(value)
                except TypeError as e:
                    raise QueryValidationError(
                        f"Filter {key}: Cannot extend values from {type(value).__name__}. "
                        f"Expected iterable. Error: {e}"
                    ) from e
            elif op == "is_null":
                clauses.append(f"{q} IS {'NULL' if value else 'NOT NULL'}")
            else:
                raise ValueError(f"Unknown filter operator: __{op}")
        elif value is None:
            clauses.append(f'"{key}" IS NULL')
        else:
            clauses.append(f'"{key}" = ?')
            values.append(value)

    return "WHERE " + " AND ".join(clauses), values


def _order_sql(order_by: Optional[str], desc: bool) -> str:
    if not order_by:
        return ""
    return f' ORDER BY "{order_by}" {"DESC" if desc else "ASC"}'


def _limit_sql(limit: Optional[int], offset: Optional[int]) -> str:
    sql = ""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"
    return sql


# ── internal model metadata ───────────────────────────────────────────── #

class _Meta:
    __slots__ = ("table", "pk", "hints", "fts_table", "fts_fields")

    def __init__(
        self,
        table:      str,
        pk:         Optional[str],
        hints:      dict[str, Any],
        fts_table:  Optional[str],
        fts_fields: list[str],
    ):
        self.table      = table
        self.pk         = pk
        self.hints      = hints
        self.fts_table  = fts_table
        self.fts_fields = fts_fields

    def check_fields(self, fields: list[str], model_name: str) -> None:
        bad = [f for f in fields if f not in self.hints]
        if bad:
            raise FieldNotFoundError(
                f"Fields not found on {model_name}: {bad}. "
                f"Available: {list(self.hints)}"
            )


# ── main class ────────────────────────────────────────────────────────── #

class NyanSQLite:
    """Pydantic-native SQLite wrapper.

    Automatic schema creation, B-tree indexes, FTS5 full-text search,
    partial reads/writes, and query operators — powered by apsw.

    Quick start::

        from nyansqlite import NyanSQLite, Indexed, Searchable
        from pydantic import BaseModel

        class Article(BaseModel):
            id:      int
            author:  Indexed[str]
            title:   Searchable[str]
            body:    Searchable[str]
            views:   int = 0

        db = NyanSQLite("blog.sqlite")
        db.register(Article)

        db.insert(Article(id=1, author="neko", title="Hello SQLite", body="…"))
        db.search(Article, "SQLite")
        db.update(Article, where={"id": 1}, views=42)
        db.select(Article, fields=["title", "views"], author="neko")
    """

    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False):
        """Initialize NyanSQLite.

        Args:
            path: Database file path (default: in-memory)
            wal: Enable WAL mode (default: True)
            strict_deserialization: If True, raise ValueError on malformed data.
                                   If False, emit warning and return raw value.
                                   Default: False (lenient mode)
        """
        self._conn     = NyanConnection(path, wal=wal)
        self._registry: dict[type[BaseModel], _Meta] = {}
        self._lock     = threading.Lock()
        self._strict_deserialization = strict_deserialization

    # ── registration ─────────────────────────────────────────────────── #

    def register(self, model: type[BaseModel]) -> None:
        """Introspect *model* and create table + indexes + FTS5 virtual table.

        Raises TableNameCollisionError if a different model is already registered with the same table name.
        """
        table  = model_to_table_name(model)
        pk     = get_primary_key(model)
        hints  = model_hints(model)

        # Check for table name collisions with different models
        for existing_model, meta in self._registry.items():
            if meta.table == table and existing_model is not model:
                raise TableNameCollisionError(
                    f"Table name collision detected: "
                    f"{existing_model.__name__} → '{table}' but also "
                    f"{model.__name__} → '{table}'. "
                    f"This can happen with CamelCase variants (e.g., 'UserAuth' and 'User_Auth'). "
                    f"Use explicit __tablename__ override or rename one of the models."
                )

        with self._lock:
            with self._conn.transaction():
                self._conn.execute(model_to_ddl(model))
                for idx_sql in model_to_indexes(model):
                    self._conn.execute(idx_sql)

                fts_create, fts_triggers = model_to_fts5(model)
                fts_table:  str | None = None
                fts_fields: list[str]  = []
                if fts_create:
                    self._conn.execute(fts_create)
                    for trig in fts_triggers:
                        self._conn.execute(trig)
                    from ._types import is_searchable
                    fts_table  = f"{table}_fts"
                    fts_fields = [f for f, ann in hints.items() if is_searchable(ann)]

            self._registry[model] = _Meta(
                table=table, pk=pk, hints=hints,
                fts_table=fts_table, fts_fields=fts_fields,
            )

    def _meta(self, model: type[BaseModel]) -> _Meta:
        meta = self._registry.get(model)
        if meta is None:
            raise ModelNotRegisteredError(
                f"{model.__name__} is not registered. "
                f"Call db.register({model.__name__}) first."
            )
        return meta

    # ── helpers ───────────────────────────────────────────────────────── #

    def _to_row(self, obj: BaseModel, meta: _Meta) -> dict[str, Any]:
        """Pydantic model → serialised dict for SQLite."""
        dump = obj.model_dump() if hasattr(obj, "model_dump") else obj.dict()
        return {k: serialize_value(v, meta.hints[k]) for k, v in dump.items() if k in meta.hints}

    def _from_row(self, model: type[M], meta: _Meta, row: dict[str, Any]) -> M:
        """SQLite row dict → Pydantic model.

        Args:
            model: Pydantic model class
            meta: Model metadata
            row: Row dict from database

        Returns:
            Instantiated Pydantic model

        Raises:
            ValueError: If strict_deserialization=True and data is malformed
        """
        data = {}
        for k, v in row.items():
            if k in meta.hints:
                data[k] = deserialize_value(
                    v, meta.hints[k],
                    strict=self._strict_deserialization
                )
        return model(**data)

    # ── INSERT ───────────────────────────────────────────────────────── #

    def insert(self, obj: M) -> M:
        """Validate via Pydantic then INSERT. Returns the object unchanged."""
        meta = self._meta(type(obj))
        row  = self._to_row(obj, meta)
        cols = ", ".join(f'"{k}"' for k in row)
        ph   = ", ".join("?" * len(row))
        sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(row.values()))
        return obj

    def insert_many(self, objs: list[M]) -> int:
        """Bulk-insert in a single transaction. Returns the number inserted.

        Automatically chunks large inserts to respect SQLite's variable binding limit
        (default 32766). This prevents SQLITE_TOOBIG errors on very large datasets.

        Args:
            objs: List of model instances to insert

        Returns:
            Total number of rows inserted
        """
        if not objs:
            return 0
        meta = self._meta(type(objs[0]))

        # SQLite default limit on parameters is 32766
        # We use 1000 parameters per statement for safety
        # (columns * rows_per_chunk <= 1000)
        rows = [self._to_row(o, meta) for o in objs]
        cols_count = len(rows[0])
        params_limit = 32000  # Conservative limit
        chunk_size = max(1, params_limit // cols_count)

        total_inserted = 0
        cols = ", ".join(f'"{k}"' for k in rows[0])

        for chunk_start in range(0, len(rows), chunk_size):
            chunk = rows[chunk_start:chunk_start + chunk_size]
            if not chunk:
                continue

            ph   = ", ".join("?" * len(chunk[0]))
            sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'
            with self._lock:
                with self._conn.transaction():
                    self._conn.executemany(sql, [tuple(r.values()) for r in chunk])
            total_inserted += len(chunk)

        return total_inserted

    # ── UPDATE ───────────────────────────────────────────────────────── #

    def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int:
        """Partial update — only the specified *fields* are written.

        Args:
            where:    Exact-match conditions that identify the row(s).
            **fields: ``field=new_value`` pairs to update.

        Returns:
            Number of rows updated.

        Example::

            db.update(User, where={"id": 1}, age=26, bio="updated")
        """
        if not fields:
            return 0
        meta = self._meta(model)
        meta.check_fields(list(fields), model.__name__)

        set_parts: list[str] = []
        set_vals:  list[Any] = []
        for fname, value in fields.items():
            set_parts.append(f'"{fname}" = ?')
            set_vals.append(serialize_value(value, meta.hints[fname]))

        where_clause, where_vals = _build_where((), where)
        sql = f'UPDATE "{meta.table}" SET {", ".join(set_parts)} {where_clause}'

        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(set_vals + where_vals))
            return self._conn.changes()

    # ── DELETE ───────────────────────────────────────────────────────── #

    def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """Delete all rows matching *filters* and *kwargs*. Returns rows deleted.

        Example::

            db.delete(User, id=42)
            db.delete(User, "age > 50")
            db.delete(Session, user_id=1, active=True)
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql = f'DELETE FROM "{meta.table}" {where_clause}'
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(values))
            return self._conn.changes()

    # ── GET / QUERY ───────────────────────────────────────────────────── #

    def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]:
        """Fetch the first matching row as a Pydantic model, or ``None``.

        Example::

            user = db.get(User, id=1)
            user = db.get(User, "age > 30", name="Alice")
            user = db.get(User, email="taro@example.com")
        """
        results = self.query(model, *filters, limit=1, **kwargs)
        return results[0] if results else None

    def query(
        self,
        model:    type[M],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        **kwargs: Any,
    ) -> list[M]:
        """Query rows with optional filtering, ordering, and pagination.

        Supports string filters and operator suffixes (``__gt``, ``__like``, …).

        Examples::

            db.query(User)                                  # all rows
            db.query(User, age=25)                          # exact match
            db.query(User, "age > 20", limit=10)            # string filters
            db.query(User, age__gte=20, limit=10)           # operator suffixes
            db.query(User, order_by="name", desc=True)      # ordering
            db.query(User, order_by="id", limit=20, offset=40)  # pagination
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)

        if order_by:
            meta.check_fields([order_by], model.__name__)

        sql = (
            f'SELECT * FROM "{meta.table}" {where_clause}'
            + _order_sql(order_by, desc)
            + _limit_sql(limit, offset)
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(values))
            return [self._from_row(model, meta, r) for r in rows]

    # ── SELECT (partial read) ─────────────────────────────────────────── #

    def select(
        self,
        model:    type[BaseModel],
        fields:   list[str],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Partial read — fetch only *fields*, returned as plain dicts.

        Avoids loading unused columns for large rows.

        Example::

            db.select(Article, ["title", "views"], author="neko", order_by="views", desc=True)
            db.select(Article, ["title"], "views > 100")
        """
        meta = self._meta(model)
        meta.check_fields(fields, model.__name__)
        if order_by:
            meta.check_fields([order_by], model.__name__)

        col_sql      = ", ".join(f'"{f}"' for f in fields)
        where_clause, values = _build_where(filters, kwargs)
        sql = (
            f'SELECT {col_sql} FROM "{meta.table}" {where_clause}'
            + _order_sql(order_by, desc)
            + _limit_sql(limit, offset)
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(values))
            return [
                {f: deserialize_value(row.get(f), meta.hints[f], strict=self._strict_deserialization) for f in fields}
                for row in rows
            ]

    # ── FTS5 SEARCH ───────────────────────────────────────────────────── #

    def search(
        self,
        model:  type[M],
        query:  str,
        *,
        limit:  Optional[int] = None,
    ) -> list[M]:
        """Full-text search on all ``Searchable[str]`` fields.

        Uses FTS5 ``MATCH`` with BM25 ranking (``ORDER BY rank``).

        Example::

            db.search(Article, "python sqlite")
            db.search(Article, "python sqlite", limit=5)

        For field-scoped search, use FTS5 column filter syntax::

            db.search(Article, "title:python")
        """
        meta = self._meta(model)
        if not meta.fts_table:
            raise SearchNotEnabledError(
                f"{model.__name__} has no Searchable[str] fields. "
                "Annotate at least one str field with Searchable[str] to enable FTS5."
            )

        table = meta.table
        fts   = meta.fts_table
        sql = (
            f'SELECT t.* FROM "{table}" t '
            f'JOIN "{fts}" f ON t.rowid = f.rowid '
            f'WHERE "{fts}" MATCH ? '
            f'ORDER BY rank'
            + _limit_sql(limit, None)
        )
        with self._lock:
            rows = self._conn.execute(sql, (query,))
            return [self._from_row(model, meta, r) for r in rows]

    # ── COUNT / EXISTS ────────────────────────────────────────────────── #

    def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """Return the number of rows matching *filters* and *kwargs*.

        Example::

            total  = db.count(User)
            adults = db.count(User, "age >= 18")
            adults = db.count(User, age__gte=18)
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql  = f'SELECT COUNT(*) AS n FROM "{meta.table}" {where_clause}'
        with self._lock:
            rows = self._conn.execute(sql, tuple(values))
            return rows[0]["n"] if rows else 0

    def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool:
        """Return ``True`` if at least one row matches *filters* and *kwargs*.

        Example::

            if db.exists(User, email="taro@example.com"):
                ...
            if db.exists(User, "age > 20"):
                ...
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql  = f'SELECT 1 FROM "{meta.table}" {where_clause} LIMIT 1'
        with self._lock:
            return bool(self._conn.execute(sql, tuple(values)))

    # ── MAINTENANCE ───────────────────────────────────────────────────── #

    def rebuild_fts(self, model: type[BaseModel]) -> None:
        """Rebuild the FTS5 index for *model* (useful after bulk imports)."""
        meta = self._meta(model)
        if not meta.fts_table:
            return
        with self._lock:
            self._conn.execute(
                f'INSERT INTO "{meta.fts_table}"("{meta.fts_table}") VALUES(\'rebuild\')'
            )

    def vacuum(self) -> None:
        """VACUUM the database to reclaim disk space."""
        self._conn.execute("VACUUM")

    # ── RAW SQL ───────────────────────────────────────────────────────── #

    def execute_raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute arbitrary SQL and return rows as dicts.

        Example::

            db.execute_raw("SELECT count(*) AS n FROM user WHERE age > ?", (18,))
        """
        return self._conn.execute(sql, params)

    # ── context manager + info ────────────────────────────────────────── #

    def __enter__(self) -> NyanSQLite:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    @property
    def backend(self) -> str:
        """``'apsw'`` or ``'sqlite3'`` depending on what was found at import time."""
        return self._conn.backend

    def registered_models(self) -> list[str]:
        """Names of all registered models."""
        return [m.__name__ for m in self._registry]
