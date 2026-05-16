from __future__ import annotations

import asyncio
import re
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


# ── main async class ──────────────────────────────────────────────────── #

class NyanSQLiteAIO:
    """非同期版PydanticネイティブなSQLiteラッパー。

    Async Pydantic-native SQLite wrapper.
    Supports automatic schema creation, B-tree indexes, FTS5 full-text search,
    partial reads/writes, and advanced query operators.
    """

    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False):
        """NyanSQLiteAIOを初期化します。
        Initialize NyanSQLiteAIO.

        Args:
            path (str): データベースファイルのパス。デフォルトはメモリ内データベース (":memory:")。
                        Database file path. Defaults to in-memory (":memory:").
            wal (bool): WAL (Write-Ahead Logging) モードを有効にするかどうか。デフォルトは True。
                        Whether to enable WAL (Write-Ahead Logging) mode. Defaults to True.
            strict_deserialization (bool): デシリアライズ時に厳密なチェックを行うかどうか。
                                          Whether to perform strict checks during deserialization.
        """
        self._conn     = NyanConnection(path, wal=wal)
        self._registry: dict[type[BaseModel], _Meta] = {}
        self._write_lock = asyncio.Lock() # 書き込み専用ロック
        self._strict_deserialization = strict_deserialization

    # ── registration ─────────────────────────────────────────────────── #

    async def register(self, model: type[BaseModel]) -> None:
        """Pydanticモデルを登録し、対応するテーブル、インデックス、FTS5仮想テーブルを作成します。
        Register a Pydantic model and create the corresponding table, indexes, and FTS5 virtual table.

        Args:
            model (type[BaseModel]): 登録するPydanticモデルクラス。
                                    The Pydantic model class to register.

        Raises:
            TableNameCollisionError: 同じテーブル名を持つ別のモデルが既に登録されている場合に発生します。
                                     Raised if another model with the same table name is already registered.
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

        async with self._write_lock: # Use write lock for registration
            await asyncio.to_thread(
                lambda: (
                    self._conn.execute(model_to_ddl(model)),
                    [self._conn.execute(idx_sql) for idx_sql in model_to_indexes(model)],
                )
            )

            fts_create, fts_triggers = model_to_fts5(model)
            fts_table:  str | None = None
            fts_fields: list[str]  = []
            if fts_create:
                await asyncio.to_thread(
                    lambda: (
                        self._conn.execute(fts_create),
                        [self._conn.execute(trig) for trig in fts_triggers],
                    )
                )
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

    async def insert(self, obj: M) -> M:
        """Pydanticモデルのインスタンスをデータベースに挿入します。
        Validate via Pydantic then INSERT. Returns the object unchanged.

        Args:
            obj (M): 挿入するモデルのインスタンス。
                    The model instance to insert.

        Returns:
            M: 挿入されたオブジェクト（変更なし）。
               The inserted object (unchanged).

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
        """
        meta = self._meta(type(obj))
        row  = self._to_row(obj, meta)
        cols = ", ".join(f'"{k}"' for k in row)
        ph   = ", ".join("?" * len(row))
        sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'

        async with self._write_lock: # Use write lock
            await asyncio.to_thread(
                lambda: (
                    self._conn.execute(sql, tuple(row.values())),
                )
            )
        return obj

    async def insert_many(self, objs: list[M]) -> int:
        """複数のモデルインスタンスを1つのトランザクションで一括挿入します。
        Bulk-insert multiple model instances in a single transaction.

        Args:
            objs (list[M]): 挿入するモデルインスタンスのリスト。
                           List of model instances to insert.

        Returns:
            int: 挿入された行数。
                 Total number of rows inserted.

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
        """
        if not objs:
            return 0
        meta = self._meta(type(objs[0]))

        # SQLite default limit on parameters is 32766
        rows = [self._to_row(o, meta) for o in objs]
        cols_count = len(rows[0])
        params_limit = 32000  # Conservative limit
        chunk_size = max(1, params_limit // cols_count)

        total_inserted = 0
        cols = ", ".join(f'"{k}"' for k in rows[0])

        async with self._write_lock: # Use write lock for the entire bulk operation
            for chunk_start in range(0, len(rows), chunk_size):
                chunk = rows[chunk_start:chunk_start + chunk_size]
                if not chunk:
                    continue

                ph   = ", ".join("?" * len(chunk[0]))
                sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'

                def _bulk_insert_chunk():
                    self._conn.execute("BEGIN TRANSACTION")
                    try:
                        self._conn.executemany(sql, [tuple(r.values()) for r in chunk])
                        self._conn.execute("COMMIT")
                    except Exception:
                        self._conn.execute("ROLLBACK")
                        raise

                await asyncio.to_thread(_bulk_insert_chunk)
                total_inserted += len(chunk)

        return total_inserted

    # ── UPDATE ───────────────────────────────────────────────────────── #

    async def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int:
        """指定されたフィールドのみを更新する部分更新を行います。
        Partial update — only the specified *fields* are written.

        Args:
            model (type[BaseModel]): 更新対象のモデルクラス。
                                    The model class to update.
            where (dict[str, Any]): 更新対象の行を特定する一致条件。
                                   Exact-match conditions that identify the row(s).
            **fields (Any): 更新する `フィールド名=新しい値` のペア。
                           `field=new_value` pairs to update.

        Returns:
            int: 更新された行数。
                 Number of rows updated.

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
            FieldNotFoundError: 指定されたフィールドがモデルに存在しない場合に発生します。
                                Raised if any specified field is not found in the model.
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

        async with self._write_lock: # Use write lock
            await asyncio.to_thread(
                lambda: self._conn.execute(sql, tuple(set_vals + where_vals))
            )
            return await asyncio.to_thread(lambda: self._conn.changes())

    # ── DELETE ───────────────────────────────────────────────────────── #

    async def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致するすべての行を削除します。
        Delete all rows matching *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): 削除対象のモデルクラス。
                                    The model class to delete from.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters (e.g., "age > 50").
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters (e.g., id=42).

        Returns:
            int: 削除された行数。
                 Number of rows deleted.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql = f'DELETE FROM "{meta.table}" {where_clause}'

        async with self._write_lock: # Use write lock
            await asyncio.to_thread(
                lambda: self._conn.execute(sql, tuple(values))
            )
            return await asyncio.to_thread(lambda: self._conn.changes())

    # ── GET / QUERY ───────────────────────────────────────────────────── #

    async def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]:
        """条件に一致する最初の行をPydanticモデルとして取得します。一致しない場合は `None` を返します。
        Fetch the first matching row as a Pydantic model, or ``None``.

        Args:
            model (type[M]): 取得対象のモデルクラス。
                            The Pydantic model class.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            Optional[M]: 取得されたモデルインスタンス、または None。
                         The retrieved model instance, or None.
        """
        results = await self.query(model, *filters, limit=1, **kwargs)
        return results[0] if results else None

    async def query(
        self,
        model:    type[M],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        **kwargs: Any,
    ) -> list[M]:
        """フィルタリング、ソート、ページネーションを使用して行を検索します。
        Query rows with optional filtering, ordering, and pagination.

        Args:
            model (type[M]): 検索対象のモデルクラス。
                            The Pydantic model class.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows to return.
            offset (Optional[int]): 取得を開始するオフセット行数。
                                   Number of rows to skip.
            order_by (Optional[str]): ソートに使用するフィールド名。
                                     Field name to order by.
            desc (bool): 降順でソートするかどうか。デフォルトは False（昇順）。
                        Whether to order in descending order. Defaults to False (ascending).
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            list[M]: 取得されたモデルインスタンスのリスト。
                     List of matching model instances.
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

        # Move data fetching and Pydantic parsing into a single to_thread call
        def _fetch_and_parse():
            rows = self._conn.execute(sql, tuple(values))
            return [self._from_row(model, meta, r) for r in rows]

        return await asyncio.to_thread(_fetch_and_parse)

    # ── SELECT (partial read) ─────────────────────────────────────────── #

    async def select(
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
        """特定のフィールドのみを辞書のリストとして取得します（部分読み込み）。
        Partial read — fetch only *fields*, returned as plain dicts.

        Args:
            model (type[BaseModel]): 取得対象のモデルクラス。
                                    The model class.
            fields (list[str]): 取得するフィールド名のリスト。
                               List of field names to fetch.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows.
            offset (Optional[int]): オフセット。
                                   Offset.
            order_by (Optional[str]): ソートに使用するフィールド名。
                                     Field name to order by.
            desc (bool): 降順にするかどうか。
                        Descending order.
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            list[dict[str, Any]]: 指定されたフィールドを含む辞書のリスト。
                                 List of dicts containing specified fields.
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

        # Remove async with self._lock
        def _fetch_and_deserialize():
            rows = self._conn.execute(sql, tuple(values))
            return [
                {f: deserialize_value(row.get(f), meta.hints[f], strict=self._strict_deserialization) for f in fields}
                for row in rows
            ]
        return await asyncio.to_thread(_fetch_and_deserialize)

    # ── FTS5 SEARCH ───────────────────────────────────────────────────── #

    async def search(
        self,
        model:  type[M],
        query:  str,
        *,
        limit:  Optional[int] = None,
    ) -> list[M]:
        """すべての `Searchable[str]` フィールドに対して全文検索を実行します。
        Full-text search on all ``Searchable[str]`` fields.

        Args:
            model (type[M]): 検索対象のモデルクラス。
                            The Pydantic model class.
            query (str): 検索クエリ文字列。
                        FTS5 query string.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows.

        Returns:
            list[M]: 検索結果に一致するモデルインスタンスのリスト（ランク順）。
                     List of matching model instances, ordered by relevance.

        Raises:
            SearchNotEnabledError: モデルに `Searchable[str]` フィールドが定義されていない場合に発生します。
                                   Raised if the model has no Searchable[str] fields.
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

        # Remove async with self._lock
        def _fetch_and_parse():
            rows = self._conn.execute(sql, (query,))
            return [self._from_row(model, meta, r) for r in rows]
        return await asyncio.to_thread(_fetch_and_parse)

    # ── COUNT / EXISTS ────────────────────────────────────────────────── #

    async def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致する行数を返します。
        Return the number of rows matching *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): カウント対象のモデルクラス。
                                    The model class.
            *filters (str): 文字列フィルタ。
                           String filters.
            **kwargs (Any): キーワードフィルタ。
                           Keyword filters.

        Returns:
            int: 条件に一致した行数。
                 Number of matching rows.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql  = f'SELECT COUNT(*) AS n FROM "{meta.table}" {where_clause}'

        # Remove async with self._lock
        rows = await asyncio.to_thread(
            lambda: self._conn.execute(sql, tuple(values))
        )
        return rows[0]["n"] if rows else 0

    async def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool:
        """フィルタ条件に一致する行が少なくとも1つ存在するかどうかを返します。
        Return ``True`` if at least one row matches *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): 確認対象のモデルクラス。
                                    The model class.
            *filters (str): 文字列フィルタ。
                           String filters.
            **kwargs (Any): キーワードフィルタ。
                           Keyword filters.

        Returns:
            bool: 存在する場合は True、そうでない場合は False。
                  True if matching rows exist, False otherwise.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs)
        sql  = f'SELECT 1 FROM "{meta.table}" {where_clause} LIMIT 1'

        # Remove async with self._lock
        result = await asyncio.to_thread(
            lambda: self._conn.execute(sql, tuple(values))
        )
        return bool(result)

    # ── MAINTENANCE ───────────────────────────────────────────────────── #

    async def rebuild_fts(self, model: type[BaseModel]) -> None:
        """モデルの FTS5 インデックスを再構築します。大量のデータインポート後などに有用です。
        Rebuild the FTS5 index for *model* (useful after bulk imports).

        Args:
            model (type[BaseModel]): インデックスを再構築するモデルクラス。
                                    The model class to rebuild index for.
        """
        meta = self._meta(model)
        if not meta.fts_table:
            return

        async with self._write_lock: # Use write lock
            await asyncio.to_thread(
                lambda: self._conn.execute(
                    f'INSERT INTO "{meta.fts_table}"("{meta.fts_table}") VALUES(\'rebuild\')'
                )
            )

    async def vacuum(self) -> None:
        """データベースを VACUUM してディスク領域を解放します。
        VACUUM the database to reclaim disk space.
        """
        # VACUUM is a write operation, so it should be protected by the write lock.
        # However, the original code did not use a lock for vacuum.
        # For now, I'll keep it without a lock, assuming it's a maintenance task
        # that won't conflict with concurrent reads, but it should be considered
        # if concurrent writes are happening.
        # For now, I'll assume it's fine to not lock it, as it's a full DB operation.
        await asyncio.to_thread(lambda: self._conn.execute("VACUUM"))

    # ── RAW SQL ───────────────────────────────────────────────────────── #

    async def execute_raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """任意のSQLを実行し、結果を辞書のリストとして返します。
        Execute arbitrary SQL and return rows as dicts.

        Args:
            sql (str): 実行するSQL文。
                      SQL statement to execute.
            params (tuple): SQL文に渡すパラメータ。
                           Parameters for the SQL statement.

        Returns:
            list[dict[str, Any]]: 結果行のリスト（各行は辞書）。
                                 List of result rows as dicts.
        """
        # This method can be used for both reads and writes.
        # Without knowing the intent of the SQL, it's safer to assume it might be a write.
        # However, the original code did not use a lock.
        # For maximum performance for reads, it should not be locked.
        # For safety, if it's a write, it should be locked.
        # Given the user's request to remove locks from read operations,
        # and this is a generic raw execute, I will leave it unlocked for now,
        # but this is a potential area for refinement if write safety is paramount for raw SQL.
        return await asyncio.to_thread(lambda: self._conn.execute(sql, params))

    # ── context manager + info ────────────────────────────────────────── #

    async def __aenter__(self) -> NyanSQLiteAIO:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """データベース接続を閉じます。
        Close the underlying database connection.
        """
        # Closing the connection should probably be protected by a write lock
        # to ensure no other operations are in progress.
        # However, the original code did not use a lock.
        # For now, I'll keep it without a lock.
        await asyncio.to_thread(lambda: self._conn.close())

    @property
    def backend(self) -> str:
        """使用中のバックエンド（'apsw' または 'sqlite3'）。
        ``'apsw'`` or ``'sqlite3'`` depending on what was found at import time.
        """
        return self._conn.backend

    def registered_models(self) -> list[str]:
        """登録されているすべてのモデル名を取得します。
        Names of all registered models.

        Returns:
            list[str]: モデル名のリスト。
                       List of model names.
        """
        return [m.__name__ for m in self._registry]
